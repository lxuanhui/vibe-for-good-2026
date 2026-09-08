import math
from datetime import datetime
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request

from app.events import (
    FilterError,
    filter_events,
    find_event,
    load_events,
    parse_bbox,
    parse_since,
    parse_status,
)
from app.history import Audit, HistoryDependencyError, HistoryInputError, normalize_geometry

api = Blueprint("api", __name__)


def _audit_store():
    return current_app.extensions["audit_store"]


def _history_service():
    return current_app.extensions["history_service"]


@api.get("/health")
def health():
    return jsonify(status="ok")


@api.get("/hello")
def hello():
    return jsonify(message="Hello from Flask")


@api.get("/events")
def list_events():
    """Environmental_Assurance_Spec.md Section 24: bbox / since / status filters, `{ events: [...] }`."""
    try:
        bbox = parse_bbox(request.args.get("bbox"))
        since = parse_since(request.args.get("since"))
        status = parse_status(request.args.get("status"))
    except FilterError as exc:
        # A bad filter is the caller's mistake; say which one and how, rather
        # than returning an empty list that reads as "no fires here".
        return jsonify(error=str(exc)), 400

    return jsonify(events=filter_events(load_events(), bbox=bbox, since=since, status=status))


@api.get("/events/<event_id>")
def get_event(event_id: str):
    event = find_event(event_id)
    if event is None:
        return jsonify(error=f"No event with id {event_id}"), 404
    return jsonify(event)


@api.post("/audits")
def create_audit():
    """Create the private, anonymised audit scope consumed by history build."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="request body must be a JSON object"), 400
    try:
        review_start = _parse_audit_date(
            payload.get("reviewStart", payload.get("review_start")), "reviewStart"
        )
        review_end = _parse_audit_date(
            payload.get("reviewEnd", payload.get("review_end")), "reviewEnd"
        )
        if review_start > review_end:
            raise HistoryInputError("reviewStart must not be after reviewEnd")
        raw_boundary = payload.get("boundary", payload.get("geometry"))
        geometry = normalize_geometry(raw_boundary)
        buffer_km = float(payload.get("contextBufferKm", payload.get("context_buffer_km", 25)))
        if not math.isfinite(buffer_km) or buffer_km < 0:
            raise HistoryInputError("contextBufferKm must be finite and non-negative")
    except (HistoryInputError, TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400

    audit = Audit(
        audit_id=f"AUD-{uuid4().hex[:12]}",
        review_start=review_start,
        review_end=review_end,
        geometry=geometry,
        context_buffer_km=buffer_km,
    )
    _audit_store().add(audit)
    return jsonify(audit=audit.to_dict(), auditId=audit.audit_id), 201


def _parse_audit_date(raw: object, field: str) -> str:
    if not isinstance(raw, str):
        raise HistoryInputError(f"{field} must be an ISO 8601 date")
    try:
        return datetime.fromisoformat(raw).date().isoformat()
    except ValueError:
        raise HistoryInputError(f"{field} must be an ISO 8601 date") from None


@api.post("/audits/<audit_id>/history/build")
def build_history(audit_id: str):
    audit = _audit_store().get(audit_id)
    if audit is None:
        return jsonify(error=f"No audit with id {audit_id}"), 404
    try:
        history = _history_service().build(audit)
    except HistoryInputError as exc:
        return jsonify(error=str(exc)), 400
    except HistoryDependencyError as exc:
        current_app.logger.exception("history pipeline dependencies unavailable")
        return jsonify(error=str(exc)), 503
    except Exception as exc:
        current_app.logger.exception("history build failed for %s", audit_id)
        return jsonify(error=f"history build failed: {exc}"), 502
    return jsonify(history)


@api.get("/audits/<audit_id>/events")
def list_audit_events(audit_id: str):
    audit = _audit_store().get(audit_id)
    if audit is None:
        return jsonify(error=f"No audit with id {audit_id}"), 404
    if audit.history is None:
        return jsonify(error="Build Fire History before listing audit events"), 409
    return jsonify(audit.history)


@api.get("/audits/<audit_id>/events/<event_id>")
def get_audit_event(audit_id: str, event_id: str):
    audit = _audit_store().get(audit_id)
    if audit is None:
        return jsonify(error=f"No audit with id {audit_id}"), 404
    if audit.history is None:
        return jsonify(error="Build Fire History before listing audit events"), 409
    event = next((item for item in audit.history["events"] if item["id"] == event_id), None)
    if event is None:
        return jsonify(error=f"No event with id {event_id}"), 404
    return jsonify(event)
