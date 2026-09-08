"""Regenerate the golden historical fixtures under `data_pipeline/golden/<case_id>/`
from live sources. Run this only when a case's frozen inputs need to change
(e.g. a new case is added, or a source's response shape changes); the
regression test (`tests/test_golden_regression.py`) never touches the
network -- it reads exactly what this script writes.

    python -m data_pipeline.golden.build_golden_cases

Each case freezes, as real historical values (not synthetic data):
  observations.csv          -- the FIRMS detections belonging to this event,
                                sliced from the cached 2019 haze sample
  weather/om_hourly.csv      -- Open-Meteo/ERA5 hourly point data covering
                                every window `weather_enrichment` computes
  weather/power_daily.csv    -- NASA POWER daily point data, same range
  weather/baseline_rainfall.json -- 5 years of prior-year rainfall sums per
                                window (the exact input shape
                                `compute_weather_windows` takes; freezing the
                                already-reduced numbers avoids also needing
                                5 years of raw hourly baseline data per case)
  peat/raster_crop.npy + raster_transform.json -- a small crop of the real
                                Global Peatland Map 2.0 raster around this
                                event's footprint, padded 1 degree so the
                                default buffer/distance-search radii never
                                run past the crop edge
  imagery/sentinel{1,2}_*.json -- raw Copernicus STAC search responses

...and, from those frozen inputs, the expected outputs of the same pure
functions the real pipeline uses (`cluster_events`, `compute_weather_windows`,
`compute_peat_context`, plus this module's own STAC-feature-to-candidate
mapping) under `expected/`. The regression test recomputes each and asserts
equality -- that is the actual guarantee this issue asks for.
"""
from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd

from data_pipeline.clustering.firms_clustering import FireEvent, cluster_events
from data_pipeline.config import OUTPUT_DIR
from data_pipeline.enrichment import peat_context, weather_enrichment
from data_pipeline.golden.cases import (
    CASES,
    case_dir,
    expected_dir,
    imagery_dir,
    observations_path,
    peat_dir,
    strip_volatile,
    weather_dir,
)
from data_pipeline.sources import copernicus_cds, nasa_power
from data_pipeline.sources.open_meteo import _hourly_to_df, fetch_point

RASTER_CROP_PAD_DEG = 1.0
IMAGERY_BBOX_PAD_DEG = 0.2
BASELINE_YEARS = weather_enrichment.DEFAULT_BASELINE_YEARS

# Only the columns `weather_enrichment.compute_weather_windows` actually
# reads -- the rest of Open-Meteo's/POWER's response is real but irrelevant
# to this pipeline, so freezing it would only bloat the fixture.
OM_COLUMNS = [
    "date",
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_10m",
    "soil_moisture_0_to_7cm",
]
POWER_COLUMNS = ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]


def _event_from_observations(obs: pd.DataFrame) -> FireEvent:
    events, _ = cluster_events(obs)
    if len(events) != 1:
        raise ValueError(f"expected the frozen observations to form exactly one event, got {len(events)}")
    return events[0]


