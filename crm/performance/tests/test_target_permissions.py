import sys
import types
import unittest
from unittest.mock import patch

with patch.dict(sys.modules, {"frappe": types.ModuleType("frappe")}):
	from crm.permissions import sales_targets


class TargetPermissionTests(unittest.TestCase):
	def test_reps_read_by_salesperson_instead_of_manager_row_owner(self):
		with patch.object(sales_targets, "frappe") as f:
			f.get_roles.return_value = ["Sales User"]
			own = types.SimpleNamespace(salesperson="rep", owner="manager")
			other = types.SimpleNamespace(salesperson="other", owner="rep")
			self.assertTrue(sales_targets.has_target_permission(own, "read", "rep"))
			self.assertFalse(sales_targets.has_target_permission(other, "read", "rep"))
			self.assertFalse(sales_targets.has_target_permission(own, "write", "rep"))
			for query in (
				sales_targets.get_target_permission_query_conditions,
				sales_targets.get_rule_permission_query_conditions,
			):
				f.db.escape.return_value = "'rep'"
				condition = query("rep")
				self.assertIn("`salesperson` = 'rep'", condition)
				self.assertNotIn("`owner`", condition)

	def test_managers_read_all_and_guest_or_non_crm_read_none(self):
		with patch.object(sales_targets, "frappe") as f:
			doc = types.SimpleNamespace(salesperson="rep", owner="someone")
			for role in ("Sales Manager", "System Manager"):
				f.get_roles.return_value = [role]
				self.assertTrue(sales_targets.has_target_permission(doc, "read", "manager"))
				self.assertEqual(sales_targets.get_target_permission_query_conditions("manager"), "")
				self.assertEqual(sales_targets.get_rule_permission_query_conditions("manager"), "")
			f.get_roles.return_value = ["Website User"]
			for user in ("Guest", "outside"):
				self.assertFalse(sales_targets.has_target_permission(doc, "read", user))
				self.assertEqual(sales_targets.get_target_permission_query_conditions(user), "1=0")

	def test_user_input_uses_database_escaping(self):
		with patch.object(sales_targets, "frappe") as f:
			f.get_roles.return_value = ["Sales User"]
			f.db.escape.return_value = "'escaped literal'"
			condition = sales_targets.get_rule_permission_query_conditions("rep' OR 1=1")
			f.db.escape.assert_called_once_with("rep' OR 1=1")
			self.assertEqual(condition, "`tabCRM Sales Target Rule`.`salesperson` = 'escaped literal'")


if __name__ == "__main__":
	unittest.main()
