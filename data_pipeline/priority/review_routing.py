"""Deterministic separation of priority, sufficiency, and human workflow.

This module routes one FireEvent after deterministic evidence has been
assembled. It never replaces the priority score with a workflow state and it
does not infer cause, responsibility, or culpability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from data_pipeline.priority.investigation_priority import (
    InvestigationPriority,
    InvestigationPriorityResult,
    compute_investigation_priority,
)
from data_pipeline.triage.stage1 import Stage1State


class HumanReviewState(StrEnum):
    SCREENED = "SCREENED"
    REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class EscalationReason(StrEnum):
    PRIORITY_HIGH = "PRIORITY_HIGH"
    PRIORITY_URGENT = "PRIORITY_URGENT"


@dataclass(frozen=True)
class ReviewRoutingResult:
    """Inspectable workflow recommendation built from a priority result."""

    event_id: str
    evidence_sufficiency: str
    priority: InvestigationPriority
    review_state: HumanReviewState
    escalation_reason_codes: tuple[str, ...]
    priority_result: InvestigationPriorityResult

    @property
    def escalated(self) -> bool:
        return self.review_state == HumanReviewState.HUMAN_REVIEW

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "evidenceSufficiency": self.evidence_sufficiency,
            "investigationPriority": self.priority.value,
            "reviewState": self.review_state.value,
            "escalatedForHumanReview": self.escalated,
            "escalationReasonCodes": list(self.escalation_reason_codes),
            "priority": self.priority_result.to_dict(),
            "algorithmVersion": "review-routing-v1",
        }


def route_for_human_review(
    event_id: str,
    triage_state: Stage1State | str,
    evidence_sufficiency: str = "PARTIAL",
    *,
    evaluated_at: str | None = None,
) -> ReviewRoutingResult:
    """Route an event without conflating its three independent states.

    The current FIRMS-only artifact has event-validity and partial-sufficiency
    evidence. Ambiguous events remain visible as REVIEW_RECOMMENDED, but only
    the calibrated high/urgent bands enter HUMAN_REVIEW. Missing evidence is
    never converted into a reassuring signal.
    """

    state = triage_state.value if isinstance(triage_state, Stage1State) else str(triage_state).upper()
    sufficiency = str(evidence_sufficiency).upper()
    priority = compute_investigation_priority(
        event_id,
        {
            "event_validity": state,
            "evidence_sufficiency": sufficiency,
        },
        evaluated_at=evaluated_at,
    )
    reasons: list[str] = []
    if priority.priority == InvestigationPriority.HIGH:
        reasons.append(EscalationReason.PRIORITY_HIGH.value)
    elif priority.priority == InvestigationPriority.URGENT:
        reasons.append(EscalationReason.PRIORITY_URGENT.value)
    if reasons:
        review_state = HumanReviewState.HUMAN_REVIEW
    elif state == Stage1State.AMBIGUOUS.value:
        review_state = HumanReviewState.REVIEW_RECOMMENDED
    else:
        review_state = HumanReviewState.SCREENED
    return ReviewRoutingResult(
        event_id=event_id,
        evidence_sufficiency=sufficiency,
        priority=priority.priority,
        review_state=review_state,
        escalation_reason_codes=tuple(reasons),
        priority_result=priority,
    )


__all__ = ["EscalationReason", "HumanReviewState", "ReviewRoutingResult", "route_for_human_review"]
