"""Bounded, evidence-linked Investigator/Skeptic analysis.

This module is the boundary between deterministic reconstruction and an agent
provider.  It deliberately does not call an LLM.  A provider receives a
structured evidence pack and returns one schema-checked assessment per round;
the result contains concise summaries and evidence references, never a chat
transcript or private chain-of-thought.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

ALGORITHM_VERSION = "investigator-skeptic-v1"
MAX_ROUNDS = 3

logger = logging.getLogger(__name__)

# Word caps the provider prompt states and this module measures. Over-length
# text is logged, never rejected: a rejected round is a FAILED job the auditor
# pays for again, which is worse than a long sentence on screen (#199).
SUMMARY_WORD_CAP = 25
QUESTION_WORD_CAP = 20
REASON_WORD_CAP = 15

# A dash with space on both sides, in any of the three forms models produce.
_SPACED_DASH = re.compile(r"\s+(?:\u2014|\u2013|--)\s+")
# A bare em-dash between digits is a range the copy rules allow as an en-dash.
_NUMERIC_EMDASH = re.compile(r"(?<=\d)\u2014(?=\d)")
_FORBIDDEN_HYPOTHESIS_TERMS = (
    "blame",
    "guilt",
    "responsib",
    "culpab",
    "intent",
    "negligence",
    "malpractice",
    "arson",
    "prosecut",
    "sanction",
    "company",
    "operator",
    "concession holder",
)


class AgentRole(StrEnum):
    INVESTIGATOR = "INVESTIGATOR"
    SKEPTIC = "SKEPTIC"


class AnalysisPhase(StrEnum):
    INDEPENDENT_ASSESSMENT = "INDEPENDENT_ASSESSMENT"
    REBUTTAL = "REBUTTAL"
    FINAL_ASSESSMENT = "FINAL_ASSESSMENT"


class EvidenceSufficiency(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class Finding:
    """One concise hypothesis assessment, with all supporting references."""

    hypothesis_id: str
    support_score: int
    evidence_sufficiency: EvidenceSufficiency
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    summary: str
    mixed_evidence_ids: tuple[str, ...] = ()
    verification_questions: tuple[UnresolvedQuestion, ...] = ()

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip():
            raise ValueError("findings require a hypothesis_id")
        if isinstance(self.support_score, bool) or not isinstance(self.support_score, int):
            raise TypeError("support_score must be an integer")
        if not 0 <= self.support_score <= 100:
            raise ValueError("support_score must be between 0 and 100")
        if not self.summary.strip():
            raise ValueError("findings require a concise summary")
        if not self.supporting_evidence_ids and not self.contradicting_evidence_ids and not self.mixed_evidence_ids:
            raise ValueError("factual findings require at least one evidence ID")

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        """All references in stable, de-duplicated order."""

        return tuple(dict.fromkeys(self.supporting_evidence_ids + self.contradicting_evidence_ids + self.mixed_evidence_ids))

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "support_score": self.support_score,
            "evidence_sufficiency": self.evidence_sufficiency.value,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradicting_evidence_ids": list(self.contradicting_evidence_ids),
            "mixed_evidence_ids": list(self.mixed_evidence_ids),
            "summary": self.summary,
            "verification_questions": [item.to_dict() for item in self.verification_questions],
        }


@dataclass(frozen=True)
class UnresolvedQuestion:
    """A human-resolvable question grounded in the supplied evidence pack."""

    question: str
    evidence_ids: tuple[str, ...]
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("unresolved questions require question text")
        if not self.evidence_ids:
            raise ValueError("unresolved questions require at least one evidence ID")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "question": self.question,
            "evidence_ids": list(self.evidence_ids),
        }
        if self.reason:
            result["reason"] = self.reason
        return result


@dataclass(frozen=True)
class AgentAssessment:
    """Public assessment output for one agent and one fixed round."""

    role: AgentRole
    round_number: int
    phase: AnalysisPhase
    findings: tuple[Finding, ...]
    unresolved_questions: tuple[UnresolvedQuestion, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "round": self.round_number,
            "phase": self.phase.value,
            "findings": [finding.to_dict() for finding in self.findings],
            "unresolved_questions": [item.to_dict() for item in self.unresolved_questions],
        }


@dataclass(frozen=True)
class AgentInput:
    """Input presented to a provider; prior inputs are summaries, not thoughts."""

    event_id: str
    role: AgentRole
    round_number: int
    phase: AnalysisPhase
    evidence: tuple[dict[str, Any], ...]
    hypotheses: tuple[dict[str, str], ...]
    prior_assessment: AgentAssessment | None = None
    opponent_assessment: AgentAssessment | None = None

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(item["evidence_id"] for item in self.evidence)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the provider input without any hidden conversation state."""

        return {
            "event_id": self.event_id,
            "role": self.role.value,
            "round": self.round_number,
            "phase": self.phase.value,
            "evidence": [dict(item) for item in self.evidence],
            "evidence_ids": list(self.evidence_ids),
            "hypotheses": [dict(item) for item in self.hypotheses],
            "prior_assessment": self.prior_assessment.to_dict()
            if self.prior_assessment
            else None,
            "opponent_assessment": self.opponent_assessment.to_dict()
            if self.opponent_assessment
            else None,
        }


