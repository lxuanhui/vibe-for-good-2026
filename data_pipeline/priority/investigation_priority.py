"""Score where human investigative attention should go next.

Investigation Priority is a review-routing result for one reconstructed
``FireEvent``.  It is not a company, ownership, intent, culpability, or legal
responsibility score.  The scorer only accepts environmental/event evidence,
and returns every candidate factor even when its source was unavailable.

The inputs are deliberately evidence-shaped.  Callers can pass existing
Stage-1, Fire Complexity, FireEventGraph, peat, and surface-compatibility
results; alternatively they can pass a ``PriorityEvidence`` object (or an
EvidenceObject-shaped mapping) for a factor.  Missing optional context remains
``NOT_EVALUATED`` rather than being treated as reassuring evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.complexity.fire_complexity import FireComplexityEvidence
from data_pipeline.enrichment.peat_context import PeatContext
from data_pipeline.graph.fire_event_graph import FireEventGraph
from data_pipeline.propagation.surface_fire import (
    SurfaceFireCompatibility,
    SurfaceFireCompatibilityResult,
)
from data_pipeline.triage.stage1 import Stage1State, Stage1TriageResult

ALGORITHM_VERSION = "investigation-priority-v1"


class PriorityFactor(StrEnum):
    """Environmental factors that may route human attention."""

    EVENT_VALIDITY = "event_validity"
    ENVIRONMENTAL_SIGNIFICANCE = "environmental_significance"
    EVENT_COMPLEXITY = "event_complexity"
    EVIDENCE_INCONSISTENCY = "evidence_inconsistency"
    UNRESOLVED_EVENT_RELATIONSHIPS = "unresolved_event_relationships"
    EVIDENCE_SUFFICIENCY = "evidence_sufficiency"
    PEAT_INVOLVEMENT = "peat_involvement"
    LAND_CHANGE_INDICATORS = "land_change_indicators"
    PROPAGATION_UNCERTAINTY = "propagation_uncertainty"


FACTOR_NAMES = tuple(factor.value for factor in PriorityFactor)

# Weights are fixed and visible so the score is reproducible and reviewable.
# They are routing choices, not probabilities or calibrated risk estimates.
FACTOR_WEIGHTS: dict[str, float] = {
    PriorityFactor.EVENT_VALIDITY.value: 15.0,
    PriorityFactor.ENVIRONMENTAL_SIGNIFICANCE.value: 15.0,
    PriorityFactor.EVENT_COMPLEXITY.value: 15.0,
    PriorityFactor.EVIDENCE_INCONSISTENCY.value: 15.0,
    PriorityFactor.UNRESOLVED_EVENT_RELATIONSHIPS.value: 10.0,
    PriorityFactor.EVIDENCE_SUFFICIENCY.value: 10.0,
    PriorityFactor.PEAT_INVOLVEMENT.value: 8.0,
    PriorityFactor.LAND_CHANGE_INDICATORS.value: 6.0,
    PriorityFactor.PROPAGATION_UNCERTAINTY.value: 6.0,
}

_FACTOR_ALIASES = {
    "validity": PriorityFactor.EVENT_VALIDITY.value,
    "environmental_significance": PriorityFactor.ENVIRONMENTAL_SIGNIFICANCE.value,
    "complexity": PriorityFactor.EVENT_COMPLEXITY.value,
    "inconsistency": PriorityFactor.EVIDENCE_INCONSISTENCY.value,
    "unresolved_relationships": PriorityFactor.UNRESOLVED_EVENT_RELATIONSHIPS.value,
    "sufficiency": PriorityFactor.EVIDENCE_SUFFICIENCY.value,
    "peat": PriorityFactor.PEAT_INVOLVEMENT.value,
    "land_change": PriorityFactor.LAND_CHANGE_INDICATORS.value,
    "propagation": PriorityFactor.PROPAGATION_UNCERTAINTY.value,
}

_FORBIDDEN_KEYS = frozenset(
    {
        "company_reputation",
        "previous_misconduct",
        "company_identity",
        "legal_culpability",
        "culpability",
        "responsibility",
        "intent",
        "guilt",
        "company",
    }
)


class InvestigationPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class PriorityEvidenceStatus(StrEnum):
    EVALUATED = "EVALUATED"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class PriorityEvidence:
    """A provenance-bearing input for one priority factor."""

    evidence_id: str
    value: Any
    observation: str
    source: str
    unit: str = "normalised signal"
    quality: float = 0.8
    limitations: tuple[str, ...] = ()
    time_window: str | None = None
    retrieved_at: str | None = None
    algorithm_version: str | None = None
    raw_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("priority evidence requires a non-empty evidence_id")
        if not self.source.strip():
            raise ValueError("priority evidence requires a source")
        if not 0 <= float(self.quality) <= 1:
            raise ValueError("priority evidence quality must be between 0 and 1")

    @classmethod
    def from_evidence_object(cls, evidence: Mapping[str, Any]) -> PriorityEvidence:
        return cls(
            evidence_id=str(evidence["evidence_id"]),
            value=evidence.get("value"),
            observation=str(evidence.get("observation", "")),
            source=str(evidence["source"]),
            unit=str(evidence.get("unit") or "unknown"),
            quality=float(evidence.get("quality", 0.8)),
            limitations=tuple(evidence.get("limitations", ())),
            time_window=evidence.get("time_window"),
            retrieved_at=evidence.get("retrieved_at"),
            algorithm_version=evidence.get("algorithm_version"),
            raw_reference=evidence.get("raw_reference"),
        )

    def to_evidence_object(self, evaluated_at: str) -> dict[str, Any]:
        result = asdict(self)
        result["limitations"] = list(self.limitations)
        result["retrieved_at"] = self.retrieved_at or evaluated_at
        return result


@dataclass(frozen=True)
class PriorityComponent:
    """One inspectable factor and its bounded contribution to the score."""

    factor: PriorityFactor
    value: float | None
    weight: float
    contribution: float
    status: PriorityEvidenceStatus
    evidence_ids: tuple[str, ...]
    observation: str
    source: str
    quality: float | None
    limitations: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def metric(self) -> str:
        return self.factor.value

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["factor"] = self.factor.value
        result["status"] = self.status.value
        result["evidence_ids"] = list(self.evidence_ids)
        result["limitations"] = list(self.limitations)
        return result


@dataclass
class InvestigationPriorityResult:
    """Explainable score and label for routing human investigation."""

    event_id: str
    score: float
    priority: InvestigationPriority
    components: list[PriorityComponent]
    evidence: list[dict[str, Any]]
    evaluated_factor_count: int
    evaluated_weight: float
    evidence_coverage: float
    algorithm_version: str = ALGORITHM_VERSION
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    limitations: list[str] = field(default_factory=list)

    @property
    def label(self) -> InvestigationPriority:
        """Alias for clients that call the categorical result a label."""

        return self.priority

    @property
    def contributing_components(self) -> list[PriorityComponent]:
        return [component for component in self.components if component.contribution > 0]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["priority"] = self.priority.value
        result["components"] = [component.to_dict() for component in self.components]
        result["limitations"] = list(self.limitations)
        return result


def _factor_name(raw_name: str | PriorityFactor) -> str:
    name = raw_name.value if isinstance(raw_name, PriorityFactor) else str(raw_name)
    normalized = name.strip().lower()
    if normalized in _FORBIDDEN_KEYS or any(
        forbidden in normalized for forbidden in _FORBIDDEN_KEYS
    ):
        raise ValueError(
            f"{raw_name!r} cannot be used in Investigation Priority; "
            "company identity, reputation, misconduct, guilt, intent, and legal responsibility are out of scope"
        )
    return _FACTOR_ALIASES.get(normalized, normalized)


def _event_id(event: str | FireEvent) -> str:
    return event.event_id if isinstance(event, FireEvent) else str(event)


def _coerce_evidence(
    event_id: str, factor: str, raw: Any, evaluated_at: str
) -> PriorityEvidence:
    if isinstance(raw, PriorityEvidence):
        return raw
    if isinstance(raw, Mapping):
        if "evidence_id" not in raw or "source" not in raw:
            raise ValueError(
                f"{factor} evidence mappings require evidence_id and source"
            )
        return PriorityEvidence.from_evidence_object(raw)
    if hasattr(raw, "evidence_id") and hasattr(raw, "value") and hasattr(raw, "source"):
        return PriorityEvidence(
            evidence_id=str(raw.evidence_id),
            value=raw.value,
            observation=str(getattr(raw, "observation", f"{factor} context supplied")),
            source=str(raw.source),
            unit=str(getattr(raw, "unit", "unknown")),
            quality=float(getattr(raw, "quality", 0.8)),
            limitations=tuple(getattr(raw, "limitations", ())),
            time_window=getattr(raw, "time_window", None),
            retrieved_at=getattr(raw, "retrieved_at", None),
            algorithm_version=getattr(raw, "algorithm_version", None),
            raw_reference=getattr(raw, "raw_reference", None),
        )
    return PriorityEvidence(
        evidence_id=f"DERIVED_PRIORITY_{event_id}_{factor}",
        value=raw,
        observation=f"Caller supplied {factor} signal: {raw!r}.",
        source="caller-supplied environmental context",
        quality=1.0,
        limitations=(
            "This signal was supplied by the caller; the priority scorer does not independently acquire or validate it.",
        ),
        retrieved_at=evaluated_at,
        raw_reference=event_id,
    )


def _finite_signal(value: Any, factor: str) -> float:
    if isinstance(value, bool):
        return float(value)
    try:
        signal = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{factor} must be a numeric signal between 0 and 1") from None
    if not math.isfinite(signal) or not 0 <= signal <= 1:
        raise ValueError(f"{factor} must be a numeric signal between 0 and 1")
    return signal


def _signal_for_value(factor: str, value: Any) -> tuple[float, dict[str, Any]]:
    """Map a factor's documented input to a 0..1 attention signal."""

    if factor == PriorityFactor.EVIDENCE_SUFFICIENCY.value:
        labels = {
            "SUFFICIENT": 0.0,
            "PARTIAL": 0.6,
            "INSUFFICIENT": 1.0,
        }
        normalized = str(value).strip().upper()
        if normalized not in labels:
            raise ValueError(
                "evidence_sufficiency must be SUFFICIENT, PARTIAL, or INSUFFICIENT"
            )
        return labels[normalized], {"source_value": normalized}
    if factor == PriorityFactor.EVENT_VALIDITY.value and isinstance(value, str):
        labels = {"LIKELY_FIRE": 1.0, "AMBIGUOUS": 0.5, "LIKELY_NON_FIRE": 0.0}
        normalized = value.strip().upper()
        if normalized not in labels:
            raise ValueError(
                "event_validity must be LIKELY_FIRE, AMBIGUOUS, or LIKELY_NON_FIRE"
            )
        return labels[normalized], {"source_value": normalized}
    if factor == PriorityFactor.PROPAGATION_UNCERTAINTY.value and isinstance(value, str):
        labels = {
            "COMPATIBLE": 0.15,
            "PARTIAL": 0.6,
            "WEAK": 0.7,
            "INCOMPATIBLE": 1.0,
            "NOT_EVALUATED": None,
        }
        normalized = value.strip().upper()
        if normalized not in labels:
            raise ValueError("unknown propagation compatibility")
        signal = labels[normalized]
        if signal is None:
            raise ValueError("NOT_EVALUATED propagation cannot be scored directly")
        return signal, {"source_value": normalized}
    return _finite_signal(value, factor), {}


