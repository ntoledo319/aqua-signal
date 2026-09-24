"""CLI: python -m aquasignal [fetch|build|all] [--offline] [--days N]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis import assess_site
from .fetch import fetch_all
from .render import render_dashboard
from .sites import SITES

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data"
OUT_DIR = ROOT / "site"


def cmd_fetch(days: int, offline: bool) -> dict:
    mode = "cache-only" if offline else "live USGS NWIS"
    print(f"Fetching {len(SITES)} sites ({mode}, {days}d window)...")
    results = fetch_all(CACHE_DIR, days=days, refresh=not offline)
    for site in SITES:
        r = results.get(site["id"])
        if r:
            params = {c: len(pts) for c, pts in r["series"].items()}
            print(f"  {site['id']} {site['name']}: {params}")
        else:
            print(f"  {site['id']} {site['name']}: NO DATA")
    return results


def cmd_build(results: dict, days: int) -> Path:
    site_by_id = {s["id"]: s for s in SITES}
    assessments = []
    for site_id, payload in results.items():
        if not payload["series"]:
            print(f"  [warn] {site_id}: no usable series, skipped")
            continue
        assessments.append(assess_site(site_by_id[site_id], payload["series"]))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "index.html"
    out.write_text(render_dashboard(assessments, window_days=days))
    print(f"Built {out} ({out.stat().st_size:,} bytes, "
          f"{len(assessments)} sites assessed)")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aquasignal")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["fetch", "build", "all"])
    ap.add_argument("--offline", action="store_true",
                    help="use cached data only (no network)")
    ap.add_argument("--days", type=int, default=400,
                    help="analysis window in days (default 400)")
    args = ap.parse_args(argv)

    if args.command in ("fetch", "all"):
        results = cmd_fetch(args.days, args.offline)
    else:
        results = fetch_all(CACHE_DIR, days=args.days, refresh=False)
    if args.command in ("build", "all"):
        cmd_build(results, args.days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
