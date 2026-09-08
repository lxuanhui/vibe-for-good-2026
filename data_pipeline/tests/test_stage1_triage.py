import json

import pandas as pd
import pytest

from data_pipeline.clustering.firms_clustering import cluster_events
from data_pipeline.triage.stage1 import (
    MetricEvidence,
    RuleEffect,
    Stage1Context,
    Stage1State,
    build_nearby_detection_context,
    summarize_triage,
    triage_event,
    triage_events,
)


def _observations(count=1, confidence="n", frp=10.0):
    return pd.DataFrame(
        [
            {
                "latitude": -2.5 + i * 0.0001,
                "longitude": 114.0 + i * 0.0001,
                "acq_date": "2019-09-01",
                "acq_time": 1200 + i,
                "confidence": confidence,
                "frp": frp,
                "satellite": "N",
                "instrument": "VIIRS",
            }
            for i in range(count)
        ]
    )


def _event_and_observations(**kwargs):
    observations = _observations(**kwargs)
    events, _ = cluster_events(observations)
    return events[0], observations


def _metric(evidence_id, value, unit="fraction", source="test fixture"):
    return MetricEvidence(
        evidence_id=evidence_id,
        value=value,
        unit=unit,
        source=source,
        observation=f"Measured value {value} {unit}",
    )


def test_strong_repeated_thermal_signal_is_likely_fire_without_ai_review():
    event, observations = _event_and_observations(count=3, confidence="h", frp=30.0)

    result = triage_event(event, observations)

    assert result.state == Stage1State.LIKELY_FIRE
    assert result.fire_support_score == 6
    assert result.requires_ai_review is False
    assert result.deeper_investigation_eligible is True
    assert result.decisive_rule_ids == [
        "FIRMS_CONFIDENCE",
        "FRP_MAGNITUDE",
        "REPEAT_OBSERVATIONS",
    ]


def test_weak_singleton_in_urban_context_is_likely_non_fire_and_explains_budget():
    event, observations = _event_and_observations(count=1, confidence="l", frp=1.0)
    context = Stage1Context(
        urban_fraction=_metric("LAND_URBAN_1", 0.9),
        settlement_distance_km=_metric("OSM_SETTLEMENT_1", 0.4, "km"),
    )

    result = triage_event(event, observations, context)

    assert result.state == Stage1State.LIKELY_NON_FIRE
    assert result.non_fire_support_score == 7
    assert result.requires_ai_review is False
    assert result.deeper_investigation_eligible is False
    assert "budget was not used" in result.budget_reason
    assert {
        "FIRMS_CONFIDENCE",
        "FRP_MAGNITUDE",
        "REPEAT_OBSERVATIONS",
        "URBAN_LAND_CONTEXT",
        "SETTLEMENT_PROXIMITY",
    } <= set(result.decisive_rule_ids)
    assert all(
        rule.evidence_ids
        for rule in result.rules
        if rule.effect == RuleEffect.SUPPORTS_NON_FIRE
    )
    assert all(
        evidence_id in rule.explanation
        for rule in result.rules
        if rule.effect == RuleEffect.SUPPORTS_NON_FIRE
        for evidence_id in rule.evidence_ids
    )
    assert json.loads(json.dumps(result.to_dict()))["state"] == "LIKELY_NON_FIRE"


def test_documented_persistent_heat_source_can_screen_weak_event():
    event, observations = _event_and_observations(count=2, confidence="n", frp=8.0)
    context = Stage1Context(
        persistent_heat_source_match=_metric(
            "HEAT_SOURCE_1", True, "boolean", "documented heat-source inventory"
        )
    )

    result = triage_event(event, observations, context)

    assert result.state == Stage1State.LIKELY_NON_FIRE
    rule = next(
        rule for rule in result.rules if rule.rule_id == "PERSISTENT_HEAT_SOURCE"
    )
    assert rule.effect == RuleEffect.SUPPORTS_NON_FIRE
    assert rule.evidence_ids == ("HEAT_SOURCE_1",)


def test_conflicting_fire_and_volcano_context_is_ambiguous_and_routes_to_ai():
    event, observations = _event_and_observations(count=4, confidence="h", frp=40.0)
    context = Stage1Context(
        volcano_geothermal_distance_km=_metric(
            "VOLCANO_1", 1.5, "km", "volcano fixture"
        )
    )

    result = triage_event(event, observations, context)

    assert result.state == Stage1State.AMBIGUOUS
    assert result.fire_support_score >= 4
    assert result.non_fire_support_score >= 4
    assert result.requires_ai_review is True
    assert result.deeper_investigation_eligible is True


