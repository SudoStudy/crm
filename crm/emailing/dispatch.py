"""Conservative dispatch: one durable attempt, never a blind SMTP retry."""

from datetime import timedelta
from email.utils import getaddresses

import frappe
from frappe import _
from frappe.email.doctype.email_queue.email_queue import EmailQueue
from frappe.model.base_document import get_controller
from frappe.utils import get_datetime, now_datetime

from crm.emailing import validation as v

DRAFT = "CRM Email Draft"


def _addresses(value):
	return {address.casefold() for _label, address in getaddresses([value or ""]) if address}


def _matches_reply(draft, communication):
	if communication.sent_or_received != "Received" or communication.communication_medium != "Email":
		return False
	if get_datetime(communication.creation) < get_datetime(draft.scheduled_at or draft.creation):
		return False
	# A receiving account (or original outbound parent for delivery reports) binds
	# new-subject mail to the actual rep mailbox, never another rep's sequence.
	account_email = None
	if communication.email_account:
		account = frappe.get_doc("Email Account", communication.email_account, for_update=True)
		account_email = account.email_id
	receiving = _addresses(communication.recipients) | _addresses(communication.cc)
	if account_email:
		receiving.add(account_email.casefold())
	parent = (
		frappe.get_doc("Communication", communication.in_reply_to, for_update=True)
		if communication.in_reply_to
		else None
	)
	if parent:
		receiving |= _addresses(parent.sender)
	if draft.sender.casefold() not in receiving:
		return False
	if communication.reference_doctype in v.REFERENCES and communication.reference_name:
		if (communication.reference_doctype, communication.reference_name) != (
			draft.reference_doctype,
			draft.reference_name,
		):
			return False
	intended = _addresses(draft.recipients) | _addresses(draft.cc) | _addresses(draft.bcc)
	if _addresses(communication.sender).intersection(intended):
		return True
	# DSNs frequently originate from mailer-daemon rather than the prospect.
	# Suppress if they are a reply to the exact original customer/recipient mail.
	return bool(
		parent
		and (parent.reference_doctype, parent.reference_name)
		== (draft.reference_doctype, draft.reference_name)
		and (_addresses(parent.recipients) | _addresses(parent.cc) | _addresses(parent.bcc)).intersection(
			intended
		)
	)


def _receiving(communication):
	result = _addresses(communication.recipients) | _addresses(communication.cc)
	if communication.email_account:
		email = frappe.db.get_value("Email Account", communication.email_account, "email_id")
		if email:
			result.add(email.casefold())
	if communication.in_reply_to:
		result |= _addresses(frappe.db.get_value("Communication", communication.in_reply_to, "sender"))
	return sorted(result)


def lock_reply_mailboxes(doc, method=None):
	"""Acquire User -> Draft -> Communication in the same order as dispatch."""
	if doc.sent_or_received != "Received" or doc.communication_medium != "Email":
		return
	addresses = _receiving(doc)
	if not addresses:
		return
	# Include shared linked mailboxes as well as matching login email identities.
	owners = set(frappe.get_all("User", filters={"email": ["in", addresses]}, pluck="name"))
	owners.update(
		frappe.db.sql(
			"""select distinct ue.parent from `tabUser Email` ue
		join `tabEmail Account` ea on ea.name=ue.email_account where ea.email_id in %s""",
			(addresses,),
			pluck=True,
		)
	)
	for owner in sorted(owners):
		frappe.get_doc("User", owner, for_update=True)


def has_reply(draft):
	accounts = frappe.get_all("Email Account", filters={"email_id": draft.sender}, pluck="name")
	# No global inbox lock: current read is restricted to the selected receiving
	# mailbox, plus messages explicitly addressed to this sender.
	rows = frappe.db.sql(
		"""select name, sent_or_received, communication_medium, creation,
		sender, recipients, cc, email_account, in_reply_to, reference_doctype, reference_name
		from `tabCommunication` where sent_or_received='Received' and communication_medium='Email'
		and creation >= %s and (email_account in %s or recipients like %s or cc like %s)
		order by creation desc for update""",
		(
			draft.scheduled_at or draft.creation,
			accounts or [""],
			"%" + draft.sender + "%",
			"%" + draft.sender + "%",
		),
		as_dict=True,
	)
	return any(_matches_reply(draft, row) for row in rows)


