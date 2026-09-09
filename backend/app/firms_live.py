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

Nothing here is persisted. These detections are live orientation context, not
audit evidence; the evidence path reads the committed, immutable 2019 artifact
so the same review reproduces.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
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
WINDOW_DAYS = 1

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

_cache: dict[str, Any] = {}


class FirmsUnavailable(RuntimeError):
    """The live layer cannot be served -- no key, or upstream did not answer."""


def _fetch_csv(map_key: str) -> str:
    bbox = ",".join(str(value) for value in SOUTHEAST_ASIA_BBOX)
    url = f"{FIRMS_ROOT}/api/area/csv/{map_key}/{SENSOR}/{bbox}/{WINDOW_DAYS}"
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


def _to_features(payload: str) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(payload)):
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

    features = _to_features(_fetch_csv(map_key))
    payload = {
        "status": "ready",
        "sensor": SENSOR,
        "windowHours": WINDOW_DAYS * 24,
        "fetchedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "detections": {"type": "FeatureCollection", "features": features},
    }
    _cache.update(payload=payload, at=clock)
    return payload
