"""The landing map's live regional FIRMS layer, served through the API."""

from __future__ import annotations

import io
import json
import time
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


class FakeSharedCache:
    """The shared level as the route sees it: read() and write(), nothing else.

    Stands in for `_S3SharedCache` so these tests cover the route's handling
    of a shared copy -- hit, miss, stale, broken -- without S3. The object is
    round-tripped through JSON on both sides so a test cannot pass by sharing
    a Python reference the real store could never share.
    """

    def __init__(self, entry=None, *, broken=False):
        self.entry = None if entry is None else json.loads(json.dumps(entry))
        self.broken = broken
        self.reads = 0
        self.writes = 0

    def read(self):
        self.reads += 1
        if self.broken:
            raise RuntimeError("shared store unreachable")
        return None if self.entry is None else json.loads(json.dumps(self.entry))

    def write(self, entry):
        self.writes += 1
        if self.broken:
            raise RuntimeError("shared store unreachable")
        self.entry = json.loads(json.dumps(entry))


@pytest.fixture
def client(monkeypatch):
    firms_live._cache.clear()
    monkeypatch.setenv("NASA_FIRMS_MAP_KEY", "test-map-key")
    # Set empty rather than deleted, for the same load_dotenv reason as the
    # unconfigured-key test below: the shared level must be off unless a test
    # installs a fake one.
    monkeypatch.setenv("LIVE_CACHE_BUCKET", "")
    yield create_app({"TESTING": True}).test_client()
    firms_live._cache.clear()


def _shared(monkeypatch, fake: FakeSharedCache) -> FakeSharedCache:
    monkeypatch.setattr(firms_live, "_shared_cache", lambda: fake)
    return fake


def _upstream_must_not_be_called(map_key: str) -> str:
    raise AssertionError("upstream FIRMS was fetched although a live shared copy existed")


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


# --- The shared level (#186) ----------------------------------------------


def test_a_cold_container_serves_the_shared_copy_without_an_upstream_fetch(client, monkeypatch):
    # A cold Lambda container has an empty process-local cache. Before the
    # shared level, that meant the first visitor after every cold start waited
    # on NASA; now it reads what another container already fetched.
    payload = {"status": "ready", "sensor": "VIIRS_SNPP_NRT", "windowHours": 24,
               "fetchedAt": "2026-09-10T01:51:00+00:00",
               "detections": {"type": "FeatureCollection", "features": []}}
    shared = _shared(monkeypatch, FakeSharedCache({"storedAt": time.time() - 60, "payload": payload}))
    monkeypatch.setattr(firms_live, "_fetch_csv", _upstream_must_not_be_called)

    response = client.get("/api/firms/live")

    assert response.status_code == 200
    assert response.get_json() == payload
    assert shared.reads == 1
    assert shared.writes == 0
    # Warm now: the next request in this container reads neither level.
    assert client.get("/api/firms/live").status_code == 200
    assert shared.reads == 1


