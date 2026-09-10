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
OVERLAY_PATH = ROOT / "frontend" / "public" / "peatland-indonesia.geojson"


def export_overlay(path: Path) -> None:
    """Create a deterministic ~4.5 km visual peatland overlay from the cache."""
    raster = load_peat_raster()
    stride = 4
    rows, cols = raster.array.shape
    polygons = []
    for row in range(0, rows, stride):
        hits = []
        for col in range(0, cols, stride):
            block = raster.array[row:min(rows, row + stride), col:min(cols, col + stride)]
            hits.append(bool(((block == 1) | (block == 2)).any()))
        start = None
        for index, peat in enumerate([*hits, False]):
            if peat and start is None:
                start = index
            elif not peat and start is not None:
                west = raster.origin_lon + (start * stride - 0.5) * raster.pixel_size_deg
                east = raster.origin_lon + (index * stride - 0.5) * raster.pixel_size_deg
                north = raster.origin_lat - (row - 0.5) * raster.pixel_size_deg
                south = raster.origin_lat - (min(rows, row + stride) - 0.5) * raster.pixel_size_deg
                polygons.append([[[west, south], [east, south], [east, north], [west, north], [west, south]]])
                start = None
    payload = {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "properties": {"source": "Greifswald Mire Centre: Global Peatland Map 2.0 (GPM 2022)", "display_resolution_km": 4.5},
        "geometry": {"type": "MultiPolygon", "coordinates": polygons},
    }]}
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote peatland display overlay to {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true", help="write the enriched committed artifact")
    parser.add_argument("--export-overlay", action="store_true", help="write the frontend peatland display overlay")
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
    if args.export_overlay:
        export_overlay(OVERLAY_PATH)


if __name__ == "__main__":
    main()
