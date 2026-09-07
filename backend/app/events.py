"""Event listing and lookup behind `/api/events`.

The event objects are the console's fixture cases, moved server-side so the
endpoint contract in `assurance_console_ui_spec.md` Section 5 is served by the
real API rather than mocked in the browser. They are still fixtures; nothing
here derives an event from an observation yet.
"""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent / "data" / "events.json"

# Matches the EventStatus union in frontend/src/api/types.ts. Section 5 of the
# UI spec lists an older set (AMBIGUOUS/REJECTED); the frontend names are the
# ones the data and the UI actually use.
VALID_STATUSES = frozenset(
    {"AWAITING_REVIEW", "STAGE1_REJECTED", "STAGE2_RUNNING", "CONVERGED"}
)


class FilterError(ValueError):
    """A query parameter was malformed. Surfaces as a 400, not a 500."""


@lru_cache(maxsize=1)
def load_events() -> tuple[dict[str, Any], ...]:
    # Read once per process: on Lambda that is once per cold start, and the
    # file ships inside the deployment bundle, so serving a request never
    # touches the network or the filesystem again.
    with DATA_PATH.open(encoding="utf-8") as handle:
        return tuple(json.load(handle))


def parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    """Parse `minLon,minLat,maxLon,maxLat` as ordered by UI spec Section 5."""
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise FilterError("bbox must be four comma-separated numbers: minLon,minLat,maxLon,maxLat")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError:
        raise FilterError("bbox values must be numbers") from None
    if min_lon > max_lon or min_lat > max_lat:
        raise FilterError("bbox minimums must not exceed their maximums")
    return min_lon, min_lat, max_lon, max_lat


def parse_since(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        # The fixtures store UTC as a trailing "Z", which fromisoformat only
        # learned to read in 3.11; the Lambda runtime is 3.13.
        return datetime.fromisoformat(raw)
    except ValueError:
        raise FilterError("since must be an ISO 8601 timestamp") from None


def parse_status(raw: str | None) -> str | None:
    if raw is None:
        return None
    if raw not in VALID_STATUSES:
        raise FilterError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    return raw


def filter_events(
    events: tuple[dict[str, Any], ...],
    bbox: tuple[float, float, float, float] | None = None,
    since: datetime | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Apply the Section 5 filters. Absent filters match everything."""
    selected = []
    for event in events:
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            if not (min_lon <= event["lon"] <= max_lon and min_lat <= event["lat"] <= max_lat):
                continue
        if since is not None and datetime.fromisoformat(event["firstDetected"]) < since:
            continue
        if status is not None and event["status"] != status:
            continue
        selected.append(event)
    return selected


def find_event(event_id: str) -> dict[str, Any] | None:
    return next((e for e in load_events() if e["id"] == event_id), None)
