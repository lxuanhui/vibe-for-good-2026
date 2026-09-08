import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    return app.test_client()


def _create_audit(client, boundary=None):
    boundary = boundary or {
        "type": "Polygon",
        "coordinates": [[[102, -5], [118, -5], [118, 2], [102, 2], [102, -5]]],
    }
    response = client.post(
        "/api/audits",
        json={
            "reviewStart": "2019-09-01",
            "reviewEnd": "2019-09-10",
            "boundary": boundary,
            "contextBufferKm": 25,
        },
    )
    assert response.status_code == 201
    return response.get_json()["auditId"]


def test_build_history_and_list_pipeline_events(client):
    audit_id = _create_audit(client)

    build = client.post(f"/api/audits/{audit_id}/history/build")
    assert build.status_code == 200
    payload = build.get_json()
    assert payload["compression"]["rawObservations"] >= payload["compression"]["qualifiedObservations"]
    assert payload["compression"]["qualifiedObservations"] >= payload["compression"]["fireEvents"]
    assert payload["events"]
    event = payload["events"][0]
    assert {
        "id",
        "scopeId",
        "firstDetected",
        "lastDetected",
        "observationCount",
        "scopeRelation",
        "evidenceIds",
        "constituentObservationIds",
        "graphReferences",
    } <= event.keys()

    listed = client.get(f"/api/audits/{audit_id}/events")
    assert listed.status_code == 200
    assert listed.get_json()["events"] == payload["events"]


def test_history_errors_are_explicit(client):
    response = client.post("/api/audits/does-not-exist/history/build")
    assert response.status_code == 404

    audit_id = _create_audit(client)
    response = client.get(f"/api/audits/{audit_id}/events")
    assert response.status_code == 409
    assert "Build Fire History" in response.get_json()["error"]

    invalid = client.post(
        "/api/audits",
        json={"reviewStart": "2019-09-10", "reviewEnd": "2019-09-01"},
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]


def test_scope_relations_and_serialized_evidence_are_stable(client):
    boundary = {
        "type": "Polygon",
        "coordinates": [[[104.03, -1.31], [104.05, -1.31], [104.05, -1.29], [104.03, -1.29], [104.03, -1.31]]],
    }
    response = client.post(
        "/api/audits",
        json={
            "reviewStart": "2019-09-01",
            "reviewEnd": "2019-09-10",
            "boundary": boundary,
            "contextBufferKm": 100,
        },
    )
    audit_id = response.get_json()["auditId"]

    built = client.post(f"/api/audits/{audit_id}/history/build").get_json()
    assert {event["scopeRelation"] for event in built["events"]} == {
        "BOUNDARY_INTERSECTING",
        "EXTERNAL_CONTEXT",
    }
    for event in built["events"]:
        assert event["evidenceIds"] == sorted(set(event["evidenceIds"]))
        assert len(event["constituentObservationIds"]) == len(
            set(event["constituentObservationIds"])
        )
        assert all(
            reference["reference"].startswith("GRAPH:")
            for reference in event["graphReferences"]
        )
        assert event["source"] == "NASA FIRMS"


def test_audit_validation_rejects_malformed_boundary(client):
    response = client.post(
        "/api/audits",
        json={
            "reviewStart": "2019-09-01",
            "reviewEnd": "2019-09-10",
            "boundary": {"type": "Point", "coordinates": [104, -1]},
        },
    )
    assert response.status_code == 400
    assert "Polygon" in response.get_json()["error"]