def on_communication(doc, method=None):
	if doc.sent_or_received != "Received" or doc.communication_medium != "Email":
		return
	if not frappe.db.exists("DocType", DRAFT):
		return
	addresses = _receiving(doc)
	if not addresses:
		return
	# The before-insert/save hook already owns receiving mailbox User mutexes.
	rows = frappe.db.sql(
		"""select name from `tabCRM Email Draft` where status='Scheduled'
		and stop_on_reply=1 and sender in %s order by name for update""",
		(addresses,),
		as_dict=True,
	)
	for row in rows:
		draft = frappe.get_doc(DRAFT, row.name, for_update=True)
		if draft.status == "Scheduled" and _matches_reply(draft, doc):
			draft.status, draft.last_error = (
				"Canceled",
				"Canceled because a reply or delivery report was received.",
			)
			v.save(draft)


def is_suppressed(draft):
	addresses = sorted(_addresses(draft.recipients) | _addresses(draft.cc) | _addresses(draft.bcc))
	if not addresses:
		return False
	return bool(
		frappe.db.sql(
			"""select name from `tabEmail Unsubscribe` where email in %s
		and (global_unsubscribe=1 or (reference_doctype=%s and reference_name=%s)) limit 1 for update""",
			(addresses, draft.reference_doctype, draft.reference_name),
		)
	)


def _cancel_suppressed(draft):
	draft.status, draft.last_error = "Canceled", "Canceled because a recipient unsubscribed."
	v.save(draft)


class ManagedEmailQueue(EmailQueue):
	"""Native queues must never retry a workspace-owned delivery automatically."""

	def send(self, *args, **kwargs):
		name = (
			frappe.db.get_value(DRAFT, {"communication": self.communication}, "name")
			if self.communication and frappe.db.exists("DocType", DRAFT)
			else None
		)
		if not name:
			return super().send(*args, **kwargs)
		if frappe.flags.get("crm_email_dispatch") != name:
			return
		owner = frappe.db.get_value(DRAFT, name, "owner")
		frappe.get_doc("User", owner, for_update=True)
		draft = frappe.get_doc(DRAFT, name, for_update=True)
		if draft.status != "Sending" or self.flags.get("crm_email_attempted"):
			return
		self.flags.crm_email_attempted = True
		from crm.api.scheduled_email import _ready

		if is_suppressed(draft):
			_cancel_suppressed(draft)
			self.update_status(status="Error", commit=True)
			return
		_ready(draft)
		expected = v.sender_account(v.current_user(), draft.sender)
		if self.get_email_account(raise_error=True).name != expected:
			frappe.throw(_("The outgoing mailbox changed. Delivery was stopped for review."))
		if draft.stop_on_reply and has_reply(draft):
			draft.status, draft.last_error = (
				"Canceled",
				"Canceled because a reply was received before dispatch.",
			)
			v.save(draft)
			self.update_status(status="Error", commit=True)
			return
		return super().send(*args, **kwargs)


def _cancel_remaining(draft, reason):
	if not draft.enrollment_id:
		return
	rows = frappe.db.sql(
		"""select name from `tabCRM Email Draft` where owner=%s and enrollment_id=%s
		and status='Scheduled' order by name for update""",
		(draft.owner, draft.enrollment_id),
		as_dict=True,
	)
	for row in rows:
		pending = frappe.get_doc(DRAFT, row.name, for_update=True)
		pending.status, pending.last_error = "Canceled", reason
		v.save(pending)


def _sequence_ready(draft):
	if not draft.enrollment_id:
		return True
	rows = frappe.db.sql(
		"""select name, status, send_at from `tabCRM Email Draft`
		where owner=%s and enrollment_id=%s and name != %s and send_at < %s
		order by name for update""",
		(draft.owner, draft.enrollment_id, draft.name, draft.send_at),
		as_dict=True,
	)
	if any(row.status == "Error" for row in rows):
		_cancel_remaining(draft, "Remaining follow-ups canceled because an earlier delivery needs review.")
		return False
	return not any(row.status in ("Scheduled", "Sending") for row in rows)


def dispatch_due_emails():
	if not frappe.db.exists("DocType", DRAFT):
		return
	# A killed worker's durable claim is not safe to retry. Show an actionable
	# outcome instead of leaving it indefinitely labeled Sending.
	frappe.db.sql(
		"""update `tabCRM Email Draft` set status='Error', last_error=%s,
		modified=%s where status='Sending' and dispatch_started_at < %s""",
		(
			"Delivery was interrupted. Verify the sent mailbox before creating another email.",
			now_datetime(),
			now_datetime() - timedelta(minutes=30),
		),
	)
	rows = frappe.get_all(
		DRAFT,
		filters={"status": "Scheduled", "send_at": ["<=", v.utcnow()]},
		pluck="name",
		order_by="send_at asc",
		limit_page_length=100,
	)
	for name in rows:
		frappe.enqueue(
			"crm.emailing.dispatch.dispatch_email", name=name, queue="short", enqueue_after_commit=True
		)


