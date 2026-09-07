"""Run every data-source feasibility check in sequence and report pass/fail.

This does not write to any database -- it is a feasibility check for the
ingestion cron jobs described in DesignSpecs/environmental_assurance_spec_v2.md
(Sections 4, 5, 11). See README.md for the per-source cadence this maps to.
"""
from __future__ import annotations

import traceback

from data_pipeline.sources import (
    copernicus_cds,
    esa_worldcover,
    global_peatland_database,
    nasa_firms,
    nasa_power,
    open_meteo,
    overpass_api,
)
from data_pipeline.sources.future import bmkg, global_forest_watch

LIVE_SOURCES = [
    ("NASA FIRMS", nasa_firms.fetch_historical_sample),
    ("Open-Meteo", open_meteo.fetch_historical_sample),
    ("NASA POWER", nasa_power.fetch_historical_sample),
    ("Copernicus Data Space Ecosystem", copernicus_cds.fetch_historical_sample),
    ("ESA WorldCover", esa_worldcover.fetch_historical_sample),
    ("Global Peatland Database", global_peatland_database.fetch_historical_sample),
    ("Overpass API (OSM)", overpass_api.fetch_historical_sample),
]

PENDING_ACCOUNT_SOURCES = [
    ("Global Forest Watch Data API", global_forest_watch.fetch_historical_sample),
    ("BMKG", bmkg.fetch_historical_sample),
]


def _run(sources: list) -> dict:
    results = {}
    for name, fn in sources:
        try:
            fn()
            results[name] = "OK"
        except Exception as exc:  # noqa: BLE001 -- this is a diagnostic runner
            results[name] = f"FAILED: {exc}"
            traceback.print_exc()
    return results


def main() -> None:
    results = _run(LIVE_SOURCES)
    results.update(_run(PENDING_ACCOUNT_SOURCES))

    print("\n=== SUMMARY ===")
    for name, result in results.items():
        print(f"{name:40s} {result}")


if __name__ == "__main__":
    main()
