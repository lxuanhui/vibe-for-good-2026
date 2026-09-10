"""Cache a small, provenance-preserving SMAP L4 PEATCLSM demo subset.

The NSIDC SPL4SMGP Version 7 product is the first version in this project
whose Catchment model includes PEATCLSM.  In addition to surface and root-zone
soil moisture, PEATCLSM provides water level relative to the peat surface.  A
water-table value is recorded only when that product variable is present in a
pre-clipped input.  The adapter never derives groundwater from soil moisture
or silently downloads a global archive.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

try:
    import h5py
except ImportError:  # pragma: no cover - catalog-only runs do not need HDF5
    h5py = None

from data_pipeline.common.http import SESSION
from data_pipeline.common.result import Provenance, SourceResult, SourceStatus
from data_pipeline.config import OUTPUT_DIR

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
PRODUCT = "NASA SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil Moisture Geophysical Data"
SHORT_NAME = "SPL4SMGP"
VERSION = "7"
DOI = "10.5067/EVKPQZ4AFC4D"
DEMO_BBOX = (116.0, -4.05, 116.5, -3.55)
DEMO_WINDOW = ("2019-09-01", "2019-09-10")
SPATIAL_RESOLUTION = "9 km EASE-Grid 2.0 (EPSG:6933)"
STORAGE_POLICY = {
    "raw": "NONE",
    "metadata": "METADATA_STORE",
    "cache": "DISPOSABLE_CACHE",
    "cache_ttl": 31536000,
}

LIMITATIONS = [
    "SMAP L4 is a model analysis informed by SMAP radiometer observations, not a well measurement.",
    "Water-table depth is only available for peat pixels where the PEATCLSM variable is present; it is not a well measurement.",
    "A 9 km grid cell is much coarser than a management unit and is not a local groundwater observation.",
    "PEATCLSM applicability is model-context metadata; this cache does not infer peat combustion or fire persistence.",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest(
    *, retrieved_at: str, granules: list[dict[str, Any]], artifacts: list[dict[str, Any]],
    groundwater_available: bool,
) -> dict[str, Any]:
    return {
        "product": PRODUCT,
        "short_name": SHORT_NAME,
        "version": VERSION,
        "doi": DOI,
        "provider": "NASA NSIDC DAAC",
        "variables": {
            "surface_soil_moisture": {"unit": "m3/m3", "depth": "0-5 cm vertical average"},
            "root_zone_soil_moisture": {"unit": "m3/m3", "depth": "0-100 cm vertical average"},
            "groundwater_water_table_depth": {
                "variable": "depth_to_water_table_from_surface_in_peat",
                "unit": "m" if groundwater_available else None,
                "depth_reference": "peat surface" if groundwater_available else None,
                "status": "available" if groundwater_available else "unavailable",
                "reason": (
                    "Valid PEATCLSM water-level rows were extracted."
                    if groundwater_available else
                    "No valid PEATCLSM water-level rows were supplied; no value was substituted."
                ),
            },
            "free_surface_water_on_peat_flux": {
                "unit": "kg m-2 s-1",
                "valid_range": [-0.001, 0.001],
                "status": "available_if_present",
            },
        },
        "temporal_coverage": {"start": DEMO_WINDOW[0], "end": DEMO_WINDOW[1], "resolution": "3 hour"},
        "spatial_coverage": {"bbox": list(DEMO_BBOX), "resolution": SPATIAL_RESOLUTION},
        "retrieved_at": retrieved_at,
        "processing": [
            "CMR granules were restricted to the demo bbox and inclusive UTC dates.",
            "Only pre-clipped inputs are accepted for extraction; no full global SAFE/archive is downloaded.",
            "HDF5 fill values, sentinel values, and non-finite values are omitted; values retain product units.",
        ],
        "limitations": LIMITATIONS,
        "storage_policy": STORAGE_POLICY,
        "granules": granules,
        "artifacts": artifacts,
    }


def search_granules(
    session=SESSION, *, bbox=DEMO_BBOX, start=DEMO_WINDOW[0], end=DEMO_WINDOW[1]
) -> list[dict[str, Any]]:
    """Return compact CMR records; this request does not require EDL login."""
    response = session.get(
        CMR_URL,
        params={
            "short_name": SHORT_NAME,
            "version": VERSION,
            "bounding_box": ",".join(str(value) for value in bbox),
            "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z",
            "page_size": 200,
        },
    )
    response.raise_for_status()
    records = []
    for item in response.json().get("feed", {}).get("entry", []):
        links = [link.get("href") for link in item.get("links", []) if link.get("href")]
        records.append({"id": item.get("id"), "time": item.get("time_start"), "links": links})
    return records


def _datasets(group: h5py.Group, prefix: str = "") -> Iterable[tuple[str, h5py.Dataset]]:
    for name, item in group.items():
        path = f"{prefix}/{name}" if prefix else name
        if isinstance(item, h5py.Dataset):
            yield path, item
        elif isinstance(item, h5py.Group):
            yield from _datasets(item, path)


def extract_clipped_rows(source_file: Path, *, bbox=DEMO_BBOX) -> list[dict[str, float]]:
    """Extract rows from a small HDF5 fixture/pre-clipped input.

    The source must expose latitude/longitude datasets and one or both named
    soil-moisture datasets.  Requiring explicit coordinates avoids pretending
    that an arbitrary HDF5 index is geographic.
    """
    if h5py is None:
        raise RuntimeError("HDF5 extraction requires the data-pipeline h5py dependency")
    with h5py.File(source_file, "r") as handle:
        datasets = dict(_datasets(handle))

        def find(*names: str) -> np.ndarray | None:
            for path, dataset in datasets.items():
                if path.rsplit("/", 1)[-1].lower() in names:
                    return np.asarray(dataset[()])
            return None

        latitudes = find("latitude", "lat")
        longitudes = find("longitude", "lon", "lng")
        surface = find("sm_surface", "surface_soil_moisture")
        root = find("sm_rootzone", "root_zone_soil_moisture")
        water_table = find(
            "depth_to_water_table_from_surface_in_peat",
            "depth_to_water_table_from_surface",
            "water_table_depth",
        )
        free_surface_flux = find("free_surface_water_on_peat_flux")
        if latitudes is None or longitudes is None or (surface is None and root is None and water_table is None):
            raise ValueError(
                "pre-clipped HDF5 must contain latitude/longitude and a SMAP moisture or PEATCLSM dataset"
            )
        arrays = [
            np.asarray(value).reshape(-1)
            for value in (latitudes, longitudes, surface, root, water_table, free_surface_flux)
            if value is not None
        ]
        size = len(arrays[0])
        if any(len(array) != size for array in arrays):
            raise ValueError("SMAP coordinate and variable arrays must have equal lengths")
        rows = []
        for index in range(size):
            lat, lon = float(arrays[0][index]), float(arrays[1][index])
            if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
                continue
            row: dict[str, float] = {"latitude": lat, "longitude": lon}
            surface_value = surface.reshape(-1)[index] if surface is not None else None
            root_value = root.reshape(-1)[index] if root is not None else None
            water_table_value = water_table.reshape(-1)[index] if water_table is not None else None
            flux_value = free_surface_flux.reshape(-1)[index] if free_surface_flux is not None else None
            if surface_value is not None and _valid(surface_value, 0, 1):
                row["surface_soil_moisture_m3_m3"] = float(surface_value)
            if root_value is not None and _valid(root_value, 0, 1):
                row["root_zone_soil_moisture_m3_m3"] = float(root_value)
            # Negative is below the peat surface (drained/degraded peat can sit
            # metres down in the dry season this demo covers); positive is
            # shallow ponding above it, which peat rarely holds more than ~15cm
            # of -- a larger positive reading is a sentinel/unit issue, not water.
            if water_table_value is not None and _valid(water_table_value, -5, 0.15):
                row["depth_to_water_table_from_surface_in_peat_m"] = float(water_table_value)
            if flux_value is not None and _valid(flux_value, -0.001, 0.001):
                row["free_surface_water_on_peat_flux_kg_m2_s"] = float(flux_value)
            if len(row) > 2:
                rows.append(row)
        return rows


def _valid(value: Any, lower: float | None = None, upper: float | None = None) -> bool:
    """Reject HDF5 fill/sentinel values while preserving signed water levels."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(numeric) or abs(numeric) >= 9990:
        return False
    return (lower is None or numeric >= lower) and (upper is None or numeric <= upper)


