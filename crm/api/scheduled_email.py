"""Session-bound durable drafts and reply-aware customer follow-ups."""

import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_system_timezone, now_datetime

from crm.emailing import validation as v

DRAFT = "CRM Email Draft"
SEQUENCE = "CRM Email Sequence"


def _owned(name, modified=None, *, doctype=DRAFT):
	user = v.current_user()
	doc = frappe.get_doc(doctype, name, for_update=True)
	if doc.owner != user.name:
		frappe.throw(_("You can only change your own emails and sequences."), frappe.PermissionError)
	if doctype == DRAFT:
		v.reference(doc.reference_doctype, doc.reference_name, email=True)
	if modified is not None:
		v.check_modified(doc, modified)
	return doc


def _sequence_public(doc):
	return {
		"name": doc.name,
		"modified": doc.modified,
		"title": doc.title,
		"steps": [
			{"day_offset": step.day_offset, "subject": step.subject, "content": step.content}
			for step in doc.steps
		],
	}


@frappe.whitelist()
def get_workspace(reference_doctype, reference_name):
	user = v.current_user()
	v.reference(reference_doctype, reference_name)
	filters = {"owner": user.name, "reference_doctype": reference_doctype, "reference_name": reference_name}
	pending = frappe.get_all(
		DRAFT,
		filters={**filters, "status": ["in", ["Draft", "Scheduled", "Sending", "Error"]]},
		pluck="name",
		order_by="modified desc",
	)
	history = frappe.get_all(
		DRAFT,
		filters={**filters, "status": ["in", ["Sent", "Canceled"]]},
		pluck="name",
		order_by="modified desc",
		limit_page_length=101,
	)
	names = pending + history[:100]
	sequences = frappe.get_all(
		SEQUENCE, filters={"owner": user.name}, pluck="name", order_by="modified desc", limit_page_length=100
	)
	return {
		"drafts": [v.public(frappe.get_doc(DRAFT, name)) for name in names],
		"sequences": [_sequence_public(frappe.get_doc(SEQUENCE, name)) for name in sequences],
		"senders": v.senders(user),
		"timezone": user.time_zone or get_system_timezone(),
		"history_truncated": len(history) > 100,
	}


@frappe.whitelist(methods=["POST"])
def save_draft(data):
	data = v.parsed(data)
	user = v.current_user()
	if data.get("name"):
		doc = _owned(data["name"])
		v.check_modified(doc, data.get("modified"))
		if doc.status not in ("Draft", "Scheduled", "Canceled") or doc.communication:
			frappe.throw(_("This email has already been dispatched and cannot be edited."))
		if (
			data.get("reference_doctype", doc.reference_doctype) != doc.reference_doctype
			or data.get("reference_name", doc.reference_name) != doc.reference_name
		):
			frappe.throw(_("A draft cannot be moved to another customer."))
	else:
		doc = frappe.new_doc(DRAFT)
		doc.reference_doctype = data.get("reference_doctype")
		doc.reference_name = data.get("reference_name")
	v.reference(doc.reference_doctype, doc.reference_name, email=True)
	for field in ("sender", "recipients", "cc", "bcc", "subject", "content"):
		value = data.get(field, "")
		if not isinstance(value, str):
			frappe.throw(_("Email fields must be text."))
		doc.set(field, value)
	if doc.sender:
		v.sender_account(user, doc.sender)
	for field in ("recipients", "cc", "bcc"):
		doc.set(field, ", ".join(v.addresses(doc.get(field))))
	if "\n" in doc.subject or "\r" in doc.subject or len(doc.subject) > 140:
		frappe.throw(_("Use a subject of at most 140 characters without line breaks."))
	doc.attachments = json.dumps(
		v.attachments(data.get("attachments", []), doc.reference_doctype, doc.reference_name, user.name)
	)
	doc.stop_on_reply = cint(data.get("stop_on_reply", 1))
	doc.status, doc.send_at, doc.scheduled_at, doc.last_error = "Draft", None, None, None
	v.save(doc)
	return v.public(doc)


