"""Exercise the actual controller method without requiring a Frappe runtime."""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


class ProbabilityDefaultTests(unittest.TestCase):
	def method(self, name, frappe):
		tree = ast.parse((Path(__file__).parents[2] / "fcrm/doctype/crm_deal/crm_deal.py").read_text())
		controller = next(
			node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CRMDeal"
		)
		method = next(
			node for node in controller.body if isinstance(node, ast.FunctionDef) and node.name == name
		)
		namespace = {"frappe": frappe, "_": lambda text: text}
		exec(compile(ast.Module(body=[method], type_ignores=[]), "controller", "exec"), namespace)
		return namespace[name]

	def test_explicit_mrr_edit_is_not_overwritten_by_product_totals(self):
		frappe = SimpleNamespace(db=SimpleNamespace(get_single_value=Mock(return_value=1)))
		doc = SimpleNamespace(
			expected_deal_value=350, net_total=1200, total=1200, has_value_changed=Mock(return_value=True)
		)
		self.method("update_expected_deal_value", frappe)(doc)
		self.assertEqual(doc.expected_deal_value, 350)

	def test_unrelated_save_preserves_manual_mrr_but_changed_products_can_auto_update(self):
		frappe = SimpleNamespace(db=SimpleNamespace(get_single_value=Mock(return_value=1)))
		doc = SimpleNamespace(
			expected_deal_value=350, net_total=1200, total=1200, has_value_changed=Mock(return_value=False)
		)
		update = self.method("update_expected_deal_value", frappe)
		update(doc)
		self.assertEqual(doc.expected_deal_value, 350)
		doc.has_value_changed.side_effect = lambda field: field == "net_total"
		update(doc)
		self.assertEqual(doc.expected_deal_value, 1200)

	def test_zero_expected_mrr_is_valid_when_forecasting_enabled(self):
		frappe = SimpleNamespace(
			db=SimpleNamespace(get_single_value=Mock(return_value=1)), MandatoryError=ValueError
		)
		frappe.throw = lambda message, error: (_ for _ in ()).throw(error(message))
		doc = SimpleNamespace(
			expected_deal_value=0,
			expected_closure_date="2026-11-01",
			update_closed_date=Mock(),
			update_default_probability=Mock(),
			update_expected_deal_value=Mock(),
		)
		self.method("validate_forecasting_fields", frappe)(doc)

	def test_explicit_zero_is_not_replaced_and_unset_uses_stage(self):
		tree = ast.parse((Path(__file__).parents[2] / "fcrm/doctype/crm_deal/crm_deal.py").read_text())
		controller = next(
			node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CRMDeal"
		)
		method = next(
			node
			for node in controller.body
			if isinstance(node, ast.FunctionDef) and node.name == "update_default_probability"
		)
		frappe = SimpleNamespace(db=SimpleNamespace(get_value=Mock(return_value=70)))
		namespace = {"frappe": frappe}
		exec(compile(ast.Module(body=[method], type_ignores=[]), "controller", "exec"), namespace)
		for value, expected in ((0, 0), (50, 50), (None, 70), ("", 70)):
			doc = SimpleNamespace(probability=value, status="Trial")
			namespace["update_default_probability"](doc)
			self.assertEqual(doc.probability, expected)
