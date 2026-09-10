import io
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from app import audit_store, audits, create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    return app.test_client()


def create_review(client):
    response = client.post(
        "/api/audits",
        json={"review_start": "2019-01-01", "review_end": "2019-12-31"},
    )
    assert response.status_code == 201
    return response.get_json()


DEMO_SCOPE = {
    "type": "Feature",
    "properties": {"label": "private demo boundary"},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[104.0, -4.0], [105.0, -4.0], [105.0, -3.0], [104.0, -3.0], [104.0, -4.0]]],
    },
}


def test_creates_an_anonymous_review_with_default_buffer(client):
    review = create_review(client)

    assert review["audit_id"].startswith("audit_")
    assert review["scope_id"].startswith("scope_")
    assert review["context_buffer_km"] == 25
    assert review["status"] == "AWAITING_SCOPE"
    assert "company" not in json.dumps(review).lower()


def test_upload_returns_scope_geometry_bbox_centroid_and_buffer(client):
    review = create_review(client)
    response = client.post(
        f"/api/audits/{review['audit_id']}/scope/upload",
        data={"file": (io.BytesIO(json.dumps(DEMO_SCOPE).encode()), "unit.geojson")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    scope = response.get_json()
    assert scope["audit_id"] == review["audit_id"]
    assert scope["bbox"] == {"minLon": 104.0, "minLat": -4.0, "maxLon": 105.0, "maxLat": -3.0}
    assert scope["centroid"] == [104.5, -3.5]
    assert scope["buffer_geometry"]["type"] == "Polygon"
    assert scope["status"] == "SCOPE_READY"


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        ({"type": "Point", "coordinates": [104, -3]}, "Polygon or MultiPolygon"),
        (
            {
                "type": "Polygon",
                "coordinates": [[[104, 104], [105, 104], [105, 105], [104, 104]]],
            },
            "latitude must be between",
        ),
        (
            {
                "type": "Polygon",
                "coordinates": [[[104, -3], [105, -3], [106, -3], [104, -3]]],
            },
            "non-empty area",
        ),
        (
            {
                "type": "Polygon",
                "coordinates": [[[104, -3], [105, -3], [105, -2], [104, -2]]],
            },
            "ring must be closed",
        ),
    ],
)
def test_invalid_scope_is_rejected_with_a_clear_error(client, scope, message):
    review = create_review(client)
    response = client.post(
        f"/api/audits/{review['audit_id']}/scope/upload",
        json=scope,
    )

    assert response.status_code == 400
    assert message in response.get_json()["error"]


def test_history_handoff_requires_a_valid_scope_and_keeps_the_same_id(client):
    review = create_review(client)
    before_scope = client.post(f"/api/audits/{review['audit_id']}/history/build")
    assert before_scope.status_code == 409

    client.post(f"/api/audits/{review['audit_id']}/scope/upload", json=DEMO_SCOPE)
    handoff = client.post(f"/api/audits/{review['audit_id']}/history/build")
    assert handoff.status_code == 202
    assert handoff.get_json()["audit_id"] == review["audit_id"]
    assert handoff.get_json()["scope_id"] == review["scope_id"]
    assert handoff.get_json()["status"] == "HISTORY_BUILD_READY"
    assert handoff.get_json()["duration_ms"] >= 0
    assert handoff.get_json()["dataset_mode"] == "cached_real_historical_dataset"

    register = client.get(f"/api/audits/{review['audit_id']}/events?limit=1")
    assert register.status_code == 200
    event_id = register.get_json()["events"][0]["eventId"]
    evidence = client.get(f"/api/audits/{review['audit_id']}/events/{event_id}/evidence")
    assert evidence.status_code == 200
    assert evidence.get_json()["event"]["triageDetail"]["rules"]


def test_event_investigation_is_one_ready_bundle_after_history_build(client):
    review = create_review(client)
    client.post(f"/api/audits/{review['audit_id']}/scope/upload", json=DEMO_SCOPE)
    client.post(f"/api/audits/{review['audit_id']}/history/build")
    event_id = client.get(f"/api/audits/{review['audit_id']}/events?limit=1").get_json()["events"][0]["eventId"]

    bundle = client.get(f"/api/audits/{review['audit_id']}/events/{event_id}/investigation")

    assert bundle.status_code == 200
    assert bundle.get_json()["event"]["event"]["eventId"] == event_id
    assert bundle.get_json()["graph"]["selectedEventIds"] == [event_id]


def test_evidence_reports_processing_before_history_is_built(client):
    review = create_review(client)
    response = client.get(f"/api/audits/{review['audit_id']}/events/FE-any/evidence")

    assert response.status_code == 202
    assert response.get_json()["status"] == "processing"


def test_rebuilding_history_does_not_discard_a_concurrent_pack_selection(client, monkeypatch):
    """Scope setup is a session write like any other (#146).

    `upload_scope` and `build_history` used to write the whole session blob
    back unconditionally. That was safe only by ordering -- they normally run
    before an auditor selects anything -- but nothing enforced the ordering,
    and an auditor who rebuilt history while an assessment was running lost
    whichever write landed first. This drives the two through the real routes
    with their reads forced to overlap.
    """
    review = create_review(client)
    audit_id = review["audit_id"]
    client.post(
        f"/api/audits/{audit_id}/scope/upload",
        data={"file": (io.BytesIO(json.dumps(DEMO_SCOPE).encode()), "scope.geojson")},
        content_type="multipart/form-data",
    )

    barrier = Barrier(2)
    remaining = {"count": 2}
    lock = Lock()
    original = audit_store._read_item

    def read(key: str):
        item = original(key)
        with lock:
            wait = remaining["count"] > 0
            if wait:
                remaining["count"] -= 1
        if wait:
            barrier.wait(timeout=5)
        return item

    monkeypatch.setattr(audit_store, "_read_item", read)
    entry = {
        "eventId": "FE-20190901-f0d0bb0675",
        "note": "",
        "disposition": "",
        "addedAt": "2019-09-01T00:00:00Z",
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(audits.build_history, audit_id),
            executor.submit(audit_store.add_pack_entry, audit_id, entry),
        ]
        for future in futures:
            future.result()

    session = audit_store.get(audit_id)
    assert session["status"] == "HISTORY_BUILD_READY"
    assert "FE-20190901-f0d0bb0675" in session["_pack"]
