"""Render assessments to a self-contained static HTML dashboard.

Zero dependencies, no JavaScript required: charts are inline SVG generated
server-side. The output is a single index.html that can be hosted anywhere
(GitHub Pages, Netlify, an S3 bucket, a file:// URL).
"""

from __future__ import annotations

import html
import time

from .sites import PARAMETERS

STATUS_COLORS = {
    "good": "#2ecc71",
    "moderate": "#f1c40f",
    "poor": "#e67e22",
    "bad": "#e74c3c",
}

PARAM_COLORS = {
    "00010": "#ff8a65",
    "00300": "#4fc3f7",
    "00400": "#ba68c8",
    "63680": "#a1887f",
}


def sparkline_svg(values: list[float], color: str, width: int = 260,
                  height: int = 64, anomalies: list[dict] | None = None) -> str:
    """Inline SVG line chart with anomaly markers."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pad = 4.0
    n = len(values)

    def xy(i: int, v: float) -> tuple[float, float]:
        x = pad + i * (width - 2 * pad) / max(1, n - 1)
        y = pad + (hi - v) * (height - 2 * pad) / span
        return x, y

    pts = " ".join(f"{xy(i, v)[0]:.1f},{xy(i, v)[1]:.1f}" for i, v in enumerate(values))
    markers = ""
    for a in (anomalies or [])[-8:]:
        x, y = xy(a["index"], a["value"])
        markers += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="none" '
                    f'stroke="#ff5252" stroke-width="1.4"><title>'
                    f'anomaly z={a["z"]:+.1f}</title></circle>')
    lx, ly = xy(n - 1, values[-1])
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="sparkline">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
        f'{markers}'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/>'
        f"</svg>"
    )


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _param_card(code: str, p: dict) -> str:
    meta = PARAMETERS.get(code, {"name": code, "unit": "", "short": code})
    stats = p["stats"]
    trend = p["trend"]
    arrow = {"increasing": "&#9650;", "decreasing": "&#9660;", "none": "&#9644;"}[
        trend["trend"]
    ]
    badges = "".join(
        f'<li class="rule rule-{_esc(r["severity"])}">{_esc(r["detail"])}</li>'
        for r in p["rules_fired"]
    ) or '<li class="rule rule-ok">no flags</li>'
    yoy = p.get("yoy")
    if yoy:
        yoy_txt = (f"YoY {yoy['delta']:+.2f} vs {yoy['prior_year']} "
                   f"({yoy['pairs']} day-pairs)")
    else:
        yoy_txt = "YoY n/a"
    color = PARAM_COLORS.get(code, "#90a4ae")
    svg = sparkline_svg(p["values"], color, anomalies=p["anomalies"])
    return f"""
      <div class="param">
        <div class="param-head">
          <span class="param-name">{_esc(meta['name'])}</span>
          <span class="param-latest">{stats['latest']:.2f} <small>{_esc(meta['unit'])}</small></span>
        </div>
        {svg}
        <div class="param-foot">
          <span>{arrow} {trend['trend']} (p={trend['p']:.3f})</span>
          <span>{_esc(yoy_txt)}</span>
          <span>n={stats['n']}</span>
          <span>score {p['score']}</span>
        </div>
        <ul class="rules">{badges}</ul>
      </div>"""


def _site_section(a: dict) -> str:
    site = a["site"]
    status = a["status"]
    color = STATUS_COLORS[status]
    cards = "".join(
        _param_card(code, p) for code, p in a["parameters"].items()
    )
    return f"""
    <section class="site" id="site-{_esc(site['id'])}">
      <header class="site-head">
        <div>
          <h2>{_esc(site['name'])}</h2>
          <p class="muted">{_esc(site['city'])} &middot; USGS {_esc(site['id'])}
             &middot; <a href="https://waterdata.usgs.gov/monitoring-location/{_esc(site['id'])}/">source</a></p>
        </div>
        <div class="status" style="--status:{color}">
          <span class="status-label">{status.upper()}</span>
          <span class="status-score">{a['score']:.0f}</span>
        </div>
      </header>
      <p class="narrative">{_esc(a['narrative'])}</p>
      <div class="params">{cards}</div>
    </section>"""


CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:#0d1117;color:#e6edf3;line-height:1.5}
.wrap{max-width:1180px;margin:0 auto;padding:24px 20px 80px}
a{color:#58a6ff;text-decoration:none}
h1{font-size:1.9rem;letter-spacing:-.5px}
h2{font-size:1.15rem}
.sub{color:#8b949e;margin:6px 0 24px}
.legend{display:flex;gap:18px;flex-wrap:wrap;margin:14px 0 8px;font-size:.85rem}
.legend span{display:flex;align-items:center;gap:6px}
.dot{width:11px;height:11px;border-radius:50%;display:inline-block}
.watch{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px 18px;margin:18px 0 30px}
.watch h2{margin-bottom:10px}
.watch ol{margin-left:22px}
.watch li{margin:5px 0}
.badge{display:inline-block;min-width:76px;text-align:center;border-radius:6px;padding:1px 9px;font-weight:600;font-size:.78rem;margin-right:8px}
.site{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px 22px;margin:22px 0}
.site-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
.muted{color:#8b949e;font-size:.85rem;margin-top:2px}
.status{text-align:center;border:2px solid var(--status);border-radius:10px;padding:6px 16px;min-width:92px}
.status-label{display:block;font-size:.75rem;font-weight:700;color:var(--status);letter-spacing:1px}
.status-score{display:block;font-size:1.5rem;font-weight:700}
.narrative{color:#c9d1d9;margin:12px 0 16px;font-size:.94rem}
.params{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px}
.param{background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:12px 14px}
.param-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
.param-name{font-size:.82rem;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}
.param-latest{font-size:1.05rem;font-weight:700}
.param-latest small{font-weight:400;color:#8b949e;font-size:.7rem}
.param-foot{display:flex;justify-content:space-between;color:#8b949e;font-size:.72rem;margin-top:5px;flex-wrap:wrap;gap:4px}
.rules{list-style:none;margin-top:8px}
.rule{font-size:.76rem;padding:2px 8px;border-radius:5px;margin:3px 0;display:block}
.rule-critical{background:#3d1215;color:#ff7b72;border-left:3px solid #e74c3c}
.rule-warning{background:#3a2f10;color:#f0c674;border-left:3px solid #e67e22}
.rule-info{background:#12233a;color:#79c0ff;border-left:3px solid #4fc3f7}
.rule-ok{background:#10281a;color:#56d364;border-left:3px solid #2ecc71}
.method{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px 20px;margin-top:34px;font-size:.9rem}
.method h2{margin-bottom:8px}
.method p{margin:8px 0;color:#c9d1d9}
.method code{background:#0d1117;padding:1px 5px;border-radius:4px}
footer{margin-top:30px;color:#8b949e;font-size:.8rem;border-top:1px solid #21262d;padding-top:14px}
"""


