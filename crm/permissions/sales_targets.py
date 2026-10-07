"""Native Desk/REST target reads use salesperson identity, never row owner."""

import frappe


def _identity(user):
	user = user or frappe.session.user
	return user, set(frappe.get_roles(user)) if user and user != "Guest" else set()


def _conditions(doctype, user=None):
	user, roles = _identity(user)
	if roles & {"Sales Manager", "System Manager"}:
		return ""
	if "Sales User" not in roles:
		return "1=0"
	return f"`tab{doctype}`.`salesperson` = {frappe.db.escape(user)}"


def get_target_permission_query_conditions(user=None):
	return _conditions("CRM Sales Target", user)


def get_rule_permission_query_conditions(user=None):
	return _conditions("CRM Sales Target Rule", user)


def has_target_permission(doc, ptype, user=None, debug=False):
	user, roles = _identity(user)
	if "System Manager" in roles:
		return True
	if ptype not in ("read", "select"):
		return False
	if "Sales Manager" in roles:
		return True
	return "Sales User" in roles and doc.salesperson == user
