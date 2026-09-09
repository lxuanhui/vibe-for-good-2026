import math

import pytest

from data_pipeline.enrich_fire_spread_audit_events import (
    MAX_ENVELOPE_REACH_KM,
    _capped_dimensions,
    _current_window_wind,
    _envelope_dict,
    _event_from_summary,
    build_graph,
    edges_by_source,
)


def _summary_row(event_id: str, lat: float, lon: float, first_detection: str, last_detection: str) -> dict:
    return {
        "eventId": event_id,
        "centroid": {"lat": lat, "lon": lon},
        "bbox": [lon, lat, lon, lat],
        "durationHours": 1.0,
        "observationCount": 3,
        "spatialExtentKm": 1.0,
        "maxFrp": 5.0,
        "meanFrp": 5.0,
        "firstDetection": first_detection,
        "lastDetection": last_detection,
    }


def test_event_from_summary_maps_camel_case_fields():
    row = _summary_row("FE-A", -3.5, 116.2, "2019-09-01T00:00:00+00:00", "2019-09-01T01:00:00+00:00")

    event = _event_from_summary(row)

    assert event.event_id == "FE-A"
    assert event.centroid == (-3.5, 116.2)
    assert event.bbox == (116.2, -3.5, 116.2, -3.5)
    assert event.observation_indices == []


def test_current_window_wind_ignores_t7d_and_uses_speed_kmh_key():
    evidence = [
        {"category": "weather", "type": "wind_direction_10m", "evidence_id": "X_current_wind_direction_10m", "value": 145.4},
        {"category": "weather", "type": "wind_speed_10m", "evidence_id": "X_current_wind_speed_10m", "value": {"mean": 15.34}},
        {"category": "weather", "type": "wind_direction_10m", "evidence_id": "X_T-7d_wind_direction_10m", "value": 999.0},
        {"category": "thermal", "type": "max_frp", "evidence_id": "X_current_max_frp", "value": 5.0},
    ]

    bundle = _current_window_wind(evidence)

    assert bundle is not None
    window = bundle["windows"][0]
    assert window["window_name"] == "event_duration"
    assert window["dominant_wind_direction_deg"] == 145.4
    # The Open-Meteo value is already km/h -- must be under `speed_kmh`, not
    # `mean_wind_speed_ms` (which `_wind_values` would multiply by 3.6).
    assert window["speed_kmh"] == 15.34
    assert "mean_wind_speed_ms" not in window


def test_current_window_wind_returns_none_without_direction():
    assert _current_window_wind([{"category": "weather", "type": "wind_speed_10m", "evidence_id": "X_current_wind_speed_10m", "value": 5.0}]) is None
    assert _current_window_wind([]) is None


def test_envelope_dict_none_when_any_field_missing():
    class Features:
        surface_envelope_semi_major_km = 10.0
        surface_envelope_semi_minor_km = None
        surface_envelope_center_offset_km = 5.0
        surface_envelope_orientation_deg = 90.0
        elapsed_time_hours = 4.0

    assert _envelope_dict(Features(), (-3.0, 116.0)) is None


def test_capped_dimensions_leaves_reach_within_the_gate_untouched():
    # 12 + 18 = 30 == MAX_ENVELOPE_REACH_KM exactly -- not over, no scaling.
    assert _capped_dimensions(18.0, 15.0, 12.0) == (18.0, 15.0, 12.0)


def test_capped_dimensions_scales_a_pair_that_would_blanket_the_map():
    # A real demo-scope case: a long-duration source event pushes the
    # envelope to 256 km reach though every candidate is within 50 km.
    semi_major, semi_minor, center_offset = _capped_dimensions(151.4, 126.2, 105.0)

    max_reach = abs(center_offset) + semi_major
    assert max_reach == pytest.approx(MAX_ENVELOPE_REACH_KM, abs=1e-6)
    # Eccentricity (the ellipse's shape) is preserved -- only scaled down.
    assert semi_minor / semi_major == pytest.approx(126.2 / 151.4, abs=1e-6)


def test_envelope_dict_caps_a_pair_that_would_otherwise_blanket_the_map():
    class Features:
        surface_envelope_semi_major_km = 151.4
        surface_envelope_semi_minor_km = 126.2
        surface_envelope_center_offset_km = 105.0
        surface_envelope_orientation_deg = 45.0
        elapsed_time_hours = 72.7

    result = _envelope_dict(Features(), (-3.78, 116.25))

    assert result is not None
    assert result["semiMajorKm"] < 151.4
    # The polygon's own farthest point from the origin must respect the cap
    # too, not just the stored semi-axis numbers.
    origin_lat, origin_lon = -3.78, 116.25
    farthest_km = max(
        math.radians(lat - origin_lat) * 6371.0088
        for lon, lat in result["polygon"]
    ) or 0.0
    assert farthest_km <= MAX_ENVELOPE_REACH_KM + 1.0


def test_envelope_dict_produces_a_closed_polygon_when_complete():
    class Features:
        # 12 + 18 = 30 == MAX_ENVELOPE_REACH_KM exactly -- no scaling, so the
        # output should equal the input dimensions unchanged.
        surface_envelope_semi_major_km = 18.0
        surface_envelope_semi_minor_km = 15.0
        surface_envelope_center_offset_km = 12.0
        surface_envelope_orientation_deg = 270.0
        elapsed_time_hours = 6.0

    result = _envelope_dict(Features(), (-3.78, 116.25))

    assert result is not None
    assert result["polygon"][0] == result["polygon"][-1]
    assert len(result["polygon"]) == 49
    assert result["orientationDeg"] == 270.0
    assert result["semiMajorKm"] == 18.0
    assert result["semiMinorKm"] == 15.0


def test_build_graph_and_edges_by_source_produce_a_real_envelope():
    events_summary = [
        _summary_row("FE-EARLY", -3.78, 116.25, "2019-09-01T00:00:00+00:00", "2019-09-01T01:00:00+00:00"),
        _summary_row("FE-LATE", -3.70, 116.35, "2019-09-02T00:00:00+00:00", "2019-09-02T01:00:00+00:00"),
    ]
    detail_audit = {
        "FE-EARLY": {"evidence": [
            {"category": "weather", "type": "wind_direction_10m", "evidence_id": "FE-EARLY_current_wind_direction_10m", "value": 45.0},
            {"category": "weather", "type": "wind_speed_10m", "evidence_id": "FE-EARLY_current_wind_speed_10m", "value": {"mean": 10.0}},
        ]},
        "FE-LATE": {"evidence": []},
    }

    graph = build_graph(events_summary, detail_audit)
    grouped = edges_by_source(graph)

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source_event_id == "FE-EARLY"
    assert edge.target_event_id == "FE-LATE"
    real_edges = grouped["FE-EARLY"]
    assert len(real_edges) == 1
    assert real_edges[0]["envelope"] is not None
