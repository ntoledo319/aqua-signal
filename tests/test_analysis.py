"""Tests for the assessment engine (stats, trends, rules, scoring)."""

import math
import random
import unittest

from aquasignal.analysis import (
    assess_site,
    build_narrative,
    classify,
    detect_anomalies,
    evaluate_parameter,
    mann_kendall,
    ols_slope,
    rank_at_risk,
    sens_slope,
    series_stats,
)


class StatsTests(unittest.TestCase):
    def test_series_stats(self):
        s = series_stats([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(s["n"], 4)
        self.assertEqual(s["min"], 1.0)
        self.assertEqual(s["max"], 4.0)
        self.assertAlmostEqual(s["mean"], 2.5)
        self.assertEqual(s["latest"], 4.0)

    def test_series_stats_empty_raises(self):
        with self.assertRaises(ValueError):
            series_stats([])

    def test_ols_slope_linear(self):
        self.assertAlmostEqual(ols_slope([float(i) for i in range(50)]), 1.0, 5)
        self.assertAlmostEqual(ols_slope([10.0 - i for i in range(50)]), -1.0, 5)
        self.assertEqual(ols_slope([5.0]), 0.0)


class TrendTests(unittest.TestCase):
    def test_mann_kendall_detects_increase(self):
        rng = random.Random(42)
        values = [i * 0.1 + rng.gauss(0, 0.05) for i in range(120)]
        mk = mann_kendall(values)
        self.assertEqual(mk["trend"], "increasing")
        self.assertLess(mk["p"], 0.05)
        self.assertGreater(mk["s"], 0)

    def test_mann_kendall_detects_decrease(self):
        rng = random.Random(7)
        values = [10 - i * 0.1 + rng.gauss(0, 0.05) for i in range(120)]
        mk = mann_kendall(values)
        self.assertEqual(mk["trend"], "decreasing")

    def test_mann_kendall_flat_is_none(self):
        rng = random.Random(1)
        values = [8.0 + rng.gauss(0, 0.02) for _ in range(120)]
        mk = mann_kendall(values)
        self.assertEqual(mk["trend"], "none")

    def test_mann_kendall_short_series(self):
        mk = mann_kendall([1.0, 2.0, 3.0])
        self.assertEqual(mk["trend"], "none")
        self.assertEqual(mk["p"], 1.0)

    def test_mann_kendall_handles_ties(self):
        values = [5.0] * 50 + [6.0] * 50
        mk = mann_kendall(values)
        self.assertEqual(mk["trend"], "increasing")
        self.assertTrue(math.isfinite(mk["z"]))

    def test_sens_slope(self):
        values = [2.0 * i + 3 for i in range(60)]
        self.assertAlmostEqual(sens_slope(values), 2.0, 6)
        self.assertEqual(sens_slope([]), 0.0)


class AnomalyTests(unittest.TestCase):
    def test_detects_spike(self):
        rng = random.Random(3)
        values = [8.0 + rng.gauss(0, 0.1) for _ in range(90)]
        values[80] = 15.0  # gross spike
        hits = detect_anomalies(values, window=30)
        self.assertTrue(any(h["index"] == 80 for h in hits))

    def test_clean_series_no_hits(self):
        rng = random.Random(5)
        values = [8.0 + rng.gauss(0, 0.05) for _ in range(90)]
        self.assertEqual(detect_anomalies(values, window=30), [])


class RulesTests(unittest.TestCase):
    def _flat(self, v, n=60):
        return [(f"2026-08-{(i % 28) + 1:02d}", v) for i in range(n)]

    def test_low_do_fires_critical(self):
        r = evaluate_parameter("00300", self._flat(2.5))
        self.assertTrue(any(f["rule"] == "do_severe" for f in r["rules_fired"]))
        self.assertLessEqual(r["score"], 60)

    def test_marginal_do_fires_warning(self):
        r = evaluate_parameter("00300", self._flat(4.5))
        self.assertTrue(any(f["rule"] == "do_low" for f in r["rules_fired"]))

    def test_healthy_do_no_rules(self):
        r = evaluate_parameter("00300", self._flat(8.5))
        fired = {f["rule"] for f in r["rules_fired"]}
        self.assertNotIn("do_severe", fired)
        self.assertNotIn("do_low", fired)
        self.assertEqual(r["score"], 100)

    def test_ph_out_of_range(self):
        r = evaluate_parameter("00400", self._flat(9.3))
        self.assertTrue(any(f["rule"] == "ph_out_of_range" for f in r["rules_fired"]))

    def test_high_temp_fires(self):
        r = evaluate_parameter("00010", self._flat(29.0))
        self.assertTrue(any(f["rule"] == "temp_high" for f in r["rules_fired"]))

    def test_declining_do_yoy_fires(self):
        # two years of September data; recent year 1.2 mg/L lower
        points = []
        for d in range(1, 31):
            points.append((f"2025-09-{d:02d}", 8.5))
        for d in range(1, 31):
            points.append((f"2026-09-{d:02d}", 7.3))
        r = evaluate_parameter("00300", points)
        self.assertTrue(
            any(f["rule"] == "do_declining_yoy" for f in r["rules_fired"]))

    def test_seasonal_warming_alone_does_not_fire(self):
        # one year of data only (no YoY possible): spring-to-autumn ramp must
        # not fire a trend rule even though MK sees a strong rise
        points = [(f"2026-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}", 5.0 + i * 0.1)
                  for i in range(180)]
        r = evaluate_parameter("00010", points)
        fired = {f["rule"] for f in r["rules_fired"]}
        self.assertNotIn("temp_rising_yoy", fired)
        self.assertEqual(r["trend"]["trend"], "increasing")  # MK sees the ramp

    def test_score_bounds(self):
        r = evaluate_parameter("00300", self._flat(1.0))
        self.assertGreaterEqual(r["score"], 0)
        self.assertLessEqual(r["score"], 100)


class YoyTests(unittest.TestCase):
    def test_yoy_delta(self):
        from aquasignal.analysis import yoy_compare
        dates = [f"2025-09-{d:02d}" for d in range(1, 31)] + \
                [f"2026-09-{d:02d}" for d in range(1, 31)]
        values = [10.0] * 30 + [12.0] * 30
        yoy = yoy_compare(dates, values)
        self.assertIsNotNone(yoy)
        self.assertAlmostEqual(yoy["delta"], 2.0)
        self.assertEqual(yoy["pairs"], 30)

    def test_yoy_single_year_returns_none(self):
        from aquasignal.analysis import yoy_compare
        dates = [f"2026-09-{d:02d}" for d in range(1, 31)]
        self.assertIsNone(yoy_compare(dates, [8.0] * 30))


class SiteAssessmentTests(unittest.TestCase):
    def test_classify_boundaries(self):
        self.assertEqual(classify(100), "good")
        self.assertEqual(classify(80), "good")
        self.assertEqual(classify(79.9), "moderate")
        self.assertEqual(classify(60), "moderate")
        self.assertEqual(classify(35), "poor")
        self.assertEqual(classify(10), "bad")

    def test_assess_site_full(self):
        site = {"id": "1", "name": "Test River at Nowhere", "city": "Nowhere"}
        series = {
            "00300": [(f"2026-06-{d:02d}", 8.0) for d in range(1, 29)],
            "00400": [(f"2026-06-{d:02d}", 7.2) for d in range(1, 29)],
        }
        a = assess_site(site, series)
        self.assertEqual(a["status"], "good")
        self.assertIn("Test River", a["narrative"])
        self.assertIn("not a regulatory determination", a["narrative"])
        self.assertEqual(len(a["parameters"]), 2)

    def test_assess_site_skips_tiny_series(self):
        site = {"id": "1", "name": "X", "city": "Y"}
        a = assess_site(site, {"00300": [("2026-09-01", 8.0)]})
        self.assertEqual(a["parameters"], {})

    def test_narrative_mentions_fired_rules(self):
        n = build_narrative(
            {"name": "Bad River"},
            {"00300": {"rules_fired": [
                {"severity": "critical", "rule": "do_severe",
                 "detail": "DO 2.0 mg/L below severe threshold 3.0"}]}},
            40.0, "poor",
        )
        self.assertIn("Critical:", n)
        self.assertIn("POOR", n)

    def test_rank_at_risk_orders_worst_first(self):
        mk = lambda score: {"score": score, "status": classify(score),
                            "site": {"name": f"s{score}"}}
        ranked = rank_at_risk([mk(90), mk(30), mk(60)])
        self.assertEqual([r["score"] for r in ranked], [30, 60, 90])


if __name__ == "__main__":
    unittest.main()
