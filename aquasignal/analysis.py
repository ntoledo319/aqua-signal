"""AI-supported assessment engine: transparent rules + statistics.

This module is deliberately *not* a black box. Every flag the dashboard shows
is traceable to (a) a published-style threshold rule, (b) a seasonality-free
year-over-year comparison (last 30 days vs the same calendar window one year
earlier), or (c) a rolling z-score anomaly detector. A raw Mann-Kendall test
with Sen's slope is also computed and displayed for context, but trend rules
fire from the YoY delta because MK over a short record is dominated by the
seasonal cycle (every river warms from spring to autumn). No machine-learning
model is trained; the "AI support" is an auditable decision-support engine
that reads sensor data and writes a plain-language assessment a human
reviewer can verify.

Status classes (good / moderate / poor / bad) are an *illustrative heuristic*
inspired by the EU Water Framework Directive's ecological-status ladder and
common EPA freshwater criteria (pH 6.5-9.0; DO >= 5 mg/L for warmwater
aquatic life). They are NOT regulatory determinations.

Thresholds are centralized in RULES so they can be tuned or replaced with
locally calibrated values.
"""

from __future__ import annotations

import math
from statistics import mean, median

# ---------------------------------------------------------------------------
# Threshold rules (per USGS parameter code)
# ---------------------------------------------------------------------------

RULES = {
    "00300": {  # dissolved oxygen, mg/L
        "bad_below": 3.0,      # acute hypoxia stress for most fish
        "warn_below": 5.0,     # EPA warmwater early-life-stage criterion
        "good_direction": "up",
        "rationale": "Dissolved oxygen below 5 mg/L stresses warmwater fish; "
                     "below 3 mg/L is acutely hazardous.",
    },
    "00400": {  # pH
        "bad_low": 5.5,
        "warn_low": 6.5,       # EPA chronic criterion lower bound
        "warn_high": 9.0,      # EPA chronic criterion upper bound
        "bad_high": 9.6,
        "good_direction": "stable",
        "rationale": "EPA aquatic-life criterion: pH should stay within 6.5-9.0.",
    },
    "00010": {  # water temperature, deg C
        "warn_above": 27.0,    # general warmwater stress band
        "bad_above": 31.0,
        "good_direction": "down_or_stable",
        "rationale": "Sustained water temperature above ~27 C raises stress "
                     "and lowers oxygen solubility in warmwater rivers.",
    },
    "63680": {  # turbidity, FNU
        "warn_above": 50.0,    # persistent cloudiness; smothers habitat
        "bad_above": 150.0,
        "good_direction": "down",
        "rationale": "Turbidity persistently above ~50 FNU degrades spawning "
                     "habitat and light penetration.",
    },
}

TREND_P_SIGNIFICANT = 0.10  # generous alpha: screening tool, not a regulator
ANOMALY_Z = 2.5
ROLLING_WINDOW = 30

STATUS_CLASSES = ["good", "moderate", "poor", "bad"]


# ---------------------------------------------------------------------------
# Basic statistics
# ---------------------------------------------------------------------------

def series_stats(values: list[float]) -> dict:
    if not values:
        raise ValueError("series_stats needs at least one value")
    return {
        "n": len(values),
        "min": min(values),
        "max": max(values),
        "mean": mean(values),
        "median": median(values),
        "latest": values[-1],
    }


def ols_slope(values: list[float]) -> float:
    """Least-squares slope in units/day over the series index."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = range(n)
    mx = (n - 1) / 2.0
    my = mean(values)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, values))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def mann_kendall(values: list[float]) -> dict:
    """Mann-Kendall trend test with tie correction.

    Returns {'s', 'z', 'p', 'trend'} where trend is
    'increasing' | 'decreasing' | 'none' at TREND_P_SIGNIFICANT.
    Normal approximation; valid for n >= ~10. For smaller n the test
    reports trend 'none' with p=1.0.
    """
    n = len(values)
    if n < 10:
        return {"s": 0, "z": 0.0, "p": 1.0, "trend": "none"}
    s = 0
    for i in range(n - 1):
        vi = values[i]
        for j in range(i + 1, n):
            d = values[j] - vi
            s += (d > 0) - (d < 0)
    # tie correction
    counts: dict[float, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    tie_term = sum(t * (t - 1) * (2 * t + 5) for t in counts.values())
    var = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var <= 0 or s == 0:
        z = 0.0
    else:
        z = (s - 1 if s > 0 else s + 1) / math.sqrt(var)
    p = 2.0 * (1.0 - _norm_cdf(abs(z)))
    trend = "none"
    if p < TREND_P_SIGNIFICANT:
        trend = "increasing" if s > 0 else "decreasing"
    return {"s": s, "z": z, "p": p, "trend": trend}


def sens_slope(values: list[float]) -> float:
    """Sen's slope: median of all pairwise slopes (units/day)."""
    n = len(values)
    if n < 2:
        return 0.0
    slopes = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            d = values[j] - values[i]
            if d != 0:
                slopes.append(d / (j - i))
    return median(slopes) if slopes else 0.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def detect_anomalies(values: list[float], window: int = ROLLING_WINDOW,
                     z_limit: float = ANOMALY_Z) -> list[dict]:
    """Rolling z-score anomaly detection.

    A point is anomalous when it deviates more than z_limit standard
    deviations from the trailing `window`-day mean. Returns a list of
    {'index', 'value', 'z'} for anomalous points.
    """
    hits = []
    for i in range(window, len(values)):
        hist = values[i - window:i]
        mu = mean(hist)
        sd = math.sqrt(sum((v - mu) ** 2 for v in hist) / len(hist))
        if sd == 0:
            continue
        z = (values[i] - mu) / sd
        if abs(z) >= z_limit:
            hits.append({"index": i, "value": values[i], "z": round(z, 2)})
    return hits


