import unittest

from crm.performance import metrics


class MetricsTests(unittest.TestCase):
	def deal(self, **values):
		return dict(
			name="d1",
			deal_owner="rep",
			status_type="Won",
			currency="USD",
			deal_value=0,
			expected_deal_value=900,
			probability=50,
			status_change_log=[dict(idx=1, from_type="Won", from_date="2026-10-03")],
			**values,
		)

	def test_quarter_is_sum_of_monthly_targets(self):
		period = metrics.period_bounds("quarter", "2026-11-01")
		self.assertEqual(period["months"], ["2026-10-01", "2026-11-01", "2026-12-01"])
		result = metrics.summarize([], [dict(month=m, amount=300) for m in period["months"]], period)
		self.assertEqual(result["target"], 900)

	def test_zero_won_is_actual_zero_not_expected(self):
		result = metrics.summarize(
			[self.deal()],
			[dict(month="2026-10-01", amount=300)],
			metrics.period_bounds("month", "2026-10-01"),
		)
		self.assertEqual(result["actual"], 0)
		self.assertEqual(result["deals"][0]["amount"], 0)
		self.assertEqual(result["deals"][0]["expected_mrr"], 900)
		self.assertEqual(result["deals"][0]["probability"], 50)

	def test_latest_won_row_by_sequence_and_no_closed_date_fallback(self):
		d = self.deal()
		d["status_change_log"] += [dict(idx=2, from_type="Won", from_date="2026-11-01")]
		d["deal_value"] = 70
		self.assertEqual(metrics.deal_contribution(d, "2026-10-01", "2026-11-01")[0], None)
		d["status_change_log"] = []
		d["closed_date"] = "2026-10-03"
		self.assertIn("won history", metrics.deal_contribution(d, "2026-10-01", "2026-11-01")[1].lower())

	def test_reopened_deal_contributes_current_open_pipeline_only(self):
		d = self.deal()
		d["status_type"] = "Ongoing"
		d["probability"] = 200
		contribution, _ = metrics.deal_contribution(d, "2026-10-01", "2026-11-01")
		self.assertEqual(contribution["kind"], "pipeline")
		self.assertEqual(contribution["weighted"], 900)

	def test_non_usd_and_missing_currency_excluded(self):
		for currency in ("PKR", None):
			d = self.deal()
			d["currency"] = currency
			contribution, warning = metrics.deal_contribution(d, "2026-10-01", "2026-11-01")
			self.assertIsNone(contribution)
			self.assertIn("currency", warning.lower())

	def test_missing_target_does_not_invent_zero_and_coverage_uses_remaining(self):
		period = metrics.period_bounds("month", "2026-10-01")
		self.assertIsNone(metrics.summarize([], [], period)["target"])
		won, pipeline = self.deal(), self.deal()
		won["deal_value"] = 100
		pipeline.update(name="d2", status_type="Open", expected_deal_value=400)
		result = metrics.summarize([won, pipeline], [dict(month="2026-10-01", amount=300)], period)
		self.assertEqual(result["remaining"], 200)
		self.assertEqual(result["coverage"], 1)
		self.assertAlmostEqual(result["progress"], 100 / 3)

	def test_invalid_period_rejected(self):
		for mode, anchor in (("year", "2026-10-01"), ("month", "2026-10-09"), ("month", "2026-10-01garbage")):
			with self.assertRaises(ValueError):
				metrics.period_bounds(mode, anchor)

	def test_latest_won_history_missing_date_is_not_earlier_history_fallback(self):
		d = self.deal()
		d["status_change_log"].append({"idx": 2, "from_type": "Won", "from_date": None})
		contribution, warning = metrics.deal_contribution(d, "2026-10-01", "2026-11-01")
		self.assertIsNone(contribution)
		self.assertIn("history", warning)

	def test_contributing_deal_exposes_real_stage_forecast_and_probability(self):
		d = self.deal()
		d.update(status="Trial", status_type="Ongoing", probability=70)
		row, _ = metrics.deal_contribution(d, "2026-10-01", "2026-11-01")
		self.assertEqual(row["status"], "Trial")
		self.assertEqual(row["expected_mrr"], 900)
		self.assertEqual(row["probability"], 70)

	def test_pipeline_summed_before_currency_rounding(self):
		deals = []
		for name in ("a", "b", "c"):
			d = self.deal()
			d.update(name=name, status_type="Open", expected_deal_value="0.01", probability=50)
			deals.append(d)
		summary = metrics.summarize(
			deals, [{"month": "2026-10-01", "amount": 300}], metrics.period_bounds("month", "2026-10-01")
		)
		self.assertEqual(summary["weighted_pipeline"], 0.02)

	def test_zero_target_warns_without_progress_or_coverage(self):
		period = metrics.period_bounds("month", "2026-10-01")
		result = metrics.summarize([], [{"month": "2026-10-01", "amount": 0}], period)
		self.assertIsNone(result["progress"])
		self.assertIsNone(result["coverage"])
		self.assertIn("Target is zero; progress and coverage are not calculated.", result["warnings"])


if __name__ == "__main__":
	unittest.main()