def build_cache(
    output_dir: Path = OUTPUT_DIR, *, source_file: Path | None = None, session=SESSION
) -> SourceResult:
    retrieved_at = _now()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        granules = search_granules(session=session)
    except Exception as exc:  # noqa: BLE001 -- normalized source outcome
        return SourceResult(
            SHORT_NAME,
            SourceStatus.FAILED,
            Provenance(CMR_URL, retrieved_at),
            LIMITATIONS,
            error=str(exc),
        )

    artifacts: list[dict[str, Any]] = []
    groundwater_path = output_dir / "groundwater_context_2019_demo.json"
    rows: list[dict[str, float]] = []
    if source_file is not None:
        rows = extract_clipped_rows(source_file)
    water_table_rows = [row for row in rows if "depth_to_water_table_from_surface_in_peat_m" in row]
    groundwater_available = bool(water_table_rows)
    groundwater_path.write_text(json.dumps({
        "variable": "groundwater_water_table_depth",
        "source_variable": "depth_to_water_table_from_surface_in_peat",
        "status": "available" if groundwater_available else "unavailable",
        "unit": "m" if groundwater_available else None,
        "reference": "mean peat-surface elevation" if groundwater_available else None,
        "values_artifact": "smap_peatclsm_2019_demo.csv" if groundwater_available else None,
        "source_product": SHORT_NAME,
        "temporal_coverage": {"start": DEMO_WINDOW[0], "end": DEMO_WINDOW[1]},
        "spatial_coverage": {"bbox": list(DEMO_BBOX)},
        "retrieved_at": retrieved_at,
        "limitation": (
            "PEATCLSM water level is available only for valid peat pixels in the input subset. "
            "No groundwater value is inferred from soil moisture."
            if groundwater_available
            else "No valid PEATCLSM water-table variable was supplied; no groundwater value was inferred from soil moisture."
        ),
    }, indent=2) + "\n", encoding="utf-8")
    artifacts.append({
        "path": groundwater_path.name,
        "status": "available" if groundwater_available else "unavailable",
        "sha256": hashlib.sha256(groundwater_path.read_bytes()).hexdigest(),
    })
    if source_file is not None:
        csv_path = output_dir / "smap_peatclsm_2019_demo.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            fields = [
                "latitude", "longitude", "surface_soil_moisture_m3_m3",
                "root_zone_soil_moisture_m3_m3",
                "depth_to_water_table_from_surface_in_peat_m",
                "free_surface_water_on_peat_flux_kg_m2_s",
            ]
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        artifacts.append({
            "path": csv_path.name,
            "rows": len(rows),
            "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        })
    else:
        artifacts.append({
            "path": None,
            "status": "not_downloaded",
            "reason": (
                "A pre-clipped HDF5 input or an authenticated server-side subset is required; "
                "no global archive was downloaded."
            ),
        })

    manifest = _manifest(
        retrieved_at=retrieved_at,
        granules=granules,
        artifacts=artifacts,
        groundwater_available=groundwater_available,
    )
    manifest_path = output_dir / "smap_peatclsm_2019_demo.metadata.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    status = SourceStatus.OK if source_file is not None and rows else SourceStatus.SKIPPED
    summary = (
        f"{len(granules)} CMR granules; "
        f"{'cached clipped rows' if source_file is not None else 'catalogued only'}"
    )
    return SourceResult(
        SHORT_NAME,
        status,
        Provenance(CMR_URL, retrieved_at),
        LIMITATIONS,
        summary=summary,
        data=manifest,
    )


def fetch_historical_sample() -> SourceResult:
    """Run the safe catalog-only default used by ``data_pipeline.run_all``."""
    return build_cache()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-file",
        type=Path,
        help="pre-clipped HDF5 input; global granules are never downloaded",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    result = build_cache(args.output_dir, source_file=args.source_file)
    print(f"{result.status.value}: {result.summary or result.error}")


if __name__ == "__main__":
    main()
