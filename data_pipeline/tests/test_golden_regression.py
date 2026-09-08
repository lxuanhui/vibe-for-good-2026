"""Golden historical regression cases (issue #8).

Every fixture under `data_pipeline/golden/<case_id>/` is real 2019 haze-window
data, frozen by `python -m data_pipeline.golden.build_golden_cases` -- real
FIRMS detections, real Open-Meteo/NASA POWER responses, a real crop of the
Global Peatland Map 2.0 raster, real Copernicus STAC search results. Nothing
here touches the network: nothing frozen here should ever change, so if any
of these assertions starts failing, either a pipeline change altered
behaviour for real historical input (investigate before touching this file)
or a case's fixtures were deliberately regenerated (re-run the builder and
review the diff, don't just re-run this test until it passes).

Each `CASES` entry is asserted against all four pipeline stages so a
regression anywhere -- clustering, weather, peat, or imagery-candidate
selection -- is caught, not just the stage a given code change happened to
touch.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from data_pipeline.clustering.firms_clustering import cluster_events
from data_pipeline.enrichment import peat_context, weather_enrichment
from data_pipeline.golden.build_golden_cases import _imagery_candidates
from data_pipeline.golden.cases import (
    CASES,
    expected_dir,
    imagery_dir,
    observations_path,
    peat_dir,
    strip_volatile,
    weather_dir,
)
from data_pipeline.triage.stage1 import Stage1State, triage_event

CASE_IDS = [c.case_id for c in CASES]

# Open-Meteo's flatbuffer response yields float32 arrays (`_hourly_to_df`),
# so the frozen `expected/weather_evidence.json` values were computed at
# float32 precision. `read_csv` infers float64 from the written decimal
# text, which is *more* precise than the original reading -- summing those
# extra digits gives a value that differs from the frozen one in the last
# couple of decimal places. Casting back to float32 after loading
# reproduces the exact arithmetic the builder did, rather than a merely
# close approximation of it.
_OM_FLOAT_COLUMNS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_10m",
    "soil_moisture_0_to_7cm",
]


def _load_expected(case_id: str, name: str):
    return json.loads((expected_dir(case_id) / f"{name}.json").read_text())


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_clustering_outcome_is_stable(case_id):
    obs = pd.read_csv(observations_path(case_id))
    events, annotated = cluster_events(obs)
    expected = _load_expected(case_id, "clustering")

    assert len(events) == 1, (
        f"golden case '{case_id}' should freeze exactly the observations of one FireEvent; "
        f"got {len(events)} after re-clustering -- either the fixture or the clustering "
        f"thresholds changed"
    )
    event = events[0]
    assert event.event_id == expected["event_id"]
    assert event.observation_count == expected["observation_count"]
    assert event.first_detection == expected["first_detection"]
    assert event.last_detection == expected["last_detection"]
    assert event.duration_hours == pytest.approx(expected["duration_hours"])
    assert event.centroid == pytest.approx(tuple(expected["centroid"]))
    assert event.bbox == pytest.approx(tuple(expected["bbox"]))
    assert event.spatial_extent_km == pytest.approx(expected["spatial_extent_km"])
    assert event.max_frp == pytest.approx(expected["max_frp"])
    assert event.mean_frp == pytest.approx(expected["mean_frp"])
    assert event.sensor_mix == expected["sensor_mix"]
    assert annotated["event_id"].nunique() == 1


def _event_for(case_id: str):
    obs = pd.read_csv(observations_path(case_id))
    events, _ = cluster_events(obs)
    return events[0]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_weather_evidence_is_stable(case_id):
    event = _event_for(case_id)
    wdir = weather_dir(case_id)

    om_hourly = pd.read_csv(wdir / "om_hourly.csv", parse_dates=["date"])
    om_hourly[_OM_FLOAT_COLUMNS] = om_hourly[_OM_FLOAT_COLUMNS].astype("float32")
    power_daily = pd.read_csv(
        wdir / "power_daily.csv", index_col="date", parse_dates=["date"]
    )
    baseline = json.loads((wdir / "baseline_rainfall.json").read_text())

    windows = weather_enrichment.compute_weather_windows(
        event, om_hourly, power_daily, baseline
    )
    bundle = weather_enrichment.WeatherEvidenceBundle(
        event_id=event.event_id, centroid=event.centroid, windows=windows
    )
    actual = strip_volatile(weather_enrichment.to_evidence_objects(bundle))
    expected = _load_expected(case_id, "weather_evidence")

    assert len(actual) == len(expected)
    for a, e in zip(actual, expected, strict=True):
        assert a["evidence_id"] == e["evidence_id"]
        assert a["observation"] == e["observation"]
        assert a["limitations"] == e["limitations"]
        if isinstance(a["value"], (int, float)) and not isinstance(a["value"], bool):
            assert a["value"] == pytest.approx(e["value"])
        else:
            assert a["value"] == e["value"]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_peat_evidence_is_stable(case_id):
    event = _event_for(case_id)
    pdir = peat_dir(case_id)

    array = np.load(pdir / "raster_crop.npy")
    transform = json.loads((pdir / "raster_transform.json").read_text())
    raster = peat_context.PeatRaster(array=array, **transform)

    context = peat_context.compute_peat_context(event, raster)
    actual = strip_volatile(peat_context.to_evidence_objects(context))
    expected = _load_expected(case_id, "peat_evidence")

    assert len(actual) == len(expected)
    for a, e in zip(actual, expected, strict=True):
        assert a["evidence_id"] == e["evidence_id"]
        assert a["observation"] == e["observation"]
        assert a["limitations"] == e["limitations"]
        if isinstance(a["value"], (int, float)) and not isinstance(a["value"], bool):
            assert a["value"] == pytest.approx(e["value"])
        else:
            assert a["value"] == e["value"]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_imagery_candidates_are_stable(case_id):
    idir = imagery_dir(case_id)
    s1 = json.loads((idir / "sentinel1_grd.json").read_text())
    s2 = json.loads((idir / "sentinel2_l2a.json").read_text())

    actual = _imagery_candidates(s1.get("features", []), s2.get("features", []))
    expected = _load_expected(case_id, "imagery_candidates")

    assert actual == expected


def test_cases_cover_simple_complex_and_peat_shapes():
    """The acceptance criteria's three required shapes, checked against the
    frozen fixtures themselves rather than just trusted from `cases.py`'s
    docstrings."""
    by_id = {c.case_id: _event_for(c.case_id) for c in CASES}

    simple = by_id["simple"]
    assert simple.observation_count <= 10
    assert simple.spatial_extent_km < 1.0

    complex_event = by_id["complex_multilobe"]
    assert complex_event.observation_count >= 500
    assert complex_event.spatial_extent_km > 10.0
    assert complex_event.duration_hours > 48.0

    peat_related = by_id["peat_related"]
    peat_ctx = peat_context.compute_peat_context(
        peat_related,
        peat_context.PeatRaster(
            array=np.load(peat_dir("peat_related") / "raster_crop.npy"),
            **json.loads(
                (peat_dir("peat_related") / "raster_transform.json").read_text()
            ),
        ),
    )
    assert peat_ctx.direct_intersection is True
    assert peat_ctx.footprint_peat_fraction is not None


@pytest.mark.parametrize(
    ("case_id", "expected_state"),
    [
        ("simple", Stage1State.AMBIGUOUS),
        ("complex_multilobe", Stage1State.LIKELY_FIRE),
        ("peat_related", Stage1State.LIKELY_FIRE),
    ],
)
def test_stage1_outcome_is_stable_for_golden_cases(case_id, expected_state):
    observations = pd.read_csv(observations_path(case_id))
    event = _event_for(case_id)
    result = triage_event(event, observations)
    assert result.state == expected_state
