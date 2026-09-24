"""Offline tests for the data pipeline (parsing + caching)."""

import json
import tempfile
import unittest
from pathlib import Path

from aquasignal.fetch import (
    FetchError,
    FetchSession,
    cache_path,
    fetch_site,
    load_cached,
    parse_time_series,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nwis_dv_01474500.json"


class FakeSession(FetchSession):
    """Returns a canned payload instead of touching the network."""

    def __init__(self, payload):
        super().__init__()
        self.payload = payload
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class ParseTimeSeriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(FIXTURE.read_text())

    def test_parses_real_usgs_payload(self):
        series = parse_time_series(self.payload, "01474500")
        # DO, pH and turbidity each report 30 daily means in the fixture window
        self.assertIn("00300", series)
        self.assertIn("00400", series)
        self.assertIn("63680", series)
        self.assertEqual(len(series["00300"]), 30)

    def test_prefers_daily_mean_statistic(self):
        series = parse_time_series(self.payload, "01474500")
        dates = [d for d, _ in series["00300"]]
        # one point per day, not three interleaved min/mean/max series
        self.assertEqual(len(dates), len(set(dates)))

    def test_skips_empty_series(self):
        payload = {"value": {"timeSeries": [
            {"sourceInfo": {"siteCode": [{"value": "01474500"}]},
             "variable": {"variableCode": [{"value": "00010"}]},
             "values": [{"value": []}]},
            {"sourceInfo": {"siteCode": [{"value": "01474500"}]},
             "variable": {"variableCode": [{"value": "00300"}]},
             "values": [{"value": [
                 {"dateTime": "2026-09-01T00:00:00.000", "value": "8.2"}]}]},
        ]}}
        series = parse_time_series(payload, "01474500")
        self.assertNotIn("00010", series)
        self.assertIn("00300", series)

    def test_drops_no_data_sentinel(self):
        payload = {"value": {"timeSeries": [{
            "sourceInfo": {"siteCode": [{"value": "01474500"}]},
            "variable": {"variableCode": [{"value": "00300"}],
                         "options": {"option": [{"name": "Statistic",
                                                 "optionCode": "00003"}]}},
            "values": [{"value": [
                {"dateTime": "2026-09-01T00:00:00.000", "value": "-999999"},
                {"dateTime": "2026-09-02T00:00:00.000", "value": "8.1"},
                {"dateTime": "2026-09-03T00:00:00.000", "value": "oops"},
            ]}],
        }]}}
        series = parse_time_series(payload, "01474500")
        self.assertEqual(series["00300"], [("2026-09-02", 8.1)])

    def test_ignores_other_sites(self):
        series = parse_time_series(self.payload, "99999999")
        self.assertEqual(series, {})

    def test_fallback_when_no_mean(self):
        payload = {"value": {"timeSeries": [{
            "sourceInfo": {"siteCode": [{"value": "1"}]},
            "variable": {"variableCode": [{"value": "00010"}],
                         "options": {"option": [{"name": "Statistic",
                                                 "optionCode": "00001"}]}},
            "values": [{"value": [
                {"dateTime": "2026-09-01T00:00:00.000", "value": "21.5"}]}],
        }]}}
        series = parse_time_series(payload, "1")
        self.assertEqual(series["00010"], [("2026-09-01", 21.5)])


class FetchSiteTests(unittest.TestCase):
    def test_fetch_site_builds_result(self):
        payload = json.loads(FIXTURE.read_text())
        session = FakeSession(payload)
        from datetime import date
        result = fetch_site(session, "01474500",
                            start=date(2026, 6, 1), end=date(2026, 6, 30))
        self.assertEqual(result["site_id"], "01474500")
        self.assertIn("00300", result["series"])
        self.assertIn("sites=01474500", session.urls[0])
        self.assertIn("parameterCd=", session.urls[0])

    def test_fetch_site_raises_after_retries(self):
        session = FakeSession(FetchError("boom"))
        with self.assertRaises(FetchError):
            fetch_site(session, "01474500")


class CacheTests(unittest.TestCase):
    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache_path(tmp, "123").write_text(json.dumps({"site_id": "123"}))
            self.assertEqual(load_cached(tmp, "123"), {"site_id": "123"})
            self.assertIsNone(load_cached(tmp, "999"))


if __name__ == "__main__":
    unittest.main()
