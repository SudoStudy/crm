"""Seven site-calendar days of CRM activity, with native timeline authorization.

``get_activity(users, mode, page=1, page_size=30, end_date=None, kind="all")`` receives an
already-authorized, explicit list of User names from the API. ``performed_by``
selects the actual event actor; ``owned_records`` selects the current CRM Lead /
Deal owner, independently of actor. The target reporting period never changes
this activity window. Frappe's naive database timestamps are in the site timezone.

The result has ``events`` (the current page), seven newest-first ``days`` (each
with date, total across all pages, and that page's events), ``pagination``, the
aliases ``page/page_size/total``, ``window``, ``mode`` and human-readable warnings.
Events have id, source_doctype/name, kind, timestamp, actor, parent_doctype/name,
title, summary, url (CRM parent), source_url and safe, plain-text details.

Version/Comment follow Frappe's native parent-authorized timeline semantics: a
time-bounded reference-only discovery never returns content. Permission-aware
parent queries and effective document checks produce an explicit allowlist before
history content is fetched. This is necessary because comments deliberately do
not update the parent's modified timestamp. All independent sources require their
own effective read permission as well as read permission on every linked parent.
No parent get_all, all-lead scan, synthetic task completion, or recording URLs.
"""

import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from email.utils import parseaddr
from html.parser import HTMLParser
from math import ceil
from urllib.parse import quote
from zoneinfo import ZoneInfo

BATCH_SIZE = 200
CRM_PARENTS = {"CRM Lead", "CRM Deal"}
HISTORY_PARENTS = CRM_PARENTS | {"CRM Task", "FCRM Note"}
LINK_PARENTS = HISTORY_PARENTS | {"CRM Call Log", "FCRM Note"}

# Explicit operational fields protect against arbitrary/custom secret fields in
# Version.data while also suppressing derived SLA/reconciliation change noise.
VERSION_FIELDS = {
	"CRM Lead": {
		"next_step",
		"next_action_date",
		"segment",
		"subjects",
		"comm_platform",
		"instagram_id",
		"status",
		"lead_owner",
		"first_name",
		"middle_name",
		"last_name",
		"lead_name",
		"email",
		"phone",
		"mobile_no",
		"website",
		"organization",
		"source",
		"industry",
		"job_title",
		"no_of_employees",
		"annual_revenue",
		"territory",
		"details",
		"lost_reason",
		"lost_notes",
	},
	"CRM Deal": {
		"customer_health",
		"health_reason",
		"churn_status",
		"churn_reason",
		"churned_on",
		"expected_students",
		"price_per_student",
		"next_action_date",
		"status",
		"deal_owner",
		"organization",
		"lead_name",
		"first_name",
		"last_name",
		"email",
		"phone",
		"mobile_no",
		"website",
		"source",
		"industry",
		"job_title",
		"territory",
		"next_step",
		"deal_value",
		"expected_deal_value",
		"probability",
		"currency",
		"expected_closure_date",
		"closed_date",
		"lost_reason",
		"lost_notes",
	},
	"CRM Task": {"title", "status", "priority", "assigned_to", "due_date", "start_date", "description"},
	"FCRM Note": {"title", "content"},
}

REFERENCE_FIELDS = {
	"Version": ("ref_doctype", "docname"),
	"Comment": ("reference_doctype", "reference_name"),
	"Communication": ("reference_doctype", "reference_name"),
	"FCRM Note": ("reference_doctype", "reference_docname"),
	"CRM Task": ("reference_doctype", "reference_docname"),
	"CRM Call Log": ("reference_doctype", "reference_docname"),
}

KIND_FILTERS = {"all", "call", "change", "note", "task", "communication", "comment"}


class _PlainText(HTMLParser):
	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.parts = []
		self.hidden = 0

	def handle_starttag(self, tag, attrs):
		if tag in {"script", "style"}:
			self.hidden += 1
		elif tag in {"p", "br", "div", "li"}:
			self.parts.append(" ")

	def handle_endtag(self, tag):
		if tag in {"script", "style"}:
			self.hidden = max(0, self.hidden - 1)
		elif tag in {"p", "div", "li"}:
			self.parts.append(" ")

	def handle_data(self, value):
		if not self.hidden:
			self.parts.append(value)


