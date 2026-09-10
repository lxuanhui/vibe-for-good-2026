"""The landing map's live regional FIRMS layer, served through the API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app import create_app, firms_live

HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight"
)


def _row(*, longitude: float, latitude: float, hours_ago: float, confidence: str, frp: float):
    """One CSV row plus the `acquiredAt` the API should report for it.

    Built relative to now rather than pinned to a date. The route filters to a
    rolling 24-hour window, so a fixture with a hard-coded `acq_date` would
    pass on the day it was written and then quietly start dropping its own
    rows the day after -- the same class of time-dependent emptiness this
    module exists to catch.

    FIRMS reports acq_time as an *unpadded* HHMM ('618' is 06:18), which is the
    field most likely to be mis-parsed, so the fixture keeps that shape.
    """
    observed = datetime.now(UTC) - timedelta(hours=hours_ago)
    acq_time = str(int(observed.strftime("%H%M")))
    row = (
        f"{latitude},{longitude},331.2,0.4,0.36,{observed:%Y-%m-%d},{acq_time},"
        f"N,VIIRS,{confidence},2.0NRT,295.1,{frp},D"
    )
    return row, f"{observed:%Y-%m-%dT%H:%M}:00Z"


FRESH, FRESH_ACQUIRED_AT = _row(
    longitude=113.5678, latitude=-2.1234, hours_ago=6, confidence="n", frp=12.7
)
RECENT, _ = _row(longitude=101.25, latitude=0.5, hours_ago=2, confidence="h", frp=48.2)
# Inside the two days fetched upstream, outside the 24 hours the layer claims.
STALE, _ = _row(longitude=102.0, latitude=1.5, hours_ago=30, confidence="h", frp=9.0)

CSV = f"{HEADER}\n{FRESH}\n{RECENT}\nnot,a,row\n"


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
        "confidence": "n", "frp": 12.7, "acquiredAt": FRESH_ACQUIRED_AT,
    }
    # The malformed third line is dropped rather than failing the whole layer.
    assert len(features) == 2

    # The key is used server-side and appears nowhere in what the browser gets.
    assert requested == ["test-map-key"]
    assert "test-map-key" not in response.get_data(as_text=True)


def test_a_detection_older_than_the_claimed_window_is_not_served_as_current(client, monkeypatch):
    # Two days are fetched upstream because the area API's day range is
    # anchored on the UTC calendar day, so asking for one can mean a window of
    # minutes. The extra day is a means of covering 24 hours, not part of what
    # the layer reports -- `windowHours: 24` has to stay true of the features.
    monkeypatch.setattr(firms_live, "_fetch_csv", lambda map_key: f"{HEADER}\n{STALE}\n{FRESH}\n")
    payload = client.get("/api/firms/live").get_json()

    features = payload["detections"]["features"]
    assert [feature["properties"]["acquiredAt"] for feature in features] == [FRESH_ACQUIRED_AT]
    assert payload["windowHours"] == 24


def test_a_row_with_no_usable_timestamp_is_dropped_rather_than_counted_as_current(client, monkeypatch):
    # The client draws an unparseable timestamp at the faintest end of the age
    # ramp, which is a fair way to *render* something already known to be in
    # range. Counting it here would place it inside a 24-hour claim nothing
    # measured.
    fields = FRESH.split(",")
    fields[5] = ""  # acq_date
    undated = ",".join(fields)
    monkeypatch.setattr(firms_live, "_fetch_csv", lambda map_key: f"{HEADER}\n{undated}\n{RECENT}\n")

    features = client.get("/api/firms/live").get_json()["detections"]["features"]
    assert [feature["geometry"]["coordinates"] for feature in features] == [[101.25, 0.5]]


def test_a_plain_text_error_served_as_200_is_reported_rather_than_read_as_no_fires(client, monkeypatch):
    # FIRMS answers an invalid or exhausted key with plain text and HTTP 200.
    # csv.DictReader reads that one line as a header with no rows, so the layer
    # used to render as an empty region -- "no fires are burning", which is an
    # observation nothing made.
    monkeypatch.setattr(
        firms_live, "_fetch_csv", lambda map_key: f"Invalid MAP_KEY. {map_key}"
    )
    response = client.get("/api/firms/live")

    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "unavailable"
    # What upstream actually said, because "invalid key" and "out of
    # transactions" need different responses from us.
    assert "Invalid MAP_KEY" in body["reason"]
    # A FIRMS error page can echo the URL it was given, and this body reaches
    # the browser.
    assert "test-map-key" not in response.get_data(as_text=True)
    assert firms_live._cache == {}


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