def test_all_ten_issue_features_are_explicit_rules_with_provenance():
    event, observations = _event_and_observations(count=3, confidence="h", frp=25.0)
    context = Stage1Context(
        vegetated_fraction=_metric("LAND_VEG", 0.8),
        urban_fraction=_metric("LAND_URBAN", 0.1),
        settlement_distance_km=_metric("OSM_SETTLEMENT", 5.0, "km"),
        persistent_heat_source_match=_metric("HEAT_SOURCE", False, "boolean"),
        volcano_geothermal_distance_km=_metric("VOLCANO", 20.0, "km"),
        recent_rainfall_mm=_metric("WEATHER_RAIN", 0.5, "mm"),
        nearby_detection_count=_metric("FIRMS_NEARBY", 4, "detections"),
    )

    result = triage_event(event, observations, context)

    assert {rule.rule_id for rule in result.rules} == {
        "FIRMS_CONFIDENCE",
        "FRP_MAGNITUDE",
        "REPEAT_OBSERVATIONS",
        "VEGETATED_LAND_CONTEXT",
        "URBAN_LAND_CONTEXT",
        "SETTLEMENT_PROXIMITY",
        "PERSISTENT_HEAT_SOURCE",
        "VOLCANO_GEOTHERMAL_CONTEXT",
        "RECENT_RAINFALL",
        "NEARBY_DETECTIONS",
    }
    evidence_ids = {obj["evidence_id"] for obj in result.evidence}
    for rule in result.rules:
        assert set(rule.evidence_ids) <= evidence_ids


def test_missing_context_is_reported_instead_of_assumed_absent():
    event, observations = _event_and_observations(count=2, confidence="n", frp=8.0)

    result = triage_event(event, observations)

    assert result.state == Stage1State.AMBIGUOUS
    assert result.requires_ai_review is True
    context_rules = result.rules[3:]
    assert all(rule.effect == RuleEffect.NOT_EVALUATED for rule in context_rules)
    assert all("unavailable" in rule.explanation for rule in context_rules)


def test_numeric_modis_confidence_is_normalized():
    event, observations = _event_and_observations(count=3, confidence=90, frp=25.0)
    result = triage_event(event, observations)
    confidence = next(
        rule for rule in result.rules if rule.rule_id == "FIRMS_CONFIDENCE"
    )
    assert confidence.effect == RuleEffect.SUPPORTS_FIRE


def test_context_requires_provenance():
    with pytest.raises(ValueError, match="evidence_id"):
        _metric("", 0.8)


def test_existing_evidence_object_retains_provenance():
    source = {
        "evidence_id": "ENV_WEATHER_1",
        "category": "weather",
        "type": "rainfall",
        "observation": "1.2 mm rainfall during T-24h",
        "source": "Open-Meteo/ERA5",
        "time_window": "2019-08-31 to 2019-09-01",
        "value": 1.2,
        "unit": "mm",
        "quality": 0.82,
        "limitations": ["gridded model estimate"],
        "retrieved_at": "2019-09-02T00:00:00+00:00",
        "algorithm_version": None,
        "raw_reference": "weather-cache-key",
    }
    metric = MetricEvidence.from_evidence_object(source)
    adapted = metric.to_evidence_object("FE-TEST", "2019-09-01T00:00:00+00:00")
    assert {key: adapted[key] for key in source} == source


def test_invalid_context_value_fails_instead_of_affecting_a_decision():
    event, observations = _event_and_observations(count=2, confidence="n", frp=8.0)
    context = Stage1Context(urban_fraction=_metric("LAND_URBAN", 1.2))
    with pytest.raises(ValueError, match="between 0 and 1"):
        triage_event(event, observations, context)


def test_batch_triage_preserves_event_order():
    observations = pd.concat(
        [
            _observations(count=3, confidence="h", frp=30.0),
            _observations(count=1, confidence="l", frp=1.0).assign(
                latitude=1.0, longitude=101.0
            ),
        ],
        ignore_index=True,
    )
    events, _ = cluster_events(observations)
    results = triage_events(events, observations)
    assert [result.event_id for result in results] == [
        event.event_id for event in events
    ]
    assert [result.state for result in results] == [
        Stage1State.LIKELY_FIRE,
        Stage1State.LIKELY_NON_FIRE,
    ]

    summary = summarize_triage(results)
    assert summary.state_counts == {
        "LIKELY_FIRE": 1,
        "LIKELY_NON_FIRE": 1,
        "AMBIGUOUS": 0,
    }
    assert summary.review_queue_count == 1
    assert summary.events_to_review_queue_compression == 2.0


def test_batch_triage_derives_nearby_detections_outside_event_cluster():
    observations = pd.DataFrame(
        [
            {
                "latitude": -2.5,
                "longitude": 114.0,
                "acq_date": "2019-09-01",
                "acq_time": 1200,
                "confidence": "n",
                "frp": 8.0,
            },
            {
                "latitude": -2.5,
                "longitude": 114.045,
                "acq_date": "2019-09-01",
                "acq_time": 1210,
                "confidence": "n",
                "frp": 8.0,
            },
            {
                "latitude": -2.501,
                "longitude": 114.046,
                "acq_date": "2019-09-01",
                "acq_time": 1220,
                "confidence": "n",
                "frp": 8.0,
            },
        ]
    )
    events, _ = cluster_events(observations)
    target = next(event for event in events if event.observation_count == 1)

    context = build_nearby_detection_context(events, observations)
    assert context[target.event_id].value == 2

    result = next(
        item
        for item in triage_events(events, observations)
        if item.event_id == target.event_id
    )
    rule = next(rule for rule in result.rules if rule.rule_id == "NEARBY_DETECTIONS")
    assert rule.effect == RuleEffect.SUPPORTS_FIRE