def test_two_containers_spend_one_upstream_transaction_between_them(client, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(firms_live, "_fetch_csv", lambda map_key: calls.append(map_key) or CSV)
    shared = _shared(monkeypatch, FakeSharedCache())

    # Container A: shared miss, fetches, publishes.
    first = client.get("/api/firms/live").get_json()
    assert calls == ["test-map-key"]
    assert shared.writes == 1
    assert shared.entry["payload"] == first
    # The publish is stamped by the wall clock, which is what another
    # container can compare against.
    assert abs(shared.entry["storedAt"] - time.time()) < 5

    # Container B: an empty process cache, but the shared copy is live.
    firms_live._cache.clear()
    second = client.get("/api/firms/live").get_json()
    assert second == first
    assert calls == ["test-map-key"]


def test_a_stale_shared_copy_is_refreshed_rather_than_served_as_current(client, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(firms_live, "_fetch_csv", lambda map_key: calls.append(map_key) or CSV)
    stale_payload = {"status": "ready", "detections": {"type": "FeatureCollection", "features": []}}
    shared = _shared(monkeypatch, FakeSharedCache({
        "storedAt": time.time() - firms_live.CACHE_SECONDS - 1, "payload": stale_payload,
    }))

    payload = client.get("/api/firms/live").get_json()

    # Fetched fresh, and the fresh copy replaced the stale one for everyone.
    assert calls == ["test-map-key"]
    assert payload != stale_payload
    assert len(payload["detections"]["features"]) == 2
    assert shared.writes == 1
    assert shared.entry["payload"] == payload


def test_the_local_copy_expires_when_the_shared_one_would(client, monkeypatch):
    # A container that reads a fourteen-minute-old shared entry must not then
    # serve it for fifteen more minutes of its own: the layer's freshness
    # claim is measured from the fetch, not from whoever last read it.
    age = firms_live.CACHE_SECONDS - 100
    _shared(monkeypatch, FakeSharedCache({
        "storedAt": time.time() - age,
        "payload": {"status": "ready", "detections": {"type": "FeatureCollection", "features": []}},
    }))
    monkeypatch.setattr(firms_live, "_fetch_csv", _upstream_must_not_be_called)

    before = time.monotonic()
    assert client.get("/api/firms/live").status_code == 200
    assert firms_live._cache["at"] <= before - age + 1


def test_a_broken_shared_store_still_serves_a_fresh_fetch(client, monkeypatch):
    # A caching layer must never turn a working page into an error: a bucket
    # that is missing, denied or slow degrades to the upstream fetch this
    # route always did, and the write failure after it is not the visitor's.
    calls: list[str] = []
    monkeypatch.setattr(firms_live, "_fetch_csv", lambda map_key: calls.append(map_key) or CSV)
    shared = _shared(monkeypatch, FakeSharedCache(broken=True))

    response = client.get("/api/firms/live")

    assert response.status_code == 200
    assert len(response.get_json()["detections"]["features"]) == 2
    assert calls == ["test-map-key"]
    assert shared.reads == 1 and shared.writes == 1
    # And the process-local level still works around it.
    assert client.get("/api/firms/live").status_code == 200
    assert calls == ["test-map-key"]


def test_an_upstream_failure_publishes_nothing_for_other_containers(client, monkeypatch):
    shared = _shared(monkeypatch, FakeSharedCache())

    def _down(map_key: str) -> str:
        raise firms_live.FirmsUnavailable("NASA FIRMS did not answer: timed out")

    monkeypatch.setattr(firms_live, "_fetch_csv", _down)
    assert client.get("/api/firms/live").status_code == 503
    assert shared.writes == 0
    assert shared.entry is None


def test_a_malformed_shared_entry_is_treated_as_a_miss(client, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(firms_live, "_fetch_csv", lambda map_key: calls.append(map_key) or CSV)
    for entry in ({"payload": {}}, {"storedAt": "yesterday", "payload": {}}, {"storedAt": True, "payload": {}}, []):
        firms_live._cache.clear()
        _shared(monkeypatch, FakeSharedCache(entry))
        assert client.get("/api/firms/live").status_code == 200
    assert len(calls) == 4


def test_the_s3_store_round_trips_gzipped_json_and_treats_no_object_as_empty():
    """The real store's encoding, against a stub client rather than S3."""
    from botocore.exceptions import ClientError

    class StubClient:
        def __init__(self):
            self.objects: dict[str, bytes] = {}

        def put_object(self, *, Bucket, Key, Body, ContentType, ContentEncoding):
            assert (ContentType, ContentEncoding) == ("application/json", "gzip")
            self.objects[(Bucket, Key)] = Body

        def get_object(self, *, Bucket, Key):
            if (Bucket, Key) not in self.objects:
                raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
            return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    store = firms_live._S3SharedCache.__new__(firms_live._S3SharedCache)
    store.bucket = "cache-bucket"
    store._client = StubClient()

    assert store.read() is None
    entry = {"storedAt": 1757468000.5, "payload": {"detections": {"features": [{"a": 1}]}}}
    store.write(entry)
    assert store.read() == entry
    stored = store._client.objects[("cache-bucket", firms_live.SHARED_CACHE_KEY)]
    assert stored[:2] == b"\x1f\x8b"  # gzip magic: what is on the wire is compressed
