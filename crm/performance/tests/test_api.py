import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

fake = types.ModuleType("frappe")
fake.whitelist = lambda **kwargs: lambda function: function
fake.PermissionError = PermissionError
fake.ValidationError = ValueError
fake.AuthenticationError = PermissionError
fake._ = lambda value: value
fake.session = types.SimpleNamespace(user="rep")
fake.get_roles = Mock(return_value=["Sales User"])
fake.db = Mock()
fake.db.get_value.return_value = 1
fake.throw = lambda message, error=ValueError: (_ for _ in ()).throw(error(message))
fake.utils = types.SimpleNamespace(nowdate=lambda: "2026-10-07", get_system_timezone=lambda: "Asia/Karachi")
with patch.dict(sys.modules, {"frappe": fake}):
	spec = importlib.util.spec_from_file_location(
		"performance_api", Path(__file__).parents[2] / "api/performance.py"
	)
	api = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(api)


class ApiTests(unittest.TestCase):
	def setUp(self):
		fake.session.user = "rep"
		fake.get_roles.side_effect = None
		fake.get_roles.return_value = ["Sales User"]
		fake.db.get_value.return_value = 1

	def test_forecast_edit_is_owner_scoped_and_checks_write_permission(self):
		doc = types.SimpleNamespace(
			name="d",
			deal_owner="other",
			check_permission=Mock(),
			modified="2026-10-10 10:00:00",
			currency="USD",
			save=Mock(),
		)
		with patch.object(api, "frappe") as f:
			f.session.user = "rep"
			f.get_roles.return_value = ["Sales User"]
			f.get_doc.return_value = doc
			f.throw.side_effect = fake.throw
			f.PermissionError = PermissionError
			with self.assertRaises(PermissionError):
				api.update_forecast("d", 300, 0, "2026-11-01", doc.modified)
			doc.save.assert_not_called()
			doc.deal_owner = "rep"
			api.update_forecast("d", 300, 0, "2026-11-01", doc.modified)
			doc.check_permission.assert_called_with("write")
			self.assertEqual(doc.probability, 0)
			self.assertEqual(doc.expected_closure_date, "2026-11-01")
			self.assertEqual(doc.expected_deal_value, 300)
			f.get_doc.assert_called_with("CRM Deal", "d", for_update=True)

	def test_forecast_invalid_values_and_stale_edits_do_not_save(self):
		doc = types.SimpleNamespace(
			deal_owner="rep", check_permission=Mock(), modified="now", currency="USD", save=Mock()
		)
		with patch.object(api, "frappe") as f:
			f.session.user = "rep"
			f.get_roles.return_value = ["Sales User"]
			f.get_doc.return_value = doc
			f.throw.side_effect = fake.throw
			f.ValidationError = ValueError
			f.TimestampMismatchError = ValueError
			for amount, probability, closing, modified in (
				(-1, 50, "2026-11-01", "now"),
				(300, 101, "2026-11-01", "now"),
				(300, "NaN", "2026-11-01", "now"),
				(300, 50, "2026-11-02", "now"),
				(300, 50, "2026-11-01", "old"),
			):
				with self.assertRaises(ValueError):
					api.update_forecast("d", amount, probability, closing, modified)
			doc.save.assert_not_called()

	def test_guest_and_non_crm_rejected_from_all_routes(self):
		for user, roles in (("Guest", []), ("web", ["Website User"])):
			fake.session.user = user
			fake.get_roles.return_value = roles
			for endpoint, kwargs in (
				(api.get_context, {}),
				(api.get_summary, {}),
				(api.get_activity, {}),
				(api.set_target, {"salesperson": "rep", "month": "2026-10-01", "amount": 300}),
				(
					api.update_forecast,
					{
						"deal": "d",
						"expected_mrr": 300,
						"probability": 50,
						"closing_month": "2026-10-01",
						"modified": "now",
					},
				),
				(api.get_call_cost, {"name": "call"}),
			):
				with self.assertRaises(PermissionError):
					endpoint(**kwargs)

	def test_rep_cross_user_and_team_queries_rejected(self):
		for endpoint in (api.get_summary, api.get_activity):
			for salesperson in ("other", "team"):
				with self.assertRaises(PermissionError):
					endpoint(salesperson=salesperson)

	def test_rep_cannot_edit_own_or_other_target(self):
		for salesperson in ("rep", "other"):
			with self.assertRaises(PermissionError):
				api.set_target(salesperson, "2026-10-01", 300)

	def test_manager_can_select_crm_user_but_not_guest_disabled_or_non_crm(self):
		fake.session.user = "manager"
		fake.get_roles.side_effect = lambda user: ["Sales Manager"] if user == "manager" else ["Website User"]
		with self.assertRaises(PermissionError):
			api.resolve_scope("external")
		fake.get_roles.side_effect = None
		fake.get_roles.return_value = ["Sales Manager"]
		fake.db.get_value.return_value = 0
		with self.assertRaises(PermissionError):
			api.resolve_scope("disabled")

	def test_summary_filters_current_owner_and_checks_effective_doc_permission(self):
		doc = types.SimpleNamespace(
			check_permission=Mock(),
			has_permission=Mock(return_value=True),
			as_dict=lambda: {
				"name": "allowed",
				"status": "Won",
				"deal_owner": "rep",
				"currency": "USD",
				"deal_value": 100,
				"status_change_log": [{"idx": 1, "from_type": "Won", "from_date": "2026-10-02"}],
			},
		)
		with (
			patch.object(api, "frappe") as f,
			patch.object(api, "get_targets", return_value=([{"month": "2026-10-01", "amount": 300}], [])),
			patch.object(api, "load_cost_summary", return_value={"confirmed_amount": 0, "pending_calls": 0}),
		):
			f.session.user = "rep"
			f.get_roles.return_value = ["Sales User"]
			f.db.get_value.return_value = 1
			f.get_list.return_value = [{"name": "denied"}, {"name": "allowed"}]
			f.get_doc.return_value = doc
			f.has_permission.side_effect = lambda doctype, ptype, doc: doc == "allowed"
			f.get_cached_value.return_value = "Won"
			result = api.get_summary(anchor="2026-10-01")
			self.assertEqual(result["actual"], 100)
			self.assertEqual(result["total"], 1)
			self.assertEqual(f.get_list.call_args.kwargs["filters"]["deal_owner"], ["in", ["rep"]])

	def test_call_cost_detail_checks_call_and_linked_parent(self):
		doc = Mock()
		doc.get.side_effect = {"reference_doctype": "CRM Lead", "reference_docname": "lead", "links": []}.get
		with (
			patch.object(api, "frappe") as f,
			patch.object(api, "load_call_cost", return_value={"status": "Pending"}) as load,
		):
			f.session.user = "rep"
			f.get_roles.return_value = ["Sales User"]
			f.get_doc.return_value = doc
			f.has_permission.return_value = False
			f.throw.side_effect = fake.throw
			f.PermissionError = PermissionError
			with self.assertRaises(PermissionError):
				api.get_call_cost("call")
			load.assert_not_called()
			f.has_permission.return_value = True
			self.assertEqual(api.get_call_cost("call"), {"status": "Pending"})
			doc.check_permission.assert_called_with("read")

	def test_team_includes_unconfigured_rep_but_not_untargeted_manager(self):
		with (
			patch.object(api, "frappe") as f,
			patch.object(
				api,
				"crm_users",
				return_value=[{"name": "rep"}, {"name": "manager"}, {"name": "quota_manager"}],
			),
		):
			f.get_roles.side_effect = lambda user: ["Sales User"] if user == "rep" else ["Sales Manager"]
			f.db.exists.side_effect = lambda doctype, filters: (
				doctype == "DocType"
				or (isinstance(filters, dict) and filters.get("salesperson") == "quota_manager")
			)
			self.assertEqual(api.team_users(), ["rep", "quota_manager"])

	def test_target_gets_validated_user_and_only_post_decorator(self):
		fake.session.user = "manager"
		fake.get_roles.return_value = ["Sales Manager"]
		with patch.object(api, "save_target") as save:
			api.set_target("rep", "2026-10-01", 300, True)
			save.assert_called_once_with("rep", "2026-10-01", 300, True)


if __name__ == "__main__":
	unittest.main()
