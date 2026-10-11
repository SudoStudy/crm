"""Native Performance endpoints. Every entry point validates identity and scope."""

from decimal import Decimal, InvalidOperation

import frappe
from frappe import _

from crm.performance.metrics import money, month_key, period_bounds, summarize
from crm.performance.targets import get_targets, save_target


def load_cost_summary(start, end):
	from crm.performance.call_costs import get_cost_summary

	return get_cost_summary(start, end)


def load_call_cost(doc):
	from crm.performance.call_costs import get_call_cost

	return get_call_cost(doc)


CRM_ROLES = {"Sales User", "Sales Manager", "System Manager"}
MANAGER_ROLES = {"Sales Manager", "System Manager"}


def identity():
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Sign in to view Performance"), frappe.AuthenticationError)
	roles = set(frappe.get_roles(user))
	if not roles & CRM_ROLES:
		frappe.throw(_("CRM access is required"), frappe.PermissionError)
	return user, bool(roles & MANAGER_ROLES)


def crm_users():
	# A manager may see the CRM user directory, not any User credential fields.
	role_users = set()
	offset = 0
	while True:
		rows = frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "role": ["in", sorted(CRM_ROLES)]},
			fields=["parent"],
			order_by="name asc",
			start=offset,
			page_length=200,
		)
		role_users.update(row["parent"] for row in rows)
		if len(rows) < 200:
			break
		offset += len(rows)
	if not role_users:
		return []
	result, offset = [], 0
	while True:
		rows = frappe.get_all(
			"User",
			filters={"name": ["in", sorted(role_users)], "enabled": 1, "user_type": "System User"},
			fields=["name", "full_name"],
			order_by="full_name asc, name asc",
			start=offset,
			page_length=200,
		)
		result.extend(rows)
		if len(rows) < 200:
			break
		offset += len(rows)
	return result


def resolve_scope(salesperson=None):
	user, manager = identity()
	selected = salesperson or user
	if not manager and selected != user:
		frappe.throw(_("You can view only your own Performance"), frappe.PermissionError)
	if selected == "team":
		return team_users()
	if (
		selected == "Guest"
		or not set(frappe.get_roles(selected)) & CRM_ROLES
		or not frappe.db.get_value("User", selected, "enabled")
	):
		frappe.throw(_("Choose an enabled CRM user"), frappe.PermissionError)
	return [selected]


def team_users(directory=None):
	"""Ordinary reps plus managers with explicit quotas; missing rep quotas stay visible."""
	users = []
	rules_exist = frappe.db.exists("DocType", "CRM Sales Target Rule")
	for row in directory if directory is not None else crm_users():
		name = row["name"]
		roles = set(frappe.get_roles(name))
		is_rep = "Sales User" in roles and not roles & MANAGER_ROLES
		has_target = frappe.db.exists("CRM Sales Target", {"salesperson": name})
		has_rule = rules_exist and frappe.db.exists("CRM Sales Target Rule", {"salesperson": name})
		if is_rep or has_target or has_rule:
			users.append(name)
	return users


def pagination(page, page_size):
	try:
		page, page_size = int(page), int(page_size)
	except (ValueError, TypeError):
		frappe.throw(_("Invalid pagination"), frappe.ValidationError)
	if page < 1 or not 1 <= page_size <= 100:
		frappe.throw(_("Invalid pagination"), frappe.ValidationError)
	return page, page_size


@frappe.whitelist()
def get_context():
	user, manager = identity()
	directory = (
		crm_users()
		if manager
		else [{"name": user, "full_name": frappe.db.get_value("User", user, "full_name") or user}]
	)
	return {
		"user": user,
		"manager": manager,
		"users": directory,
		"team_users": team_users(directory) if manager else [],
		"today": frappe.utils.nowdate(),
		"timezone": frappe.utils.get_system_timezone(),
	}