def _text(value, length=500):
	parser = _PlainText()
	parser.feed("" if value is None else str(value))
	return " ".join("".join(parser.parts).split())[:length]


def _timestamp(value, timezone):
	if isinstance(value, datetime):
		result = value
	elif isinstance(value, date):
		result = datetime.combine(value, time.min)
	elif isinstance(value, str) and value:
		try:
			result = datetime.fromisoformat(value.replace("Z", "+00:00"))
		except ValueError:
			return None
	else:
		return None
	zone = ZoneInfo(timezone)
	return result.replace(tzinfo=zone) if result.tzinfo is None else result.astimezone(zone)


def calendar_window(end_date=None, timezone="UTC"):
	"""Inclusive end date, exclusive next midnight; DST days need not be 24h."""
	zone = ZoneInfo(timezone)
	if end_date is None:
		last_day = datetime.now(zone).date()
	elif isinstance(end_date, datetime):
		last_day = (_timestamp(end_date, timezone)).date()
	elif isinstance(end_date, date):
		last_day = end_date
	else:
		last_day = date.fromisoformat(str(end_date))
	return (
		datetime.combine(last_day - timedelta(days=6), time.min, zone),
		datetime.combine(last_day + timedelta(days=1), time.min, zone),
	)


def _url(doctype, name):
	if not doctype or not name:
		return None
	encoded = quote(str(name), safe="")
	if doctype in CRM_PARENTS:
		return f"/crm/{'leads' if doctype == 'CRM Lead' else 'deals'}/{encoded}"
	return f"/app/{doctype.lower().replace(' ', '-')}/{encoded}"


def normalize_source(doctype, row, timezone="UTC"):
	"""Pure allowlisted normalization; returns None for malformed/noisy history.

	Parent identity here is only a candidate, never authorization. The service
	resolves task/call/note references and checks them before returning the event.
	"""
	if doctype not in REFERENCE_FIELDS or not row.get("name"):
		return None
	source_name = str(row.get("name"))
	timestamp_field = {"CRM Call Log": "start_time", "Communication": "communication_date"}.get(doctype)
	timestamp = _timestamp(row.get(timestamp_field) or row.get("creation"), timezone)
	if timestamp is None:
		return None
	ref_type, ref_name = REFERENCE_FIELDS[doctype]
	actor = row.get("owner")
	details = {}
	parent_doctype, parent_name = row.get(ref_type), row.get(ref_name)
	if doctype == "Version":
		try:
			data = json.loads(row.get("data") or "{}")
		except (TypeError, ValueError):
			return None
		if not isinstance(data, dict) or not isinstance(data.get("changed"), list):
			return None
		changes = []
		for change in data["changed"]:
			if not isinstance(change, list | tuple) or len(change) != 3:
				continue
			field, old, new = change
			if (
				not isinstance(field, str)
				or field not in VERSION_FIELDS.get(parent_doctype, set())
				or old == new
			):
				continue
			changes.append(
				{
					"field": field,
					"label": field.replace("_", " ").title(),
					"old_value": _text(old),
					"value": _text(new),
				}
			)
		if not changes:
			return None
		details = {"changes": changes, "changed_doctype": parent_doctype, "changed_name": parent_name}
		completed = parent_doctype == "CRM Task" and any(
			c["field"] == "status" and c["value"] in {"Done", "Completed"} for c in changes
		)
		kind = "task_completed" if completed else "changed"
		title = (
			"Task completed"
			if completed
			else f"{parent_doctype.removeprefix('CRM ').removeprefix('FCRM ')} changed"
		)
		summary = "; ".join(
			f"{c['label']}: {c['old_value'] or 'empty'} → {c['value'] or 'empty'}" for c in changes
		)
	elif doctype == "Comment":
		if row.get("comment_type") != "Comment":
			return None
		kind, title, summary = "comment", "Comment added", _text(row.get("content"))
	elif doctype == "FCRM Note":
		kind, title, summary = "note", _text(row.get("title")) or "Note added", _text(row.get("content"))
	elif doctype == "CRM Task":
		kind, title, summary = "task_created", "Task created", _text(row.get("title"))
		details = {
			"assigned_to": row.get("assigned_to"),
			"priority": _text(row.get("priority")),
			"due_date": _text(row.get("due_date")),
		}
	elif doctype == "CRM Call Log":
		direction = row.get("type")
		actor = (
			row.get("caller")
			if direction == "Outgoing"
			else row.get("receiver")
			if direction == "Incoming"
			else None
		)
		kind = (
			"outgoing_call"
			if direction == "Outgoing"
			else "incoming_call"
			if direction == "Incoming"
			else "call"
		)
		title = f"{direction} call" if direction in {"Incoming", "Outgoing"} else "Call"
		summary = _text(row.get("status"))
		details = {
			"direction": direction,
			"status": _text(row.get("status")),
			"duration": row.get("duration"),
		}
	else:
		if row.get("communication_type") not in (None, "Communication"):
			return None
		if row.get("sent_or_received") == "Sent":
			actor = parseaddr(str(row.get("sender") or ""))[1] or None
		kind, title, summary = "communication", "Communication", _text(row.get("subject"))
		details = {
			"direction": _text(row.get("sent_or_received")),
			"medium": _text(row.get("communication_medium")),
		}
	return {
		"id": f"{doctype}:{source_name}",
		"source_doctype": doctype,
		"source_name": source_name,
		"kind": kind,
		"timestamp": timestamp.isoformat(),
		"actor": actor,
		"category": "task"
		if doctype == "CRM Task" or (doctype == "Version" and parent_doctype == "CRM Task")
		else "note"
		if doctype == "Version" and parent_doctype == "FCRM Note"
		else "change"
		if doctype == "Version"
		else "call"
		if doctype == "CRM Call Log"
		else kind,
		"parent_doctype": parent_doctype,
		"parent_name": str(parent_name) if parent_name else None,
		"title": title,
		"summary": summary[:1000],
		"details": details,
		"url": _url(parent_doctype, parent_name),
		"source_url": _url(parent_doctype, parent_name)
		if doctype in {"Version", "Comment"}
		else _url(doctype, source_name),
	}


