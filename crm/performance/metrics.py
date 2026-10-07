"""Pure USD new-MRR calculations. Periods have an exclusive upper bound."""

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def month_key(value):
	if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
		raise ValueError("Choose a month using YYYY-MM-01")
	parsed = date.fromisoformat(value)
	if parsed.day != 1:
		raise ValueError("Choose the first day of an actual month")
	return parsed.isoformat()


def add_months(value, count):
	parsed = date.fromisoformat(month_key(value))
	index = parsed.year * 12 + parsed.month - 1 + count
	return date(index // 12, index % 12 + 1, 1).isoformat()


def period_bounds(period, anchor):
	start = month_key(anchor)
	if period not in ("month", "quarter"):
		raise ValueError("Period must be month or quarter")
	if period == "quarter":
		parsed = date.fromisoformat(start)
		start = parsed.replace(month=((parsed.month - 1) // 3) * 3 + 1).isoformat()
	months = [add_months(start, n) for n in range(3 if period == "quarter" else 1)]
	return {"start": start, "end": add_months(months[-1], 1), "months": months}


def money(value):
	try:
		amount = Decimal(str(value if value is not None else 0))
	except (InvalidOperation, ValueError):
		raise ValueError("Amount must be finite and nonnegative") from None
	if not amount.is_finite() or amount < 0 or amount >= Decimal("10000000000000"):
		raise ValueError("Amount must be finite and nonnegative")
	return amount


def usd(value):
	return float(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def deal_contribution(deal, start, end):
	status = deal.get("status_type")
	if status == "Lost":
		return None, None
	if deal.get("currency") != "USD":
		return None, "Deals with missing or non-USD currency are excluded; no currency conversion is assumed."
	base = {
		"name": deal["name"],
		"title": deal.get("title") or deal.get("organization") or deal["name"],
		"status": deal.get("status"),
		"status_type": status,
		"currency": "USD",
	}
	try:
		base["expected_mrr"] = (
			usd(money(deal["expected_deal_value"])) if deal.get("expected_deal_value") is not None else None
		)
	except ValueError:
		base["expected_mrr"] = None
	try:
		display_probability = Decimal(str(deal["probability"]))
		base["probability"] = (
			float(min(Decimal(100), max(Decimal(0), display_probability)))
			if display_probability.is_finite()
			else None
		)
	except (KeyError, InvalidOperation, ValueError):
		base["probability"] = None
	if status == "Won":
		rows = [row for row in deal.get("status_change_log", []) if row.get("from_type") == "Won"]
		latest = (
			max(enumerate(rows), key=lambda item: (int(item[1].get("idx") or 0), item[0]))[1]
			if rows
			else None
		)
		try:
			won_at = datetime.fromisoformat(str(latest["from_date"])) if latest else None
		except (ValueError, KeyError, TypeError):
			won_at = None
		if won_at is None:
			return None, "Currently Won deals with missing or invalid Won history are excluded."
		if not start <= won_at.date().isoformat() < end:
			return None, None
		try:
			amount = money(deal.get("deal_value"))
		except ValueError:
			return None, "Deals with invalid actual Won MRR are excluded."
		return {
			**base,
			"kind": "won",
			"amount": amount,
			"weighted": Decimal(0),
			"won_at": won_at.isoformat(),
		}, None
	if not status:
		return None, "Deals with unknown status type are excluded."
	try:
		expected = money(deal.get("expected_deal_value"))
		probability = Decimal(str(deal.get("probability") or 0))
		if not probability.is_finite():
			raise ValueError()
		weighted = expected * min(Decimal(100), max(Decimal(0), probability)) / 100
	except (ValueError, InvalidOperation):
		return None, "Deals with invalid forecast values are excluded."
	return {
		**base,
		"kind": "pipeline",
		"amount": expected,
		"weighted": weighted,
		"expected_mrr": usd(expected),
		"probability": float(min(Decimal(100), max(Decimal(0), probability))),
		"won_at": None,
	}, None


def summarize(deals, targets, period):
	contributions, warnings = [], set()
	for deal in deals:
		row, warning = deal_contribution(deal, period["start"], period["end"])
		if row is not None:
			contributions.append(row)
		if warning:
			warnings.add(warning)
	complete = all(row.get("amount") is not None for row in targets) and len(targets) == len(period["months"])
	target = sum(money(row["amount"]) for row in targets) if complete else None
	if not complete:
		warnings.add(
			"Monthly targets are missing; set every month in the selected period to calculate progress and coverage."
		)
	elif target == 0:
		warnings.add("Target is zero; progress and coverage are not calculated.")
	actual = sum(money(row["amount"]) for row in contributions if row["kind"] == "won")
	pipeline = sum(money(row["weighted"]) for row in contributions if row["kind"] == "pipeline")
	remaining = max(Decimal(0), target - actual) if target is not None else None
	return {
		"period": period,
		"target": usd(target) if target is not None else None,
		"actual": usd(actual),
		"remaining": usd(remaining) if remaining is not None else None,
		"progress": float(actual / target * 100) if target else None,
		"weighted_pipeline": usd(pipeline),
		"coverage": float(pipeline / remaining) if remaining else None,
		"warnings": sorted(warnings),
		"targets": targets,
		"deals": sorted(
			[
				{**row, "amount": usd(row["amount"]), "weighted": usd(row["weighted"])}
				for row in contributions
			],
			key=lambda row: (row["kind"], row["name"]),
		),
	}
