import math

import pytest

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.propagation import (
    SurfaceFireCompatibility,
    SurfaceFireSpreadParameters,
    WindSample,
    compare_event_progression,
    historical_wind_direction,
    project_surface_fire_envelope,
)


def _event(event_id: str, lat: float, lon: float, detected_at: str) -> FireEvent:
    return FireEvent(
        event_id=event_id,
        observation_indices=[0],
        first_detection=detected_at,
        last_detection=detected_at,
        duration_hours=0.0,
        observation_count=1,
        centroid=(lat, lon),
        bbox=(lon, lat, lon, lat),
        spatial_extent_km=0.0,
        max_frp=10.0,
        mean_frp=10.0,
        sensor_mix=["N/VIIRS"],
    )


def test_projection_orients_downwind_and_preserves_head_back_flank_parameters():
    parameters = SurfaceFireSpreadParameters(
        head_spread_kmh=4.0,
        back_spread_kmh=1.0,
        flank_spread_kmh=2.0,
    )

    envelope = project_surface_fire_envelope((0.0, 0.0), 3.0, 270.0, parameters)

    assert envelope.orientation_deg == 90.0
    assert envelope.head_distance_km == 12.0
    assert envelope.back_distance_km == 3.0
    assert envelope.flank_distance_km == 6.0
    assert envelope.center_offset_km == 4.5
    assert envelope.semi_major_km == 7.5
    assert envelope.semi_minor_km == 6.0
    assert envelope.contains_point((0.0, 0.08))
    assert not envelope.contains_point((0.2, 0.0))
    assert "does not model underground peat propagation" in envelope.limitations


def test_historical_wind_direction_is_circular_and_speed_weighted():
    direction = historical_wind_direction(
        [
            WindSample("2026-01-01T00:00:00Z", 350.0, 10.0),
            WindSample("2026-01-01T01:00:00Z", 10.0, 10.0),
        ]
    )

    assert direction == pytest.approx(0.0)


def test_event_progression_records_outside_clusters_and_partial_compatibility():
    source = _event("A", 0.0, 0.0, "2026-01-01T00:00:00Z")
    inside = _event("B", 0.0, 0.02, "2026-01-01T06:00:00Z")
    outside = _event("C", 0.0, 0.3, "2026-01-01T06:00:00Z")

    result = compare_event_progression(
        source,
        [outside, inside],
        wind_direction_from_deg=270.0,
        parameters=SurfaceFireSpreadParameters(
            head_spread_kmh=5.0,
            back_spread_kmh=1.0,
            flank_spread_kmh=2.0,
        ),
    )

    assert result.compatibility == SurfaceFireCompatibility.PARTIAL
    assert result.outside_observation_ids == ("C",)
    assert [observation.observation_id for observation in result.observations] == [
        "B",
        "C",
    ]
    assert result.observations[0].inside_expected_envelope is True
    assert result.observations[1].inside_expected_envelope is False
    assert result.to_dict()["observations_outside_expected_envelope"] == ["C"]


def test_missing_wind_is_not_treated_as_outside_evidence():
    source = _event("A", 0.0, 0.0, "2026-01-01T00:00:00Z")
    later = _event("B", 0.0, 0.3, "2026-01-01T06:00:00Z")

    result = compare_event_progression(source, [later])

    assert result.compatibility == SurfaceFireCompatibility.NOT_EVALUATED
    assert result.outside_observation_ids == ()
    assert result.observations[0].inside_expected_envelope is None
    assert "unavailable" in result.observations[0].reason


def test_invalid_spread_parameters_and_time_are_rejected():
    with pytest.raises(ValueError):
        SurfaceFireSpreadParameters(head_spread_kmh=1.0, back_spread_kmh=2.0)
    with pytest.raises(ValueError):
        project_surface_fire_envelope((0.0, 0.0), -1.0, 270.0)


def test_to_polygon_is_a_closed_ring_matching_contains_point():
    envelope = project_surface_fire_envelope(
        origin=(-3.78, 116.25),
        elapsed_hours=10.0,
        wind_direction_from_deg=90.0,
        parameters=SurfaceFireSpreadParameters(head_spread_kmh=5.0, back_spread_kmh=1.0, flank_spread_kmh=2.5),
    )

    ring = envelope.to_polygon(n_points=48)

    assert len(ring) == 49
    assert ring[0] == ring[-1]
    # Every sampled boundary vertex should sit right on the envelope
    # boundary -- inside with a hair of positive tolerance.
    for lon, lat in ring[:-1]:
        assert envelope.contains_point((lat, lon), tolerance_km=0.05)

    # Wind FROM due east blows toward due west, so the "head" vertex
    # (theta=0, the ellipse's downwind extreme) must land due west of the
    # origin at exactly semi_major + center_offset km.
    head_lon, head_lat = ring[0]
    expected_km = envelope.semi_major_km + envelope.center_offset_km
    mean_lat = math.radians((envelope.origin[0] + head_lat) / 2.0)
    actual_km = math.radians(envelope.origin[1] - head_lon) * 6371.0088 * math.cos(mean_lat)
    assert head_lat == pytest.approx(envelope.origin[0], abs=1e-6)
    assert actual_km == pytest.approx(expected_km, abs=1e-3)


def test_to_polygon_rejects_too_few_points():
    envelope = project_surface_fire_envelope((0.0, 0.0), 1.0, 0.0)
    with pytest.raises(ValueError):
        envelope.to_polygon(n_points=2)