def _iter_rows(frappe, doctype, fields, filters, *, native_history=False, sort_field="creation"):
	"""Exhaust a stable ordered stream in bounded batches; never silently cap."""
	getter = frappe.get_all if native_history else frappe.get_list
	start = 0
	while True:
		rows = getter(
			doctype,
			fields=fields,
			filters=filters,
			order_by=f"{sort_field} asc, name asc",
			limit_start=start,
			limit_page_length=BATCH_SIZE,
		)
		yield from rows
		if len(rows) < BATCH_SIZE:
			break
		start += len(rows)


class _Reader:
	"""Request-local permission/document cache; nothing is loaded before read check."""

	def __init__(self, frappe):
		self.frappe = frappe
		self.docs = {}
		self.resolved = {}

	def read(self, doctype, name):
		key = (doctype, str(name))
		if key not in self.docs:
			if not name or not self.frappe.has_permission(doctype, "read", str(name)):
				self.docs[key] = None
			else:
				try:
					self.docs[key] = self.frappe.get_doc(doctype, str(name))
				except (self.frappe.PermissionError, self.frappe.DoesNotExistError):
					self.docs[key] = None
		return self.docs[key]

	def resolve(self, doctype, name, trail=None):
		"""Returns (allowed, CRM root list); rejects cycles and unreadable links.

		A linked task must itself be readable as well as its ultimate CRM parent.
		Every CRM link on a call is checked, not just whichever link is convenient.
		"""
		if not doctype or not name or doctype not in LINK_PARENTS:
			return False, []
		key = (doctype, str(name))
		trail = set(trail or ())
		if key in trail:
			return False, []
		if key in self.resolved:
			return self.resolved[key]
		doc = self.read(doctype, name)
		if doc is None:
			return False, []
		if doctype in CRM_PARENTS:
			owner = doc.get("lead_owner" if doctype == "CRM Lead" else "deal_owner")
			result = True, [(doctype, str(name), owner)]
		else:
			trail.add(key)
			links = []
			if doc.get("reference_doctype") and doc.get("reference_docname"):
				links.append((doc.get("reference_doctype"), str(doc.get("reference_docname"))))
			if doctype == "CRM Call Log":
				links.extend(
					(link.get("link_doctype"), str(link.get("link_name")))
					for link in (doc.get("links") or [])
					if link.get("link_doctype") in CRM_PARENTS and link.get("link_name")
				)
			roots = []
			allowed = True
			for link_type, link_name in set(links):
				permitted, nested = self.resolve(link_type, link_name, trail)
				if not permitted:
					allowed = False
					break
				roots.extend(nested)
			result = allowed, sorted(set(roots)) if allowed else []
		self.resolved[key] = result
		return result


