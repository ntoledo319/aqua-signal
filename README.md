# aqua-signal

**Urban freshwater health, screened from open public sensors.**

aqua-signal turns free, no-key USGS water-quality APIs into a self-contained
static dashboard that answers one question for 10 urban rivers across the
United States: *is this water getting better or worse?*

Built for the **OneAquaHealth IEEE Global Hackathon** (Data-to-Insight track).

![status](https://img.shields.io/badge/tests-43%20passing-brightgreen)
![deps](https://img.shields.io/badge/runtime%20dependencies-zero-blue)

## What it does

- **Fetches real open data** — daily-mean water temperature, dissolved oxygen,
  pH and turbidity for 10 active USGS continuous monitors on urban rivers
  (Philadelphia, Trenton, Washington DC, Pittsburgh, Cleveland, Clinton IA,
  Atlanta, Portland, Wilmington DE metro, Baton Rouge) via the
  [USGS NWIS daily-values service](https://waterservices.usgs.gov/) — free,
  public, no API key.
- **AI-supported assessment** — a transparent rules+statistics engine
  (`aquasignal/analysis.py`) screens every site for signs it is trending
  toward poor ecological status:
  - published-style threshold rules (EPA pH 6.5–9.0, DO ≥ 5 mg/L
    warmwater criterion, temperature/turbidity stress bands),
  - **seasonality-free year-over-year comparison** (last 30 days vs the same
    calendar window one year earlier — so normal spring warming is not
    mistaken for degradation),
  - Mann-Kendall trend test with tie-corrected variance + Sen's slope
    (displayed for context),
  - a 30-day rolling z-score anomaly detector (|z| ≥ 2.5),
  - a generated plain-language narrative per site naming every rule that fired.
- **Renders a zero-dependency static dashboard** — one self-contained
  `index.html` with inline SVG charts, status badges and a worst-first watch
  list. No JavaScript, no build step, no runtime dependencies; host it on
  GitHub Pages or open it from disk.

## Honesty notes

- Status classes (good / moderate / poor / bad) are an **illustrative
  screening heuristic** inspired by the EU Water Framework Directive's
  ecological-status ladder and common EPA freshwater criteria. They are
  **not** regulatory determinations and do not replace biological or chemical
  assessment by professionals.
- No machine-learning model is trained. The "AI support" is an auditable
  decision-support engine: every flag names the rule and the numbers behind
  it. The project itself was built with AI coding assistance (see below).
- Not every monitor reports every parameter; the dashboard shows only the
  series each site actually reports.

## Quick start

Requires Python ≥ 3.10. Nothing else.

```bash
# fetch live data from USGS + build the dashboard
python3 -m aquasignal all

# rebuild offline from the cached data in data/
python3 -m aquasignal all --offline

# run the test suite (43 tests, stdlib unittest, no network)
python3 -m unittest discover -s tests
```

Output lands in `site/index.html`. The committed `site/` and `data/`
directories contain a real build from 2026-09-24 so the repo is browsable
without running anything.

## Layout

```
aquasignal/
  sites.py     site registry (verified live USGS monitors)
  fetch.py     NWIS daily-values client: retry, cache, min/mean/max selection
  analysis.py  rules engine + statistics (the "AI-supported assessment")
  render.py    static HTML + inline SVG renderer
tests/         43 offline tests, incl. a real captured USGS API fixture
data/          JSON cache of fetched series (committed for reproducibility)
site/          the built dashboard
```

## Data & credits

- Data: USGS National Water Information System (`waterservices.usgs.gov`),
  public domain. Parameter codes 00010 / 00300 / 00400 / 63680.
- Screening criteria inspired by EPA aquatic-life criteria and the EU Water
  Framework Directive status ladder; thresholds are centralized in
  `aquasignal/analysis.py: RULES` and are meant to be tuned or replaced with
  locally calibrated values.

## AI assistance disclosure

This project was designed and implemented with AI coding assistance
(Kimi Code) under human direction. All assessment logic is deterministic,
documented, and test-covered; all data shown is fetched from the cited
public USGS APIs and can be independently reproduced with
`python3 -m aquasignal all`.

## License

MIT (code). USGS data is public domain.