def yoy_compare(dates: list[str], values: list[float],
                window: int = 30) -> dict | None:
    """Seasonality-free trend evidence: last `window` days vs the same
    calendar window one year earlier.

    Pairs points by (month, day). Returns {'recent_mean', 'prior_mean',
    'delta', 'pairs'} or None when fewer than half the window pairs exist.
    This is the primary trend signal for rule-firing because a raw
    Mann-Kendall over a short record is dominated by the seasonal cycle
    (every river warms from spring to autumn).
    """
    by_mmdd: dict[tuple[int, int], dict[int, float]] = {}
    for d, v in zip(dates, values):
        try:
            y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
        except (ValueError, IndexError):
            continue
        by_mmdd.setdefault((m, dd), {})[y] = v
    years = sorted({y for yrs in by_mmdd.values() for y in yrs})
    if len(years) < 2:
        return None
    recent_y, prior_y = years[-1], years[-2]
    recent_days = sorted(
        (k for k, yrs in by_mmdd.items() if recent_y in yrs),
        key=lambda k: k,
    )[-window:]
    recent_vals, prior_vals = [], []
    for k in recent_days:
        yrs = by_mmdd[k]
        if prior_y in yrs:
            recent_vals.append(yrs[recent_y])
            prior_vals.append(yrs[prior_y])
    if len(recent_vals) < window // 2:
        return None
    rm, pm = mean(recent_vals), mean(prior_vals)
    return {
        "recent_mean": rm,
        "prior_mean": pm,
        "delta": rm - pm,
        "pairs": len(recent_vals),
        "recent_year": recent_y,
        "prior_year": prior_y,
    }


# ---------------------------------------------------------------------------
# Rules engine + composite assessment
# ---------------------------------------------------------------------------

