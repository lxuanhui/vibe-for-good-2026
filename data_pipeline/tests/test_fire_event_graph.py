import json

import numpy as np
import pytest

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.enrichment.peat_context import PEAT_DOMINATED, PeatRaster
from data_pipeline.graph import (
    ALGORITHM_VERSION,
    EdgeState,
    build_fire_event_graph,
)


def _event(
    event_id: str,
    lat: float,
    lon: float,
    first: str,
    last: str | None = None,
    extent_km: float = 0.0,
) -> FireEvent:
    return FireEvent(
        event_id=event_id,
        observation_indices=[0],
        first_detection=first,
        last_detection=last or first,
        duration_hours=0.0,
        observation_count=1,
        centroid=(lat, lon),
        bbox=(lon, lat, lon, lat),
        spatial_extent_km=extent_km,
        max_frp=10.0,
        mean_frp=10.0,
        sensor_mix=["N/VIIRS"],
    )


def test_graph_represents_temporal_chain_and_keeps_fireevents_as_nodes():
    events = [
        _event("A", 0.0, 0.0, "2026-01-01T00:00:00Z"),
        _event("B", 0.0, 0.01, "2026-01-01T06:00:00Z"),
        _event("C", 0.0, 0.02, "2026-01-01T12:00:00Z"),
    ]

    graph = build_fire_event_graph(events)

    assert graph.node_ids == ("A", "B", "C")
    assert [(edge.source_event_id, edge.target_event_id) for edge in graph.edges] == [
        ("A", "B"),
        ("A", "C"),
        ("B", "C"),
    ]
    assert all(edge.state == EdgeState.PROPAGATION_COMPATIBLE for edge in graph.edges)
    assert graph.edges[0].features.elapsed_time_hours == 6.0
    assert graph.edges[0].features.temporal_ordering.value == "A_BEFORE_B"


def test_graph_can_represent_independence_and_unresolved_overlap():
    independent_a = _event("A", 0.0, 0.0, "2026-01-01T00:00:00Z")
    independent_b = _event("B", 0.0, 0.1, "2026-01-01T00:00:00Z")
    unresolved_a = _event("C", 1.0, 1.0, "2026-01-01T00:00:00Z", extent_km=1.0)
    unresolved_b = _event("D", 1.0, 1.01, "2026-01-01T00:00:00Z", extent_km=1.0)

    graph = build_fire_event_graph([independent_a, independent_b, unresolved_a, unresolved_b])

    states = {(edge.source_event_id, edge.target_event_id): edge.state for edge in graph.edges}
    assert states[("A", "B")] == EdgeState.INDEPENDENT_PLAUSIBLE
    assert states[("C", "D")] == EdgeState.UNRESOLVED
    assert states[("A", "B")] != EdgeState.PROPAGATION_COMPATIBLE


def test_edge_features_include_wind_direction_and_optional_context_without_raw_points():
    events = [
        _event("A", 0.0, 0.0, "2026-01-01T00:00:00Z"),
        _event("B", 0.0, 0.01, "2026-01-01T06:00:00Z"),
    ]
    weather = {
        "A": {
            "windows": [
                {
                    "window_name": "event_duration",
                    "dominant_wind_direction_deg": 270.0,
                    "mean_wind_speed_ms": 4.0,
                }
            ]
        }
    }

    graph = build_fire_event_graph(
        events,
        weather_by_event=weather,
        environmental_episode_by_event={"A": "dry-1", "B": "dry-1"},
        historical_recurrence={("A", "B"): False},
    )
    edge = graph.edges[0]

    assert edge.features.wind_alignment == pytest.approx(1.0)
    assert edge.features.directional_compatibility is True
    assert edge.features.shared_environmental_episode is True
    assert edge.features.historical_recurrence is False
    assert edge.model_version == ALGORITHM_VERSION
    assert edge.supporting_evidence_ids
    assert edge.contradicting_evidence_ids
    json.dumps(graph.to_dict())


