"""Registry of monitored urban freshwater sites.

Every site is an active USGS continuous water-quality monitor on a river in or
directly adjacent to a major U.S. urban area. Verified live on 2026-09-24 via
the USGS NWIS instantaneous-values service (no API key required).

Parameter codes (USGS):
    00010  Temperature, water (deg C)
    00300  Dissolved oxygen (mg/L)
    00400  pH (standard units)
    63680  Turbidity (FNU)
"""

PARAMETERS = {
    "00010": {
        "short": "temp",
        "name": "Water temperature",
        "unit": "deg C",
    },
    "00300": {
        "short": "do",
        "name": "Dissolved oxygen",
        "unit": "mg/L",
    },
    "00400": {
        "short": "ph",
        "name": "pH",
        "unit": "std units",
    },
    "63680": {
        "short": "turbidity",
        "name": "Turbidity",
        "unit": "FNU",
    },
}

SITES = [
    {"id": "01474500", "name": "Schuylkill River at Philadelphia, PA",
     "city": "Philadelphia, PA", "huc": "02040203"},
    {"id": "01463500", "name": "Delaware River at Trenton, NJ",
     "city": "Trenton, NJ", "huc": "02040105"},
    {"id": "01646500", "name": "Potomac River near Wash, DC (Little Falls)",
     "city": "Washington, DC", "huc": "02070008"},
    {"id": "03085000", "name": "Monongahela River at Braddock, PA",
     "city": "Pittsburgh, PA", "huc": "05020005"},
    {"id": "04208000", "name": "Cuyahoga River at Independence, OH",
     "city": "Cleveland, OH", "huc": "04110002"},
    {"id": "05420500", "name": "Mississippi River at Clinton, IA",
     "city": "Clinton, IA", "huc": "07080101"},
    {"id": "02336000", "name": "Chattahoochee River at Atlanta, GA",
     "city": "Atlanta, GA", "huc": "03130001"},
    {"id": "14211720", "name": "Willamette River at Portland, OR",
     "city": "Portland, OR", "huc": "17090012"},
    {"id": "01481000", "name": "Brandywine Creek at Chadds Ford, PA",
     "city": "Wilmington, DE metro", "huc": "02040205"},
    {"id": "07374000", "name": "Mississippi River at Baton Rouge, LA",
     "city": "Baton Rouge, LA", "huc": "08070100"},
]
