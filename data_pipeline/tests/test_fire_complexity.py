import pandas as pd
import pytest

from data_pipeline.clustering.firms_clustering import cluster_events
from data_pipeline.complexity.fire_complexity import (
    ALGORITHM_VERSION,
    FIELD_NAMES,
    ComplexityEvidenceStatus,
    compute_fire_complexity,
)


def _row(lat, lon, date="2019-09-01", time=1200, frp=10.0):
    return {
        "latitude": lat,
        "longitude": lon,
        "acq_date": date,
        "acq_time": time,
        "frp": frp,
        "satellite": "N",
        "instrument": "VIIRS",
    }


def test_returns_all_named_fields_without_an_aggregate_score():
    observations = pd.DataFrame(
        [
            _row(-2.5000, 114.0000, time=1200, frp=10.0),
            _row(-2.5100, 114.0000, time=1300, frp=20.0),
            _row(-2.5200, 114.0000, time=1400, frp=30.0),
        ]
    )
    event = cluster_events(observations)[0][0]

    result = compute_fire_complexity(event, observations, wind_direction_from_deg=0)

    assert tuple(result.features) == FIELD_NAMES
    assert len(result.evidence) == len(FIELD_NAMES)
    assert not hasattr(result, "score")
    assert all(field.algorithm_version == ALGORITHM_VERSION for field in result.fields)
    assert all(
        field.status == ComplexityEvidenceStatus.EVALUATED
        for field in result.fields[:8]
    )
    assert result.duration.value == pytest.approx(2.0)
    assert result.observation_count.value == 3
    assert result.centroid_movement.value == pytest.approx(2.2239, rel=1e-3)
    assert result.directional_consistency.value == pytest.approx(1.0)
    assert result.wind_alignment.value == pytest.approx(1.0)
    assert result.frp_variability.value == pytest.approx(0.408248, rel=1e-5)
    assert result.unexplained_detections.value == 0
    assert result.surface_propagation_mismatch.value == 0


def test_peat_neighbours_recurrence_and_explicit_unexplained_context_are_separate_fields():
    target_observations = pd.DataFrame(
        [
            _row(-2.5000, 114.0000, date="2019-09-02", time=1200),
            _row(-2.5010, 114.0000, date="2019-09-02", time=1300),
        ]
    )
    neighbour_observations = pd.DataFrame([_row(-2.5450, 114.0000, date="2019-09-02")])
    prior_observations = pd.DataFrame([_row(-2.5000, 114.0000, date="2019-08-01")])
    target = cluster_events(target_observations)[0][0]
    neighbour = cluster_events(neighbour_observations)[0][0]
    prior = cluster_events(prior_observations)[0][0]

    result = compute_fire_complexity(
        target,
        target_observations,
        events=[target, neighbour, prior],
        peat_context={
            "direct_intersection": True,
            "footprint_peat_fraction": 0.75,
            "source": "synthetic peat map",
            "limitations": ["geometric context only"],
        },
        unexplained_observation_indices=[1],
    )

    assert result.peat_overlap.value == pytest.approx(0.75)
    assert result.nearby_event_count.value == 1
    assert result.historical_recurrence.value is True
    assert result.historical_recurrence.details["matching_event_count"] == 1
    assert result.unexplained_detections.value == 1
    assert (
        result.surface_propagation_mismatch.status
        == ComplexityEvidenceStatus.NOT_EVALUATED
    )
    assert "geometric context only" in result.peat_overlap.limitations


def test_missing_optional_context_is_explicitly_not_evaluated():
    observations = pd.DataFrame([_row(-2.5, 114.0)])
    event = cluster_events(observations)[0][0]

    result = compute_fire_complexity(event, observations)

    for name in (
        "wind_alignment",
        "peat_overlap",
        "nearby_event_count",
        "historical_recurrence",
        "unexplained_detections",
        "surface_propagation_mismatch",
    ):
        field = getattr(result, name)
        assert field.value is None
        assert field.status == ComplexityEvidenceStatus.NOT_EVALUATED
        assert field.observation.startswith("Not evaluated:")

    assert (
        result.evidence[0]["evidence_id"]
        == f"DERIVED_COMPLEXITY_{event.event_id}_duration"
    )
    assert (
        result.evidence[0]["time_window"]
        == f"{event.first_detection} to {event.last_detection}"
    )