def test_wind_oriented_surface_envelope_records_an_outside_target():
    events = [
        _event("A", 0.0, 0.0, "2026-01-01T00:00:00Z"),
        _event("B", 0.2, 0.0, "2026-01-01T06:00:00Z"),
    ]
    weather = {
        "A": {
            "windows": [
                {
                    "window_name": "event_duration",
                    "dominant_wind_direction_deg": 270.0,
                    "mean_wind_speed_ms": 4.0,
                }
            ]
        }
    }

    edge = build_fire_event_graph(events, weather_by_event=weather).edges[0]

    assert edge.features.surface_envelope_contains_target is False
    assert edge.features.surface_envelope_orientation_deg == pytest.approx(90.0)
    assert edge.features.propagation_compatibility.value == "INCOMPATIBLE"


def test_peat_corridor_fraction_is_derived_from_supplied_raster():
    raster = PeatRaster(
        array=np.full((20, 20), PEAT_DOMINATED, dtype="uint8"),
        origin_lon=0.0,
        origin_lat=0.2,
        pixel_size_deg=0.01,
    )
    events = [
        _event("A", 0.08, 0.02, "2026-01-01T00:00:00Z"),
        _event("B", 0.08, 0.03, "2026-01-01T06:00:00Z"),
    ]

    edge = build_fire_event_graph(events, peat_raster=raster).edges[0]

    assert edge.features.peat_corridor_fraction == 1.0


def test_weak_surface_path_is_distinguished_from_a_compatible_path():
    events = [
        _event("A", 0.0, 0.0, "2026-01-01T00:00:00Z"),
        _event("B", 0.0, 0.09, "2026-01-01T01:00:00Z"),
    ]

    graph = build_fire_event_graph(
        events,
        environmental_episode_by_event={"A": "episode-1", "B": "episode-1"},
    )

    assert graph.edges[0].features.propagation_compatibility.value == "WEAK"
    assert graph.edges[0].state == EdgeState.PROPAGATION_WEAK


def test_context_supported_but_speed_incompatible_pair_is_related_possible():
    events = [
        _event("A", 0.0, 0.0, "2026-01-01T00:00:00Z"),
        _event("B", 0.0, 0.09, "2026-01-01T00:30:00Z"),
    ]

    graph = build_fire_event_graph(
        events,
        environmental_episode_by_event={"A": "episode-1", "B": "episode-1"},
    )

    assert graph.edges[0].state == EdgeState.RELATED_POSSIBLE


@pytest.mark.parametrize(
    "kwargs",
    [
        {"candidate_distance_km": 0},
        {"candidate_time_window_hours": -1},
        {"event_buffer_km": -1},
        {"max_surface_spread_kmh": 0},
    ],
)
def test_graph_rejects_invalid_screening_parameters(kwargs):
    with pytest.raises(ValueError):
        build_fire_event_graph([], **kwargs)


def test_graph_rejects_duplicate_nodes_and_inverted_windows():
    event = _event("A", 0.0, 0.0, "2026-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="unique"):
        build_fire_event_graph([event, event])

    inverted = _event(
        "B",
        0.0,
        0.0,
        "2026-01-02T00:00:00Z",
        last="2026-01-01T00:00:00Z",
    )
    with pytest.raises(ValueError, match="inverted"):
        build_fire_event_graph([inverted])


def test_far_recurrence_link_is_retained_as_a_candidate():
    events = [
        _event("A", 0.0, 0.0, "2020-01-01T00:00:00Z"),
        _event("B", 0.0, 0.0, "2026-01-01T00:00:00Z"),
    ]

    graph = build_fire_event_graph(events, historical_recurrence={("A", "B"): True})

    assert len(graph.edges) == 1
    assert graph.edges[0].features.historical_recurrence is True


def test_unrelated_far_and_old_events_are_not_added_to_candidate_graph():
    events = [
        _event("A", 0.0, 0.0, "2020-01-01T00:00:00Z"),
        _event("B", 10.0, 10.0, "2026-01-01T00:00:00Z"),
    ]

    graph = build_fire_event_graph(events)

    assert graph.edges == []
