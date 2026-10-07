"""Monthly targets override persistent defaults without writes on dashboard reads.

Target writes are called only after the API manager and target-user checks. A User
row lock serializes writes even when that user's first target does not exist yet.
"""

import hashlib
from decimal import ROUND_HALF_UP, Decimal

import frappe

from crm.performance.metrics import money, month_key


def paged_rows(doctype, filters, fields):
	offset = 0
	while True:
		rows = frappe.get_list(
			doctype, filters=filters, fields=fields, order_by="name asc", start=offset, page_length=200
		)
		yield from rows
		if len(rows) < 200:
			break
		offset += len(rows)


def resolve_targets(users, months, rows, rules):
	result, warnings = [], set()
	for month in months:
		values, sources = [], []
		for user in users:
			explicit = [
				row for row in rows if row["salesperson"] == user and str(row["target_month"])[:10] == month
			]
			applicable = [
				rule
				for rule in rules
				if rule["salesperson"] == user and str(rule["effective_month"])[:10] <= month
			]
			if len(explicit) > 1:
				warnings.add(
					"Duplicate monthly target rows need manager review; duplicate amounts are not counted."
				)
				values.append(None)
				continue
			selected = (
				explicit[0]
				if explicit
				else max(applicable, key=lambda row: str(row["effective_month"]), default=None)
			)
			if selected is None:
				values.append(None)
				continue
			if selected.get("currency") != "USD":
				warnings.add("Targets with missing or non-USD currency need review and are excluded.")
				values.append(None)
				continue
			try:
				values.append(money(selected["target_new_mrr"]))
				sources.append("monthly" if explicit else "recurring")
			except (ValueError, KeyError):
				warnings.add("Invalid target amounts need manager review.")
				values.append(None)
		amount = sum(values, Decimal(0)) if values and all(value is not None for value in values) else None
		result.append(
			{
				"month": month,
				"amount": float(amount) if amount is not None else None,
				"source": "missing"
				if amount is None
				else (sources[0] if len(set(sources)) == 1 else "mixed"),
			}
		)
	return result, sorted(warnings)


def get_targets(users, months):
	filters = {"salesperson": ["in", users], "target_month": ["between", [months[0], months[-1]]]}
	rows = list(
		paged_rows(
			"CRM Sales Target", filters, ["name", "salesperson", "target_month", "currency", "target_new_mrr"]
		)
	)
	rules = []
	if frappe.db.exists("DocType", "CRM Sales Target Rule"):
		rules = list(
			paged_rows(
				"CRM Sales Target Rule",
				{"salesperson": ["in", users], "effective_month": ["<=", months[-1]]},
				["name", "salesperson", "effective_month", "currency", "target_new_mrr"],
			)
		)
	return resolve_targets(users, months, rows, rules)


def _name(user, month, prefix):
	return f"{prefix}-{hashlib.sha256((user + ':' + month).encode()).hexdigest()[:32]}"


def _write_one(doctype, user, month, amount, month_field, prefix):
	# Check the exact authorized user/month independently of desk list filtering:
	# a hidden legacy row must never turn an edit into a duplicate insert.
	existing = frappe.db.get_values(
		doctype, filters={"salesperson": user, month_field: month}, fieldname="name", as_dict=True, limit=2
	)
	if len(existing) > 1:
		raise ValueError("Duplicate monthly target rows must be resolved before editing")
	if existing:
		doc = frappe.get_doc(doctype, existing[0]["name"])
	else:
		doc = frappe.get_doc(
			{"doctype": doctype, "name": _name(user, month, prefix), "salesperson": user, month_field: month}
		)
	doc.currency = "USD"
	doc.target_new_mrr = float(amount)
	# The authenticated manager API is intentionally narrower than existing desk
	# System Manager-only write permissions. Other legacy fields are untouched.
	if existing:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	return doc.name


def save_target(user, month, amount, recurring=False):
	month = month_key(month)
	amount = money(amount)
	if amount >= Decimal("10000000000000"):
		raise ValueError("Target exceeds the supported USD amount")
	amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	if recurring not in (False, True, 0, 1, "0", "1"):
		raise ValueError("Recurring must be enabled or disabled")
	recurring = recurring in (True, 1, "1")
	if recurring and month < str(frappe.utils.nowdate())[:7] + "-01":
		raise ValueError("Recurring targets must start in the current or a future month.")
	frappe.db.get_value("User", user, "name", for_update=True)
	name = _write_one("CRM Sales Target", user, month, amount, "target_month", "target")
	if recurring:
		_write_one("CRM Sales Target Rule", user, month, amount, "effective_month", "rule")
	return {
		"name": name,
		"salesperson": user,
		"month": month,
		"amount": float(amount),
		"currency": "USD",
		"recurring": recurring,
	}
