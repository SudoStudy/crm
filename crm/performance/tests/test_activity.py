"""Activity normalization and effective-permission tests without a running site."""

import json
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from crm.performance.activity import calendar_window, get_activity, normalize_source

REP = "rep@example.com"
OTHER = "other@example.com"


def source(name, **values):
	return {"name": name, "creation": "2026-10-07 12:00:00", "owner": REP, **values}


class Transport:
	"""Small Frappe transport fake: implements query filters, document reads, permissions."""

	PermissionError = PermissionError
	DoesNotExistError = LookupError

	def __init__(self, rows=None, docs=None, denied=None, denied_types=None):
		self.rows = rows or {}
		self.docs = docs or {}
		self.denied = denied or set()
		self.denied_types = denied_types or set()
		self.queries = []
		self.history_queries = []
		self.reads = []
		self.session = SimpleNamespace(user=REP)
		self.utils = SimpleNamespace(get_system_timezone=lambda: "Asia/Karachi")

	def has_permission(self, doctype, ptype="read", doc=None, **kwargs):
		name = doc if isinstance(doc, str) else (doc or {}).get("name")
		return doctype not in self.denied_types and (doctype, name) not in self.denied

	def get_list(self, doctype, *, fields, filters, order_by, limit_start=0, limit_page_length=20, **kwargs):
		self.queries.append((doctype, fields, filters, order_by, limit_start, limit_page_length))
		if doctype in self.denied_types:
			raise PermissionError(doctype)
		rows = list(self.rows.get(doctype, []))
		rows.extend(doc for (doc_type, _), doc in self.docs.items() if doc_type == doctype)
		rows = [row for row in rows if self.matches(row, filters)]
		field = order_by.split()[0]
		rows.sort(key=lambda row: (str(row.get(field) or ""), str(row["name"])))
		return [
			{field: row.get(field) for field in fields}
			for row in rows[limit_start : limit_start + limit_page_length]
		]

	def get_all(self, doctype, *, fields, filters, order_by, limit_start=0, limit_page_length=20, **kwargs):
		self.history_queries.append((doctype, fields, filters, order_by, limit_start, limit_page_length))
		rows = [row for row in self.rows.get(doctype, []) if self.matches(row, filters)]
		field = order_by.split()[0]
		rows.sort(key=lambda row: (str(row.get(field) or ""), str(row["name"])))
		return [
			{field: row.get(field) for field in fields}
			for row in rows[limit_start : limit_start + limit_page_length]
		]

	def get_doc(self, doctype, name):
		self.reads.append((doctype, name))
		if (doctype, name) in self.docs:
			return self.docs[(doctype, name)]
		for row in self.rows.get(doctype, []):
			if str(row["name"]) == str(name):
				return row
		raise LookupError(name)

	@staticmethod
	def matches(row, filters):
		for field, op, expected in filters:
			value = row.get(field)
			if op == "=" and value != expected:
				return False
			if op == "in" and value not in expected:
				return False
			if op == "is" and expected == "not set" and value not in (None, ""):
				return False
			if op in (">=", "<"):
				if (
					value is None
					or (op == ">=" and str(value) < expected)
					or (op == "<" and str(value) >= expected)
				):
					return False
		return True