def render_dashboard(assessments: list[dict], generated_at: str | None = None,
                     window_days: int = 180) -> str:
    """Full HTML document for the assessment set (worst-first watch list)."""
    from .analysis import rank_at_risk

    generated_at = generated_at or time.strftime(
        "%Y-%m-%d %H:%M UTC", time.gmtime())
    ranked = rank_at_risk(assessments)
    counts = {s: sum(1 for a in assessments if a["status"] == s)
              for s in STATUS_COLORS}
    legend = "".join(
        f'<span><span class="dot" style="background:{STATUS_COLORS[s]}"></span>'
        f"{s.title()} ({counts[s]})</span>"
        for s in ("good", "moderate", "poor", "bad")
    )
    watch_items = "".join(
        f'<li><span class="badge" style="background:{STATUS_COLORS[a["status"]]}22;'
        f'color:{STATUS_COLORS[a["status"]]};border:1px solid {STATUS_COLORS[a["status"]]}">'
        f'{a["status"].upper()} {a["score"]:.0f}</span>'
        f'<a href="#site-{_esc(a["site"]["id"])}">{_esc(a["site"]["name"])}</a></li>'
        for a in ranked[:5]
    )
    sections = "".join(_site_section(a) for a in ranked)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>aqua-signal &mdash; urban freshwater health dashboard</title>
<meta name="description" content="AI-supported screening of urban river health from open USGS sensor data.">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>aqua-signal</h1>
  <p class="sub">Urban freshwater health screening from open USGS continuous
     water-quality monitors &middot; {len(assessments)} sites &middot;
     last {window_days} days &middot; generated {_esc(generated_at)}</p>
  <div class="legend">{legend}</div>
  <div class="watch">
    <h2>Watch list &mdash; sites trending toward poor status</h2>
    <ol>{watch_items}</ol>
  </div>
  {sections}
  <div class="method">
    <h2>Methodology &amp; honesty notes</h2>
    <p><strong>Data.</strong> Daily-mean values for water temperature (00010),
       dissolved oxygen (00300), pH (00400) and turbidity (63680) from the
       USGS National Water Information System daily-values service
       (<code>waterservices.usgs.gov/nwis/dv</code>), a free no-key public API.
       Not every site reports every parameter; only reported series are shown.</p>
    <p><strong>Assessment engine.</strong> A transparent rules+statistics
       module: published-style threshold rules (e.g. EPA pH 6.5&ndash;9.0,
       DO &ge; 5&nbsp;mg/L), seasonality-free year-over-year comparison of the
       last 30 days against the same calendar window one year earlier (trend
       rules fire from this, so the normal spring-to-autumn warming cycle is
       not mistaken for degradation), a raw Mann-Kendall + Sen's slope shown
       for context, and a 30-day rolling z-score anomaly detector
       (|z| &ge; 2.5). Every flag on this page names the rule that produced
       it.</p>
    <p><strong>Limits.</strong> Status classes (good/moderate/poor/bad) are an
       illustrative screening heuristic inspired by the EU Water Framework
       Directive ladder &mdash; <em>not</em> regulatory determinations.
       Composite scores average per-parameter penalties and do not replace
       biological or chemical assessment by professionals.</p>
    <p><strong>AI disclosure.</strong> This project was built with AI coding
       assistance; the assessment logic itself is deterministic and fully
       auditable in <code>aquasignal/analysis.py</code>.</p>
  </div>
  <footer>
    aqua-signal &middot; built for the OneAquaHealth IEEE Global Hackathon
    (Data-to-Insight track) &middot; source:
    <a href="https://github.com/ntoledo319/aqua-signal">github.com/ntoledo319/aqua-signal</a>
    &middot; data &copy; USGS (public domain)
  </footer>
</div>
</body>
</html>
"""
