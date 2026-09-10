"""Thin, dependency-free adapter for the audit register's routing contract."""

from __future__ import annotations

from collections import Counter
from typing import Any

ROUTING_ALGORITHM_VERSION = "review-routing-v1"
PRIORITY_ALGORITHM_VERSION = "investigation-priority-v2"

# These are intentionally the same calibrated bands as the pipeline scorer.
PRIORITY_BANDS = ((60.0, "URGENT"), (20.0, "HIGH"), (12.0, "MEDIUM"))
PRIORITY_COMPONENTS = (
    ("event_validity", 15.0),
    ("environmental_significance", 15.0),
    ("event_complexity", 15.0),
    ("evidence_inconsistency", 15.0),
    ("unresolved_event_relationships", 10.0),
    ("evidence_sufficiency", 10.0),
    ("peat_involvement", 8.0),
    ("land_change_indicators", 6.0),
    ("propagation_uncertainty", 6.0),
)
PRIORITY_WEIGHTS = dict(PRIORITY_COMPONENTS)
SUFFICIENCY_SIGNAL = {"SUFFICIENT": 0.0, "PARTIAL": 0.6, "INSUFFICIENT": 1.0}
VALIDITY_SIGNAL = {"LIKELY_NON_FIRE": 0.0, "AMBIGUOUS": 0.5, "LIKELY_FIRE": 1.0}


def _priority(score: float) -> str:
    for threshold, label in PRIORITY_BANDS:
        if score >= threshold:
            return label
    return "LOW"


def route_event(event: dict[str, Any], evidence_sufficiency: str | None = None) -> dict[str, Any]:
    """Return separate score, sufficiency, and human workflow fields."""
    state = str(event["triage"]["state"]).upper()
    sufficiency = str(
        evidence_sufficiency if evidence_sufficiency is not None
        else event.get("evidenceSufficiency", "PARTIAL")
    ).upper()
    if state not in VALIDITY_SIGNAL:
        raise ValueError(f"unsupported triage state: {state}")
    if sufficiency not in SUFFICIENCY_SIGNAL:
        raise ValueError(f"unsupported evidence sufficiency: {sufficiency}")
    evaluated = {
        "event_validity": (VALIDITY_SIGNAL[state], f"Stage-1 triage state is {state}."),
        "evidence_sufficiency": (
            SUFFICIENCY_SIGNAL[sufficiency],
            f"Evidence sufficiency is {sufficiency}; this is a routing signal, not a finding.",
        ),
    }
    components = []
    for factor, weight in PRIORITY_COMPONENTS:
        if factor in evaluated:
            value, reason = evaluated[factor]
            components.append({
                "factor": factor,
                "value": value,
                "weight": weight,
                "contribution": round(weight * value, 6),
                "status": "EVALUATED",
                "evidenceIds": [f"DERIVED_PRIORITY_{event['eventId']}_{factor}"],
                "reason": reason,
            })
        else:
            components.append({
                "factor": factor,
                "value": None,
                "weight": weight,
                "contribution": 0.0,
                "status": "NOT_EVALUATED",
                "evidenceIds": [],
                "reason": "Not evaluated: optional environmental enrichment is unavailable in this artifact.",
            })
    score = round(sum(item["contribution"] for item in components), 2)
    priority = _priority(score)
    reasons = ([f"PRIORITY_{priority}"] if priority in {"HIGH", "URGENT"} else [])
    if reasons:
        review_state = "HUMAN_REVIEW"
    elif state == "AMBIGUOUS":
        review_state = "REVIEW_RECOMMENDED"
    else:
        review_state = "SCREENED"
    return {
        "evidenceSufficiency": sufficiency,
        "investigationPriority": priority,
        "priorityScore": score,
        "reviewState": review_state,
        "escalatedForHumanReview": bool(reasons),
        "escalationReasonCodes": reasons,
        "components": components,
        "algorithmVersion": ROUTING_ALGORITHM_VERSION,
        "priorityAlgorithmVersion": PRIORITY_ALGORITHM_VERSION,
    }


def attach_routing(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Decorate summaries without mutating the committed source artifact."""
    decorated = []
    for event in events:
        routing = route_event(event)
        decorated.append({
            **event,
            "evidenceSufficiency": routing["evidenceSufficiency"],
            "investigationPriority": routing["investigationPriority"],
            "reviewState": routing["reviewState"],
            "reviewRouting": routing,
        })
    return decorated


def routing_diagnostics(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Explain concentration and report each route's inspectable reasons."""
    routes = [route_event(event) for event in events]
    priority_counts = Counter(item["investigationPriority"] for item in routes)
    # The register already carries the workflow decision on each row. Read it
    # from that represented collection so a scoped diagnostic cannot drift
    # back to a dataset-wide calibration or a second routing decision.
    review_states = [
        event.get("reviewState", route["reviewState"])
        for event, route in zip(events, routes)
    ]
    review_counts = Counter(review_states)
    sufficiency_counts = Counter(item["evidenceSufficiency"] for item in routes)
    reason_counts = Counter(reason for item in routes for reason in item["escalationReasonCodes"])
    component_counts: Counter[str] = Counter()
    component_contributions: Counter[str] = Counter()
    for route in routes:
        for component in route["components"]:
            if component["status"] == "EVALUATED":
                factor = component["factor"]
                component_counts[factor] += 1
                component_contributions[factor] += component["contribution"]
    total = len(routes)
    pct = lambda count: round(count / total, 4) if total else 0.0
    total_contribution = sum(component_contributions.values())
    return {
        "algorithmVersion": ROUTING_ALGORITHM_VERSION,
        "eventCount": total,
        "priorityDistribution": {key: {"count": value, "percentage": pct(value)} for key, value in sorted(priority_counts.items())},
        "reviewStateDistribution": {key: {"count": value, "percentage": pct(value)} for key, value in sorted(review_counts.items())},
        "evidenceSufficiencyDistribution": {key: {"count": value, "percentage": pct(value)} for key, value in sorted(sufficiency_counts.items())},
        "escalationReasonCodes": {key: {"count": value, "percentage": pct(value)} for key, value in sorted(reason_counts.items())},
        "componentContributionDistribution": {
            key: {
                "evaluatedCount": component_counts[key],
                "totalContribution": round(component_contributions[key], 6),
                "percentageOfContribution": round(component_contributions[key] / total_contribution, 4) if total_contribution else 0.0,
            }
            for key in sorted(component_counts)
        },
        "humanReviewCount": review_counts["HUMAN_REVIEW"],
        "humanReviewPercentage": pct(review_counts["HUMAN_REVIEW"]),
        "explanation": "Stage-1 validity and partial evidence are scored separately; ambiguous events remain review-recommended without entering the human-review queue by default.",
    }