@dataclass(frozen=True)
class StructuredAnalysisRound:
    """One of the maximum three public analysis rounds."""

    round_number: int
    phase: AnalysisPhase
    investigator: AgentAssessment
    skeptic: AgentAssessment
    unresolved_questions: tuple[UnresolvedQuestion, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round_number,
            "phase": self.phase.value,
            "investigator": self.investigator.to_dict(),
            "skeptic": self.skeptic.to_dict(),
            "unresolved_questions": [item.to_dict() for item in self.unresolved_questions],
        }


@dataclass(frozen=True)
class StructuredAnalysisResult:
    """Complete output suitable for persistence or a report API."""

    event_id: str
    status: str
    evidence_ids: tuple[str, ...]
    rounds: tuple[StructuredAnalysisRound, ...]
    unresolved_questions: tuple[UnresolvedQuestion, ...]
    algorithm_version: str = ALGORITHM_VERSION
    validation_status: str = "VALID"
    repaired: bool = False

    @property
    def final_round(self) -> StructuredAnalysisRound:
        return self.rounds[-1]

    def to_dict(self) -> dict[str, Any]:
        final = self.final_round
        return {
            "event_id": self.event_id,
            "status": self.status,
            "validation_status": self.validation_status,
            "repaired": self.repaired,
            "algorithm_version": self.algorithm_version,
            "evidence_ids": list(self.evidence_ids),
            "rounds": [item.to_dict() for item in self.rounds],
            "final_assessment": {
                "investigator": final.investigator.to_dict(),
                "skeptic": final.skeptic.to_dict(),
            },
            "unresolved_questions": [item.to_dict() for item in self.unresolved_questions],
        }


AgentRunner = Callable[[AgentInput], Mapping[str, Any] | AgentAssessment]

MAX_OUTPUT_REPAIR_RETRIES = 1


def _normalise_evidence(
    evidence: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    values: list[Mapping[str, Any]]
    if isinstance(evidence, Mapping):
        values = []
        for key, item in evidence.items():
            if not isinstance(item, Mapping):
                raise TypeError("evidence values must be mappings")
            if "evidence_id" in item and str(item["evidence_id"]) != str(key):
                raise ValueError(f"evidence key {key!r} does not match evidence_id")
            values.append({**item, "evidence_id": str(key)})
    else:
        values = list(evidence)

    if not values:
        raise ValueError("analysis requires at least one structured evidence object")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, Mapping):
            raise TypeError("evidence items must be mappings")
        evidence_id = str(item.get("evidence_id", "")).strip()
        if not evidence_id:
            raise ValueError("every evidence object requires a non-empty evidence_id")
        if evidence_id in seen:
            raise ValueError(f"duplicate evidence_id: {evidence_id}")
        if not str(item.get("observation", "")).strip() or not str(item.get("source", "")).strip():
            raise ValueError(f"evidence {evidence_id} requires observation and source")
        seen.add(evidence_id)
        result.append({**item, "evidence_id": evidence_id})
    return tuple(result)


