"""Reconstructed event history for an audit scope, per §24's read endpoints.

Serves the artifact `data_pipeline/export_audit_events.py` produces: real
FIRMS observations, clustered into FireEvents and run through Stage-1 triage
offline. The API does no clustering -- see that module for why.

Separate from `app.audits`, which owns the audit *session* contract (create,
scope upload, history handoff) and holds sessions in process memory. This
module owns the reconstructed history that `build_history` hands off to. The
two meet at the audit id and nowhere else, so neither has to know how the
other stores anything.

Only one scope has a reconstructed history: the demo scope baked into the
artifact. An audit created through `POST /api/audits` will not have one until
reconstruction actually runs, and `history_status` says which case a caller is
in rather than returning a bare 404.
"""

import gzip
import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.audits import get_audit as get_audit_session
from app.audits import get_scope_geometry

DATA_DIR = Path(__file__).parent / "data"
EVENTS_PATH = DATA_DIR / "audit_events.json.gz"
TRIAGE_PATH = DATA_DIR / "audit_triage_detail.json.gz"

# Stage-1 outcomes, canonical spec §10.
VALID_STATES = frozenset({"LIKELY_FIRE", "LIKELY_NON_FIRE", "AMBIGUOUS"})

# The register table wants the whole scope, but 3,610 summaries is ~3.6 MB --
# enough to be slow and to approach API Gateway's 6 MB response ceiling. The
# caller pages or filters; `total` always reports the unpaged count so the UI
# can say how many matched.
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    for index, point in enumerate(ring):
        previous = ring[index - 1]
        if ((point[1] > lat) != (previous[1] > lat)) and (
            lon < (previous[0] - point[0]) * (lat - point[1]) / (previous[1] - point[1]) + point[0]
        ):
            inside = not inside
    return inside


def _geometry_polygons(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
    if geometry.get("type") == "Feature":
        return _geometry_polygons(geometry.get("geometry") or {})
    if geometry.get("type") == "FeatureCollection":
        return [polygon for feature in geometry.get("features", []) for polygon in _geometry_polygons(feature)]
    coordinates = geometry.get("coordinates", [])
    if geometry.get("type") == "Polygon":
        return [coordinates]
    if geometry.get("type") == "MultiPolygon":
        return coordinates
    return []


def _relation(event: dict[str, Any], scope: dict[str, Any] | None) -> str:
    """Classify a centroid against private scope geometry, never as attribution."""
    if not scope or not scope.get("geometry"):
        return "EXTERNAL_CONTEXT"
    centroid = event["centroid"]
    polygons = _geometry_polygons(scope["geometry"])
    if any(_point_in_ring(centroid["lon"], centroid["lat"], polygon[0]) for polygon in polygons if polygon):
        return "INSIDE_SCOPE"
    bbox = scope.get("buffer_bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        bbox = {"minLon": bbox[0], "minLat": bbox[1], "maxLon": bbox[2], "maxLat": bbox[3]}
    event_bbox = event.get("bbox", [])
    scope_bbox = scope.get("bbox")
    if isinstance(scope_bbox, dict):
        scope_bbox = [scope_bbox["minLon"], scope_bbox["minLat"], scope_bbox["maxLon"], scope_bbox["maxLat"]]
    if scope_bbox and len(event_bbox) == 4 and not (
        event_bbox[2] < scope_bbox[0] or event_bbox[0] > scope_bbox[2]
        or event_bbox[3] < scope_bbox[1] or event_bbox[1] > scope_bbox[3]
    ):
        return "BOUNDARY_INTERSECTING"
    if bbox and bbox["minLon"] <= centroid["lon"] <= bbox["maxLon"] and bbox["minLat"] <= centroid["lat"] <= bbox["maxLat"]:
        return "EXTERNAL_CONTEXT"
    return "EXTERNAL_CONTEXT"


def _distance_km(first: dict[str, Any], second: dict[str, Any]) -> float:
    import math

    lat1, lon1 = first["centroid"]["lat"], first["centroid"]["lon"]
    lat2, lon2 = second["centroid"]["lat"], second["centroid"]["lon"]
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    value = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, value)))


def investigation_map(audit_id: str, event_ids: list[str]) -> dict[str, Any] | None:
    audit = get_audit(audit_id)
    if audit is None:
        return None
    selected_ids = set(event_ids)
    selected = [event for event in audit["events"] if event["eventId"] in selected_ids]
    if len(selected) != len(selected_ids):
        return None
    neighbours = []
    for candidate in audit["events"]:
        if candidate["eventId"] in selected_ids:
            continue
        distances = [_distance_km(candidate, subject) for subject in selected]
        if distances and min(distances) <= 50:
            neighbours.append(candidate)
    session = get_audit_session(audit_id)
    scope = {**audit["scope"], **(session or {})}
    private_geometry = get_scope_geometry(audit_id)
    if private_geometry is not None:
        scope["geometry"] = private_geometry
    visible = selected + neighbours
    nodes = [
        {
            **event,
            "scopeRelation": _relation(event, scope),
            "mapRole": "SELECTED" if event in selected else "EXTERNAL_CONTEXT",
        }
        for event in visible
    ]
    edges = []
    for candidate in neighbours:
        subject = min(selected, key=lambda event: _distance_km(candidate, event))
        edges.append({
            "sourceEventId": subject["eventId"],
            "targetEventId": candidate["eventId"],
            "state": "RELATED_POSSIBLE",
            "distanceKm": round(_distance_km(subject, candidate), 3),
            "modelVersion": "fire-event-graph-v1",
        })
    return {
        "auditId": audit_id,
        "selectedEventIds": event_ids,
        "scope": scope,
        "nodes": nodes,
        "edges": edges,
        "layers": {"selectedRawObservations": False, "fireEvents": True, "graph": True, "peat": False, "weatherWind": False, "surfaceEnvelope": False},
    }


