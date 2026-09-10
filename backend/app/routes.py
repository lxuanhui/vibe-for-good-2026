import json
from time import perf_counter

from flask import Blueprint, current_app, jsonify, request

from app import analysis_jobs, audit_events, firms_live
from app.audits import (
    AuditValidationError,
    build_history,
    create_audit,
    set_demo_scope,
    set_point_scope,
    upload_scope,
)
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


@api.post("/audits/<audit_id>/scope/point")
def set_audit_point_scope(audit_id: str):
    """Scope from latitude, longitude and a radius in km, for an evaluator
    with no boundary file to hand (#87). Same session contract as an upload."""
    try:
        session = set_point_scope(audit_id, request.get_json(silent=True))
    except AuditValidationError as exc:
        return jsonify(error=str(exc)), 400
    if session is None:
        return jsonify(error=f"No audit with id {audit_id}"), 404
    return jsonify(session)


@api.post("/audits/<audit_id>/scope/demo")
def set_audit_demo_scope(audit_id: str):
    """The predefined, clearly labelled demo study area. Server-owned so the
    session records it as a demo scope, never as something the auditor uploaded."""
    session = set_demo_scope(audit_id)
    if session is None:
        return jsonify(error=f"No audit with id {audit_id}"), 404
    return jsonify(session)


@api.post("/audits/<audit_id>/history/build")
def build_audit_history(audit_id: str):
    started = perf_counter()
    try:
        result = build_history(audit_id)
        if result is None:
            return jsonify(error=f"No audit with id {audit_id}"), 404
    except AuditValidationError as exc:
        return jsonify(error=str(exc)), 409
    # The committed demo is a cached real reconstruction. Loading it here
    # makes the timing cover the same artifact readiness check as the demo.
    if not audit_events.cached_reconstruction_ready(audit_id):
        return jsonify(error=f"No cached reconstruction for audit {audit_id}"), 503
    result["duration_ms"] = round((perf_counter() - started) * 1000, 2)
    result["dataset_mode"] = "cached_real_historical_dataset"
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


@api.get("/audits/<audit_id>/events")
def list_audit_events(audit_id: str):
    """Reconstructed history for one audit scope (Environmental_Assurance_Spec.md Section 24)."""
    status = audit_events.history_status(audit_id)
    if status != "AVAILABLE":
        return jsonify(error=f"No reconstructed history for audit {audit_id}", status=status), 404

    try:
        bbox = audit_events.parse_bbox(request.args.get("bbox"))
        since = audit_events.parse_timestamp(request.args.get("since"), "since")
        until = audit_events.parse_timestamp(request.args.get("until"), "until")
        state = audit_events.parse_state(request.args.get("state"))
        limit, offset = audit_events.parse_paging(
            request.args.get("limit"), request.args.get("offset")
        )
    except audit_events.FilterError as exc:
        return jsonify(error=str(exc)), 400

    audit = audit_events.get_audit(audit_id)
    matched = audit_events.filter_events(
        audit["events"], bbox=bbox, since=since, until=until, state=state
    )
    return jsonify(
        auditId=audit_id,
        scope=audit["scope"],
        source=audit_events.source_provenance(),
        progression=audit_events.progression(audit_id),
        total=len(matched),
        limit=limit,
        offset=offset,
        events=matched[offset : offset + limit],
    )


@api.get("/audits/<audit_id>/events/<event_id>")
def get_audit_event(audit_id: str, event_id: str):
    event = audit_events.find_event(audit_id, event_id)
    if event is None:
        status = audit_events.history_status(audit_id)
        if status != "AVAILABLE":
            return jsonify(error=f"No reconstructed history for audit {audit_id}", status=status), 404
        return jsonify(error=f"No event with id {event_id} in audit {audit_id}"), 404
    return jsonify(event)


@api.get("/audits/<audit_id>/events/<event_id>/evidence")
def get_audit_event_evidence(audit_id: str, event_id: str):
    evidence = audit_events.evidence_for_event(audit_id, event_id)
    if evidence is None:
        status = audit_events.history_status(audit_id)
        if status == "PENDING_RECONSTRUCTION":
            return jsonify(status="processing", retryAfterSeconds=1), 202
        return jsonify(error=f"No evidence for event {event_id} in audit {audit_id}", status=status), 404
    return jsonify(evidence)


