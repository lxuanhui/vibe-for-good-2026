"""Bake real wind-oriented surface-fire spread envelopes onto the demo
scope's candidate-linked FireEvent pairs.

Run once after ``enrich_audit_events.py --finalize`` has committed real
per-event wind evidence:
``python -m data_pipeline.enrich_fire_spread_audit_events --finalize``.

This does not implement any new fire-spread math. It reuses
``build_fire_event_graph``/``surface_fire.py`` exactly as they already are
(both tested, both decision-logged 2026-09-08) and only adapts the committed
weather evidence into the shape those modules expect, then writes their
output -- plus the envelope polygon needed to draw it on a map, which the
graph module computes and discards -- onto the *source* event's record in
the detail artifact next to its other derived evidence.

Scoped to the same 16 demo in-scope+buffer FireEvents ``enrich_audit_events``
fetched real historical wind for, not the full 3,610-event regional archive:
a candidate pair needs real wind on its source event to produce a real
envelope at all, and wind was only ever fetched for this scope.
"""

from __future__ import annotations

import argparse
import gzip
import json
from typing import Any

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.enrich_audit_events import (
    AUDIT_ID,
    DETAIL_PATH,
    load_event_summaries,
)
from data_pipeline.graph.fire_event_graph import FireEventGraph, build_fire_event_graph
from data_pipeline.propagation.surface_fire import SurfaceFireEnvelope

# Matches build_fire_event_graph's own default -- not a new assumption.
CANDIDATE_DISTANCE_KM = 50.0

# The drawn envelope's maximum reach (see `_capped_dimensions`). A single
# candidate pair is never farther apart than CANDIDATE_DISTANCE_KM, but a
# scoped map can show a dozen-plus candidate edges from one selection at
# once (this demo's 16-event scope: up to ~14 per focused event) -- several
# overlapping envelopes at the full 50 km gate compound into solid coverage
# well before any one of them is individually implausible. 60% of the gate
# keeps shapes legible at this map's typical zoom without needing to know
# how many will render alongside it.
MAX_ENVELOPE_REACH_KM = CANDIDATE_DISTANCE_KM * 0.6


def _event_from_summary(row: dict[str, Any]) -> FireEvent:
    """Same field mapping as ``benchmark.automated_run._event_from_artifact``."""

    centroid = row["centroid"]
    return FireEvent(
        event_id=row["eventId"],
        observation_indices=[],
        first_detection=row["firstDetection"],
        last_detection=row["lastDetection"],
        duration_hours=row["durationHours"],
        observation_count=row["observationCount"],
        centroid=(centroid["lat"], centroid["lon"]),
        bbox=tuple(row["bbox"]),
        spatial_extent_km=row["spatialExtentKm"],
        max_frp=row["maxFrp"],
        mean_frp=row["meanFrp"],
        sensor_mix=row.get("sensorMix", []),
    )


