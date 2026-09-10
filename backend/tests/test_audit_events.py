"""The audit-scoped read endpoints over the reconstructed 2019 demo history."""

import pytest

from app import create_app
from app.audit_events import scoped_register_events
from app.review_routing import route_event

AUDIT = "demo-2019-haze"
BASE = f"/api/audits/{AUDIT}/events"


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    return app.test_client()


def test_lists_events_with_scope_and_provenance(client):
    body = client.get(f"{BASE}?limit=5").get_json()

    assert body["auditId"] == AUDIT
    assert len(body["events"]) == 5
    # `total` counts every match, not the page, so the UI can say how many
    # events an auditor is actually accountable for reviewing.
    assert body["total"] > 5
    assert body["scope"]["reviewStart"] == "2019-09-01"
    assert body["scope"]["reviewQueueCount"] == 396
    assert "FIRMS" in body["source"]["dataset"]
    progression = body["progression"]
    assert progression["rawObservations"] == 21519
    assert progression["qualifiedObservations"] == 20471
    assert progression["fireEvents"] == 3610
    assert progression["requiringHumanReview"] == 396
    assert progression["routingDiagnostics"]["humanReviewCount"] == 396
    assert progression["routingDiagnostics"]["priorityDistribution"] == {
        "HIGH": {"count": 396, "percentage": 0.1097},
        "MEDIUM": {"count": 3214, "percentage": 0.8903},
    }
    assert progression["routingDiagnostics"]["escalationReasonCodes"]["PRIORITY_HIGH"]["count"] == 396
    assert progression["routingDiagnostics"]["evidenceSufficiencyDistribution"] == {
        "PARTIAL": {"count": 3610, "percentage": 1.0},
    }
    assert progression["routingDiagnostics"]["componentContributionDistribution"] == {
        "event_validity": {
            "evaluatedCount": 3610,
            "totalContribution": 30045.0,
            "percentageOfContribution": 0.5811,
        },
        "evidence_sufficiency": {
            "evaluatedCount": 3610,
            "totalContribution": 21660.0,
            "percentageOfContribution": 0.4189,
        },
    }
    assert progression["selected"] == 0
    assert progression["selectedEventIds"] == []
    assert progression["compression"] is None
    assert progression["observationsToEventsCompression"] == 5.67
    assert progression["inScopeAndBuffer"] is None
    assert progression["scopeBoundaryAvailable"] is False
    assert progression["scopeCompression"] is None


def test_event_shape_is_camel_case_and_carries_triage(client):
    event = client.get(f"{BASE}?limit=1").get_json()["events"][0]

    assert event["eventId"].startswith("FE-")
    assert set(event["centroid"]) == {"lat", "lon"}
    assert event["triage"]["state"] in {"LIKELY_FIRE", "LIKELY_NON_FIRE", "AMBIGUOUS"}
    assert event["evidenceSufficiency"] == "PARTIAL"
    assert event["investigationPriority"] in {"MEDIUM", "HIGH"}
    assert event["reviewState"] in {"REVIEW_RECOMMENDED", "HUMAN_REVIEW"}
    assert event["reviewRouting"]["components"]
    assert {component["factor"] for component in event["reviewRouting"]["components"]} == {
        "event_validity", "environmental_significance", "event_complexity",
        "evidence_inconsistency", "unresolved_event_relationships", "evidence_sufficiency",
        "peat_involvement", "land_change_indicators", "propagation_uncertainty",
    }
    assert all(
        component["status"] == "EVALUATED"
        for component in event["reviewRouting"]["components"]
        if component["factor"] in {"event_validity", "evidence_sufficiency"}
    )
    assert all(
        component["status"] == "NOT_EVALUATED"
        for component in event["reviewRouting"]["components"]
        if component["factor"] == "event_complexity"
    )
    # Nothing in a summary may assert who or why -- only what was observed and
    # what Stage-1 derived from it (spec Section 3).
    assert "sensorMix" not in event, "the 2019 export has no sensor column to report"


