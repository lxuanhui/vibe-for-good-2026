import io
import json

import pytest

from app import create_app


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
    assert scope["bbox"] == [104.0, -4.0, 105.0, -3.0]
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
    assert handoff.get_json() == {
        "audit_id": review["audit_id"],
        "scope_id": review["scope_id"],
        "status": "HISTORY_BUILD_READY",
    }