@frappe.whitelist()
def get_summary(
	salesperson: str | None = None,
	period: str = "month",
	anchor: str | None = None,
	page: int = 1,
	page_size: int = 20,
):
	users = resolve_scope(salesperson)
	page, page_size = pagination(page, page_size)
	try:
		bounds = period_bounds(period, anchor or (str(frappe.utils.nowdate())[:7] + "-01"))
	except ValueError as error:
		frappe.throw(str(error), frappe.ValidationError)
	targets, target_warnings = get_targets(users, bounds["months"])
	deals, offset = [], 0
	while users:
		rows = frappe.get_list(
			"CRM Deal",
			filters={"deal_owner": ["in", users]},
			fields=["name"],
			order_by="name asc",
			start=offset,
			page_length=200,
		)
		for row in rows:
			if not frappe.has_permission("CRM Deal", "read", row["name"]):
				continue
			doc = frappe.get_doc("CRM Deal", row["name"])
			# Recheck the real document to preserve custom permission hook behavior.
			doc.check_permission("read")
			values = doc.as_dict()
			values["can_edit_forecast"] = doc.has_permission("write")
			if values.get("deal_owner") not in users:
				continue
			values["status_type"] = (
				frappe.get_cached_value("CRM Deal Status", values.get("status"), "type")
				if values.get("status")
				else None
			)
			deals.append(values)
		if len(rows) < 200:
			break
		offset += len(rows)
	result = summarize(deals, targets, bounds)
	editable = {deal["name"]: deal.get("can_edit_forecast", False) for deal in deals}
	for row in result["deals"]:
		row["can_edit_forecast"] = bool(editable.get(row["name"]))
	result["warnings"] = sorted(set(result["warnings"] + target_warnings))
	result["total"] = len(result["deals"])
	result["deals"] = result["deals"][(page - 1) * page_size : page * page_size]
	result.update(page=page, page_size=page_size)
	result["calling_costs"] = load_cost_summary(bounds["start"], bounds["end"])
	return result


@frappe.whitelist()
def get_activity(
	salesperson: str | None = None,
	mode: str = "performed_by",
	page: int = 1,
	page_size: int = 30,
	kind: str = "all",
):
	users = resolve_scope(salesperson)
	page, page_size = pagination(page, page_size)
	if mode not in ("performed_by", "owned_records"):
		frappe.throw(_("Invalid activity scope"), frappe.ValidationError)
	if kind not in ("all", "call", "change", "note", "task", "communication", "comment"):
		frappe.throw(_("Invalid activity type"), frappe.ValidationError)
	from crm.performance.activity import get_activity as load_activity

	return load_activity(users, mode, page, page_size, kind=kind)


@frappe.whitelist(methods=["POST"])
def set_target(salesperson: str, month: str, amount: int | float | str, recurring: bool | int | str = False):
	manager = identity()[1]
	if not manager:
		frappe.throw(_("Only managers can edit targets"), frappe.PermissionError)
	users = resolve_scope(salesperson)
	if salesperson == "team" or len(users) != 1:
		frappe.throw(_("Choose one salesperson and an actual month"), frappe.ValidationError)
	try:
		return save_target(users[0], month, amount, recurring)
	except ValueError as error:
		frappe.throw(str(error), frappe.ValidationError)


@frappe.whitelist(methods=["POST"])
def update_forecast(deal: str, expected_mrr, probability, closing_month: str, modified: str):
	"""Edit only forecast inputs, preserving native authorization and Versions."""
	user, manager = identity()
	doc = frappe.get_doc("CRM Deal", deal, for_update=True)
	doc.check_permission("write")
	if not manager and doc.deal_owner != user:
		frappe.throw(_("You can edit only your own deal forecasts"), frappe.PermissionError)
	if not modified or str(doc.modified) != modified:
		frappe.throw(_("This deal changed. Reload Performance before saving."), frappe.TimestampMismatchError)
	if doc.currency != "USD":
		frappe.throw(
			_("Performance forecasts require USD; no conversion is assumed."), frappe.ValidationError
		)
	try:
		amount = money(expected_mrr)
		chance = Decimal(str(probability))
		if not chance.is_finite() or not 0 <= chance <= 100:
			raise ValueError("Probability must be between 0 and 100")
		month = month_key(closing_month)
	except (ValueError, InvalidOperation) as error:
		frappe.throw(str(error) or _("Invalid forecast inputs"), frappe.ValidationError)
	doc.expected_deal_value = float(amount)
	doc.probability = float(chance)
	doc.expected_closure_date = month
	doc.save()
	return {"name": doc.name, "modified": str(doc.modified)}


@frappe.whitelist()
def get_call_cost(name: str):
	identity()
	doc = frappe.get_doc("CRM Call Log", name)
	doc.check_permission("read")
	parents = [(doc.get("reference_doctype"), doc.get("reference_docname"))]
	parents.extend((row.get("link_doctype"), row.get("link_name")) for row in doc.get("links") or [])
	for doctype, parent in parents:
		if (
			doctype in ("CRM Lead", "CRM Deal")
			and parent
			and not frappe.has_permission(doctype, "read", parent)
		):
			frappe.throw(_("Not permitted to view this call"), frappe.PermissionError)
	return load_call_cost(doc)
