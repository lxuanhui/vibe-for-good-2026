import pytest

from data_pipeline.analysis.investigator_skeptic import (
    AgentAssessment,
    AgentRole,
    AnalysisPhase,
    EvidenceSufficiency,
    Finding,
    plain_text,
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


def test_on_round_is_told_each_round_before_its_provider_calls_start():
    """A job runner reports the round in flight; it never sees assessment content."""
    seen: list[tuple] = []
    provider_rounds: list[int] = []

    def provider(agent_input):
        provider_rounds.append(agent_input.round_number)
        return _assessment(agent_input.role, agent_input.round_number)

    run_structured_analysis(
        "FE-1",
        EVIDENCE,
        HYPOTHESES,
        provider,
        provider,
        max_rounds=2,
        on_round=lambda round_number, total, phase: seen.append((round_number, total, phase, len(provider_rounds))),
    )

    assert seen == [
        (1, 2, AnalysisPhase.INDEPENDENT_ASSESSMENT, 0),
        (2, 2, AnalysisPhase.REBUTTAL, 2),
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # A spaced dash joining two clauses becomes a comma.
        ("VH backscatter fell after 03 Sep \u2014 consistent with sustained combustion", "VH backscatter fell after 03 Sep, consistent with sustained combustion"),
        # A spaced dash before a new sentence becomes a full stop.
        ("No rain for 72 hours \u2014 The nearest peat is 3 km away.", "No rain for 72 hours. The nearest peat is 3 km away."),
        # Double hyphen and spaced en-dash are the same habit.
        ("No rain for 72 hours -- consistent with dry fuel", "No rain for 72 hours, consistent with dry fuel"),
        ("No rain for 72 hours \u2013 consistent with dry fuel", "No rain for 72 hours, consistent with dry fuel"),
        # A bare em-dash between digits is a range, and the copy rules allow an en-dash there.
        ("Wind alignment 0.81\u20140.99 over 12\u201472 hours", "Wind alignment 0.81\u20130.99 over 12\u201372 hours"),
        # Any other bare em-dash is a label break.
        ("Peat\u2014none mapped within 3 km", "Peat: none mapped within 3 km"),
        # A dangling dash leaves no punctuation behind.
        ("Peat contact unlikely \u2014", "Peat contact unlikely"),
        # Text that already follows the rules is untouched, en-dash ranges included.
        ("Estimated burn extent 240 ha; cloud gaps on 04\u201305 Sep limit confidence.", "Estimated burn extent 240 ha; cloud gaps on 04\u201305 Sep limit confidence."),
    ],
)
def test_model_prose_is_normalised_to_the_console_copy_rules(raw, expected):
    assert plain_text(raw, field="summary") == expected


def test_over_length_prose_is_logged_and_kept_rather_than_rejected(caplog):
    """A rejected round is a FAILED job the auditor pays for again."""
    long = " ".join(["word"] * 30)
    with caplog.at_level("WARNING", logger="data_pipeline.analysis.investigator_skeptic"):
        assert plain_text(long, field="finding H1 summary", word_cap=25) == long
    assert "finding H1 summary runs to 30 words against a cap of 25" in caplog.text


def test_normalisation_reaches_every_prose_field_of_a_stored_assessment():
    def provider(agent_input):
        raw = _assessment(agent_input.role, agent_input.round_number, unresolved=True)
        for finding in raw["findings"].values():
            finding["summary"] = "Dry 72 hours \u2014 consistent with local ignition"
            finding["verification_questions"] = [
                {"question": "Rain gauge \u2014 any record?", "evidence_ids": ["ENV_001"], "reason": "Gauge \u2014 decisive"}
            ]
        raw["unresolved_questions"][0]["question"] = "Which first \u2014 H1 or H2?"
        return raw

    result = run_structured_analysis("FE-1", EVIDENCE, HYPOTHESES, provider, provider, max_rounds=1).to_dict()
    text = []
    for role in ("investigator", "skeptic"):
        for finding in result["rounds"][0][role]["findings"]:
            text.append(finding["summary"])
            for question in finding["verification_questions"]:
                text.extend([question["question"], question["reason"]])
    text.extend(question["question"] for question in result["unresolved_questions"])
    assert text and not any("\u2014" in item for item in text)
    assert result["rounds"][0]["investigator"]["findings"][0]["summary"] == "Dry 72 hours, consistent with local ignition"