def evaluate_parameter(code: str, points: list[tuple[str, float]]) -> dict:
    """Assess one parameter series of (iso_date, value) pairs.

    Returns stats, raw-window trend (Mann-Kendall/Sen, shown for context),
    seasonality-free year-over-year comparison, fired rules and a 0-100 score.
    Trend rules fire from the YoY delta, not the raw MK test, so the normal
    spring-to-autumn warming cycle does not masquerade as degradation.
    """
    dates = [d for d, _ in points]
    values = [v for _, v in points]
    stats = series_stats(values)
    mk = mann_kendall(values)
    sen = sens_slope(values)
    anomalies = detect_anomalies(values)
    yoy = yoy_compare(dates, values)
    rules = RULES.get(code, {})
    fired: list[dict] = []
    penalty = 0

    def fire(severity: str, rule: str, detail: str) -> None:
        fired.append({"severity": severity, "rule": rule, "detail": detail})

    latest = stats["latest"]
    tail_mean = mean(values[-14:]) if len(values) >= 14 else stats["mean"]

    if code == "00300":
        if latest < rules["bad_below"] or tail_mean < rules["bad_below"]:
            fire("critical", "do_severe",
                 f"DO {latest:.1f} mg/L below severe threshold {rules['bad_below']}")
            penalty += 40
        elif latest < rules["warn_below"] or tail_mean < rules["warn_below"]:
            fire("warning", "do_low",
                 f"DO {latest:.1f} mg/L below aquatic-life criterion {rules['warn_below']}")
            penalty += 18
        if yoy and yoy["delta"] <= -0.5:
            fire("warning", "do_declining_yoy",
                 f"DO {yoy['delta']:+.2f} mg/L vs same period {yoy['prior_year']} "
                 f"(last 30 days, {yoy['pairs']} day-pairs)")
            penalty += 12
    elif code == "00400":
        if latest < rules["bad_low"] or latest > rules["bad_high"]:
            fire("critical", "ph_extreme",
                 f"pH {latest:.2f} outside extreme bounds "
                 f"{rules['bad_low']}-{rules['bad_high']}")
            penalty += 40
        elif latest < rules["warn_low"] or latest > rules["warn_high"]:
            fire("warning", "ph_out_of_range",
                 f"pH {latest:.2f} outside EPA criterion "
                 f"{rules['warn_low']}-{rules['warn_high']}")
            penalty += 18
        if yoy and abs(yoy["delta"]) >= 0.3:
            fire("warning", "ph_shifting_yoy",
                 f"pH shifted {yoy['delta']:+.2f} vs same period {yoy['prior_year']}")
            penalty += 10
    elif code == "00010":
        if tail_mean > rules["bad_above"]:
            fire("critical", "temp_extreme",
                 f"14-day mean temperature {tail_mean:.1f} C above {rules['bad_above']}")
            penalty += 35
        elif tail_mean > rules["warn_above"]:
            fire("warning", "temp_high",
                 f"14-day mean temperature {tail_mean:.1f} C above {rules['warn_above']}")
            penalty += 15
        if yoy and yoy["delta"] >= 1.0:
            fire("warning", "temp_rising_yoy",
                 f"Water {yoy['delta']:+.2f} C warmer than same period "
                 f"{yoy['prior_year']} (last 30 days)")
            penalty += 12
    elif code == "63680":
        if tail_mean > rules["bad_above"]:
            fire("critical", "turbidity_extreme",
                 f"14-day mean turbidity {tail_mean:.0f} FNU above {rules['bad_above']}")
            penalty += 35
        elif tail_mean > rules["warn_above"]:
            fire("warning", "turbidity_high",
                 f"14-day mean turbidity {tail_mean:.0f} FNU above {rules['warn_above']}")
            penalty += 15
        if yoy and yoy["delta"] >= 10.0:
            fire("warning", "turbidity_rising_yoy",
                 f"Turbidity {yoy['delta']:+.1f} FNU above same period "
                 f"{yoy['prior_year']} (last 30 days)")
            penalty += 10

    recent_anoms = [a for a in anomalies if a["index"] >= len(values) - 14]
    if recent_anoms:
        worst = max(recent_anoms, key=lambda a: abs(a["z"]))
        fire("info", "anomaly",
             f"{len(recent_anoms)} anomalous reading(s) in last 14 days "
             f"(worst z={worst['z']:+.1f})")
        penalty += 5

    score = max(0, 100 - penalty)
    return {
        "code": code,
        "stats": stats,
        "trend": mk,
        "sens_slope": sen,
        "sens_slope_30d": sen * 30,
        "yoy": yoy,
        "anomalies": anomalies,
        "rules_fired": fired,
        "score": score,
        "dates": dates,
        "values": values,
    }


def classify(score: float) -> str:
    if score >= 80:
        return "good"
    if score >= 60:
        return "moderate"
    if score >= 35:
        return "poor"
    return "bad"


def assess_site(site: dict, series: dict[str, list]) -> dict:
    """Full assessment for one site. `series` maps param code -> [(date, val)]."""
    params = {}
    for code, points in sorted(series.items()):
        if len(points) < 7:
            continue
        params[code] = evaluate_parameter(code, points)
    if params:
        score = mean(p["score"] for p in params.values())
    else:
        score = 0.0
    status = classify(score)
    return {
        "site": site,
        "parameters": params,
        "score": round(score, 1),
        "status": status,
        "narrative": build_narrative(site, params, score, status),
    }


def build_narrative(site: dict, params: dict, score: float, status: str) -> str:
    """Plain-language assessment generated from fired rules + trends."""
    lines = [
        f"{site['name']} currently screens as {status.upper()} "
        f"(composite {score:.0f}/100)."
    ]
    criticals, warnings, infos = [], [], []
    for p in params.values():
        for r in p["rules_fired"]:
            (criticals if r["severity"] == "critical"
             else warnings if r["severity"] == "warning"
             else infos).append(r["detail"])
    if criticals:
        lines.append("Critical: " + "; ".join(criticals) + ".")
    if warnings:
        lines.append("Warnings: " + "; ".join(warnings) + ".")
    if not criticals and not warnings:
        lines.append(
            "No threshold rules fired and no significant adverse trends were "
            "detected in the analysis window."
        )
    if infos:
        lines.append("Notes: " + "; ".join(infos) + ".")
    lines.append(
        "This is an automated screening assessment from a transparent "
        "rules+statistics engine, not a regulatory determination."
    )
    return " ".join(lines)


def rank_at_risk(assessments: list[dict]) -> list[dict]:
    """Sites sorted worst-first — the 'watch list' ordering."""
    return sorted(assessments, key=lambda a: a["score"])
