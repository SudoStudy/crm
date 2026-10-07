import sys
import types
import unittest
from unittest.mock import Mock, patch

fake = types.ModuleType("frappe")
fake.get_list = Mock(return_value=[])
fake.db = Mock()
fake.get_doc = Mock()
fake.has_permission = Mock(return_value=True)
with patch.dict(sys.modules, {"frappe": fake}):
	from crm.performance import targets


class TargetTests(unittest.TestCase):
	def test_explicit_month_overrides_latest_applicable_rule(self):
		rows = [
			{"salesperson": "rep", "target_month": "2026-10-01", "currency": "USD", "target_new_mrr": 450}
		]
		rules = [
			{"salesperson": "rep", "effective_month": "2026-09-01", "currency": "USD", "target_new_mrr": 300}
		]
		result, warnings = targets.resolve_targets(
			["rep"], ["2026-09-01", "2026-10-01", "2026-11-01"], rows, rules
		)
		self.assertEqual([row["amount"] for row in result], [300, 450, 300])
		self.assertEqual(warnings, [])

	def test_rule_does_not_backfill_before_effective_month(self):
		rules = [
			{"salesperson": "rep", "effective_month": "2026-10-01", "currency": "USD", "target_new_mrr": 300}
		]
		result, _ = targets.resolve_targets(["rep"], ["2026-09-01"], [], rules)
		self.assertIsNone(result[0]["amount"])

	def test_team_requires_target_for_every_rep_and_currency_is_not_converted(self):
		rows = [
			{"salesperson": "a", "target_month": "2026-10-01", "currency": "PKR", "target_new_mrr": 84000}
		]
		result, warnings = targets.resolve_targets(["a", "b"], ["2026-10-01"], rows, [])
		self.assertIsNone(result[0]["amount"])
		self.assertTrue(any("currency" in warning for warning in warnings))

	def test_duplicate_legacy_rows_report_instead_of_double_counting(self):
		rows = [
			{"salesperson": "rep", "target_month": "2026-10-01", "currency": "USD", "target_new_mrr": 300}
		] * 2
		result, warnings = targets.resolve_targets(["rep"], ["2026-10-01"], rows, [])
		self.assertIsNone(result[0]["amount"])
		self.assertTrue(warnings)

	def test_write_validation_precedes_lock_and_explicit_month(self):
		for amount in ("NaN", "Infinity", -1, "1e999", "10000000000000"):
			with self.assertRaises(ValueError):
				targets.save_target("rep", "2026-10-01", amount, True)
		with self.assertRaises(ValueError):
			targets.save_target("rep", "2026-10-04", 300, True)
		with self.assertRaises(ValueError):
			targets.save_target("rep", "2026-10-01garbage", 300, True)

	def test_target_amount_rounds_usd_cents_before_persistence(self):
		with patch.object(targets, "frappe") as f:
			f.get_list.return_value = []
			f.db.get_values.return_value = []
			result = targets.save_target("rep", "2026-10-01", "300.005", False)
			self.assertEqual(result["amount"], 300.01)
			self.assertEqual(f.get_doc.return_value.target_new_mrr, 300.01)

	def test_target_uniqueness_check_is_not_hidden_by_list_permissions(self):
		with patch.object(targets, "frappe") as f:
			f.get_list.return_value = []
			f.db.get_values.return_value = [{"name": "legacy"}, {"name": "duplicate"}]
			with self.assertRaises(ValueError):
				targets.save_target("rep", "2026-10-01", 400, False)
			f.get_doc.assert_not_called()

	def test_recurring_write_changes_only_explicit_effective_month(self):
		with patch.object(targets, "frappe") as f:
			f.utils.nowdate.return_value = "2026-10-07"
			f.get_list.return_value = []
			f.db.get_values.return_value = []
			targets.save_target("rep", "2026-10-01", 400, True)
			values = [call.args[0] for call in f.get_doc.call_args_list]
			self.assertEqual(
				[(row["doctype"], row.get("target_month") or row.get("effective_month")) for row in values],
				[("CRM Sales Target", "2026-10-01"), ("CRM Sales Target Rule", "2026-10-01")],
			)
			f.db.set_value.assert_not_called()

	def test_recurring_rule_rejects_past_month_before_lock_or_writes(self):
		with patch.object(targets, "frappe") as f:
			f.utils.nowdate.return_value = "2026-10-07"
			with self.assertRaisesRegex(ValueError, "current or a future month"):
				targets.save_target("rep", "2026-09-01", 400, True)
			f.db.get_value.assert_not_called()
			f.get_doc.assert_not_called()

	def test_current_future_rules_and_explicit_historical_target_edits_allowed(self):
		for month, recurring in (("2026-10-01", True), ("2026-11-01", True), ("2026-09-01", False)):
			with patch.object(targets, "frappe") as f:
				f.utils.nowdate.return_value = "2026-10-07"
				f.db.get_values.return_value = []
				result = targets.save_target("rep", month, 400, recurring)
				self.assertEqual(result["month"], month)

	def test_write_locks_user_and_updates_existing_row_preserving_legacy_fields(self):
		db = Mock()
		doc = Mock()
		doc.name = "legacy"
		with patch.object(targets, "frappe") as f:
			f.db = db
			f.get_list.return_value = [{"name": "legacy"}]
			f.db.get_values.return_value = [{"name": "legacy"}]
			f.get_doc.return_value = doc
			targets.save_target("rep", "2026-10-01", 400, False)
			db.get_value.assert_called_once_with("User", "rep", "name", for_update=True)
			f.get_doc.assert_called_once_with("CRM Sales Target", "legacy")
			self.assertEqual(doc.target_new_mrr, 400)
			doc.save.assert_called_once_with(ignore_permissions=True)
			self.assertEqual(f.get_doc.call_count, 1)


if __name__ == "__main__":
	unittest.main()
