"""Live regional NASA FIRMS detections for the landing map.

The console's first screen draws current thermal detections across Southeast
Asia as orientation context. No audit exists at that point, which is why this
is deliberately one of the few routes that is not audit-scoped -- it is
regional context *before* a scope, not evidence inside one.

The browser used to call `firms.modaps.eosdis.nasa.gov` itself. It cannot:
Vite inlines every `VITE_`-prefixed variable into the built bundle, and a
FIRMS MAP_KEY -- unlike the Carto key beside it, which is designed to be
public and domain-restricted -- cannot be restricted to a domain at all. So
shipping it hands the account's FIRMS transaction quota to anyone who opens
the JS, and *not* shipping it left the deployed landing page permanently
reporting "Live FIRMS context unavailable" (#149). The key stays on the
server and the console asks the API instead.

Moving the call server-side also fixes what the browser was actually
requesting: `world/1` -- every VIIRS detection on Earth for 24 hours, several
MB of CSV -- which the client then filtered down to the region after paying to
download it. The area API takes a bounding box.

Nothing here is persisted as evidence. These detections are live orientation
context, not audit evidence; the evidence path reads the committed, immutable
2019 artifact so the same review reproduces. The one thing stored is the
served payload itself, in a shared cache that expires (see `_cache` below).
That is a cache of a public feed, not a store of detections: it holds nothing
a fresh fetch would not return, and the audit path never reads it.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

FIRMS_ROOT = "https://firms.modaps.eosdis.nasa.gov"

# west, south, east, north -- the order the FIRMS area API takes, and the same
# window as the landing map's maxBounds. Keep the two in step: a wider fetch
# than the map can pan to is bandwidth nobody can see.
SOUTHEAST_ASIA_BBOX = (90.0, -12.0, 145.0, 25.0)

# VIIRS on Suomi-NPP, near-real-time. 375 m resolution against MODIS's 1 km,
# and the same sensor family the committed 2019 artifact was clustered from.
SENSOR = "VIIRS_SNPP_NRT"

# The window the layer *claims*, and the one it actually serves: a rolling 24
# hours ending now, filtered here rather than asked for upstream.
#
# The area API's day range, given no explicit [DATE], is anchored on the
# current UTC calendar day rather than on a rolling window. A `1` therefore
# means "since 00:00 UTC today", which at 02:00 UTC is a two-hour window --
# and VIIRS/Suomi-NPP crosses this region near 18:30 UTC (previous day) and
# 06:30 UTC, so an early-UTC request contains no Southeast Asian overpass at
# all and comes back empty for reasons that have nothing to do with fires.
#
# Fetching two days and filtering to 24 hours here is correct under either
# reading of the parameter -- calendar-anchored or rolling -- so it does not
# rest on which one is right. Measured against the live API at 01:51 UTC on
# 2026-09-10: two days returned 5,389 detections, every one stamped 09-09 and
# every one inside a rolling 24 hours. One day returned nothing at all.
FETCH_DAYS = 2
WINDOW_HOURS = 24

# The columns a real FIRMS CSV answer carries. FIRMS serves its errors as
# plain text with HTTP 200 ("Invalid MAP_KEY.", transaction-limit notices), and
# a one-line error body parses as a header with no rows -- which would render
# as an empty region, i.e. "no fires are burning". Checking the header is what
# keeps "we looked and found nothing" apart from "we could not look".
REQUIRED_COLUMNS = ("latitude", "longitude")

# One upstream fetch serves every visitor for this long. Without it each
# browser is its own FIRMS client against a per-key transaction cap, and the
# console's landing page is the screen every visitor lands on first. FIRMS
# publishes new granules well under an hour apart, so 15 minutes is fresh
# enough to call the layer live.
CACHE_SECONDS = 900

# The API Lambda's own budget is 29s. A FIRMS fetch that has not answered in
# 10 leaves room to report the layer unavailable rather than have API Gateway
# time the whole request out.
FETCH_TIMEOUT_SECONDS = 10

# Two cache levels, checked in this order.
#
# 1. `_cache`, this process's own copy. Free to read, and it is what serves
#    every visitor a warm container sees. It is also why a cache exists at
#    all: without it each browser is its own FIRMS client against a per-key
#    transaction cap.
# 2. One shared object in S3, when `LIVE_CACHE_BUCKET` is set. Lambda serves
#    consecutive requests from different containers, and a cold container's
#    `_cache` is empty, so before #186 the first visitor after every cold
#    start waited on NASA (measured: ~2.4s of extra time-to-first-byte, on
#    the screen every visitor sees first) and two warm containers each spent
#    their own upstream transaction for the same window. The shared copy is
#    what a cold container reads instead. It is S3 rather than a row in the
#    audit-state table because the payload does not reliably fit a 400 KB
#    item: gzipped, ~100 KB at the 5,389 detections measured on 2026-09-10,
#    past the cap near 20,000, which is a haze-season day -- so DynamoDB
#    would fail exactly when the layer matters (decision log, 2026-09-10,
#    live FIRMS cache).
#
# The shared level is best-effort in both directions. A read that fails, a
# write that fails, a bucket that does not exist, or no boto3 in a local
# install all fall through to the upstream fetch this module always did: a
# caching layer must never turn a working page into an error. Staleness is
# judged by the wall-clock time stored inside the object, never by this
# container's monotonic clock, because another process wrote it.
#
# What this does not do: stop two containers that miss at the same instant
# from both fetching. That costs one extra FIRMS transaction per simultaneous
# cold miss, against a quota in the thousands per ten minutes; a lease in the
# shared store would remove it at the price of a second round trip on every
# miss and a stale-lease path to get right. Not worth it at this traffic.
_cache: dict[str, Any] = {}

SHARED_CACHE_KEY = "firms-live/current.json.gz"

# S3 within the region answers in tens of milliseconds. Anything slower than
# these is worth abandoning for a direct fetch: the whole route has to answer
# inside the API Lambda's 29s, and boto3's defaults would wait a minute.
SHARED_CACHE_CONNECT_TIMEOUT_SECONDS = 2
SHARED_CACHE_READ_TIMEOUT_SECONDS = 5


class FirmsUnavailable(RuntimeError):
    """The live layer cannot be served -- no key, or upstream did not answer."""


class _S3SharedCache:
    """One gzipped JSON object: `{"storedAt": <epoch seconds>, "payload": ...}`.

    Gzipped not for the item cap (S3 has none) but because the object is read
    on every cold start and ~850 KB of point features compress to ~100 KB.
    """

    def __init__(self, bucket: str) -> None:
        import boto3  # Lambda supplies boto3; a local install needs it only with the bucket set.
        from botocore.config import Config

        self.bucket = bucket
        # Stage durations in milliseconds, for the one INFO line `_read_shared`
        # logs: this is how #251's "where do 2.5 s of cold handler go" gets
        # answered on the deployed function rather than guessed at.
        self.stages: dict[str, float] = {}
        started = time.perf_counter()
        self._client = boto3.client(
            "s3",
            config=Config(
                connect_timeout=SHARED_CACHE_CONNECT_TIMEOUT_SECONDS,
                read_timeout=SHARED_CACHE_READ_TIMEOUT_SECONDS,
                retries={"max_attempts": 2},
            ),
        )
        self.stages["client_ms"] = _elapsed_ms(started)

    def warm(self) -> None:
        """Open the connection now so the first read does not pay for it.

        A HEAD of the cache key resolves credentials, performs the TLS
        handshake and leaves a keep-alive connection in botocore's pool, all
        of which the first GET would otherwise do inside the request. Called
        from `create_app()`, which on Lambda runs in the init phase, where
        the container has a full CPU; the handler phase at 512 MB does not.
        A missing object is not a failure here: the connection is what is
        wanted, and the object will be read, or found absent, by `read()`.
        """
        from botocore.exceptions import ClientError

        started = time.perf_counter()
        try:
            self._client.head_object(Bucket=self.bucket, Key=SHARED_CACHE_KEY)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
                raise
        finally:
            self.stages["warm_ms"] = _elapsed_ms(started)

    def read(self) -> dict[str, Any] | None:
        from botocore.exceptions import ClientError

        started = time.perf_counter()
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=SHARED_CACHE_KEY)
            body = response["Body"].read()
        except ClientError as exc:
            # No object yet is the ordinary state of a fresh bucket, not a
            # failure; anything else is, and the caller decides what to do.
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        self.stages["get_ms"] = _elapsed_ms(started)
        self.stages["get_bytes"] = len(body)
        started = time.perf_counter()
        entry = json.loads(gzip.decompress(body).decode("utf-8"))
        self.stages["decode_ms"] = _elapsed_ms(started)
        return entry

    def write(self, entry: dict[str, Any]) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=SHARED_CACHE_KEY,
            Body=gzip.compress(json.dumps(entry, separators=(",", ":")).encode("utf-8")),
            ContentType="application/json",
            ContentEncoding="gzip",
        )


_shared: _S3SharedCache | None = None
_shared_lock = threading.Lock()


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _shared_cache() -> _S3SharedCache | None:
    """The shared level, built once per container, or None when not configured."""
    global _shared
    bucket = os.environ.get("LIVE_CACHE_BUCKET", "").strip()
    if not bucket:
        return None
    with _shared_lock:
        if _shared is None or _shared.bucket != bucket:
            _shared = _S3SharedCache(bucket)
        return _shared


def warm_shared_cache() -> None:
    """Build the shared level and open its connection ahead of the first request.

    Before this, the S3 client was first built inside the first cold request,
    which on the deployed function cost ~2.5 s of handler time with FIRMS
    already out of the path (#251): botocore loads the S3 service model on
    first construction, then the first request adds credential resolution and
    a TLS handshake, on the handler phase's fraction of a vCPU. `create_app()`
    calls this, so on Lambda it runs during init, and in tests and local runs
    without `LIVE_CACHE_BUCKET` it is a no-op. Never raises: a store that
    cannot be warmed is the same store that `_read_shared` falls through on.
    """
    try:
        shared = _shared_cache()
        if shared is not None:
            shared.warm()
    except Exception:
        logger.warning("Shared live FIRMS cache could not be warmed at start-up", exc_info=True)


def _read_shared() -> dict[str, Any] | None:
    """The shared entry if one exists and is well-formed, else None. Never raises."""
    try:
        shared = _shared_cache()
        if shared is None:
            return None
        started = time.perf_counter()
        entry = shared.read()
        # One line per cold read, INFO so it reaches CloudWatch (the handler
        # raises `app.*` to INFO). The stage split is what #251 asked for.
        stages = dict(getattr(shared, "stages", {}))
        stages["read_ms"] = _elapsed_ms(started)
        logger.info(
            "Shared live FIRMS cache read: %s",
            " ".join(f"{name}={value}" for name, value in sorted(stages.items())),
        )
    except Exception:
        # Deliberately broad: a missing bucket, a denied read, a timeout and a
        # missing boto3 all have the same right answer here, which is to fetch
        # upstream as if there were no shared level. Logged so a persistently
        # failing store is visible in CloudWatch rather than only as slower
        # cold starts.
        logger.warning("Shared live FIRMS cache could not be read; fetching upstream", exc_info=True)
        return None
    if (
        not isinstance(entry, dict)
        or "payload" not in entry
        or isinstance(entry.get("storedAt"), bool)
        or not isinstance(entry.get("storedAt"), (int, float))
    ):
        return None
    return entry


def _write_shared(entry: dict[str, Any]) -> None:
    """Publish a fresh fetch for other containers. Never raises."""
    try:
        shared = _shared_cache()
        if shared is not None:
            shared.write(entry)
    except Exception:
        # Same reasoning as `_read_shared`: the visitor already has their
        # payload, and a failed publish costs the next cold container one
        # upstream fetch, not this visitor anything.
        logger.warning("Shared live FIRMS cache could not be written", exc_info=True)


def _fetch_csv(map_key: str) -> str:
    bbox = ",".join(str(value) for value in SOUTHEAST_ASIA_BBOX)
    url = f"{FIRMS_ROOT}/api/area/csv/{map_key}/{SENSOR}/{bbox}/{FETCH_DAYS}"
    try:
        # S310 suppressed deliberately: the scheme and host are the module
        # constants above and the only interpolated values are a key from the
        # environment and integers -- no caller-controlled input reaches it.
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FirmsUnavailable(f"NASA FIRMS did not answer: {exc}") from exc


def _acquired_at(row: dict[str, str]) -> str | None:
    """FIRMS reports UTC as a date plus an unpadded HHMM ('618' is 06:18)."""
    date = (row.get("acq_date") or "").strip()
    time_of_day = (row.get("acq_time") or "").strip().zfill(4)
    if not date or len(time_of_day) != 4 or not time_of_day.isdigit():
        return None
    return f"{date}T{time_of_day[:2]}:{time_of_day[2:]}:00Z"


def _to_features(payload: str, *, map_key: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(payload))
    header = reader.fieldnames or []
    if not all(column in header for column in REQUIRED_COLUMNS):
        # Report what upstream actually said rather than a generic failure --
        # "Invalid MAP_KEY" and "you have exhausted your transactions" need
        # different responses from us, and neither is a statement about fires.
        # The key is redacted because this message reaches the browser in the
        # 503 body, and a FIRMS error page could echo the URL it was given.
        first_line = payload.strip().splitlines()[0][:200] if payload.strip() else "(empty response)"
        raise FirmsUnavailable(
            f"NASA FIRMS did not return detection data: {first_line.replace(map_key, '<map_key>')}"
        )

    features: list[dict[str, Any]] = []
    for row in reader:
        try:
            longitude = float(row["longitude"])
            latitude = float(row["latitude"])
        except (KeyError, TypeError, ValueError):
            # A truncated line or an error page served as 200 -- drop the row
            # rather than fail the whole layer over one of several thousand.
            continue
        try:
            frp = float(row.get("frp") or 0)
        except ValueError:
            frp = 0.0
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": {
                "confidence": (row.get("confidence") or "unknown").strip(),
                "frp": frp,
                # The client derives an age from this at render time. The
                # server must not: a response cached for 15 minutes would
                # otherwise hand every later visitor a 15-minute-old "now".
                "acquiredAt": _acquired_at(row),
            },
        })
    return features


def _within_window(features: list[dict[str, Any]], *, as_of: datetime) -> list[dict[str, Any]]:
    """Keep only detections inside the rolling window the layer claims.

    A detection whose timestamp will not parse is dropped rather than kept:
    the client draws an unplaceable one at the window's far edge, which is a
    reasonable way to *render* something already known to be in range, but
    including it here would put it inside a 24-hour claim nothing measured.
    """
    cutoff = as_of - timedelta(hours=WINDOW_HOURS)
    kept: list[dict[str, Any]] = []
    for feature in features:
        acquired_at = feature["properties"].get("acquiredAt")
        if not acquired_at:
            continue
        try:
            observed = datetime.fromisoformat(acquired_at)
        except ValueError:
            continue
        # Lower bound only. A detection cannot be observed in the future, so
        # an upper bound would police nothing but clock skew between this
        # Lambda and FIRMS -- and it would do it by silently dropping real
        # detections, which is the failure this whole route exists to avoid.
        if observed >= cutoff:
            kept.append(feature)
    return kept


def live_detections(*, now: float | None = None) -> dict[str, Any]:
    """Current regional detections, served from cache where one is warm.

    Raises FirmsUnavailable when there is no key or FIRMS did not answer --
    the caller reports that rather than returning an empty collection, because
    an empty regional layer reads as "no fires", which would be a fabricated
    observation.
    """
    map_key = os.environ.get("NASA_FIRMS_MAP_KEY", "").strip()
    if not map_key:
        raise FirmsUnavailable("NASA_FIRMS_MAP_KEY is not configured.")

    clock = time.monotonic() if now is None else now
    cached = _cache.get("payload")
    if cached is not None and clock - _cache["at"] < CACHE_SECONDS:
        return cached

    entry = _read_shared()
    if entry is not None:
        # Age by the writer's wall clock, clamped so a container whose clock
        # runs a second behind the writer's does not read a fresh entry as
        # being from the future and refetch for nothing.
        age = max(0.0, time.time() - float(entry["storedAt"]))
        if age < CACHE_SECONDS:
            payload = entry["payload"]
            # The local copy expires when the shared one would, not fifteen
            # minutes from now: otherwise a container that read a
            # fourteen-minute-old entry would serve it as current for
            # twenty-nine, and the layer would no longer be what it claims.
            _cache.update(payload=payload, at=clock - age)
            return payload

    fetched_at = datetime.now(UTC)
    features = _within_window(
        _to_features(_fetch_csv(map_key), map_key=map_key), as_of=fetched_at
    )
    payload = {
        "status": "ready",
        "sensor": SENSOR,
        "windowHours": WINDOW_HOURS,
        "fetchedAt": fetched_at.isoformat(timespec="seconds"),
        "detections": {"type": "FeatureCollection", "features": features},
    }
    _cache.update(payload=payload, at=clock)
    # Only a successful fetch is published. An upstream failure raised above,
    # so a stale or error payload can never be what other containers read.
    _write_shared({"storedAt": fetched_at.timestamp(), "payload": payload})
    return payload
