import json

from flask import Blueprint, jsonify, request

from app.audits import AuditValidationError, build_history, create_audit, upload_scope
from app.events import (
    FilterError,
    filter_events,
    find_event,
    load_events,
    parse_bbox,
    parse_since,
    parse_status,
)

api = Blueprint("api", __name__)


@api.post("/audits")
def create_audit_review():
    try:
        session = create_audit(request.get_json(silent=True))
    except AuditValidationError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(session), 201


@api.post("/audits/<audit_id>/scope/upload")
def upload_audit_scope(audit_id: str):
    uploaded = request.files.get("file")
    try:
        if uploaded is not None:
            try:
                geojson = json.load(uploaded.stream)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return jsonify(error="scope file must contain valid JSON GeoJSON"), 400
        else:
            geojson = request.get_json(silent=True)
        session = upload_scope(audit_id, geojson)
        if session is None:
            return jsonify(error=f"No audit with id {audit_id}"), 404
    except AuditValidationError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(session)


@api.post("/audits/<audit_id>/history/build")
def build_audit_history(audit_id: str):
    try:
        result = build_history(audit_id)
        if result is None:
            return jsonify(error=f"No audit with id {audit_id}"), 404
    except AuditValidationError as exc:
        return jsonify(error=str(exc)), 409
    # #57 owns reconstruction; this records a validated handoff only.
    return jsonify(result), 202


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
