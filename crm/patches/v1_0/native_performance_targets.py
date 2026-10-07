"""Adopt existing custom monthly targets without deleting legacy fields or rows.

No user-specific defaults are seeded here. On the SudoStudy site the controller
must disable the exact legacy recurring-target Server Script only after verifying
native rules, because that script overwrites manual target edits every day.
"""

import frappe


def fields(month_field):
	return [
		{
			"fieldname": "salesperson",
			"label": "Salesperson",
			"fieldtype": "Link",
			"options": "User",
			"reqd": 1,
			"in_list_view": 1,
		},
		{
			"fieldname": month_field,
			"label": "Effective Month" if month_field == "effective_month" else "Target Month",
			"fieldtype": "Date",
			"reqd": 1,
			"in_list_view": 1,
		},
		{
			"fieldname": "currency",
			"label": "Currency",
			"fieldtype": "Link",
			"options": "Currency",
			"default": "USD",
			"reqd": 1,
		},
		{
			"fieldname": "target_new_mrr",
			"label": "Monthly New MRR Target",
			"fieldtype": "Currency",
			"options": "currency",
			"reqd": 1,
			"in_list_view": 1,
		},
	]


def ensure_schema(name, month_field):
	if not frappe.db.exists("DocType", name):
		frappe.get_doc(
			{
				"doctype": "DocType",
				"name": name,
				"module": "FCRM",
				"custom": 1,
				"autoname": "hash",
				"fields": fields(month_field),
				"track_changes": 1,
				"permissions": [
					{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
					{"role": "Sales Manager", "read": 1},
					{"role": "Sales User", "read": 1},
				],
			}
		).insert(ignore_permissions=True)
		return
	doc = frappe.get_doc("DocType", name)
	changed = False
	existing = {field.fieldname for field in doc.get("fields")}
	for field in fields(month_field):
		if field["fieldname"] not in existing:
			doc.append("fields", field)
			changed = True
	if doc.module != "FCRM":
		doc.module = "FCRM"
		changed = True
	roles = {row.role for row in doc.get("permissions")}
	for role in ("Sales User", "Sales Manager"):
		if role not in roles:
			doc.append("permissions", {"role": role, "read": 1})
			changed = True
	if changed:
		doc.save(ignore_permissions=True)


def execute():
	ensure_schema("CRM Sales Target", "target_month")
	ensure_schema("CRM Sales Target Rule", "effective_month")