def _read_gzipped_json(path: Path) -> dict[str, Any]:
    # Both artifacts ship gzipped -- see `data_pipeline/export_audit_events.py`
    # for why. Decompression happens once per Lambda container, not per request.
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


class FilterError(ValueError):
    """A query parameter was malformed. Surfaces as a 400, not a 500."""


@lru_cache(maxsize=1)
def _load_events() -> dict[str, Any]:
    return _read_gzipped_json(EVENTS_PATH)


@lru_cache(maxsize=1)
def _load_triage_detail() -> dict[str, Any]:
    # Loaded only when an event is opened. Five times the size of the
    # summaries, and a list request must not pay for it.
    return _read_gzipped_json(TRIAGE_PATH)


def get_audit(audit_id: str) -> dict[str, Any] | None:
    """The reconstructed history for an audit id, if one has been built."""
    artifact = _load_events()["audits"].get(audit_id)
    if artifact is not None:
        return artifact
    # The current history adapter has one committed real dataset. Once a
    # session completes its build handoff, expose that cached dataset under
    # the anonymised audit id until persistence/reconstruction is replaced.
    session = get_audit_session(audit_id)
    if not session or session.get("status") != "HISTORY_BUILD_READY":
        return None
    demo = _load_events()["audits"].get("demo-2019-haze")
    if demo is None:
        return None
    demo_scope = demo["scope"]
    return {
        "scope": {
            "id": audit_id,
            "reviewStart": session["review_start"],
            "reviewEnd": session["review_end"],
            "contextBufferKm": session["context_buffer_km"],
            "eventCount": demo_scope["eventCount"],
            "reviewQueueCount": demo_scope["reviewQueueCount"],
            "compression": demo_scope["compression"],
        },
        "events": demo["events"],
    }


def history_status(audit_id: str) -> str:
    """Distinguish "no such audit" from "audit exists, history not built".

    A bare 404 for both would tell a caller who just created an audit that it
    does not exist, when the true answer is that reconstruction has not run
    for it yet.
    """
    if audit_id in _load_events()["audits"]:
        return "AVAILABLE"
    session = get_audit_session(audit_id)
    if session and session.get("status") == "HISTORY_BUILD_READY":
        return "AVAILABLE"
    return "PENDING_RECONSTRUCTION" if session else "NO_SUCH_AUDIT"


def source_provenance() -> dict[str, Any]:
    """Where the observations came from, and which parts are derived."""
    return _load_events()["source"]


def parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
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


def parse_timestamp(raw: str | None, field: str) -> datetime | None:
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise FilterError(f"{field} must be an ISO 8601 date or timestamp") from None
    # FIRMS acquisition times are UTC and the stored events are tz-aware, so a
    # bare `?since=2019-09-02` has to be read as UTC rather than compared naive
    # -- an unattached tzinfo raises TypeError deep inside the filter.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_state(raw: str | None) -> str | None:
    if raw is None:
        return None
    if raw not in VALID_STATES:
        raise FilterError(f"state must be one of: {', '.join(sorted(VALID_STATES))}")
    return raw


def parse_paging(limit_raw: str | None, offset_raw: str | None) -> tuple[int, int]:
    try:
        limit = DEFAULT_LIMIT if limit_raw is None else int(limit_raw)
        offset = 0 if offset_raw is None else int(offset_raw)
    except ValueError:
        raise FilterError("limit and offset must be integers") from None
    if limit < 1 or limit > MAX_LIMIT:
        raise FilterError(f"limit must be between 1 and {MAX_LIMIT}")
    if offset < 0:
        raise FilterError("offset must not be negative")
    return limit, offset


def filter_events(
    events: list[dict[str, Any]],
    bbox: tuple[float, float, float, float] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    state: str | None = None,
) -> list[dict[str, Any]]:
    """Filters from §24: bbox and date, plus the Stage-1 state.

    An event is a cluster with extent, so bbox matches on its centroid: a
    fire is either in the viewport or it is not, and half-including one whose
    bbox clips the edge would double-count it against a neighbouring tile.
    """
    selected = []
    for event in events:
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            centroid = event["centroid"]
            if not (min_lon <= centroid["lon"] <= max_lon and min_lat <= centroid["lat"] <= max_lat):
                continue
        # An event spans time, so a window matches when the event overlaps it,
        # not when it starts inside it -- a fire burning across the window's
        # start is exactly what an auditor needs to see.
        if since is not None and datetime.fromisoformat(event["lastDetection"]) < since:
            continue
        if until is not None and datetime.fromisoformat(event["firstDetection"]) > until:
            continue
        if state is not None and event["triage"]["state"] != state:
            continue
        selected.append(event)
    return selected


def find_event(audit_id: str, event_id: str) -> dict[str, Any] | None:
    audit = get_audit(audit_id)
    if audit is None:
        return None
    summary = next((e for e in audit["events"] if e["eventId"] == event_id), None)
    if summary is None:
        return None
    detail = _load_triage_detail().get(audit_id, {}).get(event_id)
    # The rule-by-rule breakdown and its evidence objects: what makes the
    # Stage-1 outcome inspectable rather than asserted (§17).
    return {**summary, "triageDetail": detail}