def _date_filters(field, start, end):
	# Database timestamps are naive local wall time, not UTC.
	return [
		[field, ">=", start.replace(tzinfo=None).isoformat(sep=" ")],
		[field, "<", end.replace(tzinfo=None).isoformat(sep=" ")],
	]


def _native_histories(frappe, reader, users, mode, start, end, warnings):
	for doctype in ("Version", "Comment"):
		ref_type, ref_name = REFERENCE_FIELDS[doctype]
		filters = [*_date_filters("creation", start, end), [ref_type, "in", sorted(HISTORY_PARENTS)]]
		if mode == "performed_by":
			filters.append(["owner", "in", users])
		if doctype == "Comment":
			filters.append(["comment_type", "=", "Comment"])
		# Only reference metadata is read here. Historical contents are never
		# fetched until the parent allowlist is established below.
		fields = ["name", "owner", "creation", ref_type, ref_name]
		candidates = defaultdict(set)
		for row in _iter_rows(frappe, doctype, fields, filters, native_history=True):
			if row.get(ref_type) in HISTORY_PARENTS and row.get(ref_name):
				candidates[row[ref_type]].add(str(row[ref_name]))
		for parent_type, names in candidates.items():
			names = sorted(names)
			for offset in range(0, len(names), BATCH_SIZE):
				parent_filters = [["name", "in", names[offset : offset + BATCH_SIZE]]]
				if mode == "owned_records" and parent_type in CRM_PARENTS:
					parent_filters.append(
						["lead_owner" if parent_type == "CRM Lead" else "deal_owner", "in", users]
					)
				try:
					parents = list(
						_iter_rows(frappe, parent_type, ["name"], parent_filters, sort_field="name")
					)
				except frappe.PermissionError:
					warnings.add(
						f"Activity on {parent_type} is unavailable with your current read permissions."
					)
					continue
				allowed_names = []
				for parent in parents:
					allowed, roots = reader.resolve(parent_type, str(parent["name"]))
					if allowed and (mode != "owned_records" or any(root[2] in users for root in roots)):
						allowed_names.append(str(parent["name"]))
				if not allowed_names:
					continue
				content_fields = fields + (["data"] if doctype == "Version" else ["content", "comment_type"])
				content_filters = [*filters, [ref_type, "=", parent_type], [ref_name, "in", allowed_names]]
				yield from (
					(doctype, row)
					for row in _iter_rows(
						frappe, doctype, content_fields, content_filters, native_history=True
					)
				)


def _independent_sources(frappe, reader, users, mode, start, end, warnings):
	for doctype in ("FCRM Note", "CRM Call Log", "CRM Task", "Communication"):
		ref_type, ref_name = REFERENCE_FIELDS[doctype]
		fields = ["name", "creation", "owner", ref_type, ref_name]
		field = {"CRM Call Log": "start_time", "Communication": "communication_date"}.get(doctype, "creation")
		queries = [_date_filters(field, start, end)]
		if field != "creation":
			fields.append(field)
			queries.append([*_date_filters("creation", start, end), [field, "is", "not set"]])
		for filters in queries:
			if mode == "performed_by" and doctype in ("FCRM Note", "CRM Task"):
				filters.append(["owner", "in", users])
			try:
				for row in _iter_rows(frappe, doctype, fields, filters, sort_field=field):
					# get_list respects list permissions; document hooks may be
					# stricter and must also authorize before reading content.
					doc = reader.read(doctype, row["name"])
					if doc is not None:
						yield doctype, doc
			except frappe.PermissionError:
				warnings.add(f"{doctype} activity is unavailable with your current read permissions.")


