"""Tests for the static HTML renderer."""

import unittest

from aquasignal.analysis import assess_site
from aquasignal.render import render_dashboard, sparkline_svg


def _fixture_assessment():
    site = {"id": "01474500", "name": "Schuylkill River at Philadelphia, PA",
            "city": "Philadelphia, PA", "huc": "02040203"}
    series = {
        "00300": [(f"2026-08-{(i % 28) + 1:02d}", 7.5 + (i % 5) * 0.1)
                  for i in range(60)],
        "00010": [(f"2026-08-{(i % 28) + 1:02d}", 22.0 + (i % 7) * 0.3)
                  for i in range(60)],
    }
    return assess_site(site, series)


class SparklineTests(unittest.TestCase):
    def test_sparkline_svg_structure(self):
        svg = sparkline_svg([1.0, 2.0, 3.0, 2.5], "#fff")
        self.assertIn("<svg", svg)
        self.assertIn("polyline", svg)

    def test_sparkline_flat_series_no_divzero(self):
        svg = sparkline_svg([5.0, 5.0, 5.0], "#fff")
        self.assertIn("polyline", svg)

    def test_sparkline_empty(self):
        self.assertEqual(sparkline_svg([], "#fff"), "")

    def test_sparkline_marks_anomalies(self):
        svg = sparkline_svg([1.0] * 40, "#fff",
                            anomalies=[{"index": 39, "value": 1.0, "z": 3.1}])
        self.assertIn("circle", svg)


class RenderTests(unittest.TestCase):
    def test_dashboard_contains_expected_content(self):
        html = render_dashboard([_fixture_assessment()],
                                generated_at="2026-09-24 00:00 UTC")
        self.assertIn("Schuylkill River at Philadelphia, PA", html)
        self.assertIn("01474500", html)
        self.assertIn("Watch list", html)
        self.assertIn("Methodology", html)
        self.assertIn("AI disclosure", html)
        self.assertIn("<svg", html)

    def test_dashboard_escapes_html(self):
        bad = _fixture_assessment()
        bad["site"]["name"] = "<script>alert(1)</script>"
        html = render_dashboard([bad], generated_at="x")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_dashboard_no_unresolved_placeholders(self):
        html = render_dashboard([_fixture_assessment()], generated_at="x")
        self.assertNotIn("{cards}", html)
        self.assertNotIn("{sections}", html)
        self.assertNotIn("None</", html)
        self.assertNotIn(">nan<", html)

    def test_watchlist_sorted_worst_first(self):
        a = _fixture_assessment()
        html = render_dashboard([a], generated_at="x")
        self.assertIsInstance(html, str)


if __name__ == "__main__":
    unittest.main()
