"""Explicit Investigator/Skeptic route and engagement-report integration."""

from __future__ import annotations

import pytest

from app import analysis_jobs, audit_events, audit_store, create_app

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


def _reset() -> None:
    audit_events.AUDIT_ANALYSES.clear()
    audit_events.AUDIT_PACKS.pop(AUDIT, None)
    # Job rows share the audit-state store, which is a module-level dict
    # locally. Leaving one behind makes the next test read a COMPLETE job.
    audit_store._MEMORY.clear()


@pytest.fixture
def client():
    _reset()
    app = create_app({"TESTING": True, "ANALYSIS_PROVIDER": _provider})
    yield app.test_client()
    _reset()


def _event_id(client) -> str:
    return client.get(f"/api/audits/{AUDIT}/events?limit=1").get_json()["events"][0]["eventId"]


def test_analysis_is_explicit_and_is_included_in_the_selected_event_report(client):
    event_id = _event_id(client)

    not_run = client.get(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert not_run.status_code == 200
    assert not_run.get_json() == {
        "auditId": AUDIT, "eventId": event_id, "jobStatus": "NOT_RUN",
    }

    # No worker function is configured here, so the job runs inline and the
    # POST already carries the outcome -- 200, not the deployed path's 202.
    generated = client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert generated.status_code == 200
    job = generated.get_json()
    assert job["jobStatus"] == "COMPLETE"
    analysis = job["analysis"]
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
    evidence = audit_events.analysis_evidence(AUDIT, "FE-20190904-0fb85076c0")

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

    _reset()
    app = create_app({"TESTING": True, "ANALYSIS_PROVIDER": unsupported_provider})
    client = app.test_client()
    event_id = _event_id(client)

    response = client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    # The request was valid; the work failed. That is a FAILED job, not a
    # 502 -- the deployed path cannot report it any other way, because the
    # response is long gone by the time the worker gets there.
    assert response.status_code == 200
    job = response.get_json()
    assert job["jobStatus"] == "FAILED"
    assert "unknown evidence IDs" in job["error"]
    assert job["analysis"] is None
    assert audit_events.analysis_for_event(AUDIT, event_id) is None


def test_poll_reports_running_work_without_starting_a_second_job(client, monkeypatch):
    """The deployed shape: dispatch hands off, and GET never spends tokens."""
    event_id = _event_id(client)
    invocations: list[dict] = []
    monkeypatch.setenv("ANALYSIS_WORKER_FUNCTION", "vibe-analysis-worker")
    monkeypatch.setattr(
        analysis_jobs,
        "_invoke_worker",
        lambda function_name, audit_id, event: invocations.append(
            {"function": function_name, "auditId": audit_id, "eventId": event}
        ),
    )

    accepted = client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert accepted.status_code == 202
    assert accepted.get_json()["jobStatus"] == "RUNNING"
    assert invocations == [
        {"function": "vibe-analysis-worker", "auditId": AUDIT, "eventId": event_id}
    ]

    polled = client.get(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert polled.status_code == 200
    assert polled.get_json()["jobStatus"] == "RUNNING"
    assert polled.get_json()["analysis"] is None

    # A second press while the first job is in flight must not run the two
    # rounds again -- that is the same result billed twice.
    again = client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert again.status_code == 202
    assert len(invocations) == 1

    # What the worker does, in the worker's own process.
    analysis_jobs.run(AUDIT, event_id, provider=_provider)
    completed = client.get(f"/api/audits/{AUDIT}/events/{event_id}/analyse").get_json()
    assert completed["jobStatus"] == "COMPLETE"
    assert completed["analysis"]["event_id"] == event_id


def test_a_worker_that_never_recorded_an_outcome_does_not_block_a_retry(client, monkeypatch):
    event_id = _event_id(client)
    monkeypatch.setenv("ANALYSIS_WORKER_FUNCTION", "vibe-analysis-worker")
    monkeypatch.setattr(analysis_jobs, "_invoke_worker", lambda *args: None)
    client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse")

    audit_store.update(
        analysis_jobs.job_key(AUDIT, event_id),
        lambda record: record.__setitem__("startedAt", "2019-09-01T00:00:00+00:00"),
    )

    retried = client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert retried.status_code == 202
    assert retried.get_json()["startedAt"] != "2019-09-01T00:00:00+00:00"


def test_a_failed_dispatch_is_recorded_rather_than_left_running(client, monkeypatch):
    event_id = _event_id(client)
    monkeypatch.setenv("ANALYSIS_WORKER_FUNCTION", "vibe-analysis-worker")

    def _unavailable(*args):
        raise RuntimeError("Lambda invoke failed")

    monkeypatch.setattr(analysis_jobs, "_invoke_worker", _unavailable)
    response = client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse")
    assert response.status_code == 200
    assert response.get_json()["jobStatus"] == "FAILED"
    assert client.get(f"/api/audits/{AUDIT}/events/{event_id}/analyse").get_json()["jobStatus"] == "FAILED"


def test_a_running_job_reports_its_stage_and_stored_prose_follows_the_copy_rules(client, monkeypatch):
    """What #198 renders under the spinner, and what the ui-copy skill forbids on screen."""
    event_id = _event_id(client)
    monkeypatch.setenv("ANALYSIS_WORKER_FUNCTION", "vibe-analysis-worker")
    monkeypatch.setattr(analysis_jobs, "_invoke_worker", lambda *args: None)

    accepted = client.post(f"/api/audits/{AUDIT}/events/{event_id}/analyse").get_json()
    assert (accepted["jobStatus"], accepted["stage"]) == ("RUNNING", "Starting")

    stages_seen_by_a_poll: list[str] = []

    def provider(agent_input):
        # What GET returns while this very round is being answered.
        stages_seen_by_a_poll.append(analysis_jobs.read(AUDIT, event_id)["stage"])
        output = _provider(agent_input)
        for finding in output["findings"]:
            finding["summary"] = "VH backscatter fell after 03 Sep \u2014 no revegetation \u2014 consistent with sustained combustion"
        return output

    analysis_jobs.run(AUDIT, event_id, provider=provider)

    assert stages_seen_by_a_poll[:2] == ["Round 1 of 2: independent assessment"] * 2
    assert stages_seen_by_a_poll[2:] == ["Round 2 of 2: rebuttal"] * 2
    completed = client.get(f"/api/audits/{AUDIT}/events/{event_id}/analyse").get_json()
    assert (completed["jobStatus"], completed["stage"]) == ("COMPLETE", None)
    summaries = [
        finding["summary"]
        for analysis_round in completed["analysis"]["rounds"]
        for role in ("investigator", "skeptic")
        for finding in analysis_round[role]["findings"]
    ]
    assert summaries
    assert all("\u2014" not in summary for summary in summaries)
    assert summaries[0] == "VH backscatter fell after 03 Sep, no revegetation, consistent with sustained combustion"
