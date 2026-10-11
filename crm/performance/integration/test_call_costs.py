"""Disposable native DB checks, never contact Twilio.

Run: bench --site test_site run-tests --module crm.performance.integration.test_call_costs
"""

import json
from unittest.mock import Mock
from uuid import uuid4

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from crm.patches.v1_0.performance_call_costs import execute as apply_schema
from crm.performance.call_costs import COST_FIELDS, get_cost_summary, reconcile_call


class TestNativeCallCosts(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		if frappe.local.site != "test_site":
			raise RuntimeError("Call cost integration checks require disposable test_site")
		super().setUpClass()
		frappe.set_user("Administrator")
		apply_schema()
		apply_schema()  # existing custom fields must remain idempotent

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		self.rep = "call-cost-test-" + uuid4().hex + "@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": self.rep,
				"first_name": "Cost test",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Sales User"}],
			}
		).insert(ignore_permissions=True)
		self.sid = "CA" + uuid4().hex
		self.call = frappe.get_doc(
			{
				"doctype": "CRM Call Log",
				"id": self.sid,
				"telephony_medium": "Twilio",
				"type": "Outgoing",
				"caller": self.rep,
				"status": "Completed",
				"from": "+10000000000",
				"to": "+10000000001",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"CRM Call Log",
			self.call.name,
			{"creation": "2040-01-05 12:00:00", "start_time": None},
			update_modified=False,
		)

	def test_schema_is_readonly_and_saved_cost_fields_reject_normal_edits(self):
		meta = frappe.get_meta("CRM Call Log")
		for field in COST_FIELDS:
			self.assertTrue(meta.get_field(field).read_only)
			self.assertEqual(len([df for df in meta.fields if df.fieldname == field]), 1)
		self.call.voice_cost_amount = 55
		with self.assertRaises(frappe.PermissionError):
			self.call.save(ignore_permissions=True)

	def test_reconciliation_keeps_decimal_child_cost_pending_parent_and_is_idempotent(self):
		from twilio.rest.api.v2010.account.call import CallInstance

		account_sid = "AC" + "b" * 32
		parent = CallInstance(
			Mock(),
			{
				"sid": self.sid,
				"account_sid": account_sid,
				"from": "client:" + self.rep.replace("@", "(at)"),
				"parent_call_sid": None,
				"price": None,
				"price_unit": "USD",
				"status": "completed",
			},
			account_sid=account_sid,
		)
		child = CallInstance(
			Mock(),
			{
				"sid": "CA" + uuid4().hex,
				"account_sid": account_sid,
				"parent_call_sid": self.sid,
				"price": "-0.125",
				"price_unit": "USD",
				"status": "completed",
			},
			account_sid=account_sid,
		)
		self.assertTrue(hasattr(parent, "_from"))
		self.assertFalse(hasattr(parent, "from_"))
		client = Mock()
		client.calls.return_value.fetch.return_value = parent
		client.calls.list.side_effect = [[child, child], [], [child], []]
		reconcile_call(self.call, client)
		reconcile_call(self.call, client)
		self.call.reload()
		self.assertEqual(self.call.voice_cost_status, "Partial")
		self.assertAlmostEqual(self.call.voice_cost_amount, 0.125, places=6)
		self.assertEqual(self.call.voice_cost_pending_legs, 1)
		# Full browser documents round-trip datetimes through JSON strings. Editing
		# an unrelated field must keep native typed cost metadata comparisons equal.
		roundtripped = frappe.get_doc(json.loads(frappe.as_json(self.call)))
		roundtripped.duration = 12
		roundtripped.voice_cost_amount = "0.125"
		roundtripped.save(ignore_permissions=True)
		roundtripped.voice_cost_amount = 55
		with self.assertRaises(frappe.PermissionError):
			roundtripped.save(ignore_permissions=True)
		summary = get_cost_summary("2040-01-01", "2040-02-01")
		self.assertGreaterEqual(summary["known_partial_amount"], 0.125)
		self.assertFalse(summary["complete"])

	def test_creation_fallback_has_exclusive_end_and_actual_start_precedence(self):
		before = get_cost_summary("2040-01-01", "2040-02-01")["call_count"]
		frappe.db.set_value(
			"CRM Call Log", self.call.name, "creation", "2040-02-01 00:00:00", update_modified=False
		)
		self.assertEqual(get_cost_summary("2040-01-01", "2040-02-01")["call_count"], before - 1)
		frappe.db.set_value(
			"CRM Call Log", self.call.name, "start_time", "2040-01-31 23:59:59", update_modified=False
		)
		self.assertEqual(get_cost_summary("2040-01-01", "2040-02-01")["call_count"], before)
