"""Deterministic Stage-1 screening for reconstructed FireEvents.

Stage 1 spends only cheap, already-available evidence. It decides whether an
event has enough thermal/context support to continue, has a strong documented
non-fire explanation, or remains ambiguous. It does not infer ignition cause,
intent, responsibility, or legality.

The rule engine is intentionally explicit. Every rule is returned, including
rules that could not run because a source was unavailable, and every factual
explanation cites the evidence object that supplied its value. Only
``AMBIGUOUS`` results request bounded AI review.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from data_pipeline.clustering.firms_clustering import FireEvent

ALGORITHM_VERSION = "stage1-rules-v1"
FIRE_DECISION_THRESHOLD = 4
NON_FIRE_DECISION_THRESHOLD = 4
EARTH_RADIUS_KM = 6371.0088
NEARBY_DETECTION_RADIUS_KM = 10.0
NEARBY_DETECTION_WINDOW_HOURS = 24.0


class Stage1State(StrEnum):
    LIKELY_FIRE = "LIKELY_FIRE"
    LIKELY_NON_FIRE = "LIKELY_NON_FIRE"
    AMBIGUOUS = "AMBIGUOUS"


class RuleEffect(StrEnum):
    SUPPORTS_FIRE = "SUPPORTS_FIRE"
    SUPPORTS_NON_FIRE = "SUPPORTS_NON_FIRE"
    NO_EFFECT = "NO_EFFECT"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class MetricEvidence:
    """A cheap contextual metric with the provenance Stage 1 may cite."""

    evidence_id: str
    value: float | int | bool
    unit: str
    source: str
    observation: str
    quality: float = 0.8
    limitations: tuple[str, ...] = ()
    category: str = "stage1_context"
    metric_type: str = "context_metric"
    time_window: str | None = None
    retrieved_at: str | None = None
    algorithm_version: str | None = None
    raw_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("context metrics require a non-empty evidence_id")
        if not self.source.strip():
            raise ValueError("context metrics require a source")
        if not 0 <= self.quality <= 1:
            raise ValueError("context metric quality must be between 0 and 1")

    @classmethod
    def from_evidence_object(cls, evidence: dict[str, Any]) -> MetricEvidence:
        """Adapt an existing EvidenceObject without losing its provenance."""
        if evidence.get("value") is None:
            raise ValueError("evidence object must contain a non-null value")
        return cls(
            evidence_id=evidence["evidence_id"],
            value=evidence["value"],
            unit=evidence.get("unit") or "unknown",
            source=evidence["source"],
            observation=evidence["observation"],
            quality=float(evidence.get("quality", 0.8)),
            limitations=tuple(evidence.get("limitations", ())),
            category=evidence.get("category", "stage1_context"),
            metric_type=evidence.get("type", "context_metric"),
            time_window=evidence.get("time_window"),
            retrieved_at=evidence.get("retrieved_at"),
            algorithm_version=evidence.get("algorithm_version"),
            raw_reference=evidence.get("raw_reference"),
        )

    def to_evidence_object(self, event_id: str, evaluated_at: str) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "category": self.category,
            "type": self.metric_type,
            "observation": self.observation,
            "source": self.source,
            "time_window": self.time_window,
            "value": self.value,
            "unit": self.unit,
            "quality": self.quality,
            "limitations": list(self.limitations),
            "retrieved_at": self.retrieved_at or evaluated_at,
            "algorithm_version": self.algorithm_version,
            "raw_reference": self.raw_reference or event_id,
        }


@dataclass(frozen=True)
class Stage1Context:
    """Optional cheap context supplied by the source/enrichment layer.

    Missing values stay missing. Stage 1 records the corresponding rule as
    ``NOT_EVALUATED`` rather than substituting a benign value.
    """

    vegetated_fraction: MetricEvidence | None = None
    urban_fraction: MetricEvidence | None = None
    settlement_distance_km: MetricEvidence | None = None
    persistent_heat_source_match: MetricEvidence | None = None
    volcano_geothermal_distance_km: MetricEvidence | None = None
    recent_rainfall_mm: MetricEvidence | None = None
    nearby_detection_count: MetricEvidence | None = None


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    feature: str
    effect: RuleEffect
    points: int
    evidence_ids: tuple[str, ...]
    explanation: str


@dataclass
class Stage1TriageResult:
    event_id: str
    state: Stage1State
    fire_support_score: int
    non_fire_support_score: int
    rules: list[RuleEvaluation]
    decisive_rule_ids: list[str]
    decision_reasons: list[str]
    evidence: list[dict[str, Any]]
    requires_ai_review: bool
    deeper_investigation_eligible: bool
    budget_reason: str
    algorithm_version: str = ALGORITHM_VERSION
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["state"] = self.state.value
        result["rules"] = [
            {
                **asdict(rule),
                "effect": rule.effect.value,
                "evidence_ids": list(rule.evidence_ids),
            }
            for rule in self.rules
        ]
        return result


@dataclass(frozen=True)
class Stage1BatchSummary:
    event_count: int
    state_counts: dict[str, int]
    review_queue_count: int
    events_to_review_queue_compression: float | None


def summarize_triage(results: list[Stage1TriageResult]) -> Stage1BatchSummary:
    """Summarize deterministic screening without hiding ambiguous events.

    ``review_queue_count`` includes likely-fire and ambiguous events. Only a
    documented ``LIKELY_NON_FIRE`` result avoids deeper investigation spend.
    """
    state_counts = {state.value: 0 for state in Stage1State}
    for result in results:
        state_counts[result.state.value] += 1
    review_queue_count = len(results) - state_counts[Stage1State.LIKELY_NON_FIRE.value]
    compression = (
        round(len(results) / review_queue_count, 4) if review_queue_count else None
    )
    return Stage1BatchSummary(
        event_count=len(results),
        state_counts=state_counts,
        review_queue_count=review_queue_count,
        events_to_review_queue_compression=compression,
    )


def _evidence_id(event: FireEvent, feature: str) -> str:
    return f"DERIVED_STAGE1_{event.event_id}_{feature}"


def _derived_evidence(
    event: FireEvent,
    feature: str,
    observation: str,
    value: float,
    unit: str,
    evaluated_at: str,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": _evidence_id(event, feature),
        "category": "thermal",
        "type": feature,
        "observation": observation,
        "source": "NASA FIRMS",
        "time_window": f"{event.first_detection} to {event.last_detection}",
        "value": value,
        "unit": unit,
        "quality": 0.82 if not limitations else 0.65,
        "limitations": limitations or [],
        "retrieved_at": evaluated_at,
        "algorithm_version": ALGORITHM_VERSION,
        "raw_reference": event.event_id,
    }


def _confidence_score(value: Any) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        labels = {
            "h": 1.0,
            "high": 1.0,
            "n": 0.5,
            "nominal": 0.5,
            "l": 0.0,
            "low": 0.0,
        }
        if normalized in labels:
            return labels[normalized]
        try:
            value = float(normalized)
        except ValueError:
            return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return min(max(numeric / 100.0, 0.0), 1.0)


def _rule(
    rule_id: str,
    feature: str,
    effect: RuleEffect,
    points: int,
    evidence_ids: tuple[str, ...],
    explanation: str,
) -> RuleEvaluation:
    return RuleEvaluation(rule_id, feature, effect, points, evidence_ids, explanation)


def _missing(rule_id: str, feature: str, source_name: str) -> RuleEvaluation:
    return _rule(
        rule_id,
        feature,
        RuleEffect.NOT_EVALUATED,
        0,
        (),
        f"Not evaluated because {source_name} evidence was unavailable.",
    )


def _context_rule(
    rule_id: str,
    feature: str,
    metric: MetricEvidence | None,
    source_name: str,
    evaluator: Callable[[float | bool], tuple[RuleEffect, int, str]],
) -> RuleEvaluation:
    if metric is None:
        return _missing(rule_id, feature, source_name)
    effect, points, message = evaluator(metric.value)
    return _rule(
        rule_id,
        feature,
        effect,
        points,
        (metric.evidence_id,),
        f"{message} ({metric.evidence_id}).",
    )


def _number(value: float | bool, feature: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{feature} must be numeric, not boolean")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{feature} must be finite")
    return result


def _fraction(value: float | bool, feature: str) -> float:
    result = _number(value, feature)
    if not 0 <= result <= 1:
        raise ValueError(f"{feature} must be between 0 and 1")
    return result


def _vegetated_effect(value: float | bool) -> tuple[RuleEffect, int, str]:
    fraction = _fraction(value, "vegetated_fraction")
    if fraction >= 0.5:
        return (
            RuleEffect.SUPPORTS_FIRE,
            1,
            f"Vegetated land fraction was {fraction:.2f}, at or above 0.50",
        )
    return (
        RuleEffect.NO_EFFECT,
        0,
        f"Vegetated land fraction was {fraction:.2f}, below 0.50",
    )


def _urban_effect(value: float | bool) -> tuple[RuleEffect, int, str]:
    fraction = _fraction(value, "urban_fraction")
    if fraction >= 0.75:
        return (
            RuleEffect.SUPPORTS_NON_FIRE,
            2,
            f"Urban land fraction was {fraction:.2f}, at or above 0.75",
        )
    return (
        RuleEffect.NO_EFFECT,
        0,
        f"Urban land fraction was {fraction:.2f}, below 0.75",
    )


def _settlement_effect(value: float | bool) -> tuple[RuleEffect, int, str]:
    distance = _number(value, "settlement_distance_km")
    if distance < 0:
        raise ValueError("settlement_distance_km must not be negative")
    if distance <= 1.0:
        return (
            RuleEffect.SUPPORTS_NON_FIRE,
            1,
            f"Nearest mapped settlement was {distance:.2f} km away, within 1 km",
        )
    return (
        RuleEffect.NO_EFFECT,
        0,
        f"Nearest mapped settlement was {distance:.2f} km away, beyond 1 km",
    )


def _persistent_heat_effect(value: float | bool) -> tuple[RuleEffect, int, str]:
    if not isinstance(value, bool):
        raise TypeError("persistent_heat_source_match must be boolean")
    if value:
        return (
            RuleEffect.SUPPORTS_NON_FIRE,
            5,
            "The event matched a documented persistent heat source",
        )
    return (
        RuleEffect.NO_EFFECT,
        0,
        "The event did not match a documented persistent heat source",
    )


def _volcano_effect(value: float | bool) -> tuple[RuleEffect, int, str]:
    distance = _number(value, "volcano_geothermal_distance_km")
    if distance < 0:
        raise ValueError("volcano_geothermal_distance_km must not be negative")
    if distance <= 3.0:
        return (
            RuleEffect.SUPPORTS_NON_FIRE,
            5,
            f"Nearest mapped volcano/geothermal feature was {distance:.2f} km away, within 3 km",
        )
    return (
        RuleEffect.NO_EFFECT,
        0,
        f"Nearest mapped volcano/geothermal feature was {distance:.2f} km away, beyond 3 km",
    )


def _rainfall_effect(value: float | bool) -> tuple[RuleEffect, int, str]:
    rainfall = _number(value, "recent_rainfall_mm")
    if rainfall < 0:
        raise ValueError("recent_rainfall_mm must not be negative")
    if rainfall <= 2.0:
        return (
            RuleEffect.SUPPORTS_FIRE,
            1,
            f"Rainfall in the preceding 24 hours was {rainfall:.2f} mm, at or below 2 mm",
        )
    if rainfall >= 20.0:
        return (
            RuleEffect.SUPPORTS_NON_FIRE,
            1,
            f"Rainfall in the preceding 24 hours was {rainfall:.2f} mm, at or above 20 mm",
        )
    return (
        RuleEffect.NO_EFFECT,
        0,
        f"Rainfall in the preceding 24 hours was {rainfall:.2f} mm, between decision thresholds",
    )


def _nearby_effect(value: float | bool) -> tuple[RuleEffect, int, str]:
    count = _number(value, "nearby_detection_count")
    if count < 0 or not count.is_integer():
        raise ValueError("nearby_detection_count must be a non-negative integer")
    count_int = int(count)
    if count_int >= 2:
        return (
            RuleEffect.SUPPORTS_FIRE,
            1,
            f"There were {count_int} nearby detections, meeting the threshold of 2",
        )
    return (
        RuleEffect.NO_EFFECT,
        0,
        f"There were {count_int} nearby detections, below the threshold of 2",
    )


def _event_observations(event: FireEvent, observations: pd.DataFrame) -> pd.DataFrame:
    if not event.observation_indices:
        return observations.iloc[0:0]
    if min(event.observation_indices) < 0 or max(event.observation_indices) >= len(
        observations
    ):
        raise IndexError(
            "FireEvent observation_indices do not match the supplied observations"
        )
    event_observations = observations.iloc[event.observation_indices]
    if len(event_observations) != event.observation_count:
        raise ValueError(
            "FireEvent observation_count does not match observation_indices"
        )
    return event_observations


def _firms_rules(
    event: FireEvent,
    observations: pd.DataFrame,
    evaluated_at: str,
) -> tuple[list[RuleEvaluation], list[dict[str, Any]]]:
    event_obs = _event_observations(event, observations)
    rules: list[RuleEvaluation] = []
    evidence: list[dict[str, Any]] = []

    confidence_values = []
    if "confidence" in event_obs.columns:
        confidence_values = [
            score
            for raw in event_obs["confidence"]
            if (score := _confidence_score(raw)) is not None
        ]
    if confidence_values:
        mean_confidence = sum(confidence_values) / len(confidence_values)
        eid = _evidence_id(event, "confidence")
        evidence.append(
            _derived_evidence(
                event,
                "confidence",
                (
                    f"{len(confidence_values)} of {len(event_obs)} FIRMS observations had parseable "
                    f"confidence; normalized mean {mean_confidence:.2f}"
                ),
                mean_confidence,
                "normalized_fraction",
                evaluated_at,
                [
                    "VIIRS categorical and MODIS numeric confidence are normalized to a common 0-1 scale"
                ],
            )
        )
        if mean_confidence >= 0.75:
            rules.append(
                _rule(
                    "FIRMS_CONFIDENCE",
                    "FIRMS confidence",
                    RuleEffect.SUPPORTS_FIRE,
                    2,
                    (eid,),
                    f"Normalized mean FIRMS confidence was {mean_confidence:.2f} ({eid})",
                )
            )
        elif mean_confidence <= 0.25:
            rules.append(
                _rule(
                    "FIRMS_CONFIDENCE",
                    "FIRMS confidence",
                    RuleEffect.SUPPORTS_NON_FIRE,
                    2,
                    (eid,),
                    f"Normalized mean FIRMS confidence was {mean_confidence:.2f} ({eid})",
                )
            )
        else:
            rules.append(
                _rule(
                    "FIRMS_CONFIDENCE",
                    "FIRMS confidence",
                    RuleEffect.NO_EFFECT,
                    0,
                    (eid,),
                    f"Normalized mean FIRMS confidence was {mean_confidence:.2f}, between decision thresholds ({eid})",
                )
            )
    else:
        rules.append(
            _missing(
                "FIRMS_CONFIDENCE", "FIRMS confidence", "parseable FIRMS confidence"
            )
        )

    if event.max_frp is not None and math.isfinite(event.max_frp):
        eid = _evidence_id(event, "max_frp")
        evidence.append(
            _derived_evidence(
                event,
                "max_frp",
                f"Maximum fire radiative power was {event.max_frp:.2f} MW",
                event.max_frp,
                "MW",
                evaluated_at,
            )
        )
        if event.max_frp >= 20.0:
            effect, points, label = (
                RuleEffect.SUPPORTS_FIRE,
                2,
                "at or above the 20 MW support threshold",
            )
        elif event.max_frp <= 2.0:
            effect, points, label = (
                RuleEffect.SUPPORTS_NON_FIRE,
                1,
                "at or below the 2 MW weak-signal threshold",
            )
        else:
            effect, points, label = (
                RuleEffect.NO_EFFECT,
                0,
                "between decision thresholds",
            )
        rules.append(
            _rule(
                "FRP_MAGNITUDE",
                "FRP",
                effect,
                points,
                (eid,),
                f"Maximum FRP was {event.max_frp:.2f} MW, {label} ({eid})",
            )
        )
    else:
        rules.append(_missing("FRP_MAGNITUDE", "FRP", "FIRMS FRP"))

    eid = _evidence_id(event, "observation_count")
    evidence.append(
        _derived_evidence(
            event,
            "observation_count",
            f"The event contains {event.observation_count} FIRMS observations",
            event.observation_count,
            "observations",
            evaluated_at,
        )
    )
    if event.observation_count >= 3:
        effect, points, label = (
            RuleEffect.SUPPORTS_FIRE,
            2,
            "met the repeat-observation threshold",
        )
    elif event.observation_count == 1:
        effect, points, label = (
            RuleEffect.SUPPORTS_NON_FIRE,
            1,
            "was a singleton observation",
        )
    else:
        effect, points, label = (
            RuleEffect.NO_EFFECT,
            0,
            "was below the repeat-observation threshold",
        )
    rules.append(
        _rule(
            "REPEAT_OBSERVATIONS",
            "repeat observations",
            effect,
            points,
            (eid,),
            f"The event contains {event.observation_count} observations and {label} ({eid})",
        )
    )
    return rules, evidence


def _context_rules(context: Stage1Context) -> list[RuleEvaluation]:
    return [
        _context_rule(
            "VEGETATED_LAND_CONTEXT",
            "vegetated land context",
            context.vegetated_fraction,
            "land-cover",
            _vegetated_effect,
        ),
        _context_rule(
            "URBAN_LAND_CONTEXT",
            "urban context",
            context.urban_fraction,
            "land-cover",
            _urban_effect,
        ),
        _context_rule(
            "SETTLEMENT_PROXIMITY",
            "settlement context",
            context.settlement_distance_km,
            "settlement",
            _settlement_effect,
        ),
        _context_rule(
            "PERSISTENT_HEAT_SOURCE",
            "persistent heat-source indicator",
            context.persistent_heat_source_match,
            "persistent heat-source",
            _persistent_heat_effect,
        ),
        _context_rule(
            "VOLCANO_GEOTHERMAL_CONTEXT",
            "volcano/geothermal context",
            context.volcano_geothermal_distance_km,
            "volcano/geothermal",
            _volcano_effect,
        ),
        _context_rule(
            "RECENT_RAINFALL",
            "recent rainfall",
            context.recent_rainfall_mm,
            "recent-rainfall",
            _rainfall_effect,
        ),
        _context_rule(
            "NEARBY_DETECTIONS",
            "nearby detections",
            context.nearby_detection_count,
            "nearby-detection",
            _nearby_effect,
        ),
    ]


def _decide(rules: list[RuleEvaluation]) -> tuple[Stage1State, int, int]:
    fire_score = sum(
        rule.points for rule in rules if rule.effect == RuleEffect.SUPPORTS_FIRE
    )
    non_fire_score = sum(
        rule.points for rule in rules if rule.effect == RuleEffect.SUPPORTS_NON_FIRE
    )
    fire_reached = fire_score >= FIRE_DECISION_THRESHOLD
    non_fire_reached = non_fire_score >= NON_FIRE_DECISION_THRESHOLD
    if fire_reached and not non_fire_reached:
        state = Stage1State.LIKELY_FIRE
    elif non_fire_reached and not fire_reached:
        state = Stage1State.LIKELY_NON_FIRE
    else:
        state = Stage1State.AMBIGUOUS
    return state, fire_score, non_fire_score


def triage_event(
    event: FireEvent,
    observations: pd.DataFrame,
    context: Stage1Context | None = None,
) -> Stage1TriageResult:
    """Evaluate all Stage-1 rules for one event without network access."""
    evaluated_at = datetime.now(timezone.utc).isoformat()
    context = context or Stage1Context()
    firms_rules, evidence = _firms_rules(event, observations, evaluated_at)
    rules = firms_rules + _context_rules(context)
    evidence.extend(
        metric.to_evidence_object(event.event_id, evaluated_at)
        for context_field in fields(context)
        if (metric := getattr(context, context_field.name)) is not None
    )
    state, fire_score, non_fire_score = _decide(rules)

    if state == Stage1State.LIKELY_FIRE:
        decisive = [rule for rule in rules if rule.effect == RuleEffect.SUPPORTS_FIRE]
        budget_reason = (
            "Eligible for deeper deterministic evidence collection because the Stage-1 fire-support "
            "threshold was met. This screening state does not establish ignition cause, intent, or responsibility."
        )
    elif state == Stage1State.LIKELY_NON_FIRE:
        decisive = [
            rule for rule in rules if rule.effect == RuleEffect.SUPPORTS_NON_FIRE
        ]
        budget_reason = (
            "Deeper investigation budget was not used because documented deterministic non-fire context "
            "met the Stage-1 threshold. This is a screening decision, not a finding about cause or responsibility."
        )
    else:
        decisive = [
            rule
            for rule in rules
            if rule.effect in {RuleEffect.SUPPORTS_FIRE, RuleEffect.SUPPORTS_NON_FIRE}
        ]
        budget_reason = (
            "Stage-1 evidence was incomplete, below threshold, or materially mixed; the event may be routed "
            "to bounded AI review before deeper investigation resources are committed."
        )

    return Stage1TriageResult(
        event_id=event.event_id,
        state=state,
        fire_support_score=fire_score,
        non_fire_support_score=non_fire_score,
        rules=rules,
        decisive_rule_ids=[rule.rule_id for rule in decisive],
        decision_reasons=[rule.explanation for rule in decisive],
        evidence=evidence,
        requires_ai_review=state == Stage1State.AMBIGUOUS,
        deeper_investigation_eligible=state != Stage1State.LIKELY_NON_FIRE,
        budget_reason=budget_reason,
        evaluated_at=evaluated_at,
    )


def triage_events(
    events: list[FireEvent], observations: pd.DataFrame
) -> list[Stage1TriageResult]:
    """Run FIRMS-only Stage 1 over an event collection.

    Nearby detections are derived once for the collection through a spatial
    index. Context-specific callers can invoke :func:`triage_event` with a
    richer ``Stage1Context`` as each cheap contextual source becomes available.
    """
    nearby_by_event = build_nearby_detection_context(events, observations)
    return [
        triage_event(
            event,
            observations,
            Stage1Context(nearby_detection_count=nearby_by_event.get(event.event_id)),
        )
        for event in events
    ]


def build_nearby_detection_context(
    events: list[FireEvent],
    observations: pd.DataFrame,
    radius_km: float = NEARBY_DETECTION_RADIUS_KM,
    window_hours: float = NEARBY_DETECTION_WINDOW_HOURS,
) -> dict[str, MetricEvidence]:
    """Count detections near each event but outside its own cluster.

    The spatial index keeps batch triage cheap. Counts are limited to the
    supplied observation collection and a window extending before the event's
    first detection and after its last detection.
    """
    required = {"latitude", "longitude", "acq_date", "acq_time"}
    if not events or observations.empty or not required <= set(observations.columns):
        return {}
    if radius_km <= 0 or window_hours < 0:
        raise ValueError(
            "nearby detection radius must be positive and window non-negative"
        )

    latitudes = pd.to_numeric(observations["latitude"], errors="coerce").to_numpy()
    longitudes = pd.to_numeric(observations["longitude"], errors="coerce").to_numpy()
    if not np.isfinite(latitudes).all() or not np.isfinite(longitudes).all():
        raise ValueError("nearby detection inputs require finite coordinates")

    hhmm = pd.to_numeric(observations["acq_time"], errors="coerce").astype("Int64")
    hhmm_text = hhmm.astype(str).str.zfill(4)
    timestamps = pd.to_datetime(
        observations["acq_date"].astype(str)
        + " "
        + hhmm_text.str[:2]
        + ":"
        + hhmm_text.str[2:],
        errors="coerce",
        utc=True,
    )

    ref_latitude = float(np.mean(latitudes))
    x_km = np.radians(longitudes) * EARTH_RADIUS_KM * np.cos(np.radians(ref_latitude))
    y_km = np.radians(latitudes) * EARTH_RADIUS_KM
    tree = cKDTree(np.column_stack([x_km, y_km]))
    delta = pd.Timedelta(hours=window_hours)

    result: dict[str, MetricEvidence] = {}
    for event in events:
        event_x = (
            math.radians(event.centroid[1])
            * EARTH_RADIUS_KM
            * math.cos(math.radians(ref_latitude))
        )
        event_y = math.radians(event.centroid[0]) * EARTH_RADIUS_KM
        candidates = tree.query_ball_point([event_x, event_y], radius_km)
        event_indices = set(event.observation_indices)
        start = pd.Timestamp(event.first_detection) - delta
        end = pd.Timestamp(event.last_detection) + delta
        count = sum(
            1
            for index in candidates
            if index not in event_indices
            and not pd.isna(timestamps.iloc[index])
            and start <= timestamps.iloc[index] <= end
        )
        evidence_id = _evidence_id(event, "nearby_detection_count")
        result[event.event_id] = MetricEvidence(
            evidence_id=evidence_id,
            value=count,
            unit="detections",
            source="NASA FIRMS",
            observation=(
                f"{count} FIRMS detections outside this event cluster fell within {radius_km:g} km "
                f"and {window_hours:g} hours of its detection window"
            ),
            quality=0.82,
            limitations=(
                "Count reflects only the supplied FIRMS observation collection and clustering result",
            ),
            category="thermal",
            metric_type="nearby_detections",
            time_window=f"{start.isoformat()} to {end.isoformat()}",
            algorithm_version=ALGORITHM_VERSION,
            raw_reference=event.event_id,
        )
    return result
