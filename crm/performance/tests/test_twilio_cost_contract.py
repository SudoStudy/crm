"""Run with the project's pinned Twilio SDK; controlled payloads, no HTTP."""

import sys
import types
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"frappe": types.ModuleType("frappe")}):
	from crm.performance import call_costs


class TwilioCostContractTests(unittest.TestCase):
	def test_real_sdk_parent_uses_from_response_property(self):
		try:
			from twilio.rest.api.v2010.account.call import CallInstance
		except ImportError:
			self.skipTest("Run with project dependency twilio==8.5.0")
		sid = "CA" + "a" * 32
		parent = CallInstance(
			Mock(),
			{
				"sid": sid,
				"account_sid": "AC" + "b" * 32,
				"from": "client:rep(at)example.com",
				"parent_call_sid": None,
				"status": "completed",
				"price": "-0.12",
				"price_unit": "USD",
			},
			account_sid="AC" + "b" * 32,
		)
		self.assertTrue(hasattr(parent, "_from"))
		self.assertFalse(hasattr(parent, "from_"))
		client = Mock()
		client.calls.return_value.fetch.return_value = parent
		client.calls.list.return_value = []
		result = call_costs.fetch_cost(client, sid, caller="rep@example.com")
		self.assertEqual(result["status"], "Complete")
		self.assertEqual(result["amount"], Decimal("0.12"))


if __name__ == "__main__":
	unittest.main()