def test_routing_boundary_keeps_escalations_inspectable():
    ambiguous = route_event({"eventId": "FE-AMBIGUOUS", "triage": {"state": "AMBIGUOUS"}})
    likely_fire_partial = route_event(
        {"eventId": "FE-FIRE", "triage": {"state": "LIKELY_FIRE"}},
        "PARTIAL",
    )

    assert ambiguous["reviewState"] == "REVIEW_RECOMMENDED"
    assert not ambiguous["escalatedForHumanReview"]
    assert likely_fire_partial["reviewState"] == "HUMAN_REVIEW"
    assert likely_fire_partial["escalationReasonCodes"] == ["PRIORITY_HIGH"]
    assert all(
        component["factor"] and component["status"]
        for component in likely_fire_partial["components"]
    )
    assert any(
        component["factor"] == "event_validity"
        and component["evidenceIds"]
        and component["status"] == "EVALUATED"
        for component in likely_fire_partial["components"]
    )


def test_routing_preserves_artifact_sufficiency_when_present():
    route = route_event(
        {
            "eventId": "FE-SUFFICIENT",
            "triage": {"state": "LIKELY_FIRE"},
            "evidenceSufficiency": "SUFFICIENT",
        }
    )

    assert route["evidenceSufficiency"] == "SUFFICIENT"
    assert route["investigationPriority"] == "MEDIUM"
    assert route["reviewState"] == "SCREENED"


def test_paging_walks_the_register_without_overlap(client):
    first = client.get(f"{BASE}?limit=3").get_json()["events"]
    second = client.get(f"{BASE}?limit=3&offset=3").get_json()["events"]

    assert [e["eventId"] for e in first] != [e["eventId"] for e in second]


def test_state_filter_selects_only_that_state(client):
    body = client.get(f"{BASE}?state=LIKELY_FIRE").get_json()

    assert body["total"] > 0
    assert {e["triage"]["state"] for e in body["events"]} == {"LIKELY_FIRE"}


def test_register_population_keeps_likely_non_fire_events_until_filtered_explicitly():
    events = [
        {
            "eventId": "FE-FIRE",
            "firstDetection": "2019-09-02T00:00:00+00:00",
            "lastDetection": "2019-09-02T01:00:00+00:00",
            "centroid": {"lon": 102.0, "lat": -1.0},
            "triage": {"state": "LIKELY_FIRE"},
        },
        {
            "eventId": "FE-NON-FIRE",
            "firstDetection": "2019-09-02T02:00:00+00:00",
            "lastDetection": "2019-09-02T03:00:00+00:00",
            "centroid": {"lon": 102.0, "lat": -1.0},
            "triage": {"state": "LIKELY_NON_FIRE"},
        },
    ]

    assert [event["eventId"] for event in scoped_register_events(events)] == [
        "FE-FIRE",
        "FE-NON-FIRE",
    ]


def test_bbox_filters_on_centroid(client):
    body = client.get(f"{BASE}?bbox=116,-4,117,-3").get_json()

    assert body["total"] > 0
    for event in body["events"]:
        assert 116 <= event["centroid"]["lon"] <= 117
        assert -4 <= event["centroid"]["lat"] <= -3


def test_progression_uses_the_current_scoped_register(client):
    full = client.get(f"{BASE}?limit=2000").get_json()
    body = client.get(f"{BASE}?bbox=116,-4,117,-3&limit=2000").get_json()
    events = body["events"]
    expected_count = sum(event["reviewState"] == "HUMAN_REVIEW" for event in events)

    assert body["total"] == len(events)
    assert body["progression"]["fireEvents"] < full["progression"]["fireEvents"]
    assert body["progression"]["requiringHumanReview"] != full["progression"]["requiringHumanReview"]
    assert body["scope"]["reviewQueueCount"] == expected_count
    assert body["progression"]["fireEvents"] == len(events)
    assert body["progression"]["requiringHumanReview"] == expected_count
    assert body["progression"]["routingDiagnostics"]["humanReviewCount"] == expected_count
    assert body["progression"]["routingDiagnostics"]["reviewStateDistribution"]["HUMAN_REVIEW"] == {
        "count": expected_count,
        "percentage": round(expected_count / len(events), 4),
    }
    assert body["progression"]["routingDiagnostics"]["humanReviewPercentage"] == round(
        expected_count / len(events), 4
    )


def test_bare_date_is_read_as_utc_not_naive(client):
    """A naive `since` compared against tz-aware detections used to raise."""
    body = client.get(f"{BASE}?since=2019-09-03").get_json()

    assert body["total"] > 0


