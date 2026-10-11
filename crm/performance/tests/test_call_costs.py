import sys
import types
import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

fake = types.ModuleType("frappe")
fake.db = Mock()
fake.get_all = Mock()
with patch.dict(sys.modules, {"frappe": fake}):
	from crm.performance import call_costs


def leg(sid, price="-0.12", currency="USD", status="completed", parent=None):
	return types.SimpleNamespace(
		sid=sid, price=price, price_unit=currency, status=status, parent_call_sid=parent
	)


class CallCostTests(unittest.TestCase):
	def setUp(self):
		fake.PermissionError = PermissionError
		fake.get_all.reset_mock()
		fake.get_all.side_effect = None
		fake.db.get_value.return_value = None
		fake.db.exists.return_value = True

	def test_excluded_scheduler_batch_advances_without_provider_access(self):
		utils = types.ModuleType("frappe.utils")
		utils.now_datetime = Mock(return_value="2026-10-10 12:00:00")
		for malformed_sid in (True, False):
			with self.subTest(malformed_sid=malformed_sid):
				rows = [
					{
						"name": f"excluded-{i}",
						"id": "CAmalformed" if malformed_sid else "CA" + f"{i:032x}",
						"caller": "removed-role",
						"type": "Outgoing",
						"telephony_medium": "Twilio",
					}
					for i in range(call_costs.BATCH_SIZE)
				]
				with (
					patch.object(call_costs, "frappe", fake),
					patch.object(call_costs, "is_crm_caller", return_value=False),
					patch.dict(sys.modules, {"frappe.utils": utils}),
				):
					fake.db.set_value.reset_mock()
					fake.db.get_single_value.return_value = True
					fake.get_all.return_value = rows
					call_costs.reconcile_pending_costs()
					self.assertEqual(fake.db.set_value.call_count, call_costs.BATCH_SIZE)
					for call in fake.db.set_value.call_args_list:
						self.assertEqual(call.args[2], {"voice_cost_checked_at": "2026-10-10 12:00:00"})
						self.assertFalse(call.kwargs["update_modified"])

	def test_parent_and_children_are_deduplicated_actual_charges(self):
		result = call_costs.calculate_cost([leg("parent"), leg("child", "-0.3"), leg("child", "-0.3")])
		self.assertEqual(result["amount"], Decimal("0.42"))
		self.assertEqual(result["status"], "Complete")
		self.assertEqual(result["leg_count"], 2)

	def test_null_browser_parent_with_billed_child_is_partial_not_complete(self):
		result = call_costs.calculate_cost([leg("parent", None), leg("child")])
		self.assertEqual(result["status"], "Partial")
		self.assertEqual(result["amount"], Decimal("0.12"))
		self.assertEqual(result["pending_legs"], 1)

	def test_explicit_zero_is_complete_but_missing_price_is_pending(self):
		self.assertEqual(call_costs.calculate_cost([leg("parent", "0")])["status"], "Complete")
		result = call_costs.calculate_cost([leg("parent", None)])
		self.assertIsNone(result["amount"])
		self.assertEqual(result["status"], "Pending")

	def test_unfinished_or_invalid_prices_are_pending_and_no_nan(self):
		for value, status in [
			("NaN", "completed"),
			("Infinity", "completed"),
			("-0.2", "in-progress"),
			("bad", "completed"),
		]:
			self.assertEqual(
				call_costs.calculate_cost([leg("parent", value, status=status)])["status"], "Pending"
			)

	def test_mixed_currency_never_sums_unlike_currencies(self):
		result = call_costs.calculate_cost([leg("parent"), leg("child", currency="GBP")])
		self.assertIsNone(result["amount"])
		self.assertEqual(result["status"], "Unsupported Currency")

	def test_incomplete_leg_discovery_does_not_confirm_total(self):
		self.assertEqual(
			call_costs.calculate_cost([leg("parent")], discovery_complete=False)["status"], "Partial"
		)

	def test_eligibility_excludes_other_providers_incoming_and_missing_identity(self):
		base = {
			"telephony_medium": "Twilio",
			"type": "Outgoing",
			"caller": "rep@example.com",
			"id": "CA" + "a" * 32,
		}
		self.assertTrue(call_costs.is_platform_call(base))
		for field, value in [
			("telephony_medium", "Bland"),
			("type", "Incoming"),
			("caller", ""),
			("id", "not-a-sid"),
		]:
			self.assertFalse(call_costs.is_platform_call({**base, field: value}))

	def test_summary_exposes_only_aggregate_usd_and_pending_warning(self):
		rows = [
			{"voice_cost_status": "Complete", "voice_cost_amount": "0.2", "voice_cost_currency": "USD"},
			{"voice_cost_status": "Partial", "voice_cost_amount": "0.1", "voice_cost_currency": "USD"},
			{"voice_cost_status": "Complete", "voice_cost_amount": "1", "voice_cost_currency": "GBP"},
			{"voice_cost_status": None},
		]
		result = call_costs.summarize_costs(rows)
		self.assertEqual(result["confirmed_amount"], 0.2)
		self.assertEqual(result["known_partial_amount"], 0.1)
		self.assertEqual(result["pending_calls"], 2)
		self.assertEqual(result["non_usd_calls"], 1)
		self.assertEqual(result["currency"], "USD")
		self.assertFalse(result["complete"])

	def test_provider_error_stores_safe_code_never_exception_payload(self):
		doc = {
			"name": "log",
			"telephony_medium": "Twilio",
			"type": "Outgoing",
			"caller": "rep@example.com",
			"id": "CA" + "a" * 32,
		}
		client = Mock()
		client.calls.side_effect = Exception("credential and provider payload must not escape")
		with patch.object(call_costs, "frappe", fake):
			fake.db.reset_mock()
			result = call_costs.reconcile_call(doc, client, now="2026-10-10 12:00:00")
			self.assertEqual(result["status"], "Error")
			self.assertNotIn("credential", str(fake.db.set_value.call_args))

	def test_fetch_children_requires_parent_link_and_flags_overflow(self):
		client = Mock()
		parent_sid = "CA" + "a" * 32
		client.calls.return_value.fetch.return_value = leg(parent_sid)
		client.calls.list.side_effect = [
			[leg("child", parent=parent_sid), leg("unrelated", parent="other")],
			[],
		]
		result = call_costs.fetch_cost(client, parent_sid)
		self.assertEqual(result["status"], "Partial")
		self.assertEqual(result["amount"], Decimal("0.24"))
		self.assertEqual(
			client.calls.list.call_args_list[0].kwargs,
			{"parent_call_sid": parent_sid, "limit": call_costs.MAX_CHILD_LEGS + 1},
		)

	def test_non_crm_caller_never_fetches_or_writes_cost(self):
		call = {
			"name": "log",
			"telephony_medium": "Twilio",
			"type": "Outgoing",
			"caller": "outsider",
			"id": "CA" + "a" * 32,
		}
		client = Mock()
		with patch.object(call_costs, "frappe", fake):
			fake.db.reset_mock()
			fake.db.exists.return_value = False
			self.assertEqual(
				call_costs.reconcile_call(call, client, now="2026-10-10 12:00:00")["status"], "Excluded"
			)
			client.calls.assert_not_called()
			fake.db.set_value.assert_not_called()
			fake.db.exists.return_value = True

	def test_summary_applies_db_bounds_and_excludes_non_crm_identity(self):
		with (
			patch.object(call_costs, "frappe", fake),
			patch.object(call_costs, "is_crm_caller", side_effect=lambda caller: caller == "rep"),
		):
			fake.get_all.return_value = [
				{
					"id": "CA" + "a" * 32,
					"caller": "rep",
					"voice_cost_status": "Complete",
					"voice_cost_amount": "0.1",
					"voice_cost_currency": "USD",
				},
				{
					"id": "CA" + "b" * 32,
					"caller": "outsider",
					"voice_cost_status": "Complete",
					"voice_cost_amount": "50",
					"voice_cost_currency": "USD",
				},
			]
			result = call_costs.get_cost_summary("2026-10-01", "2026-11-01")
			self.assertEqual(result["confirmed_amount"], 0.1)
			filters = fake.get_all.call_args_list[0].kwargs["filters"]
			self.assertIn(["start_time", ">=", "2026-10-01"], filters)
			self.assertIn(["start_time", "<", "2026-11-01"], filters)

	def test_parent_identity_must_match_crm_caller(self):
		client = Mock()
		sid = "CA" + "a" * 32
		parent = leg(sid)
		parent._from = "client:other(at)example.com"
		client.calls.return_value.fetch.return_value = parent
		with self.assertRaises(ValueError):
			call_costs.fetch_cost(client, sid, caller="rep@example.com")
		client.calls.list.assert_not_called()

	def test_duplicate_conflicting_price_observations_are_not_complete(self):
		self.assertEqual(
			call_costs.calculate_cost([leg("parent"), leg("parent", "-0.5")])["status"], "Partial"
		)

	def test_schema_fields_are_readonly_and_patch_updates_existing_fields(self):
		from crm.patches.v1_0.performance_call_costs import cost_fields

		self.assertEqual({field["fieldname"] for field in cost_fields()}, set(call_costs.COST_FIELDS))
		self.assertTrue(all(field["read_only"] and field["no_copy"] for field in cost_fields()))

	def test_child_bound_reports_known_sum_as_partial(self):
		client = Mock()
		sid = "CA" + "a" * 32
		client.calls.return_value.fetch.return_value = leg(sid)
		client.calls.list.side_effect = [
			[leg(str(i), parent=sid) for i in range(call_costs.MAX_CHILD_LEGS + 1)]
		] + [[]] * call_costs.MAX_CHILD_LEGS
		result = call_costs.fetch_cost(client, sid)
		self.assertEqual(result["status"], "Partial")
		self.assertEqual(result["amount"], Decimal("0.12") * (call_costs.MAX_CHILD_LEGS + 1))
		self.assertEqual(client.calls.list.call_count, call_costs.MAX_CHILD_LEGS + 1)

	def test_nonamount_states_never_show_currency_default_zero(self):
		base = {
			"telephony_medium": "Twilio",
			"type": "Outgoing",
			"caller": "rep",
			"id": "CA" + "a" * 32,
			"voice_cost_amount": 0,
			"voice_cost_currency": "Mixed",
		}
		with patch.object(call_costs, "is_crm_caller", return_value=True):
			for status in ("Error", "Pending", "Unsupported Currency"):
				self.assertIsNone(call_costs.get_call_cost({**base, "voice_cost_status": status})["amount"])

	def test_normal_document_saves_cannot_override_cost_metadata(self):
		doc = types.SimpleNamespace(
			voice_cost_amount=55,
			get_doc_before_save=lambda: types.SimpleNamespace(voice_cost_amount=1, get_value=lambda field: 1),
			has_value_changed=lambda field: field == "voice_cost_amount",
			get_value=lambda field: 55,
		)
		with patch.object(call_costs, "frappe", fake):
			fake.PermissionError = PermissionError
			fake.throw = Mock(side_effect=PermissionError)
			with self.assertRaises(PermissionError):
				call_costs.protect_cost_fields(doc)

	def test_json_datetime_roundtrip_delegates_to_native_typed_change_detection(self):
		values = {field: None for field in call_costs.COST_FIELDS}
		values["voice_cost_checked_at"] = datetime(2026, 10, 10, 12, 0, 0)
		previous = types.SimpleNamespace(**values)
		doc = types.SimpleNamespace(
			**{**values, "voice_cost_checked_at": "2026-10-10 12:00:00"},
			get_doc_before_save=lambda: previous,
			has_value_changed=Mock(return_value=False),
		)
		with patch.object(call_costs, "frappe", fake):
			fake.throw = Mock(side_effect=PermissionError)
			call_costs.protect_cost_fields(doc)
			fake.throw.assert_not_called()
			doc.has_value_changed.assert_any_call("voice_cost_checked_at")

	def test_numeric_string_roundtrip_uses_native_field_casting(self):
		previous = types.SimpleNamespace(voice_cost_amount=0.125, get_value=lambda field: 0.125)
		doc = types.SimpleNamespace(
			voice_cost_amount="0.125",
			get_doc_before_save=lambda: previous,
			has_value_changed=lambda field: field == "voice_cost_amount",
			get_value=lambda field: 0.125,
		)
		with patch.object(call_costs, "frappe", fake):
			fake.throw = Mock(side_effect=PermissionError)
			call_costs.protect_cost_fields(doc)
			fake.throw.assert_not_called()

	def test_transient_provider_error_preserves_known_partial_amount(self):
		call = {
			"name": "log",
			"telephony_medium": "Twilio",
			"type": "Outgoing",
			"caller": "rep",
			"id": "CA" + "a" * 32,
		}
		client = Mock()
		client.calls.side_effect = RuntimeError("provider secret payload")
		with (
			patch.object(call_costs, "frappe", fake),
			patch.object(call_costs, "is_crm_caller", return_value=True),
		):
			fake.db.get_value.return_value = {
				"voice_cost_status": "Partial",
				"voice_cost_amount": "0.25",
				"voice_cost_currency": "USD",
				"voice_cost_leg_count": 2,
				"voice_cost_pending_legs": 1,
			}
			result = call_costs.reconcile_call(call, client, now="2026-10-10 12:00:00")
			self.assertEqual(result["status"], "Partial")
			self.assertEqual(result["amount"], Decimal("0.25"))
			self.assertEqual(fake.db.set_value.call_args.args[2]["voice_cost_error"], "provider_unavailable")
			fake.db.get_value.return_value = None

	def test_creation_fallback_is_only_for_missing_start_and_keeps_exclusive_end(self):
		with (
			patch.object(call_costs, "frappe", fake),
			patch.object(call_costs, "is_crm_caller", return_value=True),
		):
			fake.get_all.reset_mock()
			fake.get_all.side_effect = [
				[],
				[{"id": "CA" + "a" * 32, "caller": "rep", "voice_cost_status": "Pending"}],
			]
			result = call_costs.get_cost_summary("2026-10-01", "2026-11-01")
			self.assertEqual(result["pending_calls"], 1)
			filters = fake.get_all.call_args.kwargs["filters"]
			self.assertIn(["start_time", "is", "not set"], filters)
			self.assertIn(["creation", ">=", "2026-10-01"], filters)
			self.assertIn(["creation", "<", "2026-11-01"], filters)
			fake.get_all.side_effect = None


if __name__ == "__main__":
	unittest.main()
