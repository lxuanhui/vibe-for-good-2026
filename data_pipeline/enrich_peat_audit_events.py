"""Attach deterministic, offline Indonesian peat context to demo events.

Run once after ``peat_context`` has created its cached Indonesia crop:
``python -m data_pipeline.enrich_peat_audit_events --finalize``.  It never
changes FIRMS coordinates, clustering, or event IDs; it only adds geometric
context EvidenceObjects to the committed detail artifact used by the API.
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

from data_pipeline.enrichment.peat_context import (
    compute_peat_context,
    load_peat_raster,
    to_evidence_objects,
)

ROOT = Path(__file__).resolve().parent.parent
DETAIL_PATH = ROOT / "backend" / "app" / "data" / "audit_triage_detail.json.gz"
EVENTS_PATH = ROOT / "backend" / "app" / "data" / "audit_events.json.gz"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true", help="write the enriched committed artifact")
    args = parser.parse_args()
    with gzip.open(EVENTS_PATH, "rt", encoding="utf-8") as handle:
        events = json.load(handle)["audits"]["demo-2019-haze"]["events"]
    with gzip.open(DETAIL_PATH, "rt", encoding="utf-8") as handle:
        detail = json.load(handle)
    raster = load_peat_raster()
    changed = 0
    for event in events:
        item = SimpleNamespace(
            event_id=event["eventId"],
            centroid=(event["centroid"]["lat"], event["centroid"]["lon"]),
            bbox=event["bbox"],
            spatial_extent_km=event["spatialExtentKm"],
        )
        peat = to_evidence_objects(compute_peat_context(item, raster))
        current = detail["demo-2019-haze"][event["eventId"]]
        existing = current.get("derivedEvidence", [])
        current["derivedEvidence"] = [value for value in existing if value.get("category") != "peat"] + peat
        changed += 1
    print(f"Prepared peat context for {changed} FireEvents.")
    if args.finalize:
        with gzip.open(DETAIL_PATH, "wt", encoding="utf-8") as handle:
            json.dump(detail, handle, separators=(",", ":"))
        print(f"Wrote {DETAIL_PATH}")
    else:
        print("Dry run only; pass --finalize to write.")


if __name__ == "__main__":
    main()