def test_since_matches_events_overlapping_the_window(client):
    """An event burning across the window's start is in scope, not excluded."""
    body = client.get(f"{BASE}?since=2019-09-03&limit=2000").get_json()

    assert any(e["firstDetection"] < "2019-09-03" for e in body["events"])


def test_until_bare_date_includes_late_same_day_fire_event(client):
    """The scoped map's inclusive review end must retain late-day events."""
    body = client.get(f"{BASE}?since=2019-09-01&until=2019-09-05&limit=2000&offset=3000").get_json()

    event = next(e for e in body["events"] if e["eventId"] == "FE-20190905-f47a306aba")
    assert event["firstDetection"] == "2019-09-05T18:03:00+00:00"


@pytest.mark.parametrize(
    "query",
    ["bbox=1,2,3", "bbox=a,b,c,d", "bbox=10,0,5,1", "since=yesterday", "state=GUILTY", "limit=0"],
)
def test_malformed_filters_are_the_callers_mistake(client, query):
    """A 400 naming the bad filter, never an empty list that reads as 'no fires'."""
    response = client.get(f"{BASE}?{query}")

    assert response.status_code == 400
    assert response.get_json()["error"]


def test_single_event_adds_the_inspectable_triage_detail(client):
    event_id = client.get(f"{BASE}?limit=1").get_json()["events"][0]["eventId"]

    event = client.get(f"{BASE}/{event_id}").get_json()

    assert event["eventId"] == event_id
    # Every Stage-1 outcome has to be traceable to the rules that produced it,
    # not asserted (spec Section 17).
    assert event["triageDetail"]["rules"]


def test_event_evidence_separates_real_observed_derived_and_missing_context(client):
    event_id = client.get(f"{BASE}?limit=1").get_json()["events"][0]["eventId"]

    response = client.get(f"{BASE}/{event_id}/evidence")

    assert response.status_code == 200
    body = response.get_json()
    assert body["event"]["eventId"] == event_id
    assert body["observedEvidence"]
    assert body["derivedEvidence"]
    assert any(item["source"] == "NASA FIRMS" for item in body["observedEvidence"])
    assert any(item["algorithm_version"] == "stage1-rules-v1" for item in body["derivedEvidence"])
    assert body["evidenceSufficiency"]["value"] == "PARTIAL"
    assert body["investigationPriority"] in {"MEDIUM", "HIGH"}
    assert isinstance(body["reviewRouting"]["escalationReasonCodes"], list)
    assert {item["kind"] for item in body["availability"]} == {"peat", "weather", "imagery"}
    # Availability tracks whatever derivedEvidence actually contains for that
    # audit artifact -- enrich_audit_events.py may have added real weather/
    # imagery evidence for some events, so this must not assume "always
    # unavailable" as a fixed fact about the artifact.
    present_categories = {item["category"] for item in body["derivedEvidence"]}
    for item in body["availability"]:
        expected = "available" if item["kind"] in present_categories else "unavailable"
        assert item["status"] == expected, f"{item['kind']}: expected {expected}, got {item['status']}"


def test_offline_peat_enrichment_is_returned_to_the_drawer(client):
    event_id = client.get(f"{BASE}?limit=1").get_json()["events"][0]["eventId"]

    body = client.get(f"{BASE}/{event_id}/evidence").get_json()

    peat = [item for item in body["derivedEvidence"] if item["category"] == "peat"]
    assert peat
    assert body["availability"][0]["kind"] == "peat"
    assert body["availability"][0]["status"] == "available"


def test_unknown_event_evidence_is_explicitly_not_found(client):
    response = client.get(f"{BASE}/FE-does-not-exist/evidence")

    assert response.status_code == 404


