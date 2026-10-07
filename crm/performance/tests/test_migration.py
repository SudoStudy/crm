import sys
import types
import unittest
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"frappe": types.ModuleType("frappe")}):
	from crm.patches.v1_0 import native_performance_targets as migration


class SchemaDoc:
	def __init__(self, module="Old App"):
		self.module = module
		self.fields = [
			types.SimpleNamespace(fieldname="legacy_forecast"),
			types.SimpleNamespace(fieldname="salesperson"),
		]
		self.permissions = [types.SimpleNamespace(role="Sales User", read=1)]
		self.save = Mock()

	def get(self, key):
		return getattr(self, key)

	def append(self, key, value):
		getattr(self, key).append(types.SimpleNamespace(**value))


class MigrationTests(unittest.TestCase):
	def test_existing_custom_schema_preserved_and_second_run_is_noop(self):
		target, rule = SchemaDoc(), SchemaDoc("FCRM")
		with patch.object(migration, "frappe") as f:
			f.db.exists.return_value = True
			f.get_doc.side_effect = lambda doctype, name: target if name == "CRM Sales Target" else rule
			migration.execute()
			self.assertEqual(target.module, "FCRM")
			self.assertIn("legacy_forecast", [field.fieldname for field in target.fields])
			self.assertEqual([field.fieldname for field in target.fields].count("salesperson"), 1)
			saves = target.save.call_count
			migration.execute()
			self.assertEqual(target.save.call_count, saves)
			f.db.sql.assert_not_called()
			f.delete_doc.assert_not_called()

	def test_missing_doctypes_created_without_seeding_users_or_targets(self):
		with patch.object(migration, "frappe") as f:
			f.db.exists.return_value = False
			migration.execute()
			self.assertEqual(f.get_doc.call_count, 2)
			names = [call.args[0]["name"] for call in f.get_doc.call_args_list]
			self.assertEqual(names, ["CRM Sales Target", "CRM Sales Target Rule"])
			self.assertTrue(all(call.args[0]["custom"] == 1 for call in f.get_doc.call_args_list))


if __name__ == "__main__":
	unittest.main()
