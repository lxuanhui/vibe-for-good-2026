"""The Bedrock adapter's request shape: prompt caching must not change the prompt."""

from __future__ import annotations

import json

import pytest
from botocore.exceptions import ClientError
from data_pipeline.analysis.investigator_skeptic import (
    AgentAssessment,
    AgentInput,
    AgentRole,
    AnalysisPhase,
    EvidenceSufficiency,
    Finding,
)

from app import analysis_provider

EVIDENCE = (
    {"evidence_id": "ENV_001", "category": "weather", "observation": "No rain for 72 hours."},
    # A value that contains the per-call key names, so a split that searched
    # the text for `"role"` would land inside the evidence.
    {"evidence_id": "ENV_002", "category": "thermal", "observation": 'Fields "role":1 and "round":2 quoted.'},
)
HYPOTHESES = ({"hypothesis_id": "H1", "label": "Independent local ignition."},)


def _assessment(role: AgentRole) -> AgentAssessment:
    return AgentAssessment(
        role=role,
        round_number=1,
        phase=AnalysisPhase.INDEPENDENT_ASSESSMENT,
        findings=(
            Finding(
                hypothesis_id="H1",
                support_score=40,
                evidence_sufficiency=EvidenceSufficiency.PARTIAL,
                supporting_evidence_ids=("ENV_001",),
                contradicting_evidence_ids=(),
                summary="Retained as an evidence-limited possibility.",
            ),
        ),
    )


def _input(role: AgentRole, round_number: int) -> AgentInput:
    previous = None if round_number == 1 else _assessment(role)
    opponent = None if round_number == 1 else _assessment(
        AgentRole.SKEPTIC if role is AgentRole.INVESTIGATOR else AgentRole.INVESTIGATOR
    )
    return AgentInput(
        event_id="FE-1",
        role=role,
        round_number=round_number,
        phase=AnalysisPhase.INDEPENDENT_ASSESSMENT if round_number == 1 else AnalysisPhase.REBUTTAL,
        evidence=EVIDENCE,
        hypotheses=HYPOTHESES,
        prior_assessment=previous,
        opponent_assessment=opponent,
    )


OK_RESPONSE = {
    "stopReason": "end_turn",
    "output": {"message": {"content": [{"text": '{"findings": [], "unresolved_questions": []}'}]}},
    "usage": {"inputTokens": 120, "outputTokens": 9, "cacheReadInputTokens": 100, "cacheWriteInputTokens": 0},
}


class FakeBedrock:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def bedrock(monkeypatch):
    fake = FakeBedrock(OK_RESPONSE)
    monkeypatch.setattr(analysis_provider, "_bedrock_client", lambda: fake)
    monkeypatch.delenv("BEDROCK_PROMPT_CACHE", raising=False)
    return fake


def _texts(call: dict) -> str:
    return "".join(block.get("text", "") for block in call["messages"][0]["content"])


def test_the_shared_prefix_is_marked_for_caching_and_the_model_reads_the_same_text(bedrock):
    agent_input = _input(AgentRole.INVESTIGATOR, 1)

    analysis_provider.bedrock_runner(agent_input)

    content = bedrock.calls[0]["messages"][0]["content"]
    assert [tuple(block) for block in content] == [("text",), ("cachePoint",), ("text",)]
    assert content[1] == {"cachePoint": {"type": "default"}}
    # Joined, the blocks are exactly the uncached prompt: caching changed the
    # request's shape, not what the model is shown.
    assert _texts(bedrock.calls[0]) == analysis_provider._prompt(agent_input)
    # The cut sits at the first per-call key, after the whole pack, even
    # though an evidence value contains the string `"role":`.
    assert content[0]["text"].endswith('"hypotheses":[{"hypothesis_id":"H1","label":"Independent local ignition."}]')
    assert content[2]["text"].startswith(',"role":"INVESTIGATOR","round":1,')
    document = json.loads(_texts(bedrock.calls[0])[len(analysis_provider._PROMPT):])
    assert document == agent_input.to_dict()