@api.get("/audits/<audit_id>/events/<event_id>/investigation")
def get_audit_event_investigation(audit_id: str, event_id: str):
    """First-drawer bundle: evidence and its one-event relationship graph.

    It replaces the fragile pair of dependent requests made on every map
    click. Optional imagery/weather remain fields of the evidence response,
    so a failure in one does not blank the event summary.
    """
    evidence = audit_events.evidence_for_event(audit_id, event_id)
    if evidence is None:
        status = audit_events.history_status(audit_id)
        if status == "PENDING_RECONSTRUCTION":
            return jsonify(status="processing", retryAfterSeconds=1), 202
        return jsonify(error=f"No evidence for event {event_id} in audit {audit_id}", status=status), 404
    return jsonify(
        event=evidence,
        graph=audit_events.investigation_map(audit_id, [event_id]),
        analysis=audit_events.analysis_for_event(audit_id, event_id),
    )


@api.route("/audits/<audit_id>/events/<event_id>/analyse", methods=["GET", "POST"])
def analyse_audit_event(audit_id: str, event_id: str):
    """Start, or poll, bounded Investigator/Skeptic analysis for one event.

    A two-round assessment outlives API Gateway's 30s response cap however
    the rounds are arranged, so POST records a job and GET reports it (#143).
    Two rules the shape depends on: an HTTP status describes the *request*
    while `jobStatus` describes the *work*, so a provider failure is a
    truthful FAILED job rather than a 5xx on a request that was valid; and
    GET only reads, so polling never re-triggers work or spends tokens.
    """
    if audit_events.find_event(audit_id, event_id) is None:
        status = audit_events.history_status(audit_id)
        if status != "AVAILABLE":
            return jsonify(error=f"No reconstructed history for audit {audit_id}", status=status), 404
        return jsonify(error=f"No event with id {event_id} in audit {audit_id}"), 404

    if request.method == "GET":
        return jsonify(analysis_jobs.read(audit_id, event_id))

    job = analysis_jobs.dispatch(
        audit_id, event_id, provider=current_app.config.get("ANALYSIS_PROVIDER")
    )
    if job is None:
        status = audit_events.history_status(audit_id)
        return jsonify(error=f"No evidence for event {event_id} in audit {audit_id}", status=status), 404
    # 202 while the work is still owed; 200 once the record already holds the
    # outcome, which is what the local inline path returns.
    return jsonify(job), 202 if job["jobStatus"] == analysis_jobs.RUNNING else 200


@api.get("/audits/<audit_id>/graph")
def get_audit_graph(audit_id: str):
    raw_ids = request.args.get("event_ids", "")
    event_ids = [event_id for event_id in raw_ids.split(",") if event_id]
    if not event_ids:
        return jsonify(error="event_ids must contain at least one FireEvent ID"), 400
    result = audit_events.investigation_map(audit_id, event_ids)
    if result is None:
        if audit_events.history_status(audit_id) == "PENDING_RECONSTRUCTION":
            return jsonify(status="processing", retryAfterSeconds=1), 202
        return jsonify(error=f"No reconstructed history or event selection for audit {audit_id}"), 404
    return jsonify(result)


@api.post("/audits/<audit_id>/events/<event_id>/add-to-pack")
def add_audit_pack_event(audit_id: str, event_id: str):
    payload = request.get_json(silent=True) or {}
    result = audit_events.add_to_pack(
        audit_id, event_id, str(payload.get("note", "")), str(payload.get("disposition", ""))
    )
    if result is None:
        return jsonify(error=f"No event with id {event_id} in audit {audit_id}"), 404
    return jsonify(result)


@api.delete("/audits/<audit_id>/events/<event_id>/add-to-pack")
def remove_audit_pack_event(audit_id: str, event_id: str):
    result = audit_events.remove_from_pack(audit_id, event_id)
    if result is None:
        return jsonify(error=f"No audit with id {audit_id}"), 404
    return jsonify(removed=event_id)


@api.route("/audits/<audit_id>/report", methods=["GET", "POST"])
def audit_report_view(audit_id: str):
    report = audit_events.audit_report(audit_id)
    if report is None:
        return jsonify(error=f"No reconstructed history for audit {audit_id}"), 404
    return jsonify(report)


@api.get("/firms/live")
def get_live_firms_detections():
    """Regional live thermal context for the landing map.

    Deliberately flat rather than audit-scoped: it is what the console shows
    *before* an audit scope exists, so there is no audit to scope it to.

    503 rather than an empty collection, because an empty regional layer is
    indistinguishable from "no fires are burning" -- a fabricated observation.
    The console renders its own unavailable state from the failure.
    """
    try:
        payload = firms_live.live_detections()
    except firms_live.FirmsUnavailable as exc:
        current_app.logger.warning("Live FIRMS layer unavailable: %s", exc)
        return jsonify(status="unavailable", reason=str(exc)), 503
    response = jsonify(payload)
    # The server already caches upstream for the same window; saying so lets a
    # reloading browser skip the request entirely.
    response.headers["Cache-Control"] = f"public, max-age={firms_live.CACHE_SECONDS}"
    return response
