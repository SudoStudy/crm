"""Stored platform voice charges; no rental, recording, storage or account scans.

A null browser-parent price is NOT evidence of zero. Even with billed child legs
the call remains Partial and its known amount is reported separately from complete
totals. Retry it rather than inventing a free parent-leg billing rule.
"""

import re
from decimal import Decimal, InvalidOperation

import frappe

MAX_CHILD_LEGS = 25
BATCH_SIZE = 50
TERMINAL = {"completed", "busy", "failed", "no-answer", "canceled"}
COST_FIELDS = (
	"voice_cost_status",
	"voice_cost_amount",
	"voice_cost_currency",
	"voice_cost_leg_count",
	"voice_cost_pending_legs",
	"voice_cost_checked_at",
	"voice_cost_error",
)


def _get(row, key, default=None):
	return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def is_platform_call(call):
	return bool(
		_get(call, "telephony_medium") == "Twilio"
		and _get(call, "type") == "Outgoing"
		and _get(call, "caller")
		and re.fullmatch(r"CA[0-9a-fA-F]{32}", _get(call, "id") or "")
	)


def is_crm_caller(caller):
	return bool(
		caller
		and frappe.db.exists("User", caller)
		and frappe.db.exists(
			"Has Role",
			{
				"parent": caller,
				"parenttype": "User",
				"role": ["in", ["Sales User", "Sales Manager", "System Manager"]],
			},
		)
	)


def calculate_cost(legs, discovery_complete=True):
	unique, conflicts = {}, False
	for leg in legs:
		sid = _get(leg, "sid")
		if not sid:
			discovery_complete = False
			continue
		if sid in unique:
			previous = unique[sid]
			if any(_get(previous, key) != _get(leg, key) for key in ("price", "price_unit", "status")):
				conflicts = True
			continue
		unique[sid] = leg
	amount, currencies, pending, priced = Decimal(0), set(), 0, 0
	for leg in unique.values():
		currency = str(_get(leg, "price_unit") or "").upper()
		try:
			price = Decimal(str(_get(leg, "price")))
			valid = price.is_finite() and bool(currency) and _get(leg, "status") in TERMINAL
		except (InvalidOperation, ValueError, TypeError):
			valid = False
		if not valid:
			pending += 1
			continue
		amount += abs(price)
		currencies.add(currency)
		priced += 1
	unknown = pending or not discovery_complete or conflicts or not unique
	status = "Partial" if priced and unknown else "Pending" if unknown else "Complete"
	if len(currencies) > 1:
		status = "Unsupported Currency"
	return {
		"status": status,
		"amount": amount if priced and len(currencies) == 1 else None,
		"currency": next(iter(currencies)) if len(currencies) == 1 else "Mixed" if currencies else None,
		"leg_count": len(unique),
		"pending_legs": pending + int(not discovery_complete or conflicts),
	}


def fetch_cost(client, sid, caller=None):
	parent = client.calls(sid).fetch()
	if _get(parent, "sid") != sid or _get(parent, "parent_call_sid"):
		raise ValueError("Invalid platform parent")
	if caller and _get(parent, "_from") != "client:" + caller.replace("@", "(at)"):
		raise ValueError("Invalid platform caller")
	# Traverse descendants, not the account list. Overflow is never a complete sum.
	legs, queue, seen, complete = [parent], [sid], {sid}, True
	while queue:
		parent_sid = queue.pop(0)
		children = client.calls.list(parent_call_sid=parent_sid, limit=MAX_CHILD_LEGS + 1)
		if len(children) > MAX_CHILD_LEGS:
			complete = False
		for child in children[:MAX_CHILD_LEGS]:
			child_sid = _get(child, "sid")
			if _get(child, "parent_call_sid") != parent_sid or not child_sid:
				complete = False
				continue
			if child_sid in seen:
				# Keep duplicate price observations for conflict detection.
				legs.append(child)
				continue
			if len(seen) >= MAX_CHILD_LEGS + 1:
				complete = False
				continue
			seen.add(child_sid)
			legs.append(child)
			queue.append(child_sid)
	return calculate_cost(legs, discovery_complete=complete)


