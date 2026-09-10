"""Minimal audit-scope session contract for the audit-first console flow.

The repository does not provision durable application storage yet. Keeping the
session adapter small and behind this module lets the history builder attach to
the same contract later without inventing a second scope model. Sessions live
for the lifetime of a Flask/Lambda process until a storage decision is made.
"""

from __future__ import annotations

from datetime import date
from math import cos, isfinite, pi, radians, sin
from secrets import token_urlsafe
from typing import Any

from app import audit_store

DEFAULT_CONTEXT_BUFFER_KM = 25.0
MAX_CONTEXT_BUFFER_KM = 1_000.0
_EPSILON = 1e-12

# A point-and-radius scope (spec 6.1, "lat/lon + radius quick analysis").
# The radius bounds are guardrails, not policy: below 100 m the circle is
# smaller than a VIIRS pixel and cannot contain a detection, and above
# 250 km it stops being a management unit and becomes a region, which the
# context buffer already provides. Latitude is kept off the poles because
# the equirectangular circle below degenerates there.
MIN_POINT_RADIUS_KM = 0.1
MAX_POINT_RADIUS_KM = 250.0
MAX_POINT_LATITUDE = 85.0
CIRCLE_VERTICES = 64
KM_PER_DEGREE = 111.32

# The predefined demo study area. It is the frontend's
# DEFAULT_MANAGEMENT_UNIT_GEOMETRY (frontend/src/lib/scope.ts) moved
# server-side so the session can say it is a demo scope rather than an
# upload: the two constants must agree until the console calls
# /scope/demo instead of posting its own copy. A rectangle over the
# Kalimantan block the 2019 artifact's enriched events fall in. It is a
# study area chosen for the data it contains, not any organisation's
# boundary, and the label says so wherever it is shown.
DEMO_SCOPE_LABEL = "Demo study area, 2019 Kalimantan haze window. Not a company boundary."
DEMO_SCOPE_GEOMETRY: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[[116.0, -4.05], [116.5, -4.05], [116.5, -3.55], [116.0, -3.55], [116.0, -4.05]]],
}

# This is deliberately an adapter seam, not a pretend durable database. A
# warm Lambda can serve the next request by audit ID; a later storage issue can
# replace this mapping without changing the frontend contract.
# Kept as a compatibility cache for a few local callers.  The source of
# truth is audit_store, which becomes DynamoDB in Lambda.
AUDIT_SESSIONS: dict[str, dict[str, Any]] = {}


def _create(session: dict[str, Any]) -> None:
    AUDIT_SESSIONS[session["audit_id"]] = session
    audit_store.create(session)


