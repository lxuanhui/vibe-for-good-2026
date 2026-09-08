import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    return app.test_client()


def test_lists_every_event_when_unfiltered(client):
    response = client.get("/api/events")
    assert response.status_code == 200
    events = response.get_json()["events"]
    assert {e["id"] for e in events} == {"IND-01120", "IND-01894", "IND-02671"}


def test_event_shape_matches_the_frontend_contract(client):
    event = client.get("/api/events").get_json()["events"][0]
    # camelCase, because these objects are consumed as FireEvent in
    # frontend/src/api/types.ts without a translation layer.
    assert {"id", "lat", "lon", "firstDetected", "status", "detections"} <= event.keys()


def test_bbox_selects_by_position(client):
    # Ogan Komering Ilir only: lon 104.702, lat -3.021.
    events = client.get("/api/events?bbox=104,-4,105,-2").get_json()["events"]
    assert [e["id"] for e in events] == ["IND-01894"]


def test_bbox_excludes_everything_outside_it(client):
    events = client.get("/api/events?bbox=0,0,1,1").get_json()["events"]
    assert events == []


def test_since_is_inclusive_of_the_boundary(client):
    # Matches the mock client's `firstDetected >= since`, so swapping the
    # transport does not quietly change which events appear.
    events = client.get("/api/events?since=2026-09-02T14:18:00Z").get_json()["events"]
    assert "IND-01894" in {e["id"] for e in events}


def test_status_filters_to_one_kind(client):
    events = client.get("/api/events?status=LIKELY_NON_FIRE").get_json()["events"]
    assert [e["id"] for e in events] == ["IND-01120"]


@pytest.mark.parametrize(
    "query",
    ["bbox=1,2", "bbox=a,b,c,d", "bbox=5,5,1,1", "since=yesterday", "status=MADE_UP"],
)
def test_malformed_filters_are_rejected_with_a_reason(client, query):
    response = client.get(f"/api/events?{query}")
    assert response.status_code == 400
    assert response.get_json()["error"]


def test_single_event_is_returned_unwrapped(client):
    response = client.get("/api/events/IND-01894")
    assert response.status_code == 200
    assert response.get_json()["location"] == "Ogan Komering Ilir, South Sumatra"


def test_unknown_event_is_404_not_an_empty_object(client):
    response = client.get("/api/events/IND-00000")
    assert response.status_code == 404
    assert response.get_json()["error"]