def reconcile_call(call, client, now=None):
	if not is_platform_call(call) or not is_crm_caller(_get(call, "caller")):
		return {"status": "Excluded"}
	if now is None:
		from frappe.utils import now_datetime

		now = now_datetime()
	try:
		result = fetch_cost(client, _get(call, "id"), caller=_get(call, "caller"))
		error = None
	except Exception:
		# Never log SDK exceptions: they can include provider payloads/URLs/tokens.
		result = {"status": "Error", "amount": None, "currency": None, "leg_count": 0, "pending_legs": 0}
		error = "provider_unavailable"
		previous = (
			frappe.db.get_value("CRM Call Log", _get(call, "name"), list(COST_FIELDS), as_dict=True) or {}
		)
		try:
			known_amount = Decimal(str(_get(previous, "voice_cost_amount")))
		except (InvalidOperation, ValueError, TypeError):
			known_amount = None
		if (
			_get(previous, "voice_cost_status") in ("Complete", "Partial")
			and _get(previous, "voice_cost_currency") not in (None, "", "Mixed")
			and known_amount is not None
			and known_amount.is_finite()
			and known_amount >= 0
		):
			result = {
				"status": "Partial",
				"amount": known_amount,
				"currency": _get(previous, "voice_cost_currency"),
				"leg_count": _get(previous, "voice_cost_leg_count") or 0,
				"pending_legs": max(_get(previous, "voice_cost_pending_legs") or 0, 1),
			}
	values = {
		"voice_cost_status": result["status"],
		"voice_cost_amount": result["amount"],
		"voice_cost_currency": result["currency"],
		"voice_cost_leg_count": result["leg_count"],
		"voice_cost_pending_legs": result["pending_legs"],
		"voice_cost_checked_at": now,
		"voice_cost_error": error,
	}
	frappe.db.set_value("CRM Call Log", _get(call, "name"), values, update_modified=False)
	return result


def reconcile_pending_costs():
	"""Hourly, bounded and oldest-first; retries cannot accumulate duplicate charges."""
	if not frappe.db.get_single_value("CRM Twilio Settings", "enabled"):
		return
	rows = frappe.get_all(
		"CRM Call Log",
		filters={
			"telephony_medium": "Twilio",
			"type": "Outgoing",
			"caller": ["is", "set"],
			"id": ["like", "CA%"],
			"status": ["in", ["Completed", "Failed", "Busy", "No Answer", "Canceled"]],
		},
		or_filters=[["voice_cost_status", "is", "not set"], ["voice_cost_status", "!=", "Complete"]],
		fields=["name", "id", "caller", "type", "telephony_medium"],
		order_by="voice_cost_checked_at asc, creation asc",
		limit_page_length=BATCH_SIZE,
	)
	eligible = []
	for call in rows:
		if is_platform_call(call) and is_crm_caller(_get(call, "caller")):
			eligible.append(call)
		else:
			# Rotate excluded rows out of this oldest-first bounded batch. Keep their
			# status unset so correcting a SID or restoring a CRM role rechecks them.
			from frappe.utils import now_datetime

			frappe.db.set_value(
				"CRM Call Log",
				_get(call, "name"),
				{"voice_cost_checked_at": now_datetime()},
				update_modified=False,
			)
	rows = eligible
	if not rows:
		return
	from crm.integrations.twilio.twilio_handler import Twilio

	try:
		client = Twilio.get_twilio_client()
	except Exception:
		return
	for call in rows:
		reconcile_call(call, client)


