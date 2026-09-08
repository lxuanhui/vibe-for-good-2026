import pytest

from data_pipeline.analysis.investigator_skeptic import (
    AgentAssessment,
    AgentRole,
    AnalysisPhase,
    EvidenceSufficiency,
    Finding,
    run_structured_analysis,
)

EVIDENCE = {
    "ENV_001": {
        "evidence_id": "ENV_001",
        "category": "weather",
        "type": "rainfall",
        "observation": "Rainfall was absent in the 72 hours before detection.",
        "source": "synthetic weather fixture",
    },
    "ENV_002": {
        "evidence_id": "ENV_002",
        "category": "thermal",
        "type": "event-cluster",
        "observation": "A neighbouring FireEvent was detected 1.8 km earlier.",
        "source": "synthetic FIRMS fixture",
    },
}

HYPOTHESES = {
    "H1": "Independent local ignition",
    "H2": "Surface propagation from an earlier neighbouring event",
}


def _assessment(role: AgentRole, round_number: int, *, unresolved: bool = False):
    if role is AgentRole.INVESTIGATOR:
        first_support, first_ids = 75, ["ENV_001"]
        second_support, second_ids = 25, ["ENV_002"]
    else:
        first_support, first_ids = 35, ["ENV_001"]
        second_support, second_ids = 78, ["ENV_002"]
    return {
        "findings": {
            "H1": {
                "support_score": first_support,
                "evidence_sufficiency": "PARTIAL",
                "supporting_evidence_ids": first_ids,
                "contradicting_evidence_ids": ["ENV_002"],
                "summary": f"Structured {role.value.lower()} finding for H1 in round {round_number}.",
            },
            "H2": {
                "support_score": second_support,
                "evidence_sufficiency": "PARTIAL",
                "supporting_evidence_ids": second_ids,
                "contradicting_evidence_ids": ["ENV_001"],
                "summary": f"Structured {role.value.lower()} finding for H2 in round {round_number}.",
            },
        },
        "unresolved_questions": (
            [
                {
                    "question": "Which event-history explanation should a human verify first?",
                    "evidence_ids": ["ENV_001", "ENV_002"],
                    "reason": "The available evidence supports competing explanations.",
                }
            ]
            if unresolved
            else []
        ),
    }


def test_runs_three_bounded_rounds_and_passes_only_structured_opponent_context():
    calls = []

    def investigator(agent_input):
        calls.append(agent_input)
        return _assessment(agent_input.role, agent_input.round_number, unresolved=agent_input.round_number == 3)

    def skeptic(agent_input):
        calls.append(agent_input)
        return _assessment(agent_input.role, agent_input.round_number, unresolved=agent_input.round_number == 3)

    result = run_structured_analysis("FIRE_001", EVIDENCE, HYPOTHESES, investigator, skeptic)

    assert [item.round_number for item in result.rounds] == [1, 2, 3]
    assert [item.phase for item in result.rounds] == [
        AnalysisPhase.INDEPENDENT_ASSESSMENT,
        AnalysisPhase.REBUTTAL,
        AnalysisPhase.FINAL_ASSESSMENT,
    ]
    assert len(calls) == 6
    round_two_investigator = next(
        item for item in calls if item.role is AgentRole.INVESTIGATOR and item.round_number == 2
    )
    assert round_two_investigator.evidence_ids == ("ENV_001", "ENV_002")
    assert round_two_investigator.opponent_assessment is not None
    assert round_two_investigator.opponent_assessment.role is AgentRole.SKEPTIC
    assert result.status == "UNRESOLVED"
    assert result.unresolved_questions

    serialized = result.to_dict()
    assert serialized["final_assessment"]["investigator"]["findings"][0]["summary"]
    assert "conversation" not in serialized
    assert "reasoning_log" not in serialized
    assert "chain_of_thought" not in serialized


def test_unknown_evidence_id_is_rejected_before_analysis_is_persisted():
    def agent(_input):
        value = _assessment(AgentRole.INVESTIGATOR, 1)
        value["findings"]["H1"]["supporting_evidence_ids"] = ["ENV_UNKNOWN"]
        return value

    with pytest.raises(ValueError, match="unknown evidence IDs"):
        run_structured_analysis("FIRE_001", EVIDENCE, HYPOTHESES, agent, agent, max_rounds=1)


def test_factual_finding_without_evidence_reference_is_rejected():
    def agent(agent_input):
        value = _assessment(agent_input.role, agent_input.round_number)
        value["findings"]["H1"]["supporting_evidence_ids"] = []
        value["findings"]["H1"]["contradicting_evidence_ids"] = []
        return value

    with pytest.raises(ValueError, match="require at least one evidence ID"):
        run_structured_analysis("FIRE_001", EVIDENCE, HYPOTHESES, agent, agent, max_rounds=1)


def test_prebuilt_assessment_cannot_skip_hypotheses():
    def agent(agent_input):
        return AgentAssessment(
            role=agent_input.role,
            round_number=agent_input.round_number,
            phase=agent_input.phase,
            findings=(
                Finding(
                    hypothesis_id="H1",
                    support_score=50,
                    evidence_sufficiency=EvidenceSufficiency.PARTIAL,
                    supporting_evidence_ids=("ENV_001",),
                    contradicting_evidence_ids=(),
                    summary="Only one of the required hypotheses was assessed.",
                ),
            ),
        )

    with pytest.raises(ValueError, match="exactly one finding for each hypothesis"):
        run_structured_analysis("FIRE_001", EVIDENCE, HYPOTHESES, agent, agent, max_rounds=1)


def test_round_limit_is_hard_bounded():
    with pytest.raises(ValueError, match="between 1 and 3"):
        run_structured_analysis("FIRE_001", EVIDENCE, HYPOTHESES, lambda _: {}, lambda _: {}, max_rounds=4)


def test_hypothesis_labels_cannot_cross_the_product_safety_boundary():
    with pytest.raises(ValueError, match="out-of-scope"):
        run_structured_analysis(
            "FIRE_001",
            EVIDENCE,
            {"H1": "Company responsibility for the fire"},
            lambda _: {},
            lambda _: {},
            max_rounds=1,
        )
