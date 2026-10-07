"""Run: bench --site test_site run-tests --module crm.performance.integration.test_performance

Requires CRM installed, the native_performance_targets patch applied, Redis and
MariaDB. These tests refuse other sites, use real Frappe APIs/two DB connections,
and clean up their uniquely named fixtures. They are outside offline discovery.
"""

from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase

from crm.api.performance import set_target
from crm.performance.activity import get_activity
from crm.performance.targets import _name


class TestNativePerformance(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		if frappe.local.site != "test_site":
			raise RuntimeError("Native Performance integration tests require disposable test_site")
		super().setUpClass()
		frappe.set_user("Administrator")
		assert frappe.db.exists("DocType", "CRM Sales Target Rule"), "Apply native_performance_targets first"
		assert frappe.get_meta("CRM Task").track_changes, "Task tracking migration must be applied"
		prefix = "performance-test-" + uuid4().hex[:12]
		cls.rep = prefix + "-rep@example.com"
		cls.other = prefix + "-other@example.com"
		cls.manager = prefix + "-manager@example.com"
		cls.users = [cls.rep, cls.other, cls.manager]
		for user in cls.users:
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "Performance test",
					"enabled": 1,
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "Sales Manager" if user == cls.manager else "Sales User"}],
				}
			).insert(ignore_permissions=True)
		frappe.db.commit()
		cls.addClassCleanup(cls.cleanup_fixtures)

	@classmethod
	def cleanup_fixtures(cls):
		frappe.local.db = cls._primary_connection
		frappe.db.rollback()
		if cls._secondary_connection:
			cls._secondary_connection.rollback()
		frappe.set_user("Administrator")
		for doctype in ("CRM Sales Target", "CRM Sales Target Rule"):
			frappe.db.delete(doctype, {"salesperson": ["in", cls.users]})
		for doctype in ("Version", "CRM Task", "FCRM Note"):
			frappe.db.delete(doctype, {"owner": ["in", cls.users]})
		for user in cls.users:
			frappe.delete_doc("User", user, ignore_permissions=True, force=True)
		frappe.db.commit()

	def setUp(self):
		super().setUp()
		frappe.local.db = self._primary_connection
		frappe.set_user(self.manager)
		self.month = frappe.utils.nowdate()[:7] + "-01"
		self.addCleanup(self._primary_connection.rollback)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_native_list_and_document_permissions_use_salesperson(self):
		own = set_target(self.rep, self.month, 300, True)
		other = set_target(self.other, self.month, 400, True)
		for doctype, own_name, other_name in (
			("CRM Sales Target", own["name"], other["name"]),
			(
				"CRM Sales Target Rule",
				_name(self.rep, self.month, "rule"),
				_name(self.other, self.month, "rule"),
			),
		):
			frappe.set_user(self.rep)
			self.assertEqual(
				frappe.get_list(
					doctype, filters={"salesperson": ["in", [self.rep, self.other]]}, pluck="name"
				),
				[own_name],
			)
			frappe.get_doc(doctype, own_name).check_permission("read")
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(doctype, other_name).check_permission("read")
			frappe.set_user(self.manager)
			frappe.get_doc(doctype, other_name).check_permission("read")
			self.assertEqual(
				len(frappe.get_list(doctype, filters={"salesperson": ["in", [self.rep, self.other]]})), 2
			)

	def test_actual_task_and_note_versions_enter_feed(self):
		frappe.set_user(self.rep)
		task = frappe.get_doc(
			{"doctype": "CRM Task", "title": "Performance fixture", "status": "Todo"}
		).insert()
		task.status = "Done"
		task.save(ignore_version=False)
		note = frappe.get_doc({"doctype": "FCRM Note", "title": "Before", "content": "Initial"}).insert()
		note.title = "After"
		note.save(ignore_version=False)
		versions = frappe.get_all(
			"Version",
			filters={"docname": ["in", [str(task.name), note.name]]},
			fields=["name", "ref_doctype", "data", "owner"],
		)
		self.assertTrue(any(row.ref_doctype == "CRM Task" and '"Done"' in row.data for row in versions))
		self.assertTrue(any(row.ref_doctype == "FCRM Note" and '"After"' in row.data for row in versions))
		result = get_activity([self.rep], "performed_by")
		self.assertTrue(
			any(
				event["kind"] == "task_completed" and event["actor"] == self.rep for event in result["events"]
			)
		)
		self.assertTrue(
			any(
				event["category"] == "note" and event["source_doctype"] == "Version"
				for event in result["events"]
			)
		)

	def test_two_connections_first_edits_see_current_row_after_old_snapshot(self):
		if frappe.db.db_type != "mariadb":
			self.skipTest("Repeatable Read regression targets MariaDB")
		with self.secondary_connection():
			frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
			self.assertEqual(
				frappe.db.get_values(
					"CRM Sales Target", {"salesperson": self.rep, "target_month": self.month}
				),
				[],
			)
		with self.primary_connection():
			frappe.set_user(self.manager)
			first = set_target(self.rep, self.month, 300, False)
			frappe.db.commit()
		with self.secondary_connection():
			frappe.set_user(self.manager)
			# Its normal snapshot still cannot see the newly committed target.
			self.assertEqual(
				frappe.db.get_values(
					"CRM Sales Target", {"salesperson": self.rep, "target_month": self.month}
				),
				[],
			)
			second = set_target(self.rep, self.month, 400, False)
			frappe.db.commit()
		with self.primary_connection():
			frappe.db.rollback()
			rows = frappe.db.get_values(
				"CRM Sales Target",
				{"salesperson": self.rep, "target_month": self.month},
				["name", "target_new_mrr"],
				as_dict=True,
			)
			self.assertEqual(len(rows), 1)
			self.assertEqual(first["name"], _name(self.rep, self.month, "target"))
			self.assertEqual(second["name"], first["name"])
			self.assertEqual(float(rows[0].target_new_mrr), 400)
