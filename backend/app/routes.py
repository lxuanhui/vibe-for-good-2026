from flask import Blueprint, jsonify, request

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