def get_activity(users, mode, page=1, page_size=30, end_date=None, kind="all"):
	"""Permission-aware entry point; caller is responsible for user-scope access."""
	if mode not in {"performed_by", "owned_records"}:
		raise ValueError("Activity mode must be performed_by or owned_records")
	if kind not in KIND_FILTERS:
		raise ValueError("Invalid activity type filter")
	if isinstance(page, bool) or isinstance(page_size, bool):
		raise ValueError("Invalid activity pagination")
	try:
		page, page_size = int(page), int(page_size)
	except (ValueError, TypeError):
		raise ValueError("Invalid activity pagination") from None
	if page < 1 or not 1 <= page_size <= 100:
		raise ValueError("Activity page must be positive and page size must be between 1 and 100")
	if (
		isinstance(users, str)
		or not isinstance(users, (list, tuple, set))
		or not all(isinstance(user, str) and user for user in users)
	):
		raise ValueError("Activity users must be an explicit list of User names")
	users = sorted(set(users))
	import frappe

	timezone = frappe.utils.get_system_timezone()
	start, end = calendar_window(end_date, timezone)
	warnings = set()
	if hasattr(frappe, "get_meta") and not frappe.get_meta("CRM Task").get("track_changes"):
		warnings.add(
			"Task change tracking is disabled; task history may be missing past changes and completions."
		)
	else:
		warnings.add(
			"Task history before tracking was enabled may be incomplete; past actions are not reconstructed."
		)
	reader = _Reader(frappe)
	events = {}
	if users:
		streams = (
			_native_histories(frappe, reader, users, mode, start, end, warnings),
			_independent_sources(frappe, reader, users, mode, start, end, warnings),
		)
		for stream in streams:
			for doctype, row in stream:
				event = normalize_source(doctype, row, timezone)
				if not event or not start <= _timestamp(event["timestamp"], timezone) < end:
					continue
				if kind != "all" and event["category"] != kind:
					continue
				if mode == "performed_by" and event["actor"] not in users:
					continue
				parent_type, parent_name = event["parent_doctype"], event["parent_name"]
				if doctype in {"CRM Task", "CRM Call Log", "FCRM Note"}:
					allowed, roots = reader.resolve(doctype, event["source_name"])
				elif parent_type and parent_name:
					allowed, roots = reader.resolve(parent_type, parent_name)
				else:
					allowed, roots = doctype == "Communication", []
				if not allowed or (mode == "owned_records" and not any(root[2] in users for root in roots)):
					continue
				if roots:
					# Prefer an owned matching CRM parent in owned-record scope;
					# all other links were already checked for effective read.
					root = next((root for root in roots if root[2] in users), roots[0])
					event["parent_doctype"], event["parent_name"] = root[:2]
					event["url"] = _url(*root[:2])
				events[event["id"]] = event
	ordered = sorted(
		events.values(),
		key=lambda event: (_timestamp(event["timestamp"], timezone), event["id"]),
		reverse=True,
	)
	total = len(ordered)
	page_events = ordered[(page - 1) * page_size : page * page_size]
	days = []
	for offset in range(7):
		day = (end.date() - timedelta(days=offset + 1)).isoformat()
		days.append(
			{
				"date": day,
				"total": sum(event["timestamp"][:10] == day for event in ordered),
				"events": [event for event in page_events if event["timestamp"][:10] == day],
			}
		)
	pagination = {
		"page": page,
		"page_size": page_size,
		"total": total,
		"total_pages": ceil(total / page_size),
		"has_next": page * page_size < total,
		"has_previous": page > 1,
	}
	return {
		"days": days,
		"events": page_events,
		"pagination": pagination,
		"page": page,
		"page_size": page_size,
		"total": total,
		"mode": mode,
		"kind": kind,
		"warnings": sorted(warnings),
		"window": {
			"start_date": start.date().isoformat(),
			"end_date": (end.date() - timedelta(days=1)).isoformat(),
			"start": start.date().isoformat(),
			"end": (end.date() - timedelta(days=1)).isoformat(),
			"timezone": timezone,
		},
	}