class NormalizationTests(unittest.TestCase):
	def test_seven_site_calendar_days_and_aware_timestamp(self):
		start, end = calendar_window("2026-10-07", "Asia/Karachi")
		self.assertEqual(start.isoformat(), "2026-10-01T00:00:00+05:00")
		self.assertEqual(end.isoformat(), "2026-10-08T00:00:00+05:00")
		row = source(
			"call", type="Outgoing", caller=REP, start_time=datetime(2026, 10, 6, 20, tzinfo=timezone.utc)
		)
		event = normalize_source("CRM Call Log", row, "Asia/Karachi")
		self.assertEqual(event["timestamp"], "2026-10-07T01:00:00+05:00")

	def test_call_actor_is_caller_or_receiver_never_webhook_owner(self):
		for direction, field in (("Outgoing", "caller"), ("Incoming", "receiver")):
			event = normalize_source(
				"CRM Call Log",
				source(
					"call",
					type=direction,
					owner="Administrator",
					**{field: REP},
					recording_url="secret recording",
				),
			)
			self.assertEqual(event["actor"], REP)
			self.assertNotIn("recording", json.dumps(event))
		unknown = normalize_source("CRM Call Log", source("unknown", type="Outgoing", owner=REP))
		self.assertIsNone(unknown["actor"])

	def test_task_completed_history_uses_version_actor_and_creation(self):
		row = source(
			"version",
			ref_doctype="CRM Task",
			docname="task",
			owner=OTHER,
			data=json.dumps({"changed": [["status", "Todo", "Done"], ["priority", "Low", "High"]]}),
		)
		event = normalize_source("Version", row)
		self.assertEqual(event["kind"], "task_completed")
		self.assertEqual(event["actor"], OTHER)
		self.assertEqual(event["parent_doctype"], "CRM Task")
		self.assertEqual(len(event["details"]["changes"]), 2)

	def test_creation_is_not_invented_completion_from_current_status_or_modified(self):
		event = normalize_source("CRM Task", source("task", status="Done", modified="2026-10-07 13:00:00"))
		self.assertEqual(event["kind"], "task_created")
		self.assertEqual(event["timestamp"], "2026-10-07T12:00:00+00:00")

	def test_derived_noise_and_malformed_versions_are_hidden(self):
		for data in (
			"{broken",
			json.dumps(
				{
					"changed": [
						["last_activity_at", "a", "b"],
						["next_action_date", "a", "b"],
						["first_response_time", 0, 1],
					]
				}
			),
			json.dumps({"changed": "invalid"}),
		):
			self.assertIsNone(
				normalize_source("Version", source("v", ref_doctype="CRM Deal", docname="deal", data=data))
			)
		self.assertIsNone(
			normalize_source("Comment", source("system", comment_type="Info", content="status changed"))
		)

	def test_zero_values_are_preserved_in_change_details(self):
		event = normalize_source(
			"Version",
			source(
				"v",
				ref_doctype="CRM Deal",
				docname="deal",
				data=json.dumps({"changed": [["deal_value", 0, 50]]}),
			),
		)
		self.assertEqual(event["details"]["changes"][0]["old_value"], "0")

	def test_calendar_window_handles_dst_without_fixed_168_hour_assumption(self):
		start, end = calendar_window("2026-11-07", "America/Los_Angeles")
		self.assertEqual(
			(end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds(), 169 * 3600
		)

	def test_comments_and_notes_return_plain_text_not_html(self):
		event = normalize_source(
			"Comment",
			source(
				"comment", comment_type="Comment", content="<p>Hello <b>team</b></p><script>bad()</script>"
			),
		)
		self.assertEqual(event["summary"], "Hello team")
		self.assertNotIn("<", event["summary"])


class ActivityServiceTests(unittest.TestCase):
	def get(self, transport, users=None, mode="performed_by", **kwargs):
		with patch.dict(sys.modules, {"frappe": transport}):
			return get_activity(users or [REP], mode, end_date="2026-10-07", **kwargs)

	def test_parent_and_source_effective_read_both_required(self):
		rows = {
			"FCRM Note": [
				source("hidden-parent", reference_doctype="CRM Deal", reference_docname="deal"),
				source("hidden-source", reference_doctype="CRM Deal", reference_docname="open"),
			]
		}
		docs = {
			("CRM Deal", "deal"): {"name": "deal", "deal_owner": REP},
			("CRM Deal", "open"): {"name": "open", "deal_owner": REP},
		}
		transport = Transport(rows, docs, denied={("CRM Deal", "deal"), ("FCRM Note", "hidden-source")})
		self.assertEqual(self.get(transport)["total"], 0)
		self.assertNotIn(("CRM Deal", "deal"), transport.reads)

	def test_task_reference_requires_task_and_ultimate_parent_permission(self):
		rows = {
			"Comment": [
				source(
					"comment",
					comment_type="Comment",
					reference_doctype="CRM Task",
					reference_name="task",
					content="private",
				)
			]
		}
		docs = {
			("CRM Task", "task"): {
				"name": "task",
				"reference_doctype": "CRM Lead",
				"reference_docname": "lead",
			},
			("CRM Lead", "lead"): {"name": "lead", "lead_owner": REP},
		}
		denied = Transport(rows, docs, denied={("CRM Lead", "lead")})
		self.assertEqual(self.get(denied)["total"], 0)
		allowed = self.get(Transport(rows, docs))
		self.assertEqual(allowed["total"], 1)
		self.assertEqual(allowed["events"][0]["parent_doctype"], "CRM Lead")

	def test_performer_scope_differs_from_current_record_owner(self):
		rows = {
			"FCRM Note": [
				source("mine", reference_doctype="CRM Deal", reference_docname="their-deal"),
				source("theirs", owner=OTHER, reference_doctype="CRM Deal", reference_docname="my-deal"),
			]
		}
		docs = {
			("CRM Deal", "their-deal"): {"name": "their-deal", "deal_owner": OTHER},
			("CRM Deal", "my-deal"): {"name": "my-deal", "deal_owner": REP},
		}
		self.assertEqual([e["source_name"] for e in self.get(Transport(rows, docs))["events"]], ["mine"])
		owned = self.get(Transport(rows, docs), mode="owned_records")
		self.assertEqual([e["source_name"] for e in owned["events"]], ["theirs"])

	def test_source_batches_and_global_pages_have_no_truncation_or_tie_duplication(self):
		rows = {
			"FCRM Note": [
				source(f"note-{i:04d}", reference_doctype="CRM Lead", reference_docname="lead")
				for i in range(425)
			]
		}
		docs = {("CRM Lead", "lead"): {"name": "lead", "lead_owner": REP}}
		transport = Transport(rows, docs)
		first = self.get(transport, page=1, page_size=100)
		last = self.get(transport, page=5, page_size=100)
		self.assertEqual(first["total"], 425)
		self.assertEqual(len(last["events"]), 25)
		self.assertFalse(last["pagination"]["has_next"])
		self.assertTrue(first["pagination"]["has_next"])
		self.assertTrue(set(e["id"] for e in first["events"]).isdisjoint(e["id"] for e in last["events"]))
		self.assertEqual(len(first["days"]), 7)
		self.assertEqual(first["days"][0]["total"], 425)
		self.assertTrue(
			all(
				any(f[0] == "name" and f[1] == "in" for f in query[2])
				for query in transport.queries
				if query[0] in ("CRM Lead", "CRM Deal")
			)
		)
		self.assertTrue(all("name asc" in query[3] for query in transport.queries))

	def test_calls_use_actual_start_time_and_exclude_integrator_owned_events(self):
		rows = {
			"CRM Call Log": [
				source(
					"in-window",
					creation="2026-09-30 12:00:00",
					start_time="2026-10-07 12:00:00",
					type="Outgoing",
					caller=REP,
					owner="Administrator",
				),
				source("old", start_time="2026-09-30 12:00:00", type="Outgoing", caller=REP),
				source("unknown", type="Outgoing", owner=REP),
			]
		}
		self.assertEqual([e["source_name"] for e in self.get(Transport(rows))["events"]], ["in-window"])

	def test_day_boundaries_include_start_and_exclude_next_midnight(self):
		rows = {
			"CRM Task": [
				source("start", creation="2026-10-01 00:00:00"),
				source("end", creation="2026-10-07 23:59:59"),
				source("outside", creation="2026-10-08 00:00:00"),
			]
		}
		result = self.get(Transport(rows))
		self.assertEqual(result["total"], 2)
		self.assertEqual(result["window"]["timezone"], "Asia/Karachi")

	def test_source_permission_denial_is_visible_as_warning(self):
		result = self.get(Transport(denied_types={"Communication"}))
		self.assertTrue(any("Communication" in warning for warning in result["warnings"]))

	def test_native_histories_are_parent_authorized_without_history_role_escalation(self):
		rows = {
			"Version": [
				source(
					"v",
					ref_doctype="CRM Deal",
					docname="deal",
					data=json.dumps({"changed": [["status", "New", "Won"]]}),
				)
			],
			"Comment": [
				source(
					"c",
					comment_type="Comment",
					reference_doctype="CRM Deal",
					reference_name="deal",
					content="New comment on an old deal",
				)
			],
		}
		docs = {("CRM Deal", "deal"): {"name": "deal", "deal_owner": REP, "modified": "2025-01-01 00:00:00"}}
		transport = Transport(rows, docs, denied_types={"Version", "Comment"})
		self.assertEqual(self.get(transport)["total"], 2)
		for _doctype, fields, filters, *_ in transport.history_queries:
			if "data" in fields or "content" in fields:
				self.assertTrue(any(f[0] in ("docname", "reference_name") and f[1] == "in" for f in filters))
		self.assertTrue(all(query[0] not in ("Version", "Comment") for query in transport.queries))

	def test_hidden_parent_history_content_is_never_loaded(self):
		rows = {
			"Comment": [
				source(
					"c",
					comment_type="Comment",
					reference_doctype="CRM Deal",
					reference_name="private",
					content="secret",
				)
			]
		}
		docs = {("CRM Deal", "private"): {"name": "private", "deal_owner": REP}}
		transport = Transport(rows, docs, denied={("CRM Deal", "private")})
		self.assertEqual(self.get(transport)["total"], 0)
		self.assertTrue(all("content" not in query[1] for query in transport.history_queries))

	def test_kind_filter_is_applied_before_totals_and_pagination(self):
		rows = {"CRM Task": [source("task")], "CRM Call Log": [source("call", type="Outgoing", caller=REP)]}
		result = self.get(Transport(rows), kind="call")
		self.assertEqual(result["total"], 1)
		self.assertEqual(result["events"][0]["source_name"], "call")
		self.assertEqual(result["days"][0]["total"], 1)

	def test_task_filter_includes_historical_noncompletion_changes(self):
		rows = {
			"Version": [
				source(
					"version",
					ref_doctype="CRM Task",
					docname="task",
					data=json.dumps({"changed": [["priority", "Low", "High"]]}),
				)
			]
		}
		docs = {
			("CRM Task", "task"): {
				"name": "task",
				"reference_doctype": "CRM Deal",
				"reference_docname": "deal",
			},
			("CRM Deal", "deal"): {"name": "deal", "deal_owner": REP},
		}
		result = self.get(Transport(rows, docs), kind="task")
		self.assertEqual(result["total"], 1)
		self.assertEqual(result["events"][0]["category"], "task")

	def test_disabled_task_tracking_is_explicit_and_not_reconstructed(self):
		transport = Transport(
			{
				"CRM Task": [
					source(
						"task", creation="2026-09-15 00:00:00", status="Done", modified="2026-10-07 12:00:00"
					)
				]
			}
		)
		transport.get_meta = lambda doctype: {"track_changes": False}
		result = self.get(transport)
		self.assertEqual(result["total"], 0)
		self.assertTrue(any("Task" in warning and "history" in warning for warning in result["warnings"]))

	def test_invalid_modes_and_pagination_fail_before_transport(self):
		for kwargs in ({"mode": "all"}, {"page": 0}, {"page_size": 0}, {"page_size": 101}):
			with self.assertRaises(ValueError):
				get_activity([REP], **{"mode": "performed_by", **kwargs})


if __name__ == "__main__":
	unittest.main()