def _ready(doc):
	from crm.emailing.dispatch import is_suppressed

	if is_suppressed(doc):
		frappe.throw(_("A recipient unsubscribed. This email cannot be scheduled."))
	user = v.current_user()
	v.reference(doc.reference_doctype, doc.reference_name, email=True)
	v.sender_account(user, doc.sender)
	v.addresses(doc.recipients, required=True)
	v.addresses(doc.cc)
	v.addresses(doc.bcc)
	if len(set(v.addresses(doc.recipients) + v.addresses(doc.cc) + v.addresses(doc.bcc))) > 50:
		frappe.throw(_("Use at most 50 recipients across To, CC and BCC."))
	v.attachments(doc.attachments or "[]", doc.reference_doctype, doc.reference_name, user.name)
	if not doc.subject or not doc.content or not frappe.utils.strip_html(doc.content).strip():
		frappe.throw(_("Add a subject and message before scheduling."))


@frappe.whitelist(methods=["POST"])
def schedule_draft(name, send_at, timezone, modified):
	doc = _owned(name)
	v.check_modified(doc, modified)
	if doc.status not in ("Draft", "Scheduled") or doc.communication:
		frappe.throw(_("Only an unsent draft can be scheduled."))
	_ready(doc)
	doc.send_at = v.to_site(send_at, timezone)
	doc.timezone = timezone
	doc.scheduled_at = now_datetime()
	doc.status, doc.last_error = "Scheduled", None
	v.save(doc)
	return v.public(doc)


@frappe.whitelist(methods=["POST"])
def cancel_email(name, modified):
	doc = _owned(name)
	if doc.status == "Canceled":
		return v.public(doc)
	v.check_modified(doc, modified)
	if doc.status not in ("Draft", "Scheduled", "Error"):
		frappe.throw(_("This email is already sending or sent and cannot be recalled."))
	doc.status = "Canceled"
	doc.last_error = _("Canceled by sender")
	v.save(doc)
	return v.public(doc)


@frappe.whitelist(methods=["POST"])
def delete_draft(name, modified):
	doc = _owned(name)
	v.check_modified(doc, modified)
	if doc.status not in ("Draft", "Canceled") or doc.communication:
		frappe.throw(_("Only drafts and canceled unsent emails can be deleted."))
	v.delete(doc)
	return {"deleted": True}


@frappe.whitelist(methods=["POST"])
def save_sequence(data):
	data = v.parsed(data)
	v.current_user()
	if data.get("name"):
		doc = _owned(data["name"], doctype=SEQUENCE)
		v.check_modified(doc, data.get("modified"))
	else:
		doc = frappe.new_doc(SEQUENCE)
	title, steps = data.get("title"), data.get("steps")
	if not isinstance(title, str) or not title.strip() or len(title) > 140:
		frappe.throw(_("Enter a sequence title of at most 140 characters."))
	if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
		frappe.throw(_("Add between 1 and 20 sequence steps."))
	previous = -1
	doc.title = title.strip()
	doc.set("steps", [])
	for step in steps:
		if not isinstance(step, dict):
			frappe.throw(_("Invalid sequence step."))
		offset = step.get("day_offset")
		if isinstance(offset, bool) or not isinstance(offset, int) or not previous < offset <= 365:
			frappe.throw(_("Day offsets must be increasing whole numbers from 0 to 365."))
		previous = offset
		if (
			not isinstance(step.get("subject"), str)
			or not step["subject"].strip()
			or len(step["subject"]) > 140
			or any(x in step["subject"] for x in "\r\n")
		):
			frappe.throw(_("Every sequence step needs a valid subject."))
		if not isinstance(step.get("content"), str) or not frappe.utils.strip_html(step["content"]).strip():
			frappe.throw(_("Every sequence step needs a message."))
		doc.append("steps", {"day_offset": offset, "subject": step["subject"], "content": step["content"]})
	v.save(doc)
	return _sequence_public(doc)


