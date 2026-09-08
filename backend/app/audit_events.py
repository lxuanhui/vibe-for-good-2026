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

# Persistence is intentionally process-local until the repository chooses a
# durable metadata store. The pack is engagement-scoped and contains only
# event IDs plus human review fields; report assembly always re-reads the
# current structured evidence artifact.
AUDIT_PACKS: dict[str, dict[str, dict[str, Any]]] = {}


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
        distance = round(_distance_km(subject, candidate), 3)
        edge_evidence_id = f"GRAPH_{subject['eventId']}_{candidate['eventId']}_distance"
        edges.append({
            "sourceEventId": subject["eventId"],
            "targetEventId": candidate["eventId"],
            "state": "RELATED_POSSIBLE",
            "distanceKm": distance,
            "modelVersion": "fire-event-graph-v1",
            "supportingEvidenceIds": [edge_evidence_id],
            "contradictingEvidenceIds": [],
            "evidence": [{
                "evidence_id": edge_evidence_id,
                "category": "graph",
                "type": "candidate_edge_distance",
                "observation": f"Candidate FireEvent relationship is {distance} km apart.",
                "source": "FireEventGraph deterministic neighbour gate",
                "time_window": f"{subject['firstDetection']} to {candidate['lastDetection']}",
                "value": {"distance_km": distance, "max_candidate_distance_km": 50},
                "quality": 1.0,
                "limitations": [
                    "A candidate edge is a relationship for review, not evidence of a shared cause or responsibility.",
                    "This current audit adapter exposes distance only; wind, peat-corridor and surface compatibility are not available in this artifact.",
                ],
                "algorithm_version": "fire-event-graph-v1",
                "raw_reference": f"{subject['eventId']}->{candidate['eventId']}",
            }],
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


def _evidence_object(
    evidence_id: str,
    category: str,
    evidence_type: str,
    observation: str,
    source: str,
    time_window: str,
    *,
    value: Any = None,
    quality: float | None = None,
    limitations: list[str] | None = None,
    algorithm_version: str | None = None,
    raw_reference: str | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "category": category,
        "type": evidence_type,
        "observation": observation,
        "source": source,
        "time_window": time_window,
        "value": value,
        "quality": quality,
        "limitations": limitations or [],
        "algorithm_version": algorithm_version,
        "raw_reference": raw_reference,
    }


def evidence_for_event(audit_id: str, event_id: str) -> dict[str, Any] | None:
    """Return the drawer contract from the current audit artifact.

    The committed demo artifact contains FIRMS clustering and Stage-1 output,
    not optional enrichment runs. Missing sources are returned as explicit
    availability records so the UI cannot mistake an absent result for a
    negative environmental finding.
    """
    event = find_event(audit_id, event_id)
    audit = get_audit(audit_id)
    if event is None or audit is None:
        return None

    start = event["firstDetection"]
    end = event["lastDetection"]
    window = f"{start} to {end}"
    scope = audit["scope"]
    session = get_audit_session(audit_id)
    scope_context = {**scope, **(session or {})}
    private_geometry = get_scope_geometry(audit_id)
    if private_geometry is not None:
        scope_context["geometry"] = private_geometry
    relation = _relation(event, scope_context)
    observed = [
        _evidence_object(
            f"OBSERVED_{event_id}_chronology", "thermal", "chronology",
            f"The FireEvent spans {start} to {end}.", "NASA FIRMS",
            window, value={"first_detection": start, "last_detection": end},
            quality=0.82, limitations=["FIRMS acquisition times describe detections, not ignition time."],
            raw_reference=event_id,
        ),
        _evidence_object(
            f"OBSERVED_{event_id}_observations", "thermal", "observation_count",
            f"The cluster contains {event['observationCount']} linked FIRMS observations.", "NASA FIRMS",
            window, value=event["observationCount"], quality=0.82,
            limitations=["Raw observations are clustered into one FireEvent; they are not independent fires."],
            raw_reference=event_id,
        ),
        _evidence_object(
            f"OBSERVED_{event_id}_frp", "thermal", "frp_summary",
            f"FRP ranges from the available summary mean of {event['meanFrp'] or 0:.2f} MW to a maximum of {event['maxFrp'] or 0:.2f} MW.", "NASA FIRMS",
            window, value={"mean_mw": event["meanFrp"], "max_mw": event["maxFrp"]}, quality=0.82,
            limitations=["FRP is a thermal detection measurement, not burned area or fire intensity at ground level."],
            raw_reference=event_id,
        ),
    ]
    derived = list(event.get("triageDetail", {}).get("evidence", []))
    derived.append(_evidence_object(
        f"DERIVED_SCOPE_{event_id}_relation", "scope", "scope_relation",
        f"The event centroid is classified as {relation} against the private audit scope.", "Audit scope geometry / FireEvent centroid",
        window, value=relation, quality=1.0,
        limitations=["Geographic intersection is context, not responsibility or attribution."],
        algorithm_version="audit-scope-relation-v1", raw_reference=event_id,
    ))

    complexity_names = [
        "duration", "observation_count", "spatial_extent", "centroid_movement",
        "directional_consistency", "wind_alignment", "frp_variability",
        "distinct_thermal_lobes", "peat_overlap", "nearby_event_count",
        "historical_recurrence", "unexplained_detections", "surface_propagation_mismatch",
    ]
    priority_names = [
        "event_validity", "environmental_significance", "event_complexity",
        "evidence_inconsistency", "unresolved_event_relationships", "evidence_sufficiency",
        "peat_involvement", "land_change_indicators", "propagation_uncertainty",
    ]
    unavailable = "This current audit artifact has no completed enrichment output for this component."
    for name in complexity_names:
        derived.append(_evidence_object(
            f"DERIVED_COMPLEXITY_{event_id}_{name}", "fire-complexity", name,
            f"Not evaluated: {unavailable}", "Fire Complexity pipeline",
            window, value=None, quality=0.0,
            limitations=[unavailable, "Missing evidence is not treated as low complexity."],
            algorithm_version="fire-complexity-evidence-v1", raw_reference=event_id,
        ))
    for name in priority_names:
        derived.append(_evidence_object(
            f"DERIVED_PRIORITY_{event_id}_{name}", "investigation-priority", name,
            f"Not evaluated: {unavailable}", "Investigation Priority pipeline",
            window, value=None, quality=0.0,
            limitations=[unavailable, "Priority is a review-routing aid, not culpability or responsibility."],
            algorithm_version="investigation-priority-v1", raw_reference=event_id,
        ))

    return {
        "auditId": audit_id,
        "event": event,
        "scopeRelation": relation,
        "observedEvidence": observed,
        "derivedEvidence": derived,
        "availability": [
            {"kind": "peat", "status": "unavailable", "reason": unavailable},
            {"kind": "weather", "status": "unavailable", "reason": unavailable},
            {"kind": "imagery", "status": "unavailable", "reason": "No imagery acquisition or scene-selection result is present for this audit artifact."},
        ],
        "evidenceSufficiency": {
            "value": "PARTIAL",
            "reason": "FIRMS observations and Stage-1 derivations are available; optional environmental enrichment is missing.",
            "algorithmVersion": "evidence-sufficiency-v1",
        },
        "provenance": {
            "source": source_provenance(),
            "algorithmVersions": ["stage1-rules-v1", "audit-scope-relation-v1", "fire-complexity-evidence-v1", "investigation-priority-v1"],
        },
    }


def _pack(audit_id: str) -> dict[str, dict[str, Any]] | None:
    if get_audit(audit_id) is None:
        return None
    return AUDIT_PACKS.setdefault(audit_id, {})


def add_to_pack(audit_id: str, event_id: str, note: str = "", disposition: str = "") -> dict[str, Any] | None:
    pack = _pack(audit_id)
    if pack is None or find_event(audit_id, event_id) is None:
        return None
    existing = pack.get(event_id, {})
    pack[event_id] = {
        "eventId": event_id,
        "note": note.strip()[:2000],
        "disposition": disposition.strip()[:80],
        "addedAt": existing.get("addedAt", datetime.now(UTC).isoformat()),
    }
    return pack[event_id]


def remove_from_pack(audit_id: str, event_id: str) -> bool | None:
    pack = _pack(audit_id)
    if pack is None:
        return None
    pack.pop(event_id, None)
    return True


def _report_counts(audit: dict[str, Any], entries: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, int]:
    sufficiency = [item["evidenceSufficiency"]["value"] for item in evidence]
    total = len(audit["events"])
    return {
        "identified": total,
        "screened": total,
        "reviewed": len(entries),
        "selected": len(entries),
        "verify": sum(1 for item in entries if item.get("disposition", "").upper() == "VERIFY"),
        "insufficient": sum(1 for value in sufficiency if value == "INSUFFICIENT"),
    }


def audit_report(audit_id: str) -> dict[str, Any] | None:
    audit = get_audit(audit_id)
    pack = _pack(audit_id)
    if audit is None or pack is None:
        return None
    entries = list(pack.values())
    selected = [find_event(audit_id, entry["eventId"]) for entry in entries]
    selected = [event for event in selected if event is not None]
    evidence = [evidence_for_event(audit_id, event["eventId"]) for event in selected]
    evidence = [item for item in evidence if item is not None]
    graph = investigation_map(audit_id, [event["eventId"] for event in selected]) if selected else {
        "auditId": audit_id, "selectedEventIds": [], "scope": audit["scope"], "nodes": [], "edges": [],
        "layers": {"selectedRawObservations": False, "fireEvents": True, "graph": True},
    }
    source = source_provenance()
    scope = audit["scope"]
    return {
        "auditId": audit_id,
        "auditScope": {"reviewStart": scope["reviewStart"], "reviewEnd": scope["reviewEnd"], "scope": scope},
        "sourceMethodSummary": {
            "observed": "NASA FIRMS thermal detections clustered into FireEvents",
            "derived": "Stage-1 deterministic triage and audit-scope relation",
            "ai": "No AI analysis is available in the current FIRMS audit artifact.",
            "source": source,
        },
        "compressionSummary": scope.get("compression", {}),
        "counts": _report_counts(audit, entries, evidence),
        "selectedFireEvents": [{"event": event, "review": pack[event["eventId"]], "evidence": item} for event, item in zip(selected, evidence)],
        "maps": {"selectedEventIds": [event["eventId"] for event in selected], "layers": graph["layers"]},
        "chronology": sorted([{"eventId": event["eventId"], "firstDetection": event["firstDetection"], "lastDetection": event["lastDetection"]} for event in selected], key=lambda item: item["firstDetection"]),
        "deterministicEvidence": [{"eventId": item["event"]["eventId"], "observed": item["observedEvidence"], "derived": item["derivedEvidence"]} for item in evidence],
        "graphRelationships": graph["edges"],
        "aiAnalysis": [],
        "unresolvedQuestions": [],
        "verificationRecommendations": [],
        "limitations": ["The current artifact contains FIRMS clustering and Stage-1 output only; peat, weather, imagery and adversarial analysis are unavailable.", "Selected events are evidence for human review, not conclusions about cause or responsibility."],
        "provenance": {"source": source, "algorithmVersions": sorted({version for item in evidence for version in item["provenance"]["algorithmVersions"]})},
        "humanNotes": [{"eventId": entry["eventId"], "note": entry["note"], "disposition": entry["disposition"]} for entry in entries],
        "disclaimer": "This report is an investigative-support product. It does not establish legal responsibility, intent, culpability, ownership liability, or criminal wrongdoing. Findings require human verification.",
    }
