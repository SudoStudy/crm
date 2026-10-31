"""Authorization and datetime rules shared by the customer email workspace."""

import json
from datetime import datetime, timezone
from email.utils import getaddresses
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, get_system_timezone, now_datetime, validate_email_address

from crm.api.session import CRM_ALLOWED_ROLES

REFERENCES = ("CRM Lead", "CRM Deal")
PUBLIC_FIELDS = (
	"name",
	"modified",
	"reference_doctype",
	"reference_name",
	"sender",
	"recipients",
	"cc",
	"bcc",
	"subject",
	"content",
	"stop_on_reply",
	"status",
	"timezone",
	"sequence_name",
	"enrollment_id",
	"communication",
	"last_error",
)


def current_user():
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to use customer email."), frappe.AuthenticationError)
	doc = frappe.get_doc("User", user, for_update=True)
	if (
		not doc.enabled
		or doc.user_type != "System User"
		or not set(frappe.get_roles(user)).intersection(CRM_ALLOWED_ROLES)
	):
		frappe.throw(_("CRM access is required."), frappe.PermissionError)
	if not hasattr(frappe.local, "response_headers"):
		frappe.local.response_headers = {}
	frappe.local.response_headers["Cache-Control"] = "no-store"
	frappe.flags.personal_settings_response = True
	return doc


def reference(doctype, name, *, email=False, user=None):
	if doctype not in REFERENCES or not name:
		frappe.throw(_("Choose a CRM lead or deal."))
	doc = frappe.get_doc(doctype, name)
	for permission in ("read", "email") if email else ("read",):
		if not frappe.has_permission(doctype, permission, doc=doc, user=user):
			frappe.throw(_("You do not have access to email this customer."), frappe.PermissionError)
	return doc


def parsed(data):
	if isinstance(data, str):
		try:
			data = json.loads(data)
		except (ValueError, TypeError):
			frappe.throw(_("Invalid email data."))
	if not isinstance(data, dict):
		frappe.throw(_("Invalid email data."))
	return data


def addresses(value, *, required=False):
	if value is None:
		value = ""
	if not isinstance(value, str) or "\r" in value or "\n" in value:
		frappe.throw(_("Enter valid email addresses separated by commas."))
	if not value.strip():
		if required:
			frappe.throw(_("Add at least one recipient."))
		return []
	result = []
	for _label, address in getaddresses([value]):
		if not address or not validate_email_address(address, throw=False) or "@" not in address:
			frappe.throw(_("Enter valid email addresses separated by commas."))
		if address.casefold() not in result:
			result.append(address.casefold())
	if required and not result:
		frappe.throw(_("Add at least one recipient."))
	if len(result) > 50:
		frappe.throw(_("Use at most 50 recipients."))
	return result


def senders(user):
	result = []
	for row in user.get("user_emails") or []:
		account = frappe.db.get_value(
			"Email Account",
			row.email_account,
			["name", "email_id", "enable_outgoing", "awaiting_password"],
			as_dict=True,
		)
		if account and account.enable_outgoing and not account.awaiting_password:
			result.append({"email": account.email_id, "label": account.name})
	return result


def sender_account(user, sender):
	links = frappe.db.sql(
		"select email_account from `tabUser Email` where parent=%s order by email_account for update",
		(user.name,),
		as_dict=True,
	)
	matches = []
	for row in links:
		account = frappe.get_doc("Email Account", row.email_account, for_update=True)
		if (
			account.enable_outgoing
			and not account.awaiting_password
			and account.email_id.casefold() == (sender or "").casefold()
		):
			matches.append(account.name)
	if len(matches) != 1:
		frappe.throw(_("Choose an enabled outgoing mailbox connected to your user."), frappe.PermissionError)
	return matches[0]


def attachments(value, doctype, name, user):
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("Invalid attachments."))
	if not isinstance(value, list) or len(value) > 20 or any(not isinstance(item, str) for item in value):
		frappe.throw(_("Use at most 20 uploaded file attachments."))
	result = list(dict.fromkeys(value))
	for file_name in result:
		file = frappe.get_doc("File", file_name)
		if not frappe.has_permission("File", "read", doc=file, user=user):
			frappe.throw(_("You cannot use this attachment."), frappe.PermissionError)
		if not (
			file.owner == user or (file.attached_to_doctype == doctype and file.attached_to_name == name)
		):
			frappe.throw(_("Choose files belonging to you or this customer."), frappe.PermissionError)
		if file.is_folder:
			frappe.throw(_("A folder cannot be attached."))
	return result


def zone(name):
	try:
		return ZoneInfo(name)
	except (ZoneInfoNotFoundError, TypeError, ValueError):
		frappe.throw(_("Choose a valid timezone."))


def aware(value):
	try:
		stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
	except (TypeError, ValueError, AttributeError):
		frappe.throw(_("Choose a valid date and time with a timezone offset."))
	if stamp.tzinfo is None or stamp.utcoffset() is None:
		frappe.throw(_("The scheduled time must include its timezone offset."))
	return stamp


def to_site(value, tz_name):
	zone(tz_name)
	stamp = aware(value).astimezone(timezone.utc).replace(tzinfo=None)
	if stamp <= utcnow():
		frappe.throw(_("Choose a future sending time."))
	return stamp


def public(doc):
	result = {key: doc.get(key) for key in PUBLIC_FIELDS}
	result["attachments"] = json.loads(doc.attachments or "[]")
	result["stop_on_reply"] = bool(cint(doc.stop_on_reply))
	result["send_at"] = (
		get_datetime(doc.send_at).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
		if doc.send_at
		else None
	)
	return result


def check_modified(doc, modified):
	if not modified or str(doc.modified) != str(modified):
		frappe.throw(
			_("This email changed in another tab. Reload before editing."), frappe.TimestampMismatchError
		)


def save(doc):
	previous = frappe.flags.get("crm_email_workspace_write")
	try:
		frappe.flags.crm_email_workspace_write = True
		doc.save(ignore_permissions=True)
	finally:
		frappe.flags.crm_email_workspace_write = previous
	return doc


def delete(doc):
	previous = frappe.flags.get("crm_email_workspace_write")
	try:
		frappe.flags.crm_email_workspace_write = True
		doc.delete(ignore_permissions=True)
	finally:
		frappe.flags.crm_email_workspace_write = previous


def utcnow():
	return datetime.now(timezone.utc).replace(tzinfo=None)