def _not_evaluated_component(factor: str) -> PriorityComponent:
    return PriorityComponent(
        factor=PriorityFactor(factor),
        value=None,
        weight=FACTOR_WEIGHTS[factor],
        contribution=0.0,
        status=PriorityEvidenceStatus.NOT_EVALUATED,
        evidence_ids=(),
        observation="Not evaluated: the required environmental evidence was unavailable.",
        source="unavailable source",
        quality=None,
        limitations=(
            "Missing evidence is not treated as low priority or as evidence that the factor is absent.",
        ),
    )


def _component_from_evidence(
    factor: str,
    evidence: Sequence[PriorityEvidence],
    signal: float,
    details: dict[str, Any] | None = None,
) -> PriorityComponent:
    quality = min(item.quality for item in evidence)
    limitations = tuple(
        dict.fromkeys(limit for item in evidence for limit in item.limitations)
    )
    return PriorityComponent(
        factor=PriorityFactor(factor),
        value=round(signal, 6),
        weight=FACTOR_WEIGHTS[factor],
        contribution=round(FACTOR_WEIGHTS[factor] * signal * quality, 6),
        status=PriorityEvidenceStatus.EVALUATED,
        evidence_ids=tuple(item.evidence_id for item in evidence),
        observation="; ".join(item.observation for item in evidence),
        source="; ".join(dict.fromkeys(item.source for item in evidence)),
        quality=round(quality, 6),
        limitations=limitations,
        details=details or {},
    )