def get_call_cost(call):
	"""Caller must check CRM Call Log + linked document permissions before using."""
	if not is_platform_call(call) or not is_crm_caller(_get(call, "caller")):
		return {"status": "Excluded", "amount": None, "currency": None}
	return {
		"status": _get(call, "voice_cost_status") or "Pending",
		"amount": float(_get(call, "voice_cost_amount"))
		if _get(call, "voice_cost_status") in ("Complete", "Partial")
		and _get(call, "voice_cost_currency") not in (None, "", "Mixed")
		and _get(call, "voice_cost_amount") is not None
		else None,
		"currency": _get(call, "voice_cost_currency"),
		"checked_at": _get(call, "voice_cost_checked_at"),
		"pending_legs": _get(call, "voice_cost_pending_legs") or 0,
	}


def summarize_costs(rows):
	confirmed, partial, pending, non_usd = Decimal(0), Decimal(0), 0, 0
	for row in rows:
		status, currency = _get(row, "voice_cost_status"), _get(row, "voice_cost_currency")
		if currency and currency != "USD":
			non_usd += 1
		if status != "Complete":
			pending += 1
		if currency != "USD":
			continue
		try:
			amount = Decimal(str(_get(row, "voice_cost_amount")))
		except (InvalidOperation, ValueError, TypeError):
			continue
		if not amount.is_finite() or amount < 0:
			continue
		if status == "Complete":
			confirmed += amount
		elif status == "Partial":
			partial += amount
	return {
		"currency": "USD",
		"confirmed_amount": float(confirmed),
		"known_partial_amount": float(partial),
		"pending_calls": pending,
		"non_usd_calls": non_usd,
		"complete": pending == 0 and non_usd == 0,
		"call_count": len(rows),
	}


def get_cost_summary(start, end):
	"""Shared aggregate ONLY. The API must authenticate and authorize CRM roles.

	Bounds are inclusive start / exclusive end, supplied by the validated API period.
	No rep identities, phone numbers, call SIDs or linked documents are returned.
	"""
	rows = frappe.get_all(
		"CRM Call Log",
		filters=[
			["telephony_medium", "=", "Twilio"],
			["type", "=", "Outgoing"],
			["caller", "is", "set"],
			["id", "like", "CA%"],
			["start_time", ">=", start],
			["start_time", "<", end],
		],
		fields=["id", "caller", "voice_cost_status", "voice_cost_amount", "voice_cost_currency"],
		limit_page_length=0,
	)
	# Creation is evidence of launching the CRM call only, not completion or billing.
	# Keep attempts visible while Twilio has not supplied their start timestamp.
	rows += frappe.get_all(
		"CRM Call Log",
		filters=[
			["telephony_medium", "=", "Twilio"],
			["type", "=", "Outgoing"],
			["caller", "is", "set"],
			["id", "like", "CA%"],
			["start_time", "is", "not set"],
			["creation", ">=", start],
			["creation", "<", end],
		],
		fields=["id", "caller", "voice_cost_status", "voice_cost_amount", "voice_cost_currency"],
		limit_page_length=0,
	)
	rows = list({row["id"]: row for row in rows}.values())
	callers = {row.get("caller") for row in rows}
	valid_callers = {caller for caller in callers if is_crm_caller(caller)}
	return summarize_costs(
		[
			row
			for row in rows
			if row.get("caller") in valid_callers
			and re.fullmatch(r"CA[0-9a-fA-F]{32}", _get(row, "id") or "")
		]
	)


def protect_cost_fields(doc, method=None):
	"""Read-only form metadata also needs server enforcement on ordinary saves.

	Only reconciliation's targeted db.set_value writes these fields.
	"""
	previous = doc.get_doc_before_save()
	for field in COST_FIELDS:
		old, new = _get(previous, field), _get(doc, field)
		changed = doc.has_value_changed(field)
		# Native has_value_changed normalizes datetimes; get_value casts numeric
		# fields too, allowing unchanged numbers serialized as strings by clients.
		if (
			changed
			and previous
			and field in ("voice_cost_amount", "voice_cost_leg_count", "voice_cost_pending_legs")
		):
			changed = previous.get_value(field) != doc.get_value(field)
		if changed and not (old in (None, "", 0) and new in (None, "", 0)):
			frappe.throw(
				frappe._("Voice cost metadata is maintained by reconciliation."), frappe.PermissionError
			)