def test_graph_handoff_returns_selected_events_and_context_neighbours(client):
    selected = client.get(f"{BASE}?limit=1").get_json()["events"][0]["eventId"]
    response = client.get(f"/api/audits/{AUDIT}/graph?event_ids={selected}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["selectedEventIds"] == [selected]
    assert any(node["mapRole"] == "SELECTED" for node in body["nodes"])
    assert body["layers"]["graph"] is True
    assert all(edge["modelVersion"] == "fire-event-graph-v1" for edge in body["edges"])
    assert all(edge["supportingEvidenceIds"] for edge in body["edges"])
    assert all(edge["evidence"][0]["algorithm_version"] == "fire-event-graph-v1" for edge in body["edges"])


def test_graph_prefers_the_precomputed_real_fire_event_graph_edge(client):
    """`data_pipeline.enrich_fire_spread_audit_events` has real wind-oriented
    envelopes for this demo pair -- the API must serve that classification,
    not the synthesized distance-only fallback (which always says
    RELATED_POSSIBLE and never carries an envelope)."""

    # Only one side selected -- the other must surface as a discovered
    # EXTERNAL_CONTEXT neighbour (edges never connect two selected events
    # directly; see `investigation_map`'s neighbour-search loop).
    response = client.get(f"/api/audits/{AUDIT}/graph?event_ids=FE-20190904-0fb85076c0")

    assert response.status_code == 200
    body = response.get_json()
    assert body["layers"]["surfaceEnvelope"] is True
    assert body["layers"]["weatherWind"] is True
    edge = next(
        e for e in body["edges"]
        if {e["sourceEventId"], e["targetEventId"]} == {"FE-20190901-f0d0bb0675", "FE-20190904-0fb85076c0"}
    )
    assert edge["state"] == "PROPAGATION_COMPATIBLE"
    assert edge["envelope"] is not None
    assert edge["envelope"]["ownerEventId"] == edge["sourceEventId"]
    assert len(edge["envelope"]["polygon"]) > 3
    assert edge["envelope"]["polygon"][0] == edge["envelope"]["polygon"][-1]


def test_multi_select_keeps_only_deterministic_edges_between_selected_events(client):
    selected = ["FE-20190901-f0d0bb0675", "FE-20190904-0fb85076c0"]
    response = client.get(f"/api/audits/{AUDIT}/graph?event_ids={','.join(selected)}")

    assert response.status_code == 200
    body = response.get_json()
    edge = next(
        e for e in body["edges"]
        if {e["sourceEventId"], e["targetEventId"]} == set(selected)
    )
    assert edge["state"] == "PROPAGATION_COMPATIBLE"
    assert edge["envelope"]["ownerEventId"] == "FE-20190901-f0d0bb0675"

    unrelated = [
        event["eventId"]
        for event in client.get(f"{BASE}?limit=3").get_json()["events"]
    ]
    unrelated_response = client.get(
        f"/api/audits/{AUDIT}/graph?event_ids={','.join(unrelated)}"
    )
    assert unrelated_response.status_code == 200
    selected_edges = [
        e for e in unrelated_response.get_json()["edges"]
        if {e["sourceEventId"], e["targetEventId"]}.issubset(unrelated)
    ]
    assert all(e["state"] != "RELATED_POSSIBLE" for e in selected_edges)
    assert all(e["evidence"][0]["type"] == "candidate_edge_fire_event_graph" for e in selected_edges)


def test_unknown_event_in_a_known_audit_is_404(client):
    response = client.get(f"{BASE}/FE-does-not-exist")

    assert response.status_code == 404


def test_unknown_audit_says_no_such_audit(client):
    body = client.get("/api/audits/nope/events").get_json()

    assert body["status"] == "NO_SUCH_AUDIT"


def test_created_audit_reports_history_pending_not_missing(client):
    """A session exists; its history does not. Telling the caller it does not
    exist at all would be wrong, and would look like the create had failed."""
    created = client.post(
        "/api/audits", json={"reviewStart": "2019-09-01", "reviewEnd": "2019-09-05"}
    ).get_json()

    response = client.get(f"/api/audits/{created['audit_id']}/events")

    assert response.status_code == 404
    assert response.get_json()["status"] == "PENDING_RECONSTRUCTION"


def test_auditor_can_add_update_remove_and_report_selected_event(client):
    event_id = client.get(f"{BASE}?limit=1").get_json()["events"][0]["eventId"]
    added = client.post(f"/api/audits/{AUDIT}/events/{event_id}/add-to-pack", json={"note": "Check field record", "disposition": "VERIFY"})
    assert added.status_code == 200
    assert added.get_json()["disposition"] == "VERIFY"

    progression = client.get(f"{BASE}?limit=1").get_json()["progression"]
    assert progression["selected"] == 1
    assert progression["selectedEventIds"] == [event_id]

    report = client.get(f"/api/audits/{AUDIT}/report")
    body = report.get_json()
    assert body["counts"]["identified"] == body["counts"]["screened"]
    assert body["counts"]["selected"] == 1
    assert body["counts"]["verify"] == 1
    assert body["selectedFireEvents"][0]["event"]["eventId"] == event_id
    assert body["selectedFireEvents"][0]["evidence"]["observedEvidence"]
    assert body["deterministicEvidence"][0]["derived"]
    assert body["disclaimer"].startswith("This report is an investigative-support product.")

    updated = client.post(f"/api/audits/{AUDIT}/events/{event_id}/add-to-pack", json={"note": "Updated"})
    assert updated.get_json()["note"] == "Updated"
    assert client.delete(f"/api/audits/{AUDIT}/events/{event_id}/add-to-pack").status_code == 200
    assert client.get(f"/api/audits/{AUDIT}/report").get_json()["counts"]["selected"] == 0


def test_new_audit_report_contains_the_events_selected_for_that_audit(client):
    """The cached regional artifact is reused, but the engagement package is
    keyed by the new audit ID -- it must never reuse a demo/example selection."""
    created = client.post(
        "/api/audits", json={"reviewStart": "2019-09-01", "reviewEnd": "2019-09-05"}
    ).get_json()
    audit_id = created["audit_id"]
    scope = {
        "type": "Polygon",
        "coordinates": [[[116.0, -4.05], [116.5, -4.05], [116.5, -3.55], [116.0, -3.55], [116.0, -4.05]]],
    }
    assert client.post(f"/api/audits/{audit_id}/scope/upload", json=scope).status_code == 200
    assert client.post(f"/api/audits/{audit_id}/history/build").status_code == 202
    event_ids = [event["eventId"] for event in client.get(f"/api/audits/{audit_id}/events?limit=4").get_json()["events"]]
    assert len(event_ids) == 4 and len(set(event_ids)) == 4
    for event_id in event_ids:
        assert client.post(f"/api/audits/{audit_id}/events/{event_id}/add-to-pack", json={}).status_code == 200

    report = client.get(f"/api/audits/{audit_id}/report").get_json()
    assert report["auditId"] == audit_id
    assert {item["event"]["eventId"] for item in report["selectedFireEvents"]} == set(event_ids)
    assert report["maps"]["selectedEventIds"] == event_ids
    assert {item["eventId"] for item in report["chronology"]} == set(event_ids)
    # The report's explicit generation controls use this list. Every selected
    # cached FireEvent must therefore reach the report-generation input, not
    # merely appear in a transient scoped-map selection.
    assert report["analysisNotRunEventIds"] == event_ids


# --- The review period as a filter (#161) ------------------------------------
#
# The window an auditor chooses is printed on the exported engagement report as
# the audit's scope, so the register has to serve the period it names. These
# cover the filtering itself and the derived counts beside it, which are the
# half that silently keeps quoting dataset-wide totals if nobody looks.

SCOPE_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[116.0, -4.05], [116.5, -4.05], [116.5, -3.55], [116.0, -3.55], [116.0, -4.05]]],
}