def dispatch_email(name):
	previous_user = frappe.session.user
	try:
		owner = frappe.db.get_value(DRAFT, name, "owner")
		frappe.get_doc("User", owner, for_update=True)
		draft = frappe.get_doc(DRAFT, name, for_update=True)
		if draft.status != "Scheduled" or get_datetime(draft.send_at) > v.utcnow():
			return
		if not _sequence_ready(draft):
			return
		# Fail closed if another installed app replaces this controller.
		if not issubclass(get_controller("Email Queue"), ManagedEmailQueue):
			frappe.throw(_("The reply-aware email queue guard is unavailable. Delivery stopped."))
		# Recheck live customer and mailbox permissions as the persisted draft owner.
		frappe.set_user(draft.owner)  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		from crm.api.scheduled_email import _ready

		if is_suppressed(draft):
			_cancel_suppressed(draft)
			# Persist unsubscribe cancellation and release mailbox locks before another worker can claim it.
			frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
			return
		_ready(draft)
		if draft.stop_on_reply and has_reply(draft):
			draft.status, draft.last_error = "Canceled", "Canceled because a reply was received."
			v.save(draft)
			# Persist reply cancellation before releasing this worker's mailbox claim.
			frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
			return
		from frappe.core.doctype.communication.email import make

		result = make(
			doctype=draft.reference_doctype,
			name=draft.reference_name,
			sender=draft.sender,
			recipients=draft.recipients,
			cc=draft.cc,
			bcc=draft.bcc,
			subject=draft.subject,
			content=draft.content,
			attachments=frappe.parse_json(draft.attachments or "[]"),
			communication_type="Communication",
			send_email=False,
		)
		communication = frappe.get_doc("Communication", result["name"])
		communication.db_set(
			"email_account", v.sender_account(v.current_user(), draft.sender), update_modified=False
		)
		draft.communication = communication.name
		draft.status, draft.dispatch_started_at = "Sending", now_datetime()
		v.save(draft)
		# Commit the attempt marker BEFORE native queue creation or SMTP. Native
		# queue itself commits while sending; all other queue entry points refuse it.
		# The durable attempt marker must survive any SMTP crash or native queue internal commit.
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.flags.crm_email_dispatch = draft.name
		mail = communication.sendmail_input_dict()
		mail["reply_to"] = draft.sender
		queue = frappe.sendmail(now=False, **mail)
		if not isinstance(queue, ManagedEmailQueue):
			frappe.throw(_("The managed email queue could not be prepared. Delivery stopped."))
		queue.send()
		frappe.flags.crm_email_dispatch = None
		frappe.get_doc("User", draft.owner, for_update=True)
		draft = frappe.get_doc(DRAFT, name, for_update=True)
		if draft.status == "Canceled":
			# Persist last-moment reply cancellation after the native queue released its locks.
			frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
			return
		queues = frappe.get_all(
			"Email Queue", filters={"communication": communication.name}, fields=["name", "status"]
		)
		if queues and all(row.status == "Sent" for row in queues):
			draft.status, draft.last_error = "Sent", None
		else:
			draft.status, draft.last_error = (
				"Error",
				"Delivery was not confirmed. Verify the sent mailbox before creating another email.",
			)
		v.save(draft)
		if draft.status == "Error":
			_cancel_remaining(
				draft, "Remaining follow-ups canceled because an earlier delivery needs review."
			)
		# Publish the terminal outcome before another worker considers later sequence steps.
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	except Exception:
		if getattr(frappe, "in_test", frappe.flags.get("in_test")) and frappe.flags.get(
			"crm_email_raise_test_errors"
		):
			raise
		frappe.flags.crm_email_dispatch = None
		# Do not expose provider exception text, message bodies or credentials.
		frappe.db.rollback()
		owner = frappe.db.get_value(DRAFT, name, "owner")
		frappe.get_doc("User", owner, for_update=True)
		draft = frappe.get_doc(DRAFT, name, for_update=True)
		if draft.communication:
			frappe.db.sql(
				"""update `tabEmail Queue` set status='Error' where communication=%s
				and status in ('Not Sent','Partially Sent','Sending')""",
				(draft.communication,),
			)
		if draft.status in ("Scheduled", "Sending"):
			draft.status, draft.last_error = (
				"Error",
				"Delivery stopped. Check mailbox access and verify whether this message was sent before creating another email.",
			)
			v.save(draft)
			_cancel_remaining(
				draft, "Remaining follow-ups canceled because an earlier delivery needs review."
			)
			# Preserve the non-retryable failure outcome even after native transport commits.
			frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	finally:
		frappe.flags.crm_email_dispatch = None
		# Restore the original worker identity on every delivery and failure path.
		frappe.set_user(previous_user)  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
