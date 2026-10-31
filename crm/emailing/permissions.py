"""Private drafts/templates remain private through native list and document APIs."""

import frappe

from crm.emailing.validation import reference
from crm.permissions.org_hierarchy import (
	get_deal_permission_query_conditions,
	get_lead_permission_query_conditions,
)


def has_permission(doc, ptype, user=None):
	user = user or frappe.session.user
	if user == "Guest" or (doc.owner and doc.owner != user):
		return False
	if ptype not in ("read", "select", "report", "print", "export"):
		return False
	if doc.doctype == "CRM Email Draft":
		try:
			reference(doc.reference_doctype, doc.reference_name, user=user)
		except (frappe.PermissionError, frappe.DoesNotExistError):
			return False
	return True


def sequence_query(user=None):
	return f"`tabCRM Email Sequence`.`owner` = {frappe.db.escape(user or frappe.session.user)}"


def draft_query(user=None):
	user = user or frappe.session.user
	conditions = []
	for dt, fn in [
		("CRM Lead", get_lead_permission_query_conditions),
		("CRM Deal", get_deal_permission_query_conditions),
	]:
		condition = fn(user)
		conditions.append(
			f"(`tabCRM Email Draft`.`reference_doctype` = {frappe.db.escape(dt)} AND "
			f"`tabCRM Email Draft`.`reference_name` IN (SELECT `tab{dt}`.`name` FROM `tab{dt}`"
			+ (f" WHERE {condition}" if condition else "")
			+ "))"
		)
	return f"`tabCRM Email Draft`.`owner` = {frappe.db.escape(user)} AND ({' OR '.join(conditions)})"