def _fetch_om_hourly(lat: float, lon: float, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    response = fetch_point(lat, lon, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    return _hourly_to_df(response)[OM_COLUMNS]


def _build_weather(case_id: str, event: FireEvent) -> None:
    lat, lon = event.centroid
    bounds = weather_enrichment.window_bounds(event)
    range_start = min(s for s, _ in bounds.values())
    range_end = max(e for _, e in bounds.values())

    wdir = weather_dir(case_id)
    wdir.mkdir(parents=True, exist_ok=True)

    om_hourly = _fetch_om_hourly(lat, lon, range_start, range_end)
    om_hourly.to_csv(wdir / "om_hourly.csv", index=False)

    power_json = nasa_power.fetch_daily(lat, lon, range_start.strftime("%Y%m%d"), range_end.strftime("%Y%m%d"))
    power_daily = weather_enrichment._power_json_to_df(power_json)
    present_cols = [c for c in POWER_COLUMNS if c in power_daily.columns]
    power_daily[present_cols].to_csv(wdir / "power_daily.csv", index_label="date")

    baseline_rainfall_by_window: dict[str, list[float]] = {name: [] for name in bounds}
    for years_back in range(1, BASELINE_YEARS + 1):
        shifted_start = range_start - pd.DateOffset(years=years_back)
        shifted_end = range_end - pd.DateOffset(years=years_back)
        shifted_hourly = _fetch_om_hourly(lat, lon, shifted_start, shifted_end)
        for name, (start, end) in bounds.items():
            sl = weather_enrichment._slice_hourly(
                shifted_hourly, start - pd.DateOffset(years=years_back), end - pd.DateOffset(years=years_back)
            )
            rainfall = weather_enrichment._rainfall_mm(sl)
            if rainfall is not None:
                baseline_rainfall_by_window[name].append(rainfall)
    (wdir / "baseline_rainfall.json").write_text(json.dumps(baseline_rainfall_by_window, indent=2))

    windows = weather_enrichment.compute_weather_windows(event, om_hourly, power_daily, baseline_rainfall_by_window)
    bundle = weather_enrichment.WeatherEvidenceBundle(event_id=event.event_id, centroid=(lat, lon), windows=windows)
    evidence = strip_volatile(weather_enrichment.to_evidence_objects(bundle))
    (expected_dir(case_id) / "weather_evidence.json").write_text(json.dumps(evidence, indent=2))


def _build_peat(case_id: str, event: FireEvent) -> None:
    full_raster = peat_context.load_peat_raster()
    west, south, east, north = event.bbox
    west, south = west - RASTER_CROP_PAD_DEG, south - RASTER_CROP_PAD_DEG
    east, north = east + RASTER_CROP_PAD_DEG, north + RASTER_CROP_PAD_DEG

    row_top, col_left = full_raster._to_pixel(north, west)
    row_bottom, col_right = full_raster._to_pixel(south, east)
    rows, cols = full_raster.array.shape
    row_min, row_max = max(0, row_top), min(rows, row_bottom + 1)
    col_min, col_max = max(0, col_left), min(cols, col_right + 1)

    crop = full_raster.array[row_min:row_max, col_min:col_max].copy()
    crop_origin_lat = full_raster.origin_lat - row_min * full_raster.pixel_size_deg
    crop_origin_lon = full_raster.origin_lon + col_min * full_raster.pixel_size_deg

    pdir = peat_dir(case_id)
    pdir.mkdir(parents=True, exist_ok=True)
    np.save(pdir / "raster_crop.npy", crop)
    (pdir / "raster_transform.json").write_text(
        json.dumps({"origin_lon": crop_origin_lon, "origin_lat": crop_origin_lat, "pixel_size_deg": full_raster.pixel_size_deg})
    )

    cropped_raster = peat_context.PeatRaster(
        array=crop, origin_lon=crop_origin_lon, origin_lat=crop_origin_lat, pixel_size_deg=full_raster.pixel_size_deg
    )
    context = peat_context.compute_peat_context(event, cropped_raster)
    evidence = strip_volatile(peat_context.to_evidence_objects(context))
    (expected_dir(case_id) / "peat_evidence.json").write_text(json.dumps(evidence, indent=2))


def _imagery_candidates(s1_features: list[dict], s2_features: list[dict]) -> dict:
    """Same shape `benchmark/automated_run.py`'s `_assemble_summary` produces
    -- kept in sync by hand since that one is benchmark-local, not a shared
    library function; if it drifts, this case's `expected/imagery_candidates.json`
    stops matching what the benchmark would actually report."""
    return {
        "sentinel1_grd": [{"id": f["id"], "datetime": f["properties"].get("datetime")} for f in s1_features[:10]],
        "sentinel2_l2a": [
            {"id": f["id"], "datetime": f["properties"].get("datetime"), "cloud_cover_pct": f["properties"].get("eo:cloud_cover")}
            for f in s2_features[:10]
        ],
    }


def _build_imagery(case_id: str, event: FireEvent) -> None:
    west, south, east, north = event.bbox
    bbox = (west - IMAGERY_BBOX_PAD_DEG, south - IMAGERY_BBOX_PAD_DEG, east + IMAGERY_BBOX_PAD_DEG, north + IMAGERY_BBOX_PAD_DEG)
    start = pd.Timestamp(event.first_detection).strftime("%Y-%m-%d")
    end = (pd.Timestamp(event.last_detection) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    s1 = copernicus_cds.search("sentinel-1-grd", bbox, start, end)
    s2 = copernicus_cds.search("sentinel-2-l2a", bbox, start, end)

    idir = imagery_dir(case_id)
    idir.mkdir(parents=True, exist_ok=True)
    (idir / "sentinel1_grd.json").write_text(json.dumps(s1, indent=2))
    (idir / "sentinel2_l2a.json").write_text(json.dumps(s2, indent=2))

    candidates = _imagery_candidates(s1.get("features", []), s2.get("features", []))
    (expected_dir(case_id) / "imagery_candidates.json").write_text(json.dumps(candidates, indent=2))


def _event_row(e: FireEvent) -> dict:
    d = asdict(e)
    d.pop("observation_indices")
    return d


def build_case(case_id: str, event_id: str) -> None:
    print(f"== Building golden case '{case_id}' ({event_id}) ==")
    sample_path = OUTPUT_DIR / "firms_observations_with_event_id.csv"
    all_obs = pd.read_csv(sample_path)
    obs = all_obs[all_obs["event_id"] == event_id].drop(columns=["event_id"]).reset_index(drop=True)
    if obs.empty:
        raise ValueError(f"no observations found for {event_id} in {sample_path}")

    case_dir(case_id).mkdir(parents=True, exist_ok=True)
    expected_dir(case_id).mkdir(parents=True, exist_ok=True)
    obs.to_csv(observations_path(case_id), index=False)

    event = _event_from_observations(obs)
    (expected_dir(case_id) / "clustering.json").write_text(json.dumps(_event_row(event), indent=2))
    print(f"  {len(obs)} observations -> 1 event, {event.observation_count} obs, {event.spatial_extent_km:.2f}km extent")

    _build_weather(case_id, event)
    print("  weather fixtures written")
    _build_peat(case_id, event)
    print("  peat fixtures written")
    _build_imagery(case_id, event)
    print("  imagery fixtures written")


def main() -> None:
    for case in CASES:
        build_case(case.case_id, case.event_id)
    print("\nAll golden cases built. Run `pytest data_pipeline/tests/test_golden_regression.py` to verify.")


if __name__ == "__main__":
    main()
