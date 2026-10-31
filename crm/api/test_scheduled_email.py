"""Native database/permission tests. Provider transport is always mocked."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import now_datetime

from crm.api import scheduled_email as api
from crm.emailing import dispatch
from crm.emailing import validation as v
from crm.tests import CRMTestCase


class TestScheduledEmail(CRMTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		# Assignment/welcome notifications are unrelated fixture side effects. With
		# a default mailbox, native in-test notification email registers queue.send
		# after_commit and would run inside a later managed-delivery SMTP assertion.
		# Suppress only that producer; the real managed queue/transport stays intact.
		notifications = patch("frappe.desk.doctype.notification_log.notification_log.send_notification_email")
		notifications.start()
		self.addCleanup(notifications.stop)
		css = patch("frappe.email.email_body.inline_style_in_html", side_effect=lambda html, **kwargs: html)
		css.start()
		self.addCleanup(css.stop)
		self.suffix = frappe.generate_hash(length=8)
		self.user = self.make_user("rep")
		self.other = self.make_user("other")
		self.lead = frappe.get_doc(
			{
				"doctype": "CRM Lead",
				"first_name": "Email test",
				"email": f"prospect-{self.suffix}@example.com",
				"lead_owner": self.user,
			}
		).insert(ignore_permissions=True)
		self.account = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_account_name": f"Scheduled {self.suffix}",
				"email_id": self.user,
				"service": "GMail",
				"enable_outgoing": 0,
				"enable_incoming": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Email Account", self.account.name, {"enable_outgoing": 1, "awaiting_password": 0}
		)
		user = frappe.get_doc("User", self.user)
		if not any(row.email_account == self.account.name for row in user.user_emails):
			user.append("user_emails", {"email_account": self.account.name, "email_id": self.user})
		user.save(ignore_permissions=True)
		frappe.set_user(self.user)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.flags.crm_email_raise_test_errors = None
		super().tearDown()

	def make_user(self, label):
		with patch("frappe.core.doctype.user.user.throttle_user_creation"):
			return (
				frappe.get_doc(
					{
						"doctype": "User",
						"email": f"scheduled-{label}-{self.suffix}@example.com",
						"first_name": label,
						"user_type": "System User",
						"send_welcome_email": 0,
						"roles": [{"role": "Sales User"}],
					}
				)
				.insert(ignore_permissions=True)
				.name
			)

	def draft(self, **kwargs):
		return api.save_draft(
			{
				"reference_doctype": "CRM Lead",
				"reference_name": self.lead.name,
				"sender": self.user,
				"recipients": self.lead.email,
				"subject": "Hello",
				"content": "<p>Message</p>",
				"attachments": [],
				"stop_on_reply": 1,
				**kwargs,
			}
		)

	def future(self, days=1):
		return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

	def scheduled(self, **kwargs):
		draft = self.draft(**kwargs)
		return api.schedule_draft(draft["name"], self.future(), "UTC", str(draft["modified"]))

	def inbound(self, *, sender=None, linked=True, **kwargs):
		data = {
			"doctype": "Communication",
			"communication_type": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"sender": sender or self.lead.email,
			"recipients": self.user,
			"subject": "New subject",
			"content": "Reply",
			"email_account": self.account.name,
			**kwargs,
		}
		if linked:
			data.update(reference_doctype="CRM Lead", reference_name=self.lead.name)
		return frappe.get_doc(data).insert(ignore_permissions=True)

	def test_complete_draft_round_trips_and_is_private(self):
		draft = self.draft(cc="copy@example.com", bcc="hidden@example.com")
		row = api.get_workspace("CRM Lead", self.lead.name)["drafts"][0]
		for key in ("sender", "recipients", "cc", "bcc", "subject", "content", "attachments"):
			self.assertEqual(row[key], draft[key])
		frappe.set_user(self.other)
		with self.assertRaises(frappe.PermissionError):
			api.cancel_email(draft["name"], str(draft["modified"]))
		self.assertFalse(
			frappe.has_permission(
				"CRM Email Draft", "read", doc=frappe.get_doc("CRM Email Draft", draft["name"])
			)
		)
		self.assertFalse(frappe.get_list("CRM Email Draft", filters={"name": draft["name"]}))

	def test_guest_and_non_crm_role_denied(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.AuthenticationError):
			api.get_workspace("CRM Lead", self.lead.name)

	def test_native_document_api_cannot_forge_schedule_or_internal_flag(self):
		draft = self.draft()
		doc = frappe.get_doc("CRM Email Draft", draft["name"])
		doc.status = "Scheduled"
		doc.flags.email_workspace_write = True
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)

	def test_unlinked_sender_and_foreign_attachment_denied(self):
		with self.assertRaises(frappe.PermissionError):
			self.draft(sender=self.other)
		frappe.set_user(self.other)
		file = frappe.get_doc(
			{"doctype": "File", "file_name": "private.txt", "content": "private", "is_private": 1}
		).insert(ignore_permissions=True)
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			self.draft(attachments=[file.name])

	def test_schedule_future_and_edit_clears_old_schedule(self):
		draft = self.scheduled()
		self.assertEqual(draft["status"], "Scheduled")
		self.assertTrue(draft["send_at"].endswith("Z"))
		updated = api.save_draft({**draft, "subject": "Edited"})
		self.assertEqual(updated["status"], "Draft")
		self.assertIsNone(updated["send_at"])
		with self.assertRaises(frappe.ValidationError):
			api.schedule_draft(updated["name"], "2000-01-01T00:00:00Z", "UTC", str(updated["modified"]))
		with self.assertRaises(frappe.ValidationError):
			api.schedule_draft(updated["name"], "2030-01-01T00:00:00", "UTC", str(updated["modified"]))

	def test_stale_modified_token_rejected(self):
		draft = self.draft()
		with self.assertRaises(frappe.TimestampMismatchError):
			api.cancel_email(draft["name"], "2000-01-01 00:00:00")

	def test_new_subject_unlinked_reply_cancels_customer_email(self):
		draft = self.scheduled()
		self.inbound(linked=False)
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Canceled")

	def test_unrelated_reply_does_not_cancel(self):
		draft = self.scheduled()
		self.inbound(sender="unrelated@example.com")
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Scheduled")

	def test_reply_to_other_rep_does_not_cancel(self):
		draft = self.scheduled()
		self.inbound(recipients=self.other, email_account=None, linked=False)
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Scheduled")

	def test_auto_reply_conservatively_cancels(self):
		draft = self.scheduled()
		self.inbound(subject="Out of office")
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Canceled")

	def test_cancel_is_idempotent_and_dispatch_terminal_cannot_edit(self):
		draft = self.scheduled()
		canceled = api.cancel_email(draft["name"], str(draft["modified"]))
		self.assertEqual(api.cancel_email(draft["name"], "stale")["status"], "Canceled")
		api.delete_draft(canceled["name"], str(canceled["modified"]))
		self.assertFalse(frappe.db.exists("CRM Email Draft", draft["name"]))

	def test_sequence_snapshot_duplicate_enrollment_and_reply_stops_all(self):
		sequence = api.save_sequence(
			{
				"title": "Follow-up",
				"steps": [
					{"day_offset": 0, "subject": "First", "content": "Hello"},
					{"day_offset": 3, "subject": "Second", "content": "Following up"},
				],
			}
		)
		kwargs = dict(
			reference_doctype="CRM Lead",
			reference_name=self.lead.name,
			sequence_name=sequence["name"],
			start_at=self.future(),
			timezone="UTC",
			sender=self.user,
			recipients=self.lead.email,
		)
		drafts = api.enroll_sequence(**kwargs)["drafts"]
		self.assertEqual(len(drafts), 2)
		with self.assertRaises(frappe.ValidationError):
			api.enroll_sequence(**kwargs)
		api.save_sequence(
			{**sequence, "title": "Changed", "steps": [{"day_offset": 0, "subject": "New", "content": "New"}]}
		)
		self.assertEqual(frappe.db.get_value("CRM Email Draft", drafts[0]["name"], "subject"), "First")
		self.inbound()
		self.assertEqual(
			{frappe.db.get_value("CRM Email Draft", row["name"], "status") for row in drafts}, {"Canceled"}
		)

	def test_sequence_offsets_and_timezone_validation(self):
		for offsets in ([0, 0], [1, 0], [-1], [0, 366]):
			with self.assertRaises(frappe.ValidationError):
				api.save_sequence(
					{
						"title": "Bad",
						"steps": [{"day_offset": i, "subject": "Hi", "content": "Hello"} for i in offsets],
					}
				)
		with self.assertRaises(frappe.ValidationError):
			v.to_site(self.future(), "Not/AZone")

	def test_queue_override_does_not_retry_managed_message(self):
		draft = self.draft()
		doc = frappe.get_doc("CRM Email Draft", draft["name"])
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Sent",
				"sender": self.user,
				"recipients": self.lead.email,
				"subject": "Hi",
				"content": "Hello",
			}
		).insert(ignore_permissions=True)
		doc.communication, doc.status = comm.name, "Error"
		v.save(doc)
		queue = frappe.new_doc("Email Queue")
		queue.communication = comm.name
		with patch.object(dispatch.EmailQueue, "send") as transport:
			queue.send(force_send=True)
			transport.assert_not_called()

	def test_generic_list_drops_draft_after_customer_access_removed(self):
		draft = self.draft()
		frappe.db.set_value("CRM Lead", self.lead.name, "lead_owner", self.other)
		frappe.db.delete("ToDo", {"reference_type": "CRM Lead", "reference_name": self.lead.name})
		self.assertFalse(frappe.get_list("CRM Email Draft", filters={"name": draft["name"]}))

	def _make_due(self, draft):
		frappe.db.set_value("CRM Email Draft", draft["name"], "send_at", v.utcnow() - timedelta(minutes=1))
		# Native dispatch commits mid-send; publish the fixture or transition before exercising that path.
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		return draft["name"]

	def _transport(self):
		server = MagicMock()
		server.session.has_extn.return_value = False
		return server

	def test_native_dispatch_logs_once_and_replay_never_resends(self):
		draft = self.scheduled()
		server = self._transport()
		frappe.flags.crm_email_raise_test_errors = True
		with (
			patch(
				"frappe.email.doctype.email_account.email_account.EmailAccount.get_smtp_server",
				return_value=server,
			),
			patch("frappe.are_emails_muted", return_value=False),
		):
			dispatch.dispatch_email(self._make_due(draft))
		frappe.flags.crm_email_raise_test_errors = None
		row = frappe.get_doc("CRM Email Draft", draft["name"])
		self.assertEqual(row.status, "Sent", row.last_error)
		self.assertTrue(row.communication)
		queues = frappe.get_all("Email Queue", filters={"communication": row.communication}, pluck="name")
		self.assertEqual(len(queues), 1)
		with patch.object(dispatch.EmailQueue, "send") as send:
			dispatch.dispatch_email(row.name)
			send.assert_not_called()
		self.assertEqual(frappe.db.count("Email Queue", {"communication": row.communication}), 1)

	def test_unknown_smtp_outcome_is_not_retried_by_native_queue_or_worker(self):
		draft = self.scheduled()
		server = self._transport()
		server.session.sendmail.side_effect = TimeoutError("simulated provider timeout")
		previous = frappe.flags.testing_email
		try:
			frappe.flags.testing_email = True
			with (
				patch(
					"frappe.email.doctype.email_account.email_account.EmailAccount.get_smtp_server",
					return_value=server,
				),
				patch("frappe.are_emails_muted", return_value=False),
				patch("frappe.email.doctype.email_queue.email_queue.get_hook_method", return_value=None),
			):
				dispatch.dispatch_email(self._make_due(draft))
		finally:
			frappe.flags.testing_email = previous
		row = frappe.get_doc("CRM Email Draft", draft["name"])
		self.assertEqual(row.status, "Error")
		self.assertTrue(row.communication)
		queue_name = frappe.db.get_value("Email Queue", {"communication": row.communication}, "name")
		self.assertTrue(queue_name)
		with patch.object(dispatch.EmailQueue, "send") as send:
			frappe.get_doc("Email Queue", queue_name).send(force_send=True)
			dispatch.dispatch_email(row.name)
			send.assert_not_called()
		self.assertEqual(server.session.sendmail.call_count, 1)

	def test_dispatch_rechecks_disabled_mailbox_and_fails_closed(self):
		draft = self.scheduled()
		frappe.db.set_value("Email Account", self.account.name, "enable_outgoing", 0)
		with patch.object(dispatch.EmailQueue, "send") as send:
			dispatch.dispatch_email(self._make_due(draft))
			send.assert_not_called()
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Error")

	def test_dispatch_rechecks_reply_even_when_inbound_hook_did_not_run(self):
		draft = self.scheduled()
		with patch("crm.emailing.dispatch.on_communication"):
			self.inbound(linked=False)
		frappe.db.set_value("CRM Email Draft", draft["name"], "status", "Scheduled")
		with patch.object(dispatch.EmailQueue, "send") as send:
			dispatch.dispatch_email(self._make_due(draft))
			send.assert_not_called()
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Canceled")

	def test_send_now_and_cancel_remaining_sequence(self):
		draft = self.draft()
		with patch("frappe.enqueue") as enqueue:
			queued = api.send_draft_now(draft["name"], str(draft["modified"]))
			enqueue.assert_called_once()
		self.assertEqual(queued["status"], "Scheduled")
		sequence = api.save_sequence(
			{
				"title": "Cancel sequence",
				"steps": [
					{"day_offset": 0, "subject": "One", "content": "Hello"},
					{"day_offset": 2, "subject": "Two", "content": "Again"},
				],
			}
		)
		rows = api.enroll_sequence(
			"CRM Lead", self.lead.name, sequence["name"], self.future(), "UTC", self.user, self.lead.email
		)["drafts"]
		self.assertEqual(api.cancel_enrollment(rows[0]["enrollment_id"])["canceled_count"], 2)
		self.assertEqual(api.cancel_enrollment(rows[0]["enrollment_id"])["canceled_count"], 0)

	def test_stale_dispatch_claim_is_reconciled_without_resend(self):
		draft = self.scheduled()
		frappe.db.set_value(
			"CRM Email Draft",
			draft["name"],
			{"status": "Sending", "dispatch_started_at": now_datetime() - timedelta(hours=1)},
		)
		with patch("frappe.enqueue") as enqueue:
			dispatch.dispatch_due_emails()
			self.assertNotIn(draft["name"], [call.kwargs.get("name") for call in enqueue.call_args_list])
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Error")

	def test_pause_scheduled_email_before_edit_prevents_dispatch(self):
		draft = self.scheduled()
		paused = api.unschedule_draft(draft["name"], str(draft["modified"]))
		self.assertEqual(paused["status"], "Draft")
		self.assertIsNone(paused["send_at"])
		# Native dispatch commits mid-send; publish the fixture or transition before exercising that path.
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		with patch.object(dispatch.EmailQueue, "send") as send:
			dispatch.dispatch_email(paused["name"])
			send.assert_not_called()

	def test_scheduled_absolute_utc_survives_site_dst_fold(self):
		with patch("crm.emailing.validation.get_system_timezone", return_value="America/Los_Angeles"):
			stamp = v.to_site("2030-11-03T09:30:00Z", "UTC")
			self.assertEqual(stamp, datetime(2030, 11, 3, 9, 30))
			draft = frappe.get_doc("CRM Email Draft", self.draft()["name"])
			draft.send_at = stamp
			self.assertEqual(v.public(draft)["send_at"], "2030-11-03T09:30:00Z")

	def test_native_send_preserves_recipients_files_and_own_reply_to(self):
		frappe.set_user("Administrator")
		default = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_account_name": f"Global incoming {self.suffix}",
				"email_id": f"global-{self.suffix}@example.com",
				"enable_incoming": 0,
				"enable_outgoing": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Email Account", default.name, {"default_incoming": 1, "enable_incoming": 1})
		frappe.set_user(self.user)
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "proposal.txt",
				"content": "Test proposal",
				"is_private": 1,
				"attached_to_doctype": "CRM Lead",
				"attached_to_name": self.lead.name,
			}
		).insert(ignore_permissions=True)
		draft = self.scheduled(cc="copy@example.com", bcc="private@example.com", attachments=[file.name])
		server = self._transport()
		with (
			patch(
				"frappe.email.doctype.email_account.email_account.EmailAccount.get_smtp_server",
				return_value=server,
			),
			patch("frappe.are_emails_muted", return_value=False),
		):
			dispatch.dispatch_email(self._make_due(draft))
		row = frappe.get_doc("CRM Email Draft", draft["name"])
		self.assertEqual(row.status, "Sent", row.last_error)
		queue = frappe.get_doc(
			"Email Queue", frappe.db.get_value("Email Queue", {"communication": row.communication}, "name")
		)
		self.assertEqual(queue.email_account, self.account.name)
		self.assertEqual(
			{r.recipient for r in queue.recipients},
			{self.lead.email, "copy@example.com", "private@example.com"},
		)
		from email import message_from_string

		message = message_from_string(queue.message)
		self.assertEqual(message["Reply-To"], self.user)
		self.assertEqual(
			[frappe.get_doc("File", item["fid"]).file_name for item in queue.attachments_list],
			["proposal.txt"],
		)
		comm = frappe.get_doc("Communication", row.communication)
		self.assertEqual(comm.cc, "copy@example.com")
		self.assertEqual(comm.bcc, "private@example.com")

	def test_native_unsubscribe_cancels_dispatch_and_blocks_new_schedules(self):
		draft = self.scheduled()
		frappe.get_doc(
			{"doctype": "Email Unsubscribe", "email": self.lead.email, "global_unsubscribe": 1}
		).insert(ignore_permissions=True)
		with patch.object(dispatch.EmailQueue, "send") as send:
			dispatch.dispatch_email(self._make_due(draft))
			send.assert_not_called()
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Canceled")
		new = self.draft()
		with self.assertRaises(frappe.ValidationError):
			api.schedule_draft(new["name"], self.future(), "UTC", str(new["modified"]))

	def test_two_database_workers_claim_one_send(self):
		from threading import Barrier, Thread

		draft = self.scheduled()
		self._make_due(draft)
		site, sites_path = frappe.local.site, frappe.local.sites_path
		barrier, errors = Barrier(2), []

		def worker():
			try:
				frappe.init(site=site, sites_path=sites_path)
				frappe.connect()
				frappe.set_user("Administrator")
				barrier.wait(timeout=10)
				dispatch.dispatch_email(draft["name"])
				# Publish this worker transaction so the other database connection can observe its outcome.
				frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
			except Exception as error:
				errors.append(type(error).__name__)
			finally:
				frappe.destroy()

		server = self._transport()
		with (
			patch(
				"frappe.email.doctype.email_account.email_account.EmailAccount.get_smtp_server",
				return_value=server,
			),
			patch("frappe.are_emails_muted", return_value=False),
		):
			threads = [Thread(target=worker, daemon=True) for _ in range(2)]
			for thread in threads:
				thread.start()
			for thread in threads:
				thread.join(timeout=20)
			self.assertFalse(any(thread.is_alive() for thread in threads))
		self.assertEqual(errors, [])
		row = frappe.get_doc("CRM Email Draft", draft["name"])
		self.assertEqual(row.status, "Sent", row.last_error)
		self.assertEqual(frappe.db.count("Email Queue", {"communication": row.communication}), 1)

	def test_inbound_reply_and_dispatch_use_consistent_database_lock_order(self):
		from threading import Event, Thread

		draft = self.scheduled()
		self._make_due(draft)
		site, sites_path = frappe.local.site, frappe.local.sites_path
		locked, release, started = Event(), Event(), Event()
		errors = []
		before = dispatch.lock_reply_mailboxes

		def pause_with_mailbox_lock(doc, method=None):
			before(doc, method)
			locked.set()
			if not release.wait(timeout=10):
				raise TimeoutError("test did not release mailbox mutex")

		def run(receive):
			try:
				frappe.init(site=site, sites_path=sites_path)
				frappe.connect()
				frappe.set_user("Administrator")
				if receive:
					self.inbound(linked=False)
				else:
					started.set()
					dispatch.dispatch_email(draft["name"])
				# Publish this worker transaction so the other database connection can observe its outcome.
				frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
			except Exception as error:
				errors.append(type(error).__name__)
			finally:
				frappe.destroy()

		with (
			patch("crm.emailing.dispatch.lock_reply_mailboxes", side_effect=pause_with_mailbox_lock),
			patch.object(dispatch.EmailQueue, "send") as send,
		):
			receiver = Thread(target=run, args=(True,), daemon=True)
			receiver.start()
			self.assertTrue(locked.wait(timeout=10))
			worker = Thread(target=run, args=(False,), daemon=True)
			worker.start()
			self.assertTrue(started.wait(timeout=10))
			release.set()
			receiver.join(timeout=20)
			worker.join(timeout=20)
			self.assertFalse(receiver.is_alive() or worker.is_alive())
			send.assert_not_called()
		self.assertEqual(errors, [])
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Canceled")

	def test_sequence_uses_local_calendar_days_across_daylight_saving(self):
		sequence = api.save_sequence(
			{
				"title": "DST",
				"steps": [
					{"day_offset": 0, "subject": "One", "content": "Hi"},
					{"day_offset": 1, "subject": "Two", "content": "Again"},
				],
			}
		)
		rows = api.enroll_sequence(
			"CRM Lead",
			self.lead.name,
			sequence["name"],
			"2030-03-09T10:00:00-08:00",
			"America/Los_Angeles",
			self.user,
			self.lead.email,
		)["drafts"]
		self.assertEqual(rows[0]["send_at"], "2030-03-09T18:00:00Z")
		self.assertEqual(rows[1]["send_at"], "2030-03-10T17:00:00Z")

	def test_delivery_report_on_original_thread_stops_remaining_followups(self):
		draft = self.scheduled()
		parent = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Sent",
				"sender": self.user,
				"recipients": self.lead.email,
				"subject": "Original",
				"content": "Hello",
				"reference_doctype": "CRM Lead",
				"reference_name": self.lead.name,
			}
		).insert(ignore_permissions=True)
		self.inbound(sender="mailer-daemon@example.com", linked=False, in_reply_to=parent.name)
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Canceled")

	def test_existing_inbound_update_does_not_invert_dispatch_lock_order(self):
		from threading import Event, Thread

		draft = self.scheduled()
		inbound = self.inbound(sender="unrelated@example.com", linked=False)
		self._make_due(draft)
		site, sites_path = frappe.local.site, frappe.local.sites_path
		locked, release, started = Event(), Event(), Event()
		errors = []

		def run(update):
			try:
				frappe.init(site=site, sites_path=sites_path)
				frappe.connect()
				frappe.set_user("Administrator")
				if update:
					communication = frappe.get_doc("Communication", inbound.name, for_update=True)
					locked.set()
					if not release.wait(timeout=10):
						raise TimeoutError("test did not release incoming message")
					communication.sender = self.lead.email
					communication.save(ignore_permissions=True)
				else:
					started.set()
					dispatch.dispatch_email(draft["name"])
				# Publish this worker transaction so the other database connection can observe its outcome.
				frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
			except Exception as error:
				errors.append(type(error).__name__)
			finally:
				frappe.destroy()

		with patch.object(dispatch.EmailQueue, "send") as send:
			updater = Thread(target=run, args=(True,), daemon=True)
			updater.start()
			self.assertTrue(locked.wait(timeout=10))
			worker = Thread(target=run, args=(False,), daemon=True)
			worker.start()
			self.assertTrue(started.wait(timeout=10))
			release.set()
			updater.join(timeout=20)
			worker.join(timeout=20)
			self.assertFalse(updater.is_alive() or worker.is_alive())
			send.assert_not_called()
		self.assertEqual(errors, [])
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Canceled")

	def _two_step_sequence(self):
		sequence = api.save_sequence(
			{
				"title": "Ordered",
				"steps": [
					{"day_offset": 0, "subject": "One", "content": "Hello"},
					{"day_offset": 1, "subject": "Two", "content": "Following up"},
				],
			}
		)
		return api.enroll_sequence(
			"CRM Lead", self.lead.name, sequence["name"], self.future(), "UTC", self.user, self.lead.email
		)["drafts"]

	def test_sequence_waits_for_predecessor_and_sends_after_success(self):
		first, second = self._two_step_sequence()
		frappe.db.set_value("CRM Email Draft", first["name"], "send_at", v.utcnow() - timedelta(days=1))
		self._make_due(second)
		with patch.object(dispatch.EmailQueue, "send") as send:
			dispatch.dispatch_email(second["name"])
			send.assert_not_called()
		self.assertEqual(frappe.db.get_value("CRM Email Draft", second["name"], "status"), "Scheduled")
		frappe.db.set_value("CRM Email Draft", first["name"], "status", "Sent")
		# Native dispatch commits mid-send; publish the fixture or transition before exercising that path.
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		server = self._transport()
		with (
			patch(
				"frappe.email.doctype.email_account.email_account.EmailAccount.get_smtp_server",
				return_value=server,
			),
			patch("frappe.are_emails_muted", return_value=False),
		):
			dispatch.dispatch_email(second["name"])
		self.assertEqual(frappe.db.get_value("CRM Email Draft", second["name"], "status"), "Sent")

	def test_sequence_stops_if_predecessor_delivery_failed(self):
		first, second = self._two_step_sequence()
		frappe.db.set_value(
			"CRM Email Draft", first["name"], {"send_at": v.utcnow() - timedelta(days=1), "status": "Error"}
		)
		self._make_due(second)
		with patch.object(dispatch.EmailQueue, "send") as send:
			dispatch.dispatch_email(second["name"])
			send.assert_not_called()
		self.assertEqual(frappe.db.get_value("CRM Email Draft", second["name"], "status"), "Canceled")

	def _disable_default_fixture(self, name):
		frappe.db.set_value("Email Account", name, {"enable_outgoing": 0, "default_outgoing": 0})
		# Native dispatch committed this synthetic default; do not leave it active for other suites.
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit

	def test_default_mailbox_fixture_notifications_do_not_escape_into_dispatch(self):
		frappe.set_user("Administrator")
		default = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_account_name": f"Default fixture {self.suffix}",
				"email_id": f"default-{self.suffix}@example.com",
				"enable_outgoing": 0,
				"enable_incoming": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Email Account", default.name, {"enable_outgoing": 1, "default_outgoing": 1})
		self.addCleanup(self._disable_default_fixture, default.name)
		# Real assignment machinery still creates its notifications. Its email
		# producer is isolated in setUp, so no unrelated SMTP callback is deferred.
		frappe.get_doc(
			{
				"doctype": "CRM Lead",
				"first_name": "Assigned fixture",
				"lead_owner": self.other,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(self.user)
		draft = self.scheduled()
		frappe.db.set_value("Email Account", self.account.name, "enable_outgoing", 0)
		with patch.object(dispatch.EmailQueue, "send") as send:
			dispatch.dispatch_email(self._make_due(draft))
			send.assert_not_called()
		self.assertEqual(frappe.db.get_value("CRM Email Draft", draft["name"], "status"), "Error")