def test_all_four_calls_in_an_assessment_share_one_cached_prefix(bedrock):
    bedrock.outcomes = [OK_RESPONSE] * 4
    inputs = [_input(role, rnd) for rnd in (1, 2) for role in (AgentRole.INVESTIGATOR, AgentRole.SKEPTIC)]

    for agent_input in inputs:
        analysis_provider.bedrock_runner(agent_input)

    prefixes = {call["messages"][0]["content"][0]["text"] for call in bedrock.calls}
    tails = [call["messages"][0]["content"][2]["text"] for call in bedrock.calls]
    assert len(prefixes) == 1
    assert len(set(tails)) == 4
    # Round 2 carries the opponent's assessment, and only in the fresh tail.
    assert '"opponent_assessment":{' in tails[2] and '"opponent_assessment":{' in tails[3]
    assert "opponent_assessment" not in next(iter(prefixes))


def test_a_retry_carrying_the_rejection_reuses_the_cached_prefix(bedrock):
    """The reason the first reply was rejected rides in the per-call tail.

    If it landed in the shared block the retry would rewrite the cache it was
    meant to read, and the four-call assessment would pay for a fifth prefix.
    """
    from dataclasses import replace

    bedrock.outcomes = [OK_RESPONSE, OK_RESPONSE]
    first = _input(AgentRole.SKEPTIC, 1)
    retry = replace(first, rejection="agent output must contain exactly one finding for each hypothesis")

    analysis_provider.bedrock_runner(first)
    analysis_provider.bedrock_runner(retry)

    prefixes = [call["messages"][0]["content"][0]["text"] for call in bedrock.calls]
    tails = [call["messages"][0]["content"][2]["text"] for call in bedrock.calls]
    assert prefixes[0] == prefixes[1]
    assert "previous_reply_rejected" not in tails[0]
    assert tails[1].endswith('"previous_reply_rejected":"agent output must contain exactly one finding for each hypothesis"}')
    assert "previous_reply_rejected" in analysis_provider._PROMPT


def test_a_provider_that_rejects_the_cache_point_is_retried_once_uncached(bedrock):
    bedrock.outcomes = [
        ClientError(
            {"Error": {"Code": "ValidationException", "Message": "cachePoint is not supported by this model"}},
            "Converse",
        ),
        OK_RESPONSE,
    ]
    agent_input = _input(AgentRole.SKEPTIC, 1)

    result = analysis_provider.bedrock_runner(agent_input)

    assert result == {"findings": [], "unresolved_questions": []}
    assert len(bedrock.calls) == 2
    retried = bedrock.calls[1]["messages"][0]["content"]
    assert len(retried) == 1 and "cachePoint" not in retried[0]
    assert retried[0]["text"] == analysis_provider._prompt(agent_input)


def test_other_provider_errors_are_not_retried(bedrock):
    bedrock.outcomes = [
        ClientError({"Error": {"Code": "AccessDeniedException", "Message": "not available"}}, "Converse"),
    ]
    with pytest.raises(analysis_provider.AnalysisProviderUnavailable):
        analysis_provider.bedrock_runner(_input(AgentRole.INVESTIGATOR, 1))
    assert len(bedrock.calls) == 1


def test_caching_can_be_switched_off_to_measure_the_uncached_cost(bedrock, monkeypatch):
    monkeypatch.setenv("BEDROCK_PROMPT_CACHE", "0")
    agent_input = _input(AgentRole.INVESTIGATOR, 1)

    analysis_provider.bedrock_runner(agent_input)

    content = bedrock.calls[0]["messages"][0]["content"]
    assert content == [{"text": analysis_provider._prompt(agent_input)}]


def test_usage_including_cache_tokens_is_logged_per_call(bedrock, caplog):
    with caplog.at_level("INFO", logger="app.analysis_provider"):
        analysis_provider.bedrock_runner(_input(AgentRole.SKEPTIC, 2))
    line = next(record.getMessage() for record in caplog.records if "Bedrock usage" in record.getMessage())
    assert "role=SKEPTIC round=2 cached=True input=120 output=9 cache_read=100 cache_write=0" in line