def _apply(audit_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Persist a scope change without overwriting what another writer added.

    Scope setup used to write the whole session blob back unconditionally,
    which was safe only because it always precedes pack selection and
    analysis. It does not have to: an auditor who re-uploads a boundary while
    an assessment is running would have dropped that assessment's result
    (#146). These updates are a fixed dict computed before the call, so
    re-applying them to whatever the store now holds is the right answer on a
    retry rather than a merge to reason about.
    """
    session = audit_store.update(audit_id, lambda stored: stored.update(updates))
    if session is not None:
        AUDIT_SESSIONS[audit_id] = session
    return session


def _load(audit_id: str) -> dict[str, Any] | None:
    session = audit_store.get(audit_id)
    if session is not None:
        AUDIT_SESSIONS[audit_id] = session
    return session


class AuditValidationError(ValueError):
    """A caller supplied an invalid audit or scope input."""


def _record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditValidationError("request body must be a JSON object")
    return value


def _required_date(payload: dict[str, Any], snake_name: str, camel_name: str) -> str:
    raw = payload.get(snake_name, payload.get(camel_name))
    if not isinstance(raw, str) or not raw:
        raise AuditValidationError(f"{snake_name} is required and must be an ISO date")
    try:
        date.fromisoformat(raw)
    except ValueError:
        raise AuditValidationError(f"{snake_name} must be an ISO date (YYYY-MM-DD)") from None
    return raw


def _context_buffer(payload: dict[str, Any]) -> float:
    raw = payload.get("context_buffer_km", payload.get("contextBufferKm", DEFAULT_CONTEXT_BUFFER_KM))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise AuditValidationError("context_buffer_km must be a number") from None
    if not isfinite(value) or value < 0 or value > MAX_CONTEXT_BUFFER_KM:
        raise AuditValidationError(
            f"context_buffer_km must be between 0 and {MAX_CONTEXT_BUFFER_KM:g} km"
        )
    return value


def _bbox_dict(bbox: tuple[float, float, float, float] | list[float]) -> dict[str, float]:
    """`{minLon, minLat, maxLon, maxLat}` -- the shape the frontend's BBox
    type expects everywhere else (fetchEvents, fetchAuditRegister,
    buildScopePreview's client-side preview). The canonical spec's §25
    AuditScope sketch uses a raw tuple, but that is a suggestion, and every
    real consumer of this field in this repo is already the object shape.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    return {"minLon": min_lon, "minLat": min_lat, "maxLon": max_lon, "maxLat": max_lat}


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in session.items() if key != "_geometry"}


def create_audit(payload: Any) -> dict[str, Any]:
    values = _record(payload)
    review_start = _required_date(values, "review_start", "reviewStart")
    review_end = _required_date(values, "review_end", "reviewEnd")
    if review_end < review_start:
        raise AuditValidationError("review_end must be on or after review_start")

    audit_id = f"audit_{token_urlsafe(12)}"
    scope_id = f"scope_{token_urlsafe(12)}"
    session = {
        "audit_id": audit_id,
        "scope_id": scope_id,
        "review_start": review_start,
        "review_end": review_end,
        "context_buffer_km": _context_buffer(values),
        "status": "AWAITING_SCOPE",
        # How the scope was supplied: "upload", "point_radius" or "demo".
        # Recorded so a session can never present a predefined area as if
        # the auditor had uploaded it (#87).
        "scope_source": None,
        "scope_label": None,
        "bbox": None,
        "centroid": None,
        "buffer_bbox": None,
        "buffer_geometry": None,
        "_geometry": None,
    }
    _create(session)
    return _public_session(session)


def get_audit(audit_id: str) -> dict[str, Any] | None:
    session = _load(audit_id)
    return _public_session(session) if session else None


def get_scope_geometry(audit_id: str) -> Any:
    """Private geometry access for server-side spatial classification only."""
    session = _load(audit_id)
    return session.get("_geometry") if session else None


def _polygon_groups(geojson: Any) -> tuple[list[list[list[list[float]]]], Any]:
    """Return polygon coordinate groups and the original JSON value."""

    record = _record(geojson)
    geojson_type = record.get("type")

    def geometry_groups(geometry: Any) -> list[list[list[list[float]]]]:
        if not isinstance(geometry, dict):
            raise AuditValidationError("GeoJSON feature must contain a geometry object")
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if geometry_type == "Polygon":
            return [coordinates] if isinstance(coordinates, list) else []
        if geometry_type == "MultiPolygon":
            return coordinates if isinstance(coordinates, list) else []
        raise AuditValidationError("management-unit geometry must be a Polygon or MultiPolygon")

    if geojson_type == "FeatureCollection":
        features = record.get("features")
        if not isinstance(features, list) or not features:
            raise AuditValidationError("GeoJSON FeatureCollection must contain at least one feature")
        groups: list[list[list[list[float]]]] = []
        for feature in features:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise AuditValidationError("GeoJSON FeatureCollection contains an invalid feature")
            groups.extend(geometry_groups(feature.get("geometry")))
        return groups, geojson
    if geojson_type == "Feature":
        return geometry_groups(record.get("geometry")), geojson
    if geojson_type in {"Polygon", "MultiPolygon"}:
        return geometry_groups(record), geojson
    raise AuditValidationError(
        "upload a GeoJSON Feature, FeatureCollection, or a Polygon or MultiPolygon geometry"
    )


def _ring_area(ring: list[list[float]]) -> float:
    return 0.5 * sum(
        ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1]
        for index in range(len(ring) - 1)
    )


def _validate_position(position: Any) -> list[float]:
    if not isinstance(position, list) or len(position) < 2:
        raise AuditValidationError(
            "GeoJSON coordinates must be [longitude, latitude] positions"
        )
    try:
        longitude, latitude = float(position[0]), float(position[1])
    except (TypeError, ValueError):
        raise AuditValidationError(
            "GeoJSON coordinates must be numeric [longitude, latitude] positions"
        ) from None
    if not isfinite(longitude) or not isfinite(latitude):
        raise AuditValidationError("GeoJSON coordinates must be finite numbers")
    if not -180 <= longitude <= 180:
        raise AuditValidationError("longitude must be between -180 and 180")
    if not -90 <= latitude <= 90:
        raise AuditValidationError(
            "latitude must be between -90 and 90; GeoJSON order is [longitude, latitude]"
        )
    return [longitude, latitude]


def _validate_groups(groups: list[list[list[list[float]]]]) -> tuple[float, float, float, float]:
    if not groups:
        raise AuditValidationError("GeoJSON must contain at least one polygon")

    positions: list[list[float]] = []
    for polygon in groups:
        if not isinstance(polygon, list) or not polygon:
            raise AuditValidationError("polygon must contain an outer ring")
        for ring_index, raw_ring in enumerate(polygon):
            if not isinstance(raw_ring, list) or len(raw_ring) < 4:
                raise AuditValidationError("polygon rings must contain at least four positions")
            ring = [_validate_position(position) for position in raw_ring]
            if ring[0] != ring[-1]:
                raise AuditValidationError("each polygon ring must be closed (first position equals last)")
            if abs(_ring_area(ring)) <= _EPSILON:
                label = "outer ring" if ring_index == 0 else "polygon ring"
                raise AuditValidationError(f"{label} must enclose a non-empty area")
            positions.extend(ring)

    longitudes = [position[0] for position in positions]
    latitudes = [position[1] for position in positions]
    bbox = min(longitudes), min(latitudes), max(longitudes), max(latitudes)
    if bbox[0] == bbox[2] or bbox[1] == bbox[3]:
        raise AuditValidationError("management-unit bounds must be non-empty")
    return bbox


def _buffer_geometry(bbox: tuple[float, float, float, float], buffer_km: float) -> tuple[list[float], dict[str, Any]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    center_lat = (min_lat + max_lat) / 2
    lat_delta = buffer_km / 111.32
    longitude_scale = max(abs(cos(radians(center_lat))), 0.01)
    lon_delta = buffer_km / (111.32 * longitude_scale)
    buffered = [
        max(-180.0, min_lon - lon_delta),
        max(-90.0, min_lat - lat_delta),
        min(180.0, max_lon + lon_delta),
        min(90.0, max_lat + lat_delta),
    ]
    buffer_polygon = {
        "type": "Polygon",
        "coordinates": [[
            [buffered[0], buffered[1]],
            [buffered[2], buffered[1]],
            [buffered[2], buffered[3]],
            [buffered[0], buffered[3]],
            [buffered[0], buffered[1]],
        ]],
    }
    return buffered, buffer_polygon


def _set_scope(
    audit_id: str,
    geojson: Any,
    *,
    source: str,
    label: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """One path for every way a scope can be supplied.

    An uploaded boundary, a generated circle and the demo rectangle all
    become the same polygon geometry, go through the same validation and
    buffer, and set the same status. That is what keeps downstream scope
    relations identical whichever way the scope arrived (#87 forbids a
    second scope model), and `scope_source` is the only thing that differs.
    """
    session = _load(audit_id)
    if session is None:
        return None

    groups, original = _polygon_groups(geojson)
    bbox = _validate_groups(groups)
    centroid = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    buffer_bbox, buffer_geometry = _buffer_geometry(bbox, session["context_buffer_km"])

    session = _apply(
        audit_id,
        {
            "status": "SCOPE_READY",
            "scope_source": source,
            "scope_label": label,
            "bbox": _bbox_dict(bbox),
            "centroid": centroid,
            "buffer_bbox": _bbox_dict(buffer_bbox),
            "buffer_geometry": buffer_geometry,
            "_geometry": original,
            **(extra or {}),
        },
    )
    if session is None:
        return None
    return _public_session(session) | {"geometry": original}


def upload_scope(audit_id: str, geojson: Any) -> dict[str, Any] | None:
    return _set_scope(audit_id, geojson, source="upload")


def _number(payload: dict[str, Any], snake_name: str, camel_name: str) -> float:
    raw = payload.get(snake_name, payload.get(camel_name))
    if raw is None:
        raise AuditValidationError(f"{snake_name} is required")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise AuditValidationError(f"{snake_name} must be a number")
    try:
        value = float(raw)
    except ValueError:
        raise AuditValidationError(f"{snake_name} must be a number") from None
    if not isfinite(value):
        raise AuditValidationError(f"{snake_name} must be a finite number")
    return value


def circle_polygon(latitude: float, longitude: float, radius_km: float) -> dict[str, Any]:
    """A closed GeoJSON Polygon approximating a circle on the ground.

    Equirectangular, like `_buffer_geometry`: at the radii allowed here and
    away from the poles the error is well under a detection pixel, and it
    keeps the scope a plain polygon so relation logic needs no circle case.
    Longitude wraps at the antimeridian rather than clamping, so a circle
    straddling it stays a ring; latitude cannot reach a pole because the
    input is bounded at 85 degrees plus 250 km.
    """
    lat_delta = radius_km / KM_PER_DEGREE
    lon_delta = radius_km / (KM_PER_DEGREE * max(abs(cos(radians(latitude))), 0.01))
    ring = []
    for step in range(CIRCLE_VERTICES):
        angle = 2 * pi * step / CIRCLE_VERTICES
        lon = longitude + lon_delta * cos(angle)
        lat = latitude + lat_delta * sin(angle)
        if lon > 180:
            lon -= 360
        elif lon < -180:
            lon += 360
        ring.append([round(lon, 6), round(max(-90.0, min(90.0, lat)), 6)])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def set_point_scope(audit_id: str, payload: Any) -> dict[str, Any] | None:
    """Scope from a centre point and a radius, validated before anything is stored."""
    values = _record(payload)
    latitude = _number(values, "latitude", "lat")
    longitude = _number(values, "longitude", "lon")
    radius_km = _number(values, "radius_km", "radiusKm")
    if not -MAX_POINT_LATITUDE <= latitude <= MAX_POINT_LATITUDE:
        raise AuditValidationError(
            f"latitude must be between -{MAX_POINT_LATITUDE:g} and {MAX_POINT_LATITUDE:g}"
        )
    if not -180 <= longitude <= 180:
        raise AuditValidationError("longitude must be between -180 and 180")
    if not MIN_POINT_RADIUS_KM <= radius_km <= MAX_POINT_RADIUS_KM:
        raise AuditValidationError(
            f"radius_km must be between {MIN_POINT_RADIUS_KM:g} and {MAX_POINT_RADIUS_KM:g} km"
        )
    return _set_scope(
        audit_id,
        circle_polygon(latitude, longitude, radius_km),
        source="point_radius",
        label=f"{radius_km:g} km around {latitude:.4f}, {longitude:.4f}",
        extra={"scope_point": {"latitude": latitude, "longitude": longitude, "radius_km": radius_km}},
    )


def set_demo_scope(audit_id: str) -> dict[str, Any] | None:
    """The predefined demo study area, labelled as such in the session."""
    return _set_scope(audit_id, DEMO_SCOPE_GEOMETRY, source="demo", label=DEMO_SCOPE_LABEL)


def build_history(audit_id: str) -> dict[str, Any] | None:
    session = _load(audit_id)
    if session is None:
        return None
    if session["status"] != "SCOPE_READY":
        raise AuditValidationError(
            "set an audit scope before building history: upload a management-unit GeoJSON, "
            "enter a point and radius, or use the demo scope"
        )
    session = _apply(audit_id, {"status": "HISTORY_BUILD_READY"})
    if session is None:
        return None
    return {"audit_id": audit_id, "scope_id": session["scope_id"], "status": session["status"]}