def _complexity_signal(result: FireComplexityEvidence) -> tuple[float | None, list[PriorityEvidence], dict[str, Any]]:
    """Collapse named complexity evidence without hiding its subcomponents."""

    transforms: dict[str, Any] = {
        "duration": lambda value: min(float(value) / 72.0, 1.0),
        "observation_count": lambda value: min(float(value) / 20.0, 1.0),
        "spatial_extent": lambda value: min(float(value) / 10.0, 1.0),
        "centroid_movement": lambda value: min(float(value) / 10.0, 1.0),
        "directional_consistency": lambda value: 1.0 - float(value),
        "wind_alignment": lambda value: 1.0 - (float(value) + 1.0) / 2.0,
        "frp_variability": lambda value: min(float(value), 1.0),
        "distinct_thermal_lobes": lambda value: min(max(float(value) - 1.0, 0.0) / 4.0, 1.0),
        "nearby_event_count": lambda value: min(float(value) / 3.0, 1.0),
        "historical_recurrence": lambda value: float(bool(value)),
        "unexplained_detections": lambda value: min(float(value) / 10.0, 1.0),
        "surface_propagation_mismatch": lambda value: float(value),
    }
    signals: dict[str, float] = {}
    evidence: list[PriorityEvidence] = []
    for name, transform in transforms.items():
        field = result.features[name]
        if field.value is None or field.status.value != "EVALUATED":
            continue
        value = float(transform(field.value))
        if not math.isfinite(value):
            continue
        signals[name] = max(0.0, min(1.0, value))
        evidence.append(
            PriorityEvidence(
                evidence_id=field.evidence_id,
                value=field.value,
                observation=field.observation,
                source=field.source,
                unit=field.unit,
                quality=field.quality,
                limitations=field.limitations,
                time_window=field.time_window,
                retrieved_at=getattr(field, "retrieved_at", None),
                algorithm_version=field.algorithm_version,
                raw_reference=field.raw_reference,
            )
        )
    if not signals:
        return None, [], {"subcomponents": {}}
    return (
        sum(signals.values()) / len(signals),
        evidence,
        {"subcomponents": {name: round(value, 6) for name, value in signals.items()}},
    )


