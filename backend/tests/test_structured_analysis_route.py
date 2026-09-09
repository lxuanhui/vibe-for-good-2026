"""Explicit Investigator/Skeptic route and engagement-report integration."""

from __future__ import annotations

import pytest

from app import audit_events, create_app

AUDIT = "demo-2019-haze"


def _provider(agent_input):
    """A schema-valid provider double that only cites the supplied pack."""

    evidence_id = agent_input.evidence_ids[0]
    findings = [
        {
            "hypothesis_id": hypothesis["hypothesis_id"],
            "support_score": 35 if hypothesis["hypothesis_id"] == "H1" else 15,
            "evidence_sufficiency": "PARTIAL",
            "supporting_evidence_ids": [evidence_id],
            "contradicting_evidence_ids": [],
            "summary": f"{agent_input.role.value} retains this as an evidence-limited possibility.",
            "verification_questions": [],
        }
        for hypothesis in agent_input.hypotheses
    ]
    return {
        "findings": findings,
        "unresolved_questions": [{
            "question": "Can an independent field observation distinguish the competing mechanisms?",
            "evidence_ids": [evidence_id],
            "reason": "The supplied evidence is limited to the current reconstruction.",
        }],
    }


@pytest.fixture
def client():
    audit_events.AUDIT_ANALYSES.clear()
    audit_events.AUDIT_PACKS.pop(AUDIT, None)
    app = create_app({"TESTING": True, "ANALYSIS_PROVIDER": _provider})
    yield app.test_client()
    audit_events.AUDIT_ANALYSES.clear()
    audit_events.AUDIT_PACKS.pop(AUDIT, None)


def _event_id(client) -> str:
    return client.get(f"/api/audits/{AUDIT}/events?limit=1").get_json()["events"][0]["eventId"]


def test_analysis_is_explicit_and_is_included_in_the_selected_event_report(client):
    event_id = _event_id(client)

    not_run = client.get(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert not_run.status_code == 200
    assert not_run.get_json() == {"status": "not_run", "eventId": event_id}

    generated = client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert generated.status_code == 201
    analysis = generated.get_json()
    assert analysis["event_id"] == event_id
    assert {finding["hypothesis_id"] for finding in analysis["final_assessment"]["investigator"]["findings"]} == {
        "H1", "H2", "H3", "H4", "H5", "H6"
    }
    valid_ids = set(analysis["evidence_ids"])
    assert valid_ids
    for assessment in analysis["final_assessment"].values():
        for finding in assessment["findings"]:
            assert set(finding["supporting_evidence_ids"]) <= valid_ids
            assert set(finding["contradicting_evidence_ids"]) <= valid_ids

    assert client.post(f"/api/audits/{AUDIT}/events/{event_id}/add-to-pack", json={}).status_code == 200
    report = client.get(f"/api/audits/{AUDIT}/report").get_json()
    assert report["aiAnalysis"] == [{"eventId": event_id, "analysis": analysis}]
    assert report["analysisNotRunEventIds"] == []
    assert report["unresolvedQuestions"]


def test_analysis_pack_keeps_weather_peat_and_graph_context_separate_from_raw_observations():
    # This event has the committed weather/peat enrichment and a precomputed
    # FireEventGraph relationship. The adapter is intentionally fed those
    # EvidenceObjects, not its raw FIRMS point membership list.
    evidence = audit_events._analysis_evidence(AUDIT, "FE-20190904-0fb85076c0")

    assert evidence is not None
    categories = {item["category"] for item in evidence}
    assert {"weather", "peat", "graph"} <= categories
    assert all(item["type"] != "raw_observation" for item in evidence)


def test_report_keeps_a_selected_event_honestly_not_run(client):
    event_id = _event_id(client)
    assert client.post(f"/api/audits/{AUDIT}/events/{event_id}/add-to-pack", json={}).status_code == 200

    report = client.get(f"/api/audits/{AUDIT}/report").get_json()
    assert report["aiAnalysis"] == []
    assert report["analysisNotRunEventIds"] == [event_id]
    assert "No Investigator/Skeptic analysis has been run" in report["sourceMethodSummary"]["ai"]


def test_unsupported_provider_evidence_is_rejected_and_not_persisted():
    def unsupported_provider(agent_input):
        result = _provider(agent_input)
        result["findings"][0]["supporting_evidence_ids"] = ["NOT_A_REAL_EVIDENCE_ID"]
        return result

    audit_events.AUDIT_ANALYSES.clear()
    app = create_app({"TESTING": True, "ANALYSIS_PROVIDER": unsupported_provider})
    client = app.test_client()
    event_id = _event_id(client)

    response = client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert response.status_code == 502
    assert "unknown evidence IDs" in response.get_json()["error"]
    assert audit_events.analysis_for_event(AUDIT, event_id) is None
