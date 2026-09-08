import json

import pytest

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.enrichment.peat_context import PeatContext
from data_pipeline.graph import build_fire_event_graph
from data_pipeline.priority import (
    FACTOR_NAMES,
    InvestigationPriority,
    PriorityEvidenceStatus,
    compute_investigation_priority,
)
from data_pipeline.propagation.surface_fire import SurfaceFireCompatibility
from data_pipeline.triage.stage1 import Stage1State, Stage1TriageResult


def _evidence(factor: str, value, quality: float = 1.0) -> dict:
    return {
        "evidence_id": f"TEST_{factor.upper()}",
        "value": value,
        "unit": "normalised signal",
        "observation": f"Observed {factor}: {value}",
        "source": "test fixture",
        "quality": quality,
        "limitations": ["synthetic fixture"],
    }


def test_all_candidate_factors_produce_an_explainable_urgent_result():
    factors = {
        factor: _evidence(factor, "INSUFFICIENT" if factor == "evidence_sufficiency" else 1.0)
        for factor in FACTOR_NAMES
    }

    result = compute_investigation_priority("FE-TEST", factors)

    assert result.priority == InvestigationPriority.URGENT
    assert result.score == 100.0
    assert result.evidence_coverage == 1.0
    assert result.evaluated_factor_count == len(FACTOR_NAMES)
    assert [component.factor.value for component in result.components] == list(FACTOR_NAMES)
    assert all(component.status == PriorityEvidenceStatus.EVALUATED for component in result.components)
    assert all(component.evidence_ids for component in result.components)
    assert {item["evidence_id"] for item in result.evidence} == {
        f"TEST_{factor.upper()}" for factor in FACTOR_NAMES
    }
    assert json.loads(json.dumps(result.to_dict()))["priority"] == "URGENT"


def test_missing_context_is_explicit_and_does_not_look_like_low_evidence():
    result = compute_investigation_priority("FE-MISSING")

    assert result.priority == InvestigationPriority.MEDIUM
    assert result.score == 0.0
    assert result.evidence_coverage == 0.0
    assert all(
        component.status == PriorityEvidenceStatus.NOT_EVALUATED
        for component in result.components
    )
    assert all(not component.evidence_ids for component in result.components)
    assert "conservative routing" in result.limitations[0]


def test_evidence_sufficiency_is_routing_signal_not_a_claim_about_cause():
    result = compute_investigation_priority(
        "FE-PARTIAL",
        {"evidence_sufficiency": _evidence("evidence_sufficiency", "PARTIAL")},
    )

    component = result.components[5]
    assert component.value == pytest.approx(0.6)
    assert component.contribution == pytest.approx(6.0)
    assert result.priority == InvestigationPriority.LOW
    assert result.evidence[0]["evidence_id"] == "TEST_EVIDENCE_SUFFICIENCY"


def test_company_and_legal_fields_are_rejected_before_scoring():
    with pytest.raises(ValueError, match="out of scope"):
        compute_investigation_priority("FE-SAFE", {"company_reputation": 1.0})


def test_direct_numeric_signals_are_bounded():
    with pytest.raises(ValueError, match="between 0 and 1"):
        compute_investigation_priority("FE-BOUNDED", {"event_validity": 1.1})


def _event(event_id: str, lat: float, lon: float, extent_km: float = 0.0) -> FireEvent:
    return FireEvent(
        event_id=event_id,
        observation_indices=[0],
        first_detection="2026-01-01T00:00:00+00:00",
        last_detection="2026-01-01T00:00:00+00:00",
        duration_hours=0.0,
        observation_count=1,
        centroid=(lat, lon),
        bbox=(lon, lat, lon, lat),
        spatial_extent_km=extent_km,
        max_frp=10.0,
        mean_frp=10.0,
        sensor_mix=["N/VIIRS"],
    )


def test_existing_derived_contexts_feed_priority_without_collapsing_provenance():
    event = _event("FE-DERIVED", 0.0, 0.0, extent_km=1.0)
    neighbour = _event("FE-NEIGHBOUR", 0.0, 0.01, extent_km=1.0)
    triage = Stage1TriageResult(
        event_id=event.event_id,
        state=Stage1State.AMBIGUOUS,
        fire_support_score=4,
        non_fire_support_score=4,
        rules=[],
        decisive_rule_ids=[],
        decision_reasons=[],
        evidence=[],
        requires_ai_review=True,
        deeper_investigation_eligible=True,
        budget_reason="ambiguous fixture",
    )
    peat = PeatContext(
        event_id=event.event_id,
        centroid=event.centroid,
        direct_intersection=True,
        footprint_peat_fraction=0.8,
        buffer_km=5.0,
        buffer_peat_fraction=0.6,
        distance_to_peat_km=0.0,
        limitations=["geometric context only"],
    )

    result = compute_investigation_priority(
        event,
        triage=triage,
        graph=build_fire_event_graph([event, neighbour]),
        peat_context=peat,
        propagation=SurfaceFireCompatibility.INCOMPATIBLE,
    )

    by_factor = {component.factor.value: component for component in result.components}
    assert by_factor["event_validity"].value == pytest.approx(0.5)
    assert by_factor["unresolved_event_relationships"].value == pytest.approx(1.0)
    assert by_factor["peat_involvement"].value == pytest.approx(0.8)
    assert by_factor["propagation_uncertainty"].value == pytest.approx(1.0)
    assert result.evidence_coverage > 0
    assert all(component.evidence_ids for component in result.contributing_components)