def ready_audit(client, review_start: str, review_end: str) -> str:
    """An audit whose history handoff has completed, for a given review period."""
    created = client.post(
        "/api/audits", json={"reviewStart": review_start, "reviewEnd": review_end}
    ).get_json()
    audit_id = created["audit_id"]
    assert client.post(f"/api/audits/{audit_id}/scope/upload", json=SCOPE_POLYGON).status_code == 200
    assert client.post(f"/api/audits/{audit_id}/history/build").status_code == 202
    return audit_id


def register(client, audit_id: str, query: str = "limit=2000"):
    return client.get(f"/api/audits/{audit_id}/events?{query}").get_json()


def test_full_review_period_reproduces_the_artifact_totals(client):
    """The recomputation must be a no-op at full coverage.

    If it is not, every number the demo shows moved -- so this pins the
    unfiltered path rather than only the filtered one.
    """
    body = register(client, ready_audit(client, "2019-09-01", "2019-09-05"))
    scope = body["scope"]

    assert body["total"] == 3610
    assert scope["eventCount"] == 3610
    assert scope["qualifiedObservations"] == 20471
    assert scope["rawObservations"] == 21519
    assert scope["reviewQueueCount"] == 396
    assert scope["compression"] == 1.0


def test_sub_window_narrows_the_register_and_its_counts(client):
    body = register(client, ready_audit(client, "2019-09-02", "2019-09-03"))
    scope = body["scope"]

    assert body["total"] == 1463
    assert len(body["events"]) == 1463
    # The count on the scope is what the console displays; it must follow the
    # events actually served, not the artifact it was sliced from.
    assert scope["eventCount"] == body["total"]
    assert scope["reviewQueueCount"] < 396
    assert scope["qualifiedObservations"] == 15455
    assert scope["qualifiedObservations"] < 20471

    # Every event served overlaps the chosen period.
    for event in body["events"]:
        assert event["firstDetection"] <= "2019-09-03T23:59:59"
        assert event["lastDetection"] >= "2019-09-02T00:00:00"


