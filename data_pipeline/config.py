"""Shared configuration for the data-source feasibility scripts.

This is a research spike: each module in `sources/` proves an API can be
reached and can return *historical* data for real Indonesian coordinates.
Nothing here writes to a database yet -- see README.md for the planned
cron/DB wiring once a source is confirmed workable.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --- Credentials -------------------------------------------------------
NASA_FIRMS_MAP_KEY = os.environ.get("NASA_FIRMS_MAP_KEY", "")
CDSE_USERNAME = os.environ.get("CDSE_USERNAME", "")
CDSE_PASSWORD = os.environ.get("CDSE_PASSWORD", "")

# Sources the user is registering for separately -- wired for later use,
# see sources/future/.
GFW_API_KEY = os.environ.get("GFW_API_KEY", "")
BMKG_API_KEY = os.environ.get("BMKG_API_KEY", "")

# --- Indonesian points of interest --------------------------------------
# Real peat-fire-prone locations, used everywhere instead of a country
# centroid, specifically to prove per-point (not national-aggregate)
# retrieval where that distinction matters (Open-Meteo).
POINTS: dict[str, tuple[float, float]] = {
    "riau_peatland": (1.05, 101.45),                     # Bengkalis/Siak peat coast, Riau, Sumatra
    "central_kalimantan_ex_mega_rice": (-2.50, 114.00),  # Ex-Mega Rice Project peatland, Central Kalimantan
    "south_sumatra_oki": (-3.20, 104.80),                # Ogan Komering Ilir peatland, South Sumatra
}

# west, south, east, north
INDONESIA_BBOX = (95.0, -11.0, 141.0, 6.0)
SUMATRA_KALIMANTAN_BBOX = (95.0, -6.0, 119.0, 6.0)

# The 2019 Indonesia haze crisis -- one of the worst peat-fire seasons on
# record, and a good stress test for "does the archive actually reach
# this far back" across every source below.
HISTORICAL_WINDOW = ("2019-09-01", "2019-09-10")
