"""The landing map's live regional FIRMS layer, served through the API."""

from __future__ import annotations

import pytest

from app import create_app, firms_live

# Two real-shaped VIIRS rows and one truncated line. FIRMS reports acq_time as
# an unpadded HHMM, which is the field most likely to be mis-parsed.
CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-2.1234,113.5678,331.2,0.4,0.36,2026-09-10,618,N,VIIRS,n,2.0NRT,295.1,12.7,D\n"
    "0.5,101.25,367.8,0.5,0.4,2026-09-10,1442,N,VIIRS,h,2.0NRT,300.0,48.2,D\n"
    "not,a,row\n"
)


@pytest.fixture
def client(monkeypatch):
    firms_live._cache.clear()
    monkeypatch.setenv("NASA_FIRMS_MAP_KEY", "test-map-key")
    yield create_app({"TESTING": True}).test_client()
    firms_live._cache.clear()


def test_live_layer_is_served_as_geojson_and_the_key_never_leaves_the_server(client, monkeypatch):
    requested: list[str] = []

    def _fetch(map_key: str) -> str:
        requested.append(map_key)
        return CSV

    monkeypatch.setattr(firms_live, "_fetch_csv", _fetch)
    response = client.get("/api/firms/live")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["sensor"] == "VIIRS_SNPP_NRT"
    assert payload["windowHours"] == 24

    features = payload["detections"]["features"]
    assert [feature["geometry"]["coordinates"] for feature in features] == [
        [113.5678, -2.1234], [101.25, 0.5],
    ]
    assert features[0]["properties"] == {
        "confidence": "n", "frp": 12.7, "acquiredAt": "2026-09-10T06:18:00Z",
    }
    # The malformed third line is dropped rather than failing the whole layer.
    assert len(features) == 2

    # The key is used server-side and appears nowhere in what the browser gets.
    assert requested == ["test-map-key"]
    assert "test-map-key" not in response.get_data(as_text=True)


def test_a_warm_cache_serves_repeat_visitors_without_a_second_firms_transaction(client, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(firms_live, "_fetch_csv", lambda map_key: calls.append(map_key) or CSV)

    assert client.get("/api/firms/live").status_code == 200
    assert client.get("/api/firms/live").status_code == 200
    assert len(calls) == 1

    # Past the window the layer refreshes rather than going stale silently.
    firms_live._cache["at"] -= firms_live.CACHE_SECONDS + 1
    assert client.get("/api/firms/live").status_code == 200
    assert len(calls) == 2


def test_an_unconfigured_key_is_reported_rather_than_drawn_as_an_empty_region(monkeypatch):
    firms_live._cache.clear()
    # Set empty rather than deleted: create_app() calls load_dotenv(), which
    # will fill an absent variable from a developer's .env but never overrides
    # one that is already set.
    monkeypatch.setenv("NASA_FIRMS_MAP_KEY", "")
    client = create_app({"TESTING": True}).test_client()

    response = client.get("/api/firms/live")
    # An empty FeatureCollection would render as "no fires are burning", which
    # is an observation nothing measured.
    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"


def test_an_upstream_failure_does_not_cache_and_does_not_raise(client, monkeypatch):
    def _down(map_key: str) -> str:
        raise firms_live.FirmsUnavailable("NASA FIRMS did not answer: timed out")

    monkeypatch.setattr(firms_live, "_fetch_csv", _down)
    assert client.get("/api/firms/live").status_code == 503
    assert firms_live._cache == {}