def _normalise_hypotheses(
    hypotheses: Mapping[str, str] | Sequence[str | Mapping[str, str]],
) -> tuple[dict[str, str], ...]:
    if isinstance(hypotheses, Mapping):
        values = [{"hypothesis_id": str(key), "label": str(label)} for key, label in hypotheses.items()]
    else:
        values = []
        for item in hypotheses:
            if isinstance(item, Mapping):
                hypothesis_id = str(item.get("hypothesis_id", item.get("id", ""))).strip()
                label = str(item.get("label", item.get("hypothesis", ""))).strip()
            else:
                hypothesis_id = str(item).strip()
                label = hypothesis_id
            values.append({"hypothesis_id": hypothesis_id, "label": label})
    if not values:
        raise ValueError("analysis requires at least one hypothesis")
    seen: set[str] = set()
    for item in values:
        if not item["hypothesis_id"] or not item["label"]:
            raise ValueError("hypotheses require non-empty IDs and labels")
        label = item["label"].lower()
        if any(term in label for term in _FORBIDDEN_HYPOTHESIS_TERMS):
            raise ValueError(
                f"hypothesis {item['hypothesis_id']!r} uses out-of-scope blame, legal, or entity framing"
            )
        if item["hypothesis_id"] in seen:
            raise ValueError(f"duplicate hypothesis_id: {item['hypothesis_id']}")
        seen.add(item["hypothesis_id"])
    return tuple(values)


def plain_text(text: Any, *, field: str, word_cap: int | None = None) -> str:
    """Normalise model prose to the console's copy rules.

    The prompt asks for no em-dashes; this is the guard for a model that
    ignores it, because a rule the prompt states and nothing enforces is a
    rule the screen breaks. A spaced dash becomes a full stop when a new
    sentence follows (capital letter) and a comma otherwise; a bare em-dash
    between digits is a range and becomes an en-dash; any other bare em-dash
    becomes a colon. Word caps are measured and logged, not enforced, for the
    reason at the constants above.
    """

    text = " ".join(str(text).split())

    def _clause_break(match: re.Match[str]) -> str:
        following = match.string[match.end() : match.end() + 1]
        return ". " if following.isupper() else ", "

    text = _SPACED_DASH.sub(_clause_break, text)
    text = _NUMERIC_EMDASH.sub("\u2013", text)
    text = text.replace("\u2014", ": ")
    text = " ".join(text.split()).rstrip(" :,")
    if word_cap is not None:
        words = len(text.split())
        if words > word_cap:
            logger.warning("%s runs to %d words against a cap of %d", field, words, word_cap)
    return text


