"""Fetch daily-value time series from the USGS NWIS web service.

No API key required. Responses are cached as JSON on disk so the dashboard
build is reproducible offline and tests never touch the network.

Public API:
    fetch_site(session, site_id, param_codes, start, end) -> dict
    parse_time_series(payload, site_id) -> dict[str, list[tuple[date, float]]]
    fetch_all(cache_dir, days) -> dict
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .sites import PARAMETERS, SITES

NWIS_DV_URL = "https://waterservices.usgs.gov/nwis/dv/"
USER_AGENT = "aqua-signal/0.1 (+https://github.com/ntoledo319/aqua-signal)"
USGS_NO_DATA = -999999.0


@dataclass
class FetchSession:
    """Minimal HTTP session with retry/backoff. Stdlib only."""

    retries: int = 3
    timeout: float = 45.0
    backoff: float = 2.0

    def get_json(self, url: str) -> dict:
        last_err: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": USER_AGENT}
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_err = exc
                if attempt < self.retries:
                    time.sleep(self.backoff * attempt)
        raise FetchError(f"GET {url} failed after {self.retries} tries: {last_err}")


class FetchError(RuntimeError):
    pass


def dv_url(site_id: str, param_codes: list[str], start: date, end: date) -> str:
    params = ",".join(param_codes)
    return (
        f"{NWIS_DV_URL}?format=json&sites={site_id}&parameterCd={params}"
        f"&startDT={start.isoformat()}&endDT={end.isoformat()}&siteStatus=active"
    )


def _statistic_code(series: dict) -> str | None:
    for opt in series.get("variable", {}).get("options", {}).get("option", []):
        if opt.get("name") == "Statistic":
            return opt.get("optionCode")
    return None


def parse_time_series(payload: dict, site_id: str) -> dict[str, list[tuple[str, float]]]:
    """Turn a NWIS DV JSON payload into {param_code: [(iso_date, value), ...]}.

    NWIS daily values emit one series per statistic (max=00001, min=00002,
    mean=00003). We keep the daily *mean*; if a parameter has no mean series
    with values, we fall back to whichever statistic has data. Skips USGS
    no-data sentinels (-999999) and unparseable values.
    """
    candidates: dict[str, dict[str, list[tuple[str, float]]]] = {}
    value = payload.get("value", {})
    for series in value.get("timeSeries", []):
        series_site = series["sourceInfo"]["siteCode"][0]["value"]
        if series_site.lstrip("0") != site_id.lstrip("0"):
            continue
        code = series["variable"]["variableCode"][0]["value"]
        stat = _statistic_code(series) or "unknown"
        points: list[tuple[str, float]] = []
        for block in series.get("values", []):
            for item in block.get("value", []):
                try:
                    v = float(item["value"])
                except (KeyError, TypeError, ValueError):
                    continue
                if v <= USGS_NO_DATA + 1:
                    continue
                points.append((item["dateTime"][:10], v))
        if points:
            candidates.setdefault(code, {})[stat] = points
    out: dict[str, list[tuple[str, float]]] = {}
    for code, by_stat in candidates.items():
        if "00003" in by_stat:
            out[code] = by_stat["00003"]
        else:  # no daily mean: take the statistic with the most points
            out[code] = max(by_stat.values(), key=len)
    return out


def fetch_site(
    session: FetchSession,
    site_id: str,
    param_codes: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    days: int = 180,
) -> dict:
    """Fetch one site; returns {'site_id', 'fetched_at', 'series': {...}}."""
    codes = param_codes or list(PARAMETERS)
    end = end or date.today()
    start = start or (end - timedelta(days=days))
    payload = session.get_json(dv_url(site_id, codes, start, end))
    series = parse_time_series(payload, site_id)
    return {
        "site_id": site_id,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "series": series,
    }


def cache_path(cache_dir: Path, site_id: str) -> Path:
    return cache_dir / f"{site_id}.json"


def load_cached(cache_dir: Path, site_id: str) -> dict | None:
    p = cache_path(cache_dir, site_id)
    if p.exists():
        return json.loads(p.read_text())
    return None


def fetch_all(
    cache_dir: Path,
    days: int = 180,
    refresh: bool = True,
    session: FetchSession | None = None,
) -> dict[str, dict]:
    """Fetch (or load from cache) every registered site.

    With refresh=False this is fully offline and deterministic.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = session or FetchSession()
    results: dict[str, dict] = {}
    for site in SITES:
        cached = None if refresh else load_cached(cache_dir, site["id"])
        if cached is None:
            try:
                cached = fetch_site(session, site["id"], days=days)
            except FetchError as exc:
                cached = load_cached(cache_dir, site["id"])
                if cached is None:
                    print(f"  [warn] {site['id']} fetch failed, no cache: {exc}")
                    continue
                print(f"  [warn] {site['id']} fetch failed, using stale cache: {exc}")
            else:
                cache_path(cache_dir, site["id"]).write_text(
                    json.dumps(cached, indent=1)
                )
        results[site["id"]] = cached
    return results
