"""Personal CRM credentials; identity and mailbox routing are always session-bound."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from crm.api.session import CRM_ALLOWED_ROLES


def _personal_user(*, for_update=False):
	name = frappe.session.user
	if not name or name == "Guest":
		frappe.throw(_("Please sign in to manage your personal settings."), frappe.AuthenticationError)
	user = frappe.get_doc("User", name, for_update=for_update)
	if (
		not user.enabled
		or user.user_type != "System User"
		or not set(frappe.get_roles(name)).intersection(CRM_ALLOWED_ROLES)
	):
		frappe.throw(_("CRM access is required."), frappe.PermissionError)
	if not hasattr(frappe.local, "response_headers"):
		frappe.local.response_headers = {}
	frappe.local.response_headers["Cache-Control"] = "no-store"
	frappe.flags.personal_settings_response = True
	return user


def no_store_personal_settings(response, request=None):
	# Frappe 15 does not consume local.response_headers; use the native response hook.
	if frappe.flags.get("personal_settings_response"):
		response.headers["Cache-Control"] = "no-store"
		response.headers["Pragma"] = "no-cache"


def _mailbox(user):
	accounts = frappe.get_all(
		"Email Account", filters={"email_id": user.email}, fields=["name"], limit_page_length=2
	)
	if len(accounts) > 1:
		frappe.throw(_("Multiple accounts use this email. Ask an administrator to review them."))
	return frappe.get_doc("Email Account", accounts[0].name, for_update=True) if accounts else None


def _can_manage(account, user):
	if not account:
		return True
	return (
		account.owner == user.name
		and account.service == "GMail"
		and account.auth_method in (None, "", "Basic")
		and not account.default_incoming
		and not account.default_outgoing
		and not account.enable_automatic_linking
		and account.connected_user in (None, "", user.name)
		and not frappe.db.exists("User Email", {"email_account": account.name, "parent": ["!=", user.name]})
	)


def _save_own_mailbox(account, user):
	# Frappe's native Email Account.validate reads administrator-only Property Setter
	# metadata even when Append To is empty. Elevate only this pre-authorized save;
	# set_user also resets request state, which must be restored on every exit path.
	if account.email_id.casefold() != user.email.casefold() or not _can_manage(account, user):
		frappe.throw(_("You can only connect your own mailbox."), frappe.PermissionError)
	is_new = account.is_new()
	if is_new:
		account.owner = user.name
	local_fields = (
		"cache",
		"form_dict",
		"jenv_restricted",
		"jenv_unrestricted",
		"role_permissions",
		"new_doc_templates",
		"user_perms",
	)
	saved = {key: getattr(frappe.local, key, None) for key in local_fields}
	session = frappe.local.session
	session_values = dict(session)
	try:
		frappe.set_user("Administrator")
		account.save(ignore_permissions=True)
		if is_new:
			# Native insert overwrites owner with the service user. Assign the newly
			# provisioned account back to its authenticated owner in this transaction.
			account.db_set("owner", user.name, update_modified=False)
	finally:
		session.clear()
		session.update(session_values)
		frappe.local.session = session
		for key, value in saved.items():
			setattr(frappe.local, key, value)


def _mailbox_status(account, user):
	return {
		"name": account.name if account else None,
		"email_id": user.email,
		"connected": bool(account and account.enable_incoming and account.enable_outgoing),
		"enable_incoming": bool(account and account.enable_incoming),
		"enable_outgoing": bool(account and account.enable_outgoing),
		"can_manage": bool(_can_manage(account, user)),
	}


@frappe.whitelist()
def get_personal_settings():
	user = _personal_user()
	return {
		"mailbox": _mailbox_status(_mailbox(user), user),
		"api_configured": bool(user.api_key),
	}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=5, seconds=300)
def connect_personal_mailbox(password: str, email_id: str | None = None):
	user = _personal_user(for_update=True)
	if email_id and email_id.strip().casefold() != user.email.casefold():
		frappe.throw(_("You can only connect your own email address."), frappe.PermissionError)
	if not password or not password.strip():
		frappe.throw(_("Enter your Google app password."))
	account = _mailbox(user)
	if not _can_manage(account, user):
		frappe.throw(
			_("This mailbox is managed by an administrator or shared. Ask an administrator to update it."),
			frappe.PermissionError,
		)
	if not account:
		account = frappe.new_doc("Email Account")
		account.email_account_name = f"CRM - {user.email}"
		account.email_id = user.email
	account.update(
		{
			"service": "GMail",
			"auth_method": "Basic",
			"password": password.strip(),
			"enable_incoming": 1,
			"enable_outgoing": 1,
			"default_incoming": 0,
			"default_outgoing": 0,
			"awaiting_password": 0,
			"email_server": "imap.gmail.com",
			"use_imap": 1,
			"use_ssl": 1,
			"incoming_port": 993,
			"smtp_server": "smtp.gmail.com",
			"smtp_port": 587,
			"use_tls": 1,
			"use_ssl_for_outgoing": 0,
			"use_starttls": 0,
			"no_smtp_authentication": 0,
			"login_id_is_different": 0,
			"always_use_account_email_id_as_sender": 1,
			"create_contact": 0,
			"create_lead_from_incoming_email": 0,
			"enable_automatic_linking": 0,
			"append_to": None,
			"email_sync_option": "UNSEEN",
		}
	)
	account.set("imap_folder", [{"folder_name": "INBOX", "append_to": None}])
	failed = False
	try:
		# Native validation checks Google credentials; only this own account bypasses DocPerm.
		_save_own_mailbox(account, user)
	except Exception:
		failed = True
	finally:
		# Keep app passwords out of a later validation error's frame/exception context.
		password = None
		account.password = None
	if failed:
		frappe.clear_messages()
		frappe.throw(
			_("Could not connect to Google. Check your app password and your Workspace email policy.")
		)
	# The Email Account hook can update the user's inbox, so load its current locked version.
	user = _personal_user(for_update=True)
	if not any(row.email_account == account.name for row in user.user_emails):
		user.append("user_emails", {"email_account": account.name, "email_id": user.email})
		user.save(ignore_permissions=True)
	return _mailbox_status(account, user)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=5, seconds=300)
def generate_personal_api_keys(confirm_replace: bool = False):
	user = _personal_user(for_update=True)
	if user.api_key and not cint(confirm_replace):
		frappe.throw(_("Confirm replacement before generating a new API secret."))
	if not user.api_key:
		user.api_key = frappe.generate_hash(length=32)
	secret = frappe.generate_hash(length=32)
	user.api_secret = secret
	user.save(ignore_permissions=True)
	return {"api_key": user.api_key, "api_secret": secret}
