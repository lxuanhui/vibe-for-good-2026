"""Convert a pipeline output CSV into GeoJSON the web console can render
directly, as a proof of concept that pipeline output can reach the UI.

Usage:
    python -m data_pipeline.export_web_geojson

Reads output/firms_2019_haze_sample.csv (the 2019 Sumatra/Kalimantan haze
window pull -- see README.md) and writes one combined FeatureCollection to
apps/web/public/pipeline/firms-2019-09.json (a static asset fetched at
runtime, not bundled), keyed by acquisition date.
"""

import csv
import json
from pathlib import Path

CONFIDENCE_LABELS = {"h": "high", "n": "nominal", "l": "low"}

SOURCE_CSV = Path(__file__).parent / "output" / "firms_2019_haze_sample.csv"
DEST_JSON = Path(__file__).parent.parent / "apps" / "web" / "public" / "pipeline" / "firms-2019-09.json"


def main() -> None:
    by_date: dict[str, list[dict]] = {}

    with SOURCE_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            date = row["acq_date"]
            hhmm = row["acq_time"].zfill(4)
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude"]), float(row["latitude"])],
                },
                "properties": {
                    "frp": float(row["frp"]),
                    "confidence": CONFIDENCE_LABELS.get(row["confidence"], row["confidence"]),
                    "acquiredAt": f"{date}T{hhmm[:2]}:{hhmm[2:]}:00Z",
                },
            }
            by_date.setdefault(date, []).append(feature)

    out = {date: {"type": "FeatureCollection", "features": feats} for date, feats in sorted(by_date.items())}

    DEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    DEST_JSON.write_text(json.dumps(out), encoding="utf-8")

    total = sum(len(v["features"]) for v in out.values())
    print(f"wrote {total} points across {len(out)} dates -> {DEST_JSON}")
    for date, fc in out.items():
        print(f"  {date}: {len(fc['features'])} points")


if __name__ == "__main__":
    main()