@frappe.whitelist(methods=["POST"])
def enroll_sequence(reference_doctype, reference_name, sequence_name, start_at, timezone, sender, recipients):
	user = v.current_user()
	# The owner User is a stable mutex even before any enrollment rows exist. Read
	# matching pending rows with FOR UPDATE too: MariaDB snapshots must be refreshed.
	frappe.get_doc("User", user.name, for_update=True)
	v.reference(reference_doctype, reference_name, email=True)
	sequence = _owned(sequence_name, doctype=SEQUENCE)
	addresses = v.addresses(recipients, required=True)
	v.sender_account(user, sender)
	pending = frappe.db.sql(
		"""select name, recipients from `tabCRM Email Draft` where owner=%s and reference_doctype=%s
		and reference_name=%s and enrollment_id != '' and status in ('Scheduled','Sending') for update""",
		(user.name, reference_doctype, reference_name),
		as_dict=True,
	)
	if any(set(v.addresses(row.recipients)).intersection(addresses) for row in pending):
		frappe.throw(_("A follow-up sequence is already active for this customer and recipient."))
	base = v.aware(start_at).astimezone(v.zone(timezone))
	v.to_site(start_at, timezone)
	enrollment = frappe.generate_hash(length=24)
	drafts = []
	for step in sequence.steps:
		local = base.replace(tzinfo=None) + timedelta(days=step.day_offset)
		early = local.replace(tzinfo=v.zone(timezone), fold=0)
		late = local.replace(tzinfo=v.zone(timezone), fold=1)
		if early.utcoffset() != late.utcoffset():
			frappe.throw(
				_(
					"A sequence step falls in an ambiguous or missing daylight-saving hour. Choose another start time."
				)
			)
		stamp = early
		# Do not silently shift a sequence step that lands in a spring DST gap.
		if stamp.astimezone(v.zone("UTC")).astimezone(v.zone(timezone)).replace(tzinfo=None) != local:
			frappe.throw(_("A sequence step falls in a daylight-saving time gap. Choose another start time."))
		doc = frappe.new_doc(DRAFT)
		doc.update(
			{
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"sender": sender,
				"recipients": ", ".join(addresses),
				"cc": "",
				"bcc": "",
				"subject": step.subject,
				"content": step.content,
				"attachments": "[]",
				"stop_on_reply": 1,
				"status": "Scheduled",
				"send_at": v.to_site(stamp.isoformat(), timezone),
				"timezone": timezone,
				"scheduled_at": now_datetime(),
				"sequence_name": sequence.name,
				"enrollment_id": enrollment,
			}
		)
		v.save(doc)
		drafts.append(v.public(doc))
	return {"drafts": drafts}


@frappe.whitelist(methods=["POST"])
def send_draft_now(name, modified):
	doc = _owned(name)
	v.check_modified(doc, modified)
	if doc.status != "Draft" or doc.communication:
		frappe.throw(_("Only an unsent draft can be sent now."))
	_ready(doc)
	doc.send_at, doc.scheduled_at = v.utcnow(), now_datetime()
	doc.timezone = v.current_user().time_zone or get_system_timezone()
	doc.status, doc.last_error = "Scheduled", None
	v.save(doc)
	frappe.enqueue(
		"crm.emailing.dispatch.dispatch_email", name=doc.name, queue="short", enqueue_after_commit=True
	)
	return v.public(doc)


@frappe.whitelist(methods=["POST"])
def cancel_enrollment(enrollment_id):
	user = v.current_user()
	if not isinstance(enrollment_id, str) or not enrollment_id:
		frappe.throw(_("Choose a follow-up enrollment."))
	rows = frappe.db.sql(
		"""select name from `tabCRM Email Draft` where owner=%s and enrollment_id=%s
		order by name for update""",
		(user.name, enrollment_id),
		as_dict=True,
	)
	if not rows:
		frappe.throw(_("Follow-up enrollment not found."), frappe.DoesNotExistError)
	count, sending = 0, False
	for row in rows:
		doc = _owned(row.name)
		if doc.status == "Sending":
			sending = True
		elif doc.status in ("Draft", "Scheduled"):
			doc.status, doc.last_error = "Canceled", "Remaining follow-up sequence canceled by sender."
			v.save(doc)
			count += 1
	return {"canceled_count": count, "already_sending": sending}


@frappe.whitelist(methods=["POST"])
def unschedule_draft(name, modified):
	doc = _owned(name)
	v.check_modified(doc, modified)
	if doc.status != "Scheduled" or doc.communication:
		frappe.throw(_("Only a pending scheduled email can be paused for editing."))
	doc.status, doc.send_at, doc.scheduled_at = "Draft", None, None
	v.save(doc)
	return v.public(doc)