def test_sub_window_does_not_claim_a_raw_detection_count_it_cannot_know(client):
    """`rawObservations` counts detections dropped before clustering.

    They are not in the artifact, so how many fell inside a narrower window is
    unknowable -- and repeating the full-window 21,519 beside a filtered event
    count is the mislabel this issue exists to remove.
    """
    body = register(client, ready_audit(client, "2019-09-02", "2019-09-03"))

    assert body["scope"]["rawObservations"] is None
    assert body["progression"]["rawObservations"] is None


def test_narrowing_the_period_does_not_manufacture_a_compression_figure(client):
    """Stage-1 does not compress this dataset and must not appear to.

    `compression` divides by the Stage-1 queue (events that are not
    LIKELY_NON_FIRE), never by the calibrated `reviewQueueCount` sitting beside
    it -- that would report ~9x where nothing was reduced. See #187.
    """
    for start, end in [("2019-09-01", "2019-09-05"), ("2019-09-01", "2019-09-01"), ("2019-09-03", "2019-09-04")]:
        scope = register(client, ready_audit(client, start, end))["scope"]
        assert scope["compression"] == 1.0, f"{start}..{end}"

    # And the observations-to-events ratio uses the window's own observation
    # count, not the artifact's 20,471 over a filtered event count.
    progression = register(client, ready_audit(client, "2019-09-02", "2019-09-03"))["progression"]
    assert progression["qualifiedObservations"] == 15455
    assert progression["fireEvents"] == 1463
    assert progression["observationsToEventsCompression"] == round(15455 / 1463, 2)


def test_closing_date_includes_the_whole_day(client):
    """The form collects whole dates, so the last day is inclusive.

    Comparing against the closing date's midnight would drop every event first
    detected during it -- most of them, since VIIRS crosses this region in
    daylight.
    """
    body = register(client, ready_audit(client, "2019-09-05", "2019-09-05"))

    assert body["total"] == 1307
    started_after_midnight = [
        event for event in body["events"] if event["firstDetection"] > "2019-09-05T00:00:00+00:00"
    ]
    assert started_after_midnight, "events first detected during the closing day were dropped"


def test_period_outside_the_dataset_is_an_empty_register_not_a_missing_one(client):
    """"We looked and found none" is a measurement; a 404 is not.

    The scope form bounds the pickers to the artifact's coverage (#95), so this
    is not reachable through the console -- but the API must still answer it as
    an empty result rather than claiming the audit has no history.
    """
    audit_id = ready_audit(client, "2020-01-01", "2020-01-31")
    response = client.get(f"/api/audits/{audit_id}/events")

    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == 0
    assert body["events"] == []
    assert body["scope"]["eventCount"] == 0
    assert body["scope"]["qualifiedObservations"] == 0
    # No events means no ratio -- not a ratio of zero.
    assert body["scope"]["compression"] is None
    assert body["progression"]["observationsToEventsCompression"] is None


def test_the_demo_artifact_scope_itself_is_never_filtered(client):
    """`demo-2019-haze` is addressed directly, without a session or a window."""
    body = client.get(f"{BASE}?limit=1").get_json()

    assert body["total"] == 3610
    assert body["scope"]["rawObservations"] == 21519