def _ids(raw: Any, *, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise TypeError(f"{field_name} must be a sequence of evidence IDs")
    values = tuple(str(value).strip() for value in raw)
    if any(not value for value in values):
        raise ValueError(f"{field_name} cannot contain empty evidence IDs")
    return tuple(dict.fromkeys(values))


def _question(
    raw: str | Mapping[str, Any],
    valid_evidence_ids: set[str],
) -> UnresolvedQuestion:
    if isinstance(raw, Mapping):
        question = raw.get("question", raw.get("text", ""))
        evidence_ids = _ids(raw.get("evidence_ids", raw.get("evidence", ())), field_name="question evidence_ids")
        reason = raw.get("reason", "")
    else:
        question = raw
        evidence_ids = ()
        reason = ""
    question = plain_text(question, field="question", word_cap=QUESTION_WORD_CAP)
    reason = plain_text(reason, field="question reason", word_cap=REASON_WORD_CAP)
    _validate_ids(evidence_ids, valid_evidence_ids, "question")
    return UnresolvedQuestion(question=question, evidence_ids=evidence_ids, reason=reason)


def _validate_ids(ids: Sequence[str], valid_evidence_ids: set[str], context: str) -> None:
    unknown = sorted(set(ids) - valid_evidence_ids)
    if unknown:
        raise ValueError(f"{context} cites unknown evidence IDs: {', '.join(unknown)}")


def _assessment(
    raw: Mapping[str, Any] | AgentAssessment,
    *,
    role: AgentRole,
    round_number: int,
    phase: AnalysisPhase,
    hypotheses: tuple[dict[str, str], ...],
    valid_evidence_ids: set[str],
) -> AgentAssessment:
    if isinstance(raw, AgentAssessment):
        assessment = raw
        if (assessment.role, assessment.round_number, assessment.phase) != (role, round_number, phase):
            raise ValueError("provider returned an assessment for the wrong agent or round")
        expected = tuple(item["hypothesis_id"] for item in hypotheses)
        actual = tuple(finding.hypothesis_id for finding in assessment.findings)
        if set(actual) != set(expected) or len(actual) != len(expected):
            raise ValueError(
                "agent output must contain exactly one finding for each "
                f"hypothesis: {expected}"
            )
        for finding in assessment.findings:
            _validate_finding(finding, hypotheses, valid_evidence_ids)
        for question in assessment.unresolved_questions:
            _validate_ids(question.evidence_ids, valid_evidence_ids, "question")
        return assessment
    if not isinstance(raw, Mapping):
        raise TypeError("agent output must be a structured mapping or AgentAssessment")

    raw_findings = raw.get("findings", raw.get("hypotheses"))
    if isinstance(raw_findings, Mapping):
        finding_items = [
            {**(value if isinstance(value, Mapping) else {}), "hypothesis_id": key}
            for key, value in raw_findings.items()
        ]
    elif isinstance(raw_findings, Sequence) and not isinstance(raw_findings, str):
        finding_items = list(raw_findings)
    else:
        raise TypeError("agent output requires structured findings for every hypothesis")

    findings: list[Finding] = []
    for raw_finding in finding_items:
        if not isinstance(raw_finding, Mapping):
            raise TypeError("each finding must be a mapping")
        hypothesis_id = str(raw_finding.get("hypothesis_id", raw_finding.get("id", ""))).strip()
        support = raw_finding.get("support_score", raw_finding.get("support"))
        if support is None:
            raise ValueError(f"finding {hypothesis_id!r} requires support_score")
        sufficiency = str(
            raw_finding.get("evidence_sufficiency", raw_finding.get("sufficiency", ""))
        ).upper()
        try:
            parsed_sufficiency = EvidenceSufficiency(sufficiency)
        except ValueError:
            raise ValueError(f"finding {hypothesis_id!r} has invalid evidence_sufficiency") from None
        supporting = _ids(
            raw_finding.get("supporting_evidence_ids", raw_finding.get("supporting_evidence", ())),
            field_name="supporting_evidence_ids",
        )
        contradicting = _ids(
            raw_finding.get("contradicting_evidence_ids", raw_finding.get("contradicting_evidence", ())),
            field_name="contradicting_evidence_ids",
        )
        mixed = _ids(
            raw_finding.get("mixed_evidence_ids", raw_finding.get("mixed_evidence", ())),
            field_name="mixed_evidence_ids",
        )
        _validate_ids(supporting + contradicting + mixed, valid_evidence_ids, f"finding {hypothesis_id}")
        # Overlap is a recoverable model-output problem. Keeping the ID in a
        # first-class mixed bucket preserves the fact that the model saw
        # implications in both directions without arbitrarily choosing one.
        overlap = set(supporting) & set(contradicting)
        if overlap:
            mixed = tuple(dict.fromkeys(mixed + tuple(item for item in supporting if item in overlap) + tuple(item for item in contradicting if item in overlap)))
            supporting = tuple(item for item in supporting if item not in overlap)
            contradicting = tuple(item for item in contradicting if item not in overlap)
        raw_questions = raw_finding.get("verification_questions", ())
        questions = tuple(_question(item, valid_evidence_ids) for item in raw_questions)
        summary = plain_text(
            raw_finding.get("summary", raw_finding.get("reasoning_summary", "")),
            field=f"finding {hypothesis_id} summary",
            word_cap=SUMMARY_WORD_CAP,
        )
        if isinstance(support, bool):
            raise TypeError(f"finding {hypothesis_id!r} support_score must be an integer")
        try:
            numeric_support = float(support)
        except (TypeError, ValueError):
            raise TypeError(f"finding {hypothesis_id!r} support_score must be an integer") from None
        if not math.isfinite(numeric_support) or not numeric_support.is_integer():
            raise ValueError(f"finding {hypothesis_id!r} support_score must be an integer")
        findings.append(
            Finding(
                hypothesis_id=hypothesis_id,
                support_score=int(numeric_support),
                evidence_sufficiency=parsed_sufficiency,
                supporting_evidence_ids=supporting,
                contradicting_evidence_ids=contradicting,
                mixed_evidence_ids=mixed,
                summary=summary,
                verification_questions=questions,
            )
        )

    expected = tuple(item["hypothesis_id"] for item in hypotheses)
    actual = tuple(item.hypothesis_id for item in findings)
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise ValueError(f"agent output must contain exactly one finding for each hypothesis: {expected}")
    if len(set(actual)) != len(actual):
        raise ValueError("agent output contains duplicate hypothesis findings")
    unresolved = tuple(
        _question(item, valid_evidence_ids)
        for item in raw.get("unresolved_questions", raw.get("unresolved_disagreements", ()))
    )
    return AgentAssessment(
        role=role,
        round_number=round_number,
        phase=phase,
        findings=tuple(findings),
        unresolved_questions=unresolved,
    )


def _validate_finding(
    finding: Finding,
    hypotheses: tuple[dict[str, str], ...],
    valid_evidence_ids: set[str],
) -> None:
    if finding.hypothesis_id not in {item["hypothesis_id"] for item in hypotheses}:
        raise ValueError(f"unknown hypothesis ID: {finding.hypothesis_id}")
    _validate_ids(finding.evidence_ids, valid_evidence_ids, f"finding {finding.hypothesis_id}")
    if set(finding.supporting_evidence_ids) & set(finding.contradicting_evidence_ids):
        raise ValueError(f"finding {finding.hypothesis_id!r} cites evidence in both directions")
    _validate_ids(finding.mixed_evidence_ids, valid_evidence_ids, f"finding {finding.hypothesis_id} mixed evidence")
    for question in finding.verification_questions:
        _validate_ids(question.evidence_ids, valid_evidence_ids, "question")


def _synthesise_disagreement(
    investigator: AgentAssessment,
    skeptic: AgentAssessment,
    valid_evidence_ids: set[str],
) -> UnresolvedQuestion | None:
    investigator_top = max(investigator.findings, key=lambda item: item.support_score)
    skeptic_top = max(skeptic.findings, key=lambda item: item.support_score)
    if investigator_top.hypothesis_id == skeptic_top.hypothesis_id and abs(
        investigator_top.support_score - skeptic_top.support_score
    ) < 20:
        return None
    evidence_ids = tuple(
        dict.fromkeys(investigator_top.evidence_ids + skeptic_top.evidence_ids)
    )
    _validate_ids(evidence_ids, valid_evidence_ids, "synthesised disagreement")
    if investigator_top.hypothesis_id == skeptic_top.hypothesis_id:
        question = (
            f"Why do the Investigator and Skeptic assign materially different support "
            f"to {investigator_top.hypothesis_id}?"
        )
    else:
        question = (
            "Which competing event-history explanation is better supported: "
            f"{investigator_top.hypothesis_id} or {skeptic_top.hypothesis_id}?"
        )
    return UnresolvedQuestion(
        question=question,
        evidence_ids=evidence_ids,
        reason="The final structured assessments retain different leading support rather than forcing agreement.",
    )


def run_structured_analysis(
    event_id: str,
    evidence: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    hypotheses: Mapping[str, str] | Sequence[str | Mapping[str, str]],
    investigator: AgentRunner,
    skeptic: AgentRunner,
    *,
    max_rounds: int = MAX_ROUNDS,
    on_round: Callable[[int, int, AnalysisPhase], None] | None = None,
) -> StructuredAnalysisResult:
    """Run independent, rebuttal, and final rounds with strict output checks.

    The callbacks are intentionally provider-neutral.  Round two receives the
    opponent's round-one structured assessment; round three receives the
    opponent's round-two assessment.  No callback output is copied through as
    conversation: only the validated schema is persisted and returned.

    ``on_round`` is told ``(round_number, max_rounds, phase)`` before each
    round's provider calls start. It exists so a job runner can report which
    round is in flight to whoever is waiting; it sees no assessment content.
    """

    if not str(event_id).strip():
        raise ValueError("analysis requires a non-empty event_id")
    if not isinstance(max_rounds, int) or not 1 <= max_rounds <= MAX_ROUNDS:
        raise ValueError(f"max_rounds must be between 1 and {MAX_ROUNDS}")
    evidence_objects = _normalise_evidence(evidence)
    valid_evidence_ids = {item["evidence_id"] for item in evidence_objects}
    hypothesis_objects = _normalise_hypotheses(hypotheses)
    rounds: list[StructuredAnalysisRound] = []
    repaired_output = False

    for round_number in range(1, max_rounds + 1):
        phase = (
            AnalysisPhase.INDEPENDENT_ASSESSMENT
            if round_number == 1
            else AnalysisPhase.REBUTTAL
            if round_number == 2
            else AnalysisPhase.FINAL_ASSESSMENT
        )
        if on_round is not None:
            on_round(round_number, max_rounds, phase)
        previous = rounds[-1] if rounds else None
        investigator_input = AgentInput(
            event_id=str(event_id),
            role=AgentRole.INVESTIGATOR,
            round_number=round_number,
            phase=phase,
            evidence=evidence_objects,
            hypotheses=hypothesis_objects,
            prior_assessment=previous.investigator if previous else None,
            opponent_assessment=previous.skeptic if previous else None,
        )
        skeptic_input = AgentInput(
            event_id=str(event_id),
            role=AgentRole.SKEPTIC,
            round_number=round_number,
            phase=phase,
            evidence=evidence_objects,
            hypotheses=hypothesis_objects,
            prior_assessment=previous.skeptic if previous else None,
            opponent_assessment=previous.investigator if previous else None,
        )
        def validated_call(
            agent: AgentRunner,
            agent_input: AgentInput,
            current_round: int = round_number,
            current_phase: AnalysisPhase = phase,
        ) -> tuple[AgentAssessment, bool]:
            """Allow one bounded provider retry for recoverable output failures.

            The second call is still schema-constrained and goes through the
            same semantic validator. Unknown evidence, invalid hypotheses and
            missing usable findings therefore remain hard failures.
            """
            last_error: Exception | None = None
            for attempt in range(MAX_OUTPUT_REPAIR_RETRIES + 1):
                try:
                    output = agent(agent_input)
                    return _assessment(
                        output,
                        role=agent_input.role,
                        round_number=current_round,
                        phase=current_phase,
                        hypotheses=hypothesis_objects,
                        valid_evidence_ids=valid_evidence_ids,
                    ), attempt > 0
                except Exception as exc:  # noqa: BLE001 - provider SDKs expose unrelated failure types
                    last_error = exc
                    if attempt < MAX_OUTPUT_REPAIR_RETRIES:
                        logger.warning(
                            "Retrying %s round %d after structured-output failure: %s",
                            agent_input.role.value,
                            current_round,
                            exc,
                        )
            assert last_error is not None
            raise last_error

        # Both roles in a round read only the *previous* round, never each
        # other, so running them concurrently changes wall time and nothing
        # else -- same inputs, same outputs, same validation. It is what keeps
        # a two-round assessment inside API Gateway's 30s response cap; run
        # sequentially, four provider calls overshoot it. Resolving the
        # investigator first preserves the sequential exception precedence.
        with ThreadPoolExecutor(max_workers=2) as pool:
            investigator_future = pool.submit(validated_call, investigator, investigator_input)
            skeptic_future = pool.submit(validated_call, skeptic, skeptic_input)
            investigator_output = investigator_future.result()
            skeptic_output = skeptic_future.result()
        investigator_assessment, investigator_repaired = investigator_output
        skeptic_assessment, skeptic_repaired = skeptic_output
        repaired_output = repaired_output or investigator_repaired or skeptic_repaired
        questions = list(investigator_assessment.unresolved_questions)
        questions.extend(skeptic_assessment.unresolved_questions)
        if round_number == max_rounds:
            disagreement = _synthesise_disagreement(
                investigator_assessment, skeptic_assessment, valid_evidence_ids
            )
            if disagreement:
                questions.append(disagreement)
        unique_questions: dict[tuple[str, tuple[str, ...]], UnresolvedQuestion] = {}
        for question in questions:
            unique_questions.setdefault((question.question, question.evidence_ids), question)
        rounds.append(
            StructuredAnalysisRound(
                round_number=round_number,
                phase=phase,
                investigator=investigator_assessment,
                skeptic=skeptic_assessment,
                unresolved_questions=tuple(unique_questions.values()),
            )
        )

    final_questions = rounds[-1].unresolved_questions
    status = "UNRESOLVED" if final_questions else "CONVERGED"
    has_mixed_evidence = any(
        finding.mixed_evidence_ids
        for analysis_round in rounds
        for assessment in (analysis_round.investigator, analysis_round.skeptic)
        for finding in assessment.findings
    )
    return StructuredAnalysisResult(
        event_id=str(event_id),
        status=status,
        evidence_ids=tuple(item["evidence_id"] for item in evidence_objects),
        rounds=tuple(rounds),
        unresolved_questions=final_questions,
        validation_status=(
            "VALID_WITH_AMBIGUITY"
            if has_mixed_evidence
            else "REPAIRED"
            if repaired_output
            else "VALID"
        ),
        repaired=has_mixed_evidence or repaired_output,
    )


run_investigator_skeptic_analysis = run_structured_analysis
run_adversarial_analysis = run_structured_analysis
AnalysisResult = StructuredAnalysisResult


__all__ = [
    "ALGORITHM_VERSION",
    "MAX_ROUNDS",
    "AgentAssessment",
    "AgentInput",
    "AgentRole",
    "AnalysisPhase",
    "AnalysisResult",
    "EvidenceSufficiency",
    "Finding",
    "StructuredAnalysisResult",
    "StructuredAnalysisRound",
    "UnresolvedQuestion",
    "run_adversarial_analysis",
    "run_investigator_skeptic_analysis",
    "run_structured_analysis",
]