def _derived_evidence(event_id: str, factor: str, value: Any, observation: str, source: str, limitations: tuple[str, ...] = ()) -> PriorityEvidence:
    return PriorityEvidence(
        evidence_id=f"DERIVED_PRIORITY_{event_id}_{factor}",
        value=value,
        observation=observation,
        source=source,
        quality=0.8,
        limitations=limitations,
        raw_reference=event_id,
    )


def compute_investigation_priority(
    event: str | FireEvent,
    factors: Mapping[str | PriorityFactor, Any] | None = None,
    *,
    triage: Stage1TriageResult | None = None,
    complexity: FireComplexityEvidence | None = None,
    graph: FireEventGraph | None = None,
    peat_context: PeatContext | None = None,
    propagation: SurfaceFireCompatibilityResult | SurfaceFireCompatibility | str | None = None,
    evaluated_at: str | None = None,
    **factor_values: Any,
) -> InvestigationPriorityResult:
    """Compute a bounded, explainable Investigation Priority result.

    Direct factor values must be normalized signals in the inclusive range
    ``0..1``. ``evidence_sufficiency`` and propagation/status enums use their
    documented labels. Existing derived results are converted into evidence
    and are preferred only when that factor was not supplied directly.
    """

    event_id = _event_id(event)
    evaluated_at = evaluated_at or datetime.now(timezone.utc).isoformat()
    provided: dict[str, Any] = {}
    for raw_name, raw_value in (factors or {}).items():
        name = _factor_name(raw_name)
        if name not in FACTOR_WEIGHTS:
            raise ValueError(f"unknown Investigation Priority factor: {raw_name!r}")
        if raw_value is not None:
            provided[name] = raw_value
    for raw_name, raw_value in factor_values.items():
        name = _factor_name(raw_name)
        if name not in FACTOR_WEIGHTS:
            raise ValueError(f"unknown Investigation Priority factor: {raw_name!r}")
        if raw_value is not None:
            provided[name] = raw_value

    derived: dict[str, tuple[list[PriorityEvidence], float, dict[str, Any]]] = {}

    if triage is not None and PriorityFactor.EVENT_VALIDITY.value not in provided:
        evidence = [
            _derived_evidence(
                event_id,
                PriorityFactor.EVENT_VALIDITY.value,
                triage.state.value,
                f"Stage-1 triage state is {triage.state.value}.",
                "deterministic Stage-1 triage",
                ("Stage-1 screening is an event-validity routing signal, not a finding about cause or responsibility.",),
            )
        ]
        derived[PriorityFactor.EVENT_VALIDITY.value] = (
            evidence,
            {Stage1State.LIKELY_FIRE: 1.0, Stage1State.AMBIGUOUS: 0.5, Stage1State.LIKELY_NON_FIRE: 0.0}[triage.state],
            {"source_value": triage.state.value, "triage_evidence_ids": [item["evidence_id"] for item in triage.evidence]},
        )

    if complexity is not None and PriorityFactor.EVENT_COMPLEXITY.value not in provided:
        signal, evidence, details = _complexity_signal(complexity)
        if signal is not None:
            derived[PriorityFactor.EVENT_COMPLEXITY.value] = (evidence, signal, details)

    if peat_context is not None and PriorityFactor.PEAT_INVOLVEMENT.value not in provided:
        values = [
            value
            for value in (peat_context.footprint_peat_fraction, peat_context.buffer_peat_fraction)
            if value is not None
        ]
        if values:
            signal = max(values)
            peat_evidence = [
                PriorityEvidence.from_evidence_object(item)
                for item in _peat_evidence_objects(peat_context)
                if item.get("value") is not None
            ]
            derived[PriorityFactor.PEAT_INVOLVEMENT.value] = (
                peat_evidence,
                signal,
                {"footprint_peat_fraction": peat_context.footprint_peat_fraction, "buffer_peat_fraction": peat_context.buffer_peat_fraction},
            )

    if graph is not None and PriorityFactor.UNRESOLVED_EVENT_RELATIONSHIPS.value not in provided:
        edges = graph.edges_for(event_id)
        unresolved = [edge for edge in edges if edge.state.value in {"UNRESOLVED", "RELATED_POSSIBLE"}]
        signal = min(len(unresolved) / max(len(edges), 1), 1.0)
        evidence = [
            _derived_evidence(
                event_id,
                PriorityFactor.UNRESOLVED_EVENT_RELATIONSHIPS.value,
                edge.state.value,
                edge.explanation or f"Candidate relationship is {edge.state.value}.",
                "deterministic FireEventGraph",
                ("A candidate relationship is an investigative lead, not a causal or responsibility finding.",),
            )
            for edge in edges
        ]
        if not evidence:
            evidence = [
                _derived_evidence(
                    event_id,
                    PriorityFactor.UNRESOLVED_EVENT_RELATIONSHIPS.value,
                    0.0,
                    "No candidate FireEventGraph relationship was generated for this event.",
                    "deterministic FireEventGraph",
                    ("The graph candidate thresholds do not prove that no physical relationship exists.",),
                )
            ]
        derived[PriorityFactor.UNRESOLVED_EVENT_RELATIONSHIPS.value] = (
            evidence,
            signal,
            {"candidate_edge_count": len(edges), "unresolved_edge_count": len(unresolved), "graph_model_version": graph.model_version},
        )

    if propagation is not None and PriorityFactor.PROPAGATION_UNCERTAINTY.value not in provided:
        if isinstance(propagation, SurfaceFireCompatibilityResult):
            compatibility = propagation.compatibility
            limitations = tuple(propagation.limitations)
            source = "first-order surface-fire compatibility model"
        else:
            compatibility = propagation
            limitations = ()
            source = "caller-supplied propagation context"
        normalized = compatibility.value if isinstance(compatibility, SurfaceFireCompatibility) else str(compatibility).upper()
        if normalized != SurfaceFireCompatibility.NOT_EVALUATED.value:
            signal, details = _signal_for_value(PriorityFactor.PROPAGATION_UNCERTAINTY.value, normalized)
            derived[PriorityFactor.PROPAGATION_UNCERTAINTY.value] = (
                [_derived_evidence(event_id, PriorityFactor.PROPAGATION_UNCERTAINTY.value, normalized, f"Surface progression compatibility is {normalized}.", source, limitations)],
                signal,
                details,
            )

    components: list[PriorityComponent] = []
    evidence_objects: list[dict[str, Any]] = []
    evaluated_weight = 0.0
    total_contribution = 0.0
    for factor in FACTOR_NAMES:
        if factor in provided:
            item = _coerce_evidence(event_id, factor, provided[factor], evaluated_at)
            signal, details = _signal_for_value(factor, item.value)
            evidence = [item]
            component = _component_from_evidence(factor, evidence, signal, details)
        elif factor in derived:
            evidence, signal, details = derived[factor]
            component = _component_from_evidence(factor, evidence, signal, details)
        else:
            component = _not_evaluated_component(factor)
        components.append(component)
        if component.status == PriorityEvidenceStatus.EVALUATED:
            evaluated_weight += component.weight
            total_contribution += component.contribution
            evidence_objects.extend(item.to_evidence_object(evaluated_at) for item in evidence)

    score = round(total_contribution, 2)
    coverage = round(evaluated_weight / sum(FACTOR_WEIGHTS.values()), 6)
    if evaluated_weight == 0:
        priority = InvestigationPriority.MEDIUM
        limitations = [
            "No priority factors were evaluated; MEDIUM is a conservative routing result until evidence is assembled.",
        ]
    else:
        priority = _priority_for_score(score)
        limitations = []
    if coverage < 1.0:
        limitations.append(
            f"Only {coverage:.0%} of weighted priority factors had evidence; unavailable factors were not treated as absent."
        )

    # Preserve distinct source evidence IDs while keeping the result compact.
    unique_evidence: dict[str, dict[str, Any]] = {}
    for item in evidence_objects:
        unique_evidence.setdefault(item["evidence_id"], item)
    return InvestigationPriorityResult(
        event_id=event_id,
        score=score,
        priority=priority,
        components=components,
        evidence=list(unique_evidence.values()),
        evaluated_factor_count=sum(
            component.status == PriorityEvidenceStatus.EVALUATED for component in components
        ),
        evaluated_weight=round(evaluated_weight, 6),
        evidence_coverage=coverage,
        evaluated_at=evaluated_at,
        limitations=limitations,
    )


