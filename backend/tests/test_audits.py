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


# --- scope without a file (#87) -------------------------------------------


def set_point(client, audit_id, **payload):
    return client.post(f"/api/audits/{audit_id}/scope/point", json=payload)


def test_point_and_radius_scope_uses_the_same_session_contract_as_an_upload(client):
    review = create_review(client)
    response = set_point(client, review["audit_id"], latitude=-3.8, longitude=116.25, radius_km=20)

    assert response.status_code == 200
    scope = response.get_json()
    assert scope["audit_id"] == review["audit_id"]
    assert scope["scope_id"] == review["scope_id"]
    assert scope["status"] == "SCOPE_READY"
    assert scope["scope_source"] == "point_radius"
    assert scope["scope_point"] == {"latitude": -3.8, "longitude": 116.25, "radius_km": 20.0}
    assert scope["geometry"]["type"] == "Polygon"
    ring = scope["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]
    assert len(ring) == audits.CIRCLE_VERTICES + 1
    # The circle is centred where asked and 20 km across in each direction.
    assert scope["centroid"] == pytest.approx([116.25, -3.8], abs=1e-6)
    assert scope["bbox"]["maxLat"] - scope["bbox"]["minLat"] == pytest.approx(40 / 111.32, abs=1e-3)
    # The context buffer is applied exactly as for an upload: 25 km beyond.
    assert scope["buffer_bbox"]["maxLat"] - scope["bbox"]["maxLat"] == pytest.approx(25 / 111.32, abs=1e-3)
    assert scope["buffer_geometry"]["type"] == "Polygon"
    assert "company" not in json.dumps(scope).lower()
    assert "—" not in json.dumps(scope)


def test_point_scope_accepts_camel_case_and_string_numbers(client):
    review = create_review(client)
    response = set_point(client, review["audit_id"], lat="-3.8", lon="116.25", radiusKm="5")
    assert response.status_code == 200
    assert response.get_json()["scope_point"]["radius_km"] == 5.0


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "latitude is required"),
        ({"latitude": -3.8, "longitude": 116.25}, "radius_km is required"),
        ({"latitude": 91, "longitude": 116.25, "radius_km": 5}, "latitude must be between"),
        ({"latitude": -3.8, "longitude": 181, "radius_km": 5}, "longitude must be between"),
        ({"latitude": -3.8, "longitude": 116.25, "radius_km": 0}, "radius_km must be between"),
        ({"latitude": -3.8, "longitude": 116.25, "radius_km": -5}, "radius_km must be between"),
        ({"latitude": -3.8, "longitude": 116.25, "radius_km": 1e9}, "radius_km must be between"),
        ({"latitude": "north", "longitude": 116.25, "radius_km": 5}, "latitude must be a number"),
        ({"latitude": True, "longitude": 116.25, "radius_km": 5}, "latitude must be a number"),
        ({"latitude": -3.8, "longitude": 116.25, "radius_km": "NaN"}, "radius_km must be a finite number"),
        ({"latitude": [1], "longitude": 116.25, "radius_km": 5}, "latitude must be a number"),
    ],
)
def test_invalid_point_scopes_are_rejected_before_anything_is_stored(client, payload, message):
    review = create_review(client)
    response = set_point(client, review["audit_id"], **payload)
    assert response.status_code == 400
    assert message in response.get_json()["error"]
    assert audits.get_audit(review["audit_id"])["status"] == "AWAITING_SCOPE"


def test_point_scope_body_must_be_an_object(client):
    review = create_review(client)
    response = client.post(f"/api/audits/{review['audit_id']}/scope/point", data="[]", content_type="application/json")
    assert response.status_code == 400


def test_point_and_demo_scopes_404_for_an_unknown_audit(client):
    assert set_point(client, "audit_missing", latitude=0, longitude=0, radius_km=1).status_code == 404
    assert client.post("/api/audits/audit_missing/scope/demo").status_code == 404


def test_circle_polygon_wraps_the_antimeridian_and_stays_valid():
    ring = audits.circle_polygon(0.0, 179.99, 50)["coordinates"][0]
    assert all(-180 <= lon <= 180 for lon, _lat in ring)
    assert any(lon < 0 for lon, _lat in ring) and any(lon > 0 for lon, _lat in ring)


def _distance_km(event, latitude, longitude):
    d_lat = (event["centroid"]["lat"] - latitude) * 111.32
    d_lon = (event["centroid"]["lon"] - longitude) * 111.32 * 0.9978
    return (d_lat**2 + d_lon**2) ** 0.5


def test_point_scope_reaches_history_build_and_classifies_events_by_the_circle(client):
    review = create_review(client)
    # 30 km around the middle of the block the artifact's enriched events sit in.
    set_point(client, review["audit_id"], latitude=-3.8, longitude=116.25, radius_km=30)
    handoff = client.post(f"/api/audits/{review['audit_id']}/history/build")
    assert handoff.status_code == 202

    register = client.get(f"/api/audits/{review['audit_id']}/events?limit=2000").get_json()
    assert register["progression"]["scopeBoundaryAvailable"] is True
    assert register["progression"]["inScopeAndBuffer"] > 0

    # The relation is served per event on the evidence bundle and follows the
    # circle, not its bounding box: a centroid well inside is INSIDE_SCOPE, one
    # hundreds of km away is EXTERNAL_CONTEXT.
    by_distance = sorted(register["events"], key=lambda event: _distance_km(event, -3.8, 116.25))
    nearest, farthest = by_distance[0], by_distance[-1]
    assert _distance_km(nearest, -3.8, 116.25) < 30
    assert _distance_km(farthest, -3.8, 116.25) > 100
    evidence = client.get(f"/api/audits/{review['audit_id']}/events/{nearest['eventId']}/evidence").get_json()
    assert evidence["scopeRelation"] == "INSIDE_SCOPE"
    evidence = client.get(f"/api/audits/{review['audit_id']}/events/{farthest['eventId']}/evidence").get_json()
    assert evidence["scopeRelation"] == "EXTERNAL_CONTEXT"


def test_demo_scope_is_labelled_as_a_demo_and_never_as_an_upload(client):
    review = create_review(client)
    response = client.post(f"/api/audits/{review['audit_id']}/scope/demo")

    assert response.status_code == 200
    scope = response.get_json()
    assert scope["status"] == "SCOPE_READY"
    assert scope["scope_source"] == "demo"
    assert scope["scope_label"] == audits.DEMO_SCOPE_LABEL
    assert "demo" in scope["scope_label"].lower()
    assert "not a company boundary" in scope["scope_label"].lower()
    assert scope["geometry"] == audits.DEMO_SCOPE_GEOMETRY
    assert "—" not in json.dumps(scope)

    handoff = client.post(f"/api/audits/{review['audit_id']}/history/build")
    assert handoff.status_code == 202
    register = client.get(f"/api/audits/{review['audit_id']}/events?limit=2000").get_json()
    # The 16 enriched demo events are the ones this area was chosen around.
    assert register["progression"]["inScopeAndBuffer"] == 16


def test_an_upload_is_recorded_as_an_upload(client):
    review = create_review(client)
    scope = client.post(f"/api/audits/{review['audit_id']}/scope/upload", json=DEMO_SCOPE).get_json()
    assert scope["scope_source"] == "upload"
    assert scope["scope_label"] is None
    assert audits.get_audit(review["audit_id"])["scope_source"] == "upload"


def test_history_build_error_names_every_scope_path(client):
    review = create_review(client)
    response = client.post(f"/api/audits/{review['audit_id']}/history/build")
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert "GeoJSON" in error and "radius" in error and "demo" in error
    assert "—" not in error
