"""Run every data-source feasibility check in sequence and report pass/fail.

This does not write to any database -- it is a feasibility check for the
ingestion jobs described in DesignSpecs/Environmental_Assurance_Spec.md
(§7 Data sources, §8 Persistence architecture). See README.md for the
per-source cadence this maps to.

`nasa_firms`, `open_meteo`, `nasa_power`, `copernicus_cds`, and
`global_peatland_database` return a normalized `SourceResult`
(`common/result.py`) so their PASS/FAIL/SKIPPED status and limitations can be
reported without this module knowing anything about their internals. The
remaining sources (`esa_worldcover`, `overpass_api`) are still plain spike
scripts that print and return `None`, outside issue #2's normalization
scope. `_run` treats "ran without raising, no SourceResult" as PASS for
those, unchanged from before this existed.
"""
from __future__ import annotations

import traceback

from data_pipeline.common.result import SourceResult
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


def _format(name: str, outcome: SourceResult | None) -> str:
    if outcome is None:
        # Legacy spike module: no SourceResult, no exception raised == PASS.
        return "PASS"
    label = outcome.status.value
    if outcome.error:
        return f"{label}: {outcome.error}"
    if outcome.summary:
        return f"{label}: {outcome.summary}"
    return label


def _run(sources: list) -> dict[str, str]:
    results = {}
    for name, fn in sources:
        try:
            outcome = fn()
        except Exception as exc:  # noqa: BLE001 -- this is a diagnostic runner
            results[name] = f"FAIL: {exc}"
            traceback.print_exc()
            continue
        results[name] = _format(name, outcome)
    return results


def main() -> None:
    results = _run(LIVE_SOURCES)
    results.update(_run(PENDING_ACCOUNT_SOURCES))

    print("\n=== SUMMARY ===")
    for name, result in results.items():
        print(f"{name:40s} {result}")


if __name__ == "__main__":
    main()