def _priority_for_score(score: float) -> InvestigationPriority:
    if score >= 75:
        return InvestigationPriority.URGENT
    if score >= 50:
        return InvestigationPriority.HIGH
    if score >= 25:
        return InvestigationPriority.MEDIUM
    return InvestigationPriority.LOW


def _peat_evidence_objects(context: PeatContext) -> list[dict[str, Any]]:
    """Keep the priority module independent of the peat module's serializer."""

    values = [
        (
            "footprint_fraction",
            context.footprint_peat_fraction,
            "peat footprint fraction",
            "fraction",
        ),
        (
            "buffer_fraction",
            context.buffer_peat_fraction,
            "peat buffer fraction",
            "fraction",
        ),
    ]
    return [
        {
            "evidence_id": f"ENV_PEAT_{context.event_id}_{name}",
            "category": "peat",
            "type": metric_type,
            "observation": f"{metric_type} is {value}",
            "source": context.source,
            "value": value,
            "unit": unit,
            "quality": 0.7,
            "limitations": list(context.limitations),
            "raw_reference": context.event_id,
        }
        for name, value, metric_type, unit in values
        if value is not None
    ]


score_investigation_priority = compute_investigation_priority


__all__ = [
    "ALGORITHM_VERSION",
    "FACTOR_NAMES",
    "FACTOR_WEIGHTS",
    "InvestigationPriority",
    "InvestigationPriorityResult",
    "PriorityComponent",
    "PriorityEvidence",
    "PriorityEvidenceStatus",
    "PriorityFactor",
    "compute_investigation_priority",
    "score_investigation_priority",
]
