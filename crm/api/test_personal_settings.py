from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.password import get_decrypted_password
from werkzeug.wrappers import Response

from crm.api.personal_settings import (
	connect_personal_mailbox,
	generate_personal_api_keys,
	get_personal_settings,
	no_store_personal_settings,
)


class TestPersonalSettings(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("personal_settings_test")
		frappe.set_user("Administrator")
		self.suffix = frappe.generate_hash(length=8)
		self.user = self.make_user("rep")
		self.other = self.make_user("other")
		frappe.set_user(self.user)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="personal_settings_test")
		super().tearDown()

	def make_user(self, label, role="Sales User"):
		return (
			frappe.get_doc(
				doctype="User",
				email=f"personal-{label}-{self.suffix}@example.com",
				first_name=f"Personal {label}",
				user_type="System User",
				send_welcome_email=0,
				roles=[{"role": role}],
			)
			.insert(ignore_permissions=True)
			.name
		)

	def make_account(self, user, **values):
		frappe.set_user("Administrator")
		doc = frappe.get_doc(
			doctype="Email Account",
			email_account_name=f"Personal test {user}",
			email_id=user,
			service="GMail",
			auth_method="Basic",
			enable_incoming=0,
			enable_outgoing=0,
			**values,
		).insert(ignore_permissions=True)
		frappe.set_user(self.user)
		return doc

	def test_guest_cannot_access_any_personal_endpoint(self):
		frappe.set_user("Guest")
		for fn, kwargs in [
			(get_personal_settings, {}),
			(generate_personal_api_keys, {}),
			(connect_personal_mailbox, {"password": "local-test-only"}),
		]:
			with self.assertRaises(frappe.AuthenticationError):
				fn(**kwargs)

	def test_non_crm_user_is_rejected(self):
		frappe.set_user("Administrator")
		name = self.make_user("non-crm", role="Desk User")
		frappe.set_user(name)
		with self.assertRaises(frappe.PermissionError):
			get_personal_settings()

	def test_status_is_allowlisted_and_has_no_credentials(self):
		self.make_account(self.other)
		status = get_personal_settings()
		self.assertEqual(set(status), {"mailbox", "api_configured"})
		self.assertFalse(status["api_configured"])
		self.assertIsNone(status["mailbox"]["name"])
		self.assertEqual(status["mailbox"]["email_id"], self.user)
		self.assertEqual(
			set(status["mailbox"]),
			{"name", "email_id", "connected", "enable_incoming", "enable_outgoing", "can_manage"},
		)
		self.assertEqual(frappe.local.response_headers["Cache-Control"], "no-store")

	def test_key_generation_is_self_only_and_status_never_returns_it(self):
		result = generate_personal_api_keys()
		self.assertTrue(len(result["api_key"]) == 32 and len(result["api_secret"]) == 32)
		self.assertTrue(frappe.db.get_value("User", self.user, "api_key") == result["api_key"])
		self.assertTrue(get_decrypted_password("User", self.user, "api_secret") == result["api_secret"])
		self.assertFalse(frappe.db.get_value("User", self.other, "api_key"))
		self.assertNotIn("api_secret", get_personal_settings())
		self.assertTrue(get_personal_settings()["api_configured"])
		self.assertEqual(frappe.get_roles(self.user).count("System Manager"), 0)

	def test_key_replacement_requires_confirmation_and_preserves_key(self):
		first = generate_personal_api_keys()
		with self.assertRaises(frappe.ValidationError):
			generate_personal_api_keys()
		second = generate_personal_api_keys(confirm_replace=True)
		self.assertTrue(first["api_key"] == second["api_key"])
		self.assertTrue(first["api_secret"] != second["api_secret"])

	def test_key_endpoint_accepts_no_target_user(self):
		with self.assertRaises(TypeError):
			generate_personal_api_keys(user=self.other)
		self.assertFalse(frappe.db.get_value("User", self.other, "api_key"))

	def test_another_mailbox_address_is_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			connect_personal_mailbox(password="local-test-only", email_id=self.other)
		self.assertFalse(frappe.db.exists("Email Account", {"email_id": self.other}))

	def test_blank_password_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			connect_personal_mailbox(password=" ")

	def test_connect_own_mailbox_without_creating_crm_records(self):
		before = {dt: frappe.db.count(dt) for dt in ["Contact", "CRM Lead", "CRM Organization"]}
		with (
			patch("frappe.email.doctype.email_account.email_account.EmailAccount.validate_smtp_conn"),
			patch("frappe.email.doctype.email_account.email_account.EmailAccount.get_incoming_server"),
		):
			status = connect_personal_mailbox(password="local-test-only", email_id=self.user)
		self.assertTrue(status["connected"])
		account = frappe.get_doc("Email Account", status["name"])
		self.assertEqual(account.owner, self.user)
		self.assertEqual(account.email_server, "imap.gmail.com")
		self.assertEqual(account.smtp_server, "smtp.gmail.com")
		self.assertFalse(account.default_incoming or account.default_outgoing)
		self.assertFalse(account.create_contact or account.enable_automatic_linking)
		self.assertFalse(account.create_lead_from_incoming_email)
		self.assertFalse(account.append_to)
		self.assertFalse(any(row.append_to for row in account.imap_folder))
		self.assertTrue(account.always_use_account_email_id_as_sender)
		self.assertEqual(account.email_sync_option, "UNSEEN")
		self.assertEqual({dt: frappe.db.count(dt) for dt in before}, before)
		user = frappe.get_doc("User", self.user)
		self.assertEqual([row.email_account for row in user.user_emails], [account.name])
		self.assertFalse(frappe.get_doc("User", self.other).user_emails)
		self.assertNotIn("password", status)

	def test_reconnection_reuses_only_own_account(self):
		first = connect_personal_mailbox(password="local-test-only")
		frappe.db.set_value("Email Account", first["name"], "create_lead_from_incoming_email", 1)
		second = connect_personal_mailbox(password="replacement-test-only")
		self.assertEqual(first["name"], second["name"])
		self.assertFalse(
			frappe.db.get_value("Email Account", first["name"], "create_lead_from_incoming_email")
		)
		self.assertEqual(frappe.db.count("Email Account", {"email_id": self.user}), 1)
		self.assertEqual(len(frappe.get_doc("User", self.user).user_emails), 1)

	def test_administrator_managed_mailbox_cannot_be_overwritten(self):
		account = self.make_account(self.user)
		self.assertFalse(get_personal_settings()["mailbox"]["can_manage"])
		with self.assertRaises(frappe.PermissionError):
			connect_personal_mailbox(password="local-test-only")
		self.assertEqual(frappe.db.get_value("Email Account", account.name, "owner"), "Administrator")

	def test_existing_global_defaults_are_preserved(self):
		# Keep the default account disabled so no external SMTP connection is attempted.
		account = self.make_account(self.other)
		frappe.db.set_value("Email Account", account.name, {"default_incoming": 1, "default_outgoing": 1})
		connect_personal_mailbox(password="local-test-only")
		account.reload()
		self.assertTrue(account.default_incoming and account.default_outgoing)

	def test_own_mailbox_shared_with_someone_else_is_readonly(self):
		status = connect_personal_mailbox(password="local-test-only")
		frappe.set_user("Administrator")
		other = frappe.get_doc("User", self.other)
		other.append("user_emails", {"email_account": status["name"], "email_id": self.user})
		other.save(ignore_permissions=True)
		frappe.set_user(self.user)
		self.assertFalse(get_personal_settings()["mailbox"]["can_manage"])
		with self.assertRaises(frappe.PermissionError):
			connect_personal_mailbox(password="local-test-only")

	def test_mailbox_save_restores_session_and_request_state(self):
		frappe.local.session.sid = "local-test-session"
		frappe.local.form_dict = frappe._dict(cmd="local-test-command")
		session = dict(frappe.local.session)
		form_dict = frappe.local.form_dict
		connect_personal_mailbox(password="local-test-only")
		self.assertEqual(dict(frappe.local.session), session)
		self.assertIs(frappe.local.form_dict, form_dict)
		self.assertFalse(frappe.has_permission("Property Setter", "read"))

	def test_mailbox_save_error_restores_session_without_echoing_provider_error(self):
		frappe.local.session.sid = "local-test-session"
		session = dict(frappe.local.session)
		with patch(
			"frappe.email.doctype.email_account.email_account.EmailAccount.validate",
			side_effect=RuntimeError("private-provider-test-error"),
		):
			with self.assertRaises(frappe.ValidationError) as error:
				connect_personal_mailbox(password="local-test-only")
		self.assertNotIn("private-provider-test-error", str(error.exception))
		self.assertEqual(dict(frappe.local.session), session)
		self.assertFalse(frappe.has_permission("Property Setter", "read"))

	def test_rpc_cannot_generate_keys_for_another_user(self):
		result = frappe.call(generate_personal_api_keys, user=self.other)
		self.assertTrue(frappe.db.get_value("User", self.user, "api_key") == result["api_key"])
		self.assertFalse(frappe.db.get_value("User", self.other, "api_key"))

	def test_disabled_user_is_rejected(self):
		frappe.db.set_value("User", self.user, "enabled", 0)
		with self.assertRaises(frappe.PermissionError):
			get_personal_settings()

	def test_personal_page_cannot_change_own_global_default_account(self):
		status = connect_personal_mailbox(password="local-test-only")
		frappe.db.set_value("Email Account", status["name"], "default_outgoing", 1)
		with self.assertRaises(frappe.PermissionError):
			connect_personal_mailbox(password="replacement-test-only")
		self.assertTrue(frappe.db.get_value("Email Account", status["name"], "default_outgoing"))

	def test_personal_page_cannot_replace_an_oauth_connection(self):
		status = connect_personal_mailbox(password="local-test-only")
		frappe.db.set_value("Email Account", status["name"], "auth_method", "OAuth")
		self.assertFalse(get_personal_settings()["mailbox"]["can_manage"])
		with self.assertRaises(frappe.PermissionError):
			connect_personal_mailbox(password="replacement-test-only")

	def test_personal_responses_have_no_store_headers_on_both_framework_versions(self):
		get_personal_settings()
		response = Response()
		no_store_personal_settings(response)
		self.assertEqual(response.headers["Cache-Control"], "no-store")
		self.assertEqual(response.headers["Pragma"], "no-cache")
		frappe.flags.personal_settings_response = False
		unrelated = Response()
		no_store_personal_settings(unrelated)
		self.assertNotIn("Cache-Control", unrelated.headers)