def _current_window_wind(evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
    """This event's own-detection-window wind, shaped for
    ``fire_event_graph._wind_values`` (a ``{"windows": [...]}`` bundle).

    Deliberately ``speed_kmh``, not ``mean_wind_speed_ms``: Open-Meteo's
    default unit is already km/h (``enrich_audit_events.py`` never
    overrides ``wind_speed_unit``), and ``_wind_values`` multiplies
    ``mean_wind_speed_ms`` by 3.6 assuming m/s input -- the wrong key here
    would silently inflate every speed 3.6x.
    """

    direction = speed = None
    for item in evidence:
        if item.get("category") != "weather" or "_current_" not in item.get("evidence_id", ""):
            continue
        if item.get("type") == "wind_direction_10m":
            direction = item["value"]
        elif item.get("type") == "wind_speed_10m":
            value = item["value"]
            speed = value["mean"] if isinstance(value, dict) else value
    if direction is None:
        return None
    return {
        "windows": [
            {
                "window_name": "event_duration",
                "dominant_wind_direction_deg": direction,
                "speed_kmh": speed,
            }
        ]
    }


def build_graph(events_summary: list[dict[str, Any]], detail_audit: dict[str, Any]) -> FireEventGraph:
    events = [_event_from_summary(row) for row in events_summary]
    weather_by_event: dict[str, Any] = {}
    for row in events_summary:
        record = detail_audit.get(row["eventId"], {})
        wind = _current_window_wind(record.get("evidence", []))
        if wind is not None:
            weather_by_event[row["eventId"]] = wind
    return build_fire_event_graph(
        events, weather_by_event=weather_by_event, candidate_distance_km=CANDIDATE_DISTANCE_KM
    )


def _capped_dimensions(semi_major: float, semi_minor: float, center_offset: float) -> tuple[float, float, float]:
    """Cap the *drawn* envelope's reach at the same candidate-distance gate
    that decided which pairs get an edge at all.

    `compare_event_progression` sizes the envelope from elapsed time between
    the source event's own first and last detection to the target's, which
    for a long-duration source event can be far larger than the gap
    (`elapsed_time_hours` on the edge) between them -- real cases in the demo
    scope reach 300+ km. No candidate this feature considers is ever farther
    than `CANDIDATE_DISTANCE_KM` apart, so a drawn reach beyond that adds no
    discriminating information and only blankets a scoped map (tens of km
    across) in solid fill. All three dimensions are linear in elapsed_hours,
    so scaling them by one factor is exactly what capping elapsed_hours and
    re-projecting would produce -- a presentation cap, not a different
    envelope; the edge's `state`/compatibility classification is untouched.
    """

    max_reach = abs(center_offset) + semi_major
    if max_reach <= MAX_ENVELOPE_REACH_KM:
        return semi_major, semi_minor, center_offset
    scale = MAX_ENVELOPE_REACH_KM / max_reach
    return semi_major * scale, semi_minor * scale, center_offset * scale


def _envelope_dict(features: Any, source_centroid: tuple[float, float]) -> dict[str, Any] | None:
    """Reconstruct the envelope geometry the graph module discarded and
    render it as a polygon. Exact, not approximate: head/back/flank are
    recovered algebraically from semi_major/center_offset/semi_minor
    (``semi_major = (head + back) / 2``, ``center_offset = (head - back) /
    2`` invert to ``head = semi_major + center_offset``, ``back = semi_major
    - center_offset``; ``flank`` is ``semi_minor`` directly) -- these three
    aren't used by ``to_polygon()`` itself, they're just required fields on
    the frozen dataclass.
    """

    if (
        features.surface_envelope_semi_major_km is None
        or features.surface_envelope_semi_minor_km is None
        or features.surface_envelope_center_offset_km is None
        or features.surface_envelope_orientation_deg is None
    ):
        return None
    semi_major, semi_minor, center_offset = _capped_dimensions(
        features.surface_envelope_semi_major_km,
        features.surface_envelope_semi_minor_km,
        features.surface_envelope_center_offset_km,
    )
    envelope = SurfaceFireEnvelope(
        origin=source_centroid,
        elapsed_hours=features.elapsed_time_hours,
        orientation_deg=features.surface_envelope_orientation_deg,
        head_distance_km=semi_major + center_offset,
        back_distance_km=semi_major - center_offset,
        flank_distance_km=semi_minor,
        center_offset_km=center_offset,
        semi_major_km=semi_major,
        semi_minor_km=semi_minor,
    )
    return {
        "polygon": envelope.to_polygon(),
        "orientationDeg": envelope.orientation_deg,
        "semiMajorKm": semi_major,
        "semiMinorKm": semi_minor,
    }


def edges_by_source(graph: FireEventGraph) -> dict[str, list[dict[str, Any]]]:
    centroid_by_id = {node.event_id: node.centroid for node in graph.nodes}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for edge in graph.edges:
        edge_dict = edge.to_dict()
        edge_dict["envelope"] = _envelope_dict(edge.features, centroid_by_id[edge.source_event_id])
        grouped.setdefault(edge.source_event_id, []).append(edge_dict)
    return grouped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--finalize", action="store_true", help="write the enriched committed artifact")
    args = parser.parse_args()

    events_summary = load_event_summaries()
    with gzip.open(DETAIL_PATH, "rt", encoding="utf-8") as handle:
        detail = json.load(handle)
    detail_audit = detail[AUDIT_ID]

    graph = build_graph(events_summary, detail_audit)
    grouped = edges_by_source(graph)
    with_envelope = sum(1 for edges in grouped.values() for e in edges if e["envelope"] is not None)
    print(
        f"{len(events_summary)} events, {len(graph.edges)} candidate edge(s), "
        f"{with_envelope} with a real wind-oriented envelope."
    )

    changed = 0
    for row in events_summary:
        event_id = row["eventId"]
        edges = grouped.get(event_id, [])
        record = detail_audit[event_id]
        record["fireSpreadEdges"] = edges
        changed += 1

    if args.finalize:
        with gzip.open(DETAIL_PATH, "wt", encoding="utf-8") as handle:
            json.dump(detail, handle, separators=(",", ":"), sort_keys=True)
        print(f"Finalized fireSpreadEdges onto {changed} event record(s) in {DETAIL_PATH}")
    else:
        print("Dry run only; pass --finalize to write.")


if __name__ == "__main__":
    main()
