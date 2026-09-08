"""Audit-scoped FireEvent history built from the deterministic data pipeline.

This module is deliberately an adapter, not a second implementation of any
environmental model.  It turns the pipeline's dataclasses and EvidenceObjects
into the stable JSON shape used by the Flask API and keeps the small in-memory
demo store appropriate for the current Lambda/MVP architecture.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Local development runs from `backend/`, while Lambda places this sibling
# package beside `app/`. Add the repository/package root at the adapter seam so
# both execution paths import the same pipeline modules.
PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if not (PIPELINE_ROOT / "data_pipeline").exists():
    # The Lambda bundle flattens `app/` and `data_pipeline/` under its task
    # root, unlike the repository's `backend/app/` local-dev layout.
    PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

PIPELINE_PACKAGE_ROOT = PIPELINE_ROOT / "data_pipeline"
GOLDEN_ROOT = PIPELINE_PACKAGE_ROOT / "golden"
CACHE_DATASET_LABEL = "NASA FIRMS 2019 haze-window observations (frozen real export)"
CACHE_SOURCE_REFERENCE = "data_pipeline/golden/*/observations.csv"

ScopeRelation = str


class HistoryInputError(ValueError):
    """A malformed audit or scope request that should become HTTP 400."""


class HistoryDependencyError(RuntimeError):
    """The optional scientific runtime is unavailable for a build request."""


_PIPELINE_READY = False

# These symbols are populated by `_ensure_pipeline`. Defining them here keeps
# type checking and static analysis honest without importing NumPy/Pandas at
# Flask module import time.
np: Any = None
pd: Any = None
FireEvent: Any = Any
cluster_events: Any = None
compute_fire_complexity: Any = None
PeatRaster: Any = Any
compute_peat_context: Any = None
peat_evidence: Any = None
WeatherEvidenceBundle: Any = Any
compute_weather_windows: Any = None
weather_evidence: Any = None
FireEventGraph: Any = Any
build_fire_event_graph: Any = None
compute_investigation_priority: Any = None
compare_event_progression: Any = None
fetch_historical_range: Any = None
Stage1State: Any = Any
summarize_triage: Any = None
triage_events: Any = None


def _ensure_pipeline() -> None:
    """Load scientific dependencies only when the history pipeline is used.

    The legacy event API and Flask health checks do not need NumPy/Pandas. A
    lazy seam keeps those routes importable in a minimal local environment,
    while the deployed Lambda still installs the complete backend dependency
    set before a real history build is accepted.
    """
    global _PIPELINE_READY
    if _PIPELINE_READY:
        return
    try:
        import numpy as np_module
        import pandas as pd_module
        from data_pipeline.clustering.firms_clustering import (
            FireEvent as fire_event_type,
        )
        from data_pipeline.clustering.firms_clustering import (
            cluster_events as cluster_events_fn,
        )
        from data_pipeline.complexity.fire_complexity import (
            compute_fire_complexity as compute_fire_complexity_fn,
        )
        from data_pipeline.enrichment.peat_context import (
            PeatRaster as peat_raster_type,
        )
        from data_pipeline.enrichment.peat_context import (
            compute_peat_context as compute_peat_context_fn,
        )
        from data_pipeline.enrichment.peat_context import (
            to_evidence_objects as peat_evidence_fn,
        )
        from data_pipeline.enrichment.weather_enrichment import (
            WeatherEvidenceBundle as weather_bundle_type,
        )
        from data_pipeline.enrichment.weather_enrichment import (
            compute_weather_windows as compute_weather_windows_fn,
        )
        from data_pipeline.enrichment.weather_enrichment import (
            to_evidence_objects as weather_evidence_fn,
        )
        from data_pipeline.graph.fire_event_graph import (
            FireEventGraph as fire_event_graph_type,
        )
        from data_pipeline.graph.fire_event_graph import (
            build_fire_event_graph as build_fire_event_graph_fn,
        )
        from data_pipeline.priority.investigation_priority import (
            compute_investigation_priority as compute_investigation_priority_fn,
        )
        from data_pipeline.propagation.surface_fire import (
            compare_event_progression as compare_event_progression_fn,
        )
        from data_pipeline.sources.nasa_firms_backfill import (
            fetch_historical_range as fetch_historical_range_fn,
        )
        from data_pipeline.triage.stage1 import (
            Stage1State as stage1_state_type,
        )
        from data_pipeline.triage.stage1 import (
            summarize_triage as summarize_triage_fn,
        )
        from data_pipeline.triage.stage1 import (
            triage_events as triage_events_fn,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise HistoryDependencyError(
            "Build Fire History requires the data_pipeline runtime dependencies "
            "(install backend dependencies, including numpy and pandas)"
        ) from exc

    globals().update(
        {
            "np": np_module,
            "pd": pd_module,
            "FireEvent": fire_event_type,
            "cluster_events": cluster_events_fn,
            "compute_fire_complexity": compute_fire_complexity_fn,
            "PeatRaster": peat_raster_type,
            "compute_peat_context": compute_peat_context_fn,
            "peat_evidence": peat_evidence_fn,
            "WeatherEvidenceBundle": weather_bundle_type,
            "compute_weather_windows": compute_weather_windows_fn,
            "weather_evidence": weather_evidence_fn,
            "FireEventGraph": fire_event_graph_type,
            "build_fire_event_graph": build_fire_event_graph_fn,
            "compute_investigation_priority": compute_investigation_priority_fn,
            "compare_event_progression": compare_event_progression_fn,
            "fetch_historical_range": fetch_historical_range_fn,
            "Stage1State": stage1_state_type,
            "summarize_triage": summarize_triage_fn,
            "triage_events": triage_events_fn,
        }
    )
    _PIPELINE_READY = True


@dataclass
class Audit:
    audit_id: str
    review_start: str
    review_end: str
    geometry: dict[str, Any]
    context_buffer_km: float = 25.0
    history: dict[str, Any] | None = None

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return geometry_bbox(self.geometry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "auditId": self.audit_id,
            "reviewStart": self.review_start,
            "reviewEnd": self.review_end,
            "boundary": self.geometry,
            "bbox": list(self.bbox),
            "contextBufferKm": self.context_buffer_km,
        }


@dataclass
class AuditStore:
    audits: dict[str, Audit] = field(default_factory=dict)

    def add(self, audit: Audit) -> None:
        self.audits[audit.audit_id] = audit

    def get(self, audit_id: str) -> Audit | None:
        return self.audits.get(audit_id)


def _number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HistoryInputError(f"{name} must be a number") from None
    if not math.isfinite(number):
        raise HistoryInputError(f"{name} must be finite")
    return number


def _ring(raw: Any) -> list[tuple[float, float]]:
    if not isinstance(raw, list) or len(raw) < 4:
        raise HistoryInputError("Polygon rings need at least four coordinate pairs")
    points: list[tuple[float, float]] = []
    for point in raw:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise HistoryInputError("boundary coordinates must be [longitude, latitude]")
        lon, lat = _number(point[0], "longitude"), _number(point[1], "latitude")
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise HistoryInputError("boundary coordinates are outside valid ranges")
        points.append((lon, lat))
    if points[0] != points[-1]:
        points.append(points[0])
    return points


def normalize_geometry(raw: Any) -> dict[str, Any]:
    """Accept a GeoJSON Polygon/MultiPolygon or Feature wrapper."""
    if not isinstance(raw, dict):
        raise HistoryInputError("boundary must be a GeoJSON Polygon or MultiPolygon")
    if raw.get("type") == "Feature":
        raw = raw.get("geometry")
    if not isinstance(raw, dict) or raw.get("type") not in {"Polygon", "MultiPolygon"}:
        raise HistoryInputError("boundary must be a GeoJSON Polygon or MultiPolygon")
    coordinates = raw.get("coordinates")
    if raw["type"] == "Polygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise HistoryInputError("Polygon boundary must contain coordinates")
        normalized = [[list(point) for point in _ring(ring)] for ring in coordinates]
    else:
        if not isinstance(coordinates, list) or not coordinates:
            raise HistoryInputError("MultiPolygon boundary must contain coordinates")
        normalized = [
            [[list(point) for point in _ring(ring)] for ring in polygon]
            for polygon in coordinates
        ]
    return {"type": raw["type"], "coordinates": normalized}


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    points: list[tuple[float, float]] = []
    coordinates = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        rings = coordinates
    else:
        rings = [ring for polygon in coordinates for ring in polygon]
    for ring in rings:
        points.extend((float(point[0]), float(point[1])) for point in ring)
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _polygons(geometry: dict[str, Any]) -> list[list[list[tuple[float, float]]]]:
    coordinates = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        return [[[(float(point[0]), float(point[1])) for point in ring] for ring in coordinates]]
    return [
        [[(float(point[0]), float(point[1])) for point in ring] for ring in polygon]
        for polygon in coordinates
    ]


def _point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for first, second in itertools.pairwise(ring):
        x1, y1 = first
        x2, y2 = second
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
    return inside


def _point_in_geometry(point: tuple[float, float], geometry: dict[str, Any]) -> bool:
    for polygon in _polygons(geometry):
        if _point_in_ring(point, polygon[0]) and not any(
            _point_in_ring(point, hole) for hole in polygon[1:]
        ):
            return True
    return False


def _distance_to_segment_km(
    point: tuple[float, float],
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    """Local equirectangular distance; sufficient for small audit boundaries."""
    mean_lat = math.radians((point[1] + first[1] + second[1]) / 3)
    scale_x = 6371.0088 * math.cos(mean_lat) * math.pi / 180
    scale_y = 6371.0088 * math.pi / 180
    px, py = point[0] * scale_x, point[1] * scale_y
    ax, ay = first[0] * scale_x, first[1] * scale_y
    bx, by = second[0] * scale_x, second[1] * scale_y
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    ratio = (
        0.0
        if length_sq == 0
        else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    )
    return math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy))


def _distance_to_boundary_km(point: tuple[float, float], geometry: dict[str, Any]) -> float:
    return min(
        _distance_to_segment_km(point, first, second)
        for polygon in _polygons(geometry)
        for ring in polygon
        for first, second in itertools.pairwise(ring)
    )


def _expand_bbox(
    bbox: tuple[float, float, float, float], buffer_km: float
) -> tuple[float, float, float, float]:
    west, south, east, north = bbox
    latitude = max(abs(south), abs(north), 0.1)
    lat_delta = buffer_km / 111.32
    lon_delta = buffer_km / (111.32 * max(math.cos(math.radians(latitude)), 0.1))
    return west - lon_delta, south - lat_delta, east + lon_delta, north + lat_delta


def _row_point(row: pd.Series) -> tuple[float, float]:
    return float(row["longitude"]), float(row["latitude"])


def _classify_event(
    event: FireEvent,
    observations: pd.DataFrame,
    geometry: dict[str, Any],
) -> tuple[ScopeRelation, float]:
    points = [_row_point(observations.iloc[index]) for index in event.observation_indices]
    inside = [_point_in_geometry(point, geometry) for point in points]
    boundary_distance = min(_distance_to_boundary_km(point, geometry) for point in points)
    if any(inside) and not all(inside):
        return "BOUNDARY_INTERSECTING", round(boundary_distance, 3)
    if any(inside):
        return "INSIDE_SCOPE", round(boundary_distance, 3)
    # The context buffer controls which observations are fetched; it is not
    # a scope relation. A cluster just outside the boundary remains external
    # context unless its own footprint reaches the boundary.
    if boundary_distance <= max(event.spatial_extent_km / 2.0, 0.0):
        return "BOUNDARY_INTERSECTING", round(boundary_distance, 3)
    return "EXTERNAL_CONTEXT", round(boundary_distance, 3)


def _observation_id(row: pd.Series) -> str:
    natural_key = "|".join(str(row.get(column, "")) for column in (
        "latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument"
    ))
    digest = hashlib.sha1(natural_key.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"FIRMS-{digest}"


def _load_cached_observations() -> pd.DataFrame:
    paths = sorted(GOLDEN_ROOT.glob("*/observations.csv"))
    if not paths:
        raise HistoryInputError("cached historical FIRMS dataset is unavailable")
    frames = [pd.read_csv(path) for path in paths]
    result = pd.concat(frames, ignore_index=True)
    dedup = [column for column in (
        "latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument"
    ) if column in result.columns]
    return result.drop_duplicates(subset=dedup).reset_index(drop=True)


def _load_cached_weather(event_id: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    for path in sorted(GOLDEN_ROOT.glob("*/weather/om_hourly.csv")):
        observations_path = path.parents[1] / "observations.csv"
        events, _ = cluster_events(pd.read_csv(observations_path))
        if any(event.event_id == event_id for event in events):
            power_path = path.with_name("power_daily.csv")
            hourly = pd.read_csv(path, parse_dates=["date"])
            daily = (
                pd.read_csv(power_path, index_col=0, parse_dates=True)
                if power_path.exists()
                else pd.DataFrame()
            )
            return hourly, daily
    return None


def _load_cached_raster(event_id: str) -> PeatRaster | None:
    for directory in sorted(GOLDEN_ROOT.glob("*/peat")):
        observations_path = directory.parents[0] / "observations.csv"
        events, _ = cluster_events(pd.read_csv(observations_path))
        if not any(event.event_id == event_id for event in events):
            continue
        array_path = directory / "raster_crop.npy"
        transform_path = directory / "raster_transform.json"
        if array_path.exists() and transform_path.exists():
            return PeatRaster(
                array=np.load(array_path),
                **json.loads(transform_path.read_text(encoding="utf-8")),
            )
    return None


def _wind_direction(bundle: Any) -> float | None:
    if bundle is None:
        return None
    for window in sorted(
        bundle.windows,
        key=lambda item: 0 if item.window_name == "event_duration" else 1,
    ):
        if window.dominant_wind_direction_deg is not None:
            return float(window.dominant_wind_direction_deg)
    return None


def _scope_events(
    events: list[FireEvent],
    observations: pd.DataFrame,
    geometry: dict[str, Any],
) -> dict[str, tuple[str, float]]:
    return {
        event.event_id: _classify_event(event, observations, geometry)
        for event in events
    }


def serialize_event(
    event: FireEvent,
    observations: pd.DataFrame,
    scope_id: str,
    relation: ScopeRelation,
    distance_km: float,
    triage: Any,
    peat: Any,
    complexity: Any,
    priority: Any,
    graph: FireEventGraph,
    weather_objects: list[dict[str, Any]],
) -> dict[str, Any]:
    event_observations = observations.iloc[event.observation_indices]
    evidence_objects = []
    if triage:
        evidence_objects.extend(triage.evidence)
    if peat:
        evidence_objects.extend(peat_evidence(peat))
    if complexity:
        evidence_objects.extend(complexity.to_evidence_objects())
    evidence_objects.extend(weather_objects)
    if priority:
        evidence_objects.extend(priority.evidence)
    evidence_by_id = {item["evidence_id"]: item for item in evidence_objects}
    graph_refs = []
    for edge in graph.edges_for(event.event_id):
        graph_refs.append({
            "reference": f"GRAPH:{edge.source_event_id}:{edge.target_event_id}",
            "sourceEventId": edge.source_event_id,
            "targetEventId": edge.target_event_id,
            "state": edge.state.value,
            "modelVersion": edge.model_version,
            "evidenceIds": sorted(
                set(edge.supporting_evidence_ids + edge.contradicting_evidence_ids)
            ),
        })
    evaluated_complexity = (
        sum(field.status.value == "EVALUATED" for field in complexity.fields)
        if complexity
        else 0
    )
    total_context = len(weather_objects) + (len(peat_evidence(peat)) if peat else 0)
    if total_context >= 4:
        sufficiency = "SUFFICIENT"
    elif total_context:
        sufficiency = "PARTIAL"
    else:
        sufficiency = "INSUFFICIENT"
    return {
        "id": event.event_id,
        "scopeId": scope_id,
        "firstDetected": event.first_detection,
        "lastDetected": event.last_detection,
        "durationHours": round(event.duration_hours, 3),
        "observationCount": event.observation_count,
        "centroid": [event.centroid[1], event.centroid[0]],
        "bbox": list(event.bbox),
        "lat": event.centroid[0],
        "lon": event.centroid[1],
        "scopeRelation": relation,
        "distanceToBoundaryKm": distance_km,
        "peakFrp": event.max_frp,
        "meanFrp": event.mean_frp,
        "frpSummary": {"peak": event.max_frp, "mean": event.mean_frp, "unit": "MW"},
        "peatFraction": peat.footprint_peat_fraction if peat else None,
        "complexity": {
            "evaluatedFieldCount": evaluated_complexity,
            "fieldCount": len(complexity.fields) if complexity else 0,
            "evidenceIds": [field.evidence_id for field in complexity.fields] if complexity else [],
            "algorithmVersion": complexity.algorithm_version if complexity else None,
        },
        "evidenceSufficiency": sufficiency,
        "investigationPriority": priority.priority.value if priority else "MEDIUM",
        "investigationPriorityScore": priority.score if priority else None,
        "reviewState": "UNREVIEWED",
        "stage1State": triage.state.value if triage else Stage1State.AMBIGUOUS.value,
        "constituentObservationIds": [
            _observation_id(row) for _, row in event_observations.iterrows()
        ],
        "evidenceIds": sorted(evidence_by_id),
        "evidence": [evidence_by_id[key] for key in sorted(evidence_by_id)],
        "graphReferences": graph_refs,
        "source": "NASA FIRMS",
    }


@dataclass
class HistoryService:
    """Build and retain one generated history per in-memory audit."""

    fetcher: Callable[..., Any] | None = None

    def build(self, audit: Audit) -> dict[str, Any]:
        _ensure_pipeline()
        query_bbox = _expand_bbox(audit.bbox, audit.context_buffer_km)
        source_mode = os.environ.get("HISTORY_SOURCE", "cached").lower()
        if source_mode == "live" or self.fetcher is not None:
            result = (self.fetcher or fetch_historical_range)(
                query_bbox,
                audit.review_start,
                audit.review_end,
                analysis_region=query_bbox,
            )
            observations = pd.concat(
                [result.observations, result.external_context], ignore_index=True
            )
            source_run = {
                "mode": "live",
                "source": result.source,
                "windows": [vars(window) for window in result.windows],
            }
        else:
            observations = _load_cached_observations()
            observations = observations[
                observations["acq_date"].between(audit.review_start, audit.review_end)
                & observations["latitude"].between(query_bbox[1], query_bbox[3])
                & observations["longitude"].between(query_bbox[0], query_bbox[2])
            ].reset_index(drop=True)
            source_run = {
                "mode": "cached",
                "dataset": CACHE_DATASET_LABEL,
                "reference": CACHE_SOURCE_REFERENCE,
            }
        if observations.empty:
            raise HistoryInputError(
                "no FIRMS observations were found for this scope and date range"
            )

        events, annotated = cluster_events(observations)
        triage_results = triage_events(events, observations)
        triage_by_id = {item.event_id: item for item in triage_results}
        qualified_ids = {
            item.event_id for item in triage_results if item.state != Stage1State.LIKELY_NON_FIRE
        }
        qualified_observations = annotated[annotated["event_id"].isin(qualified_ids)]
        events = [event for event in events if event.event_id in qualified_ids]
        if not events:
            raise HistoryInputError(
                "deterministic triage found no qualified FireEvents for this scope"
            )

        scope_by_id = _scope_events(events, observations, audit.geometry)
        weather_by_event: dict[str, Any] = {}
        weather_objects_by_event: dict[str, list[dict[str, Any]]] = {}
        peat_by_event: dict[str, Any] = {}
        complexity_by_event: dict[str, Any] = {}
        propagation_by_event: dict[str, Any] = {}
        for event in events:
            cached_weather = _load_cached_weather(event.event_id)
            weather_objects: list[dict[str, Any]] = []
            weather_bundle = None
            if cached_weather is not None:
                hourly, daily = cached_weather
                weather_bundle = WeatherEvidenceBundle(
                    event_id=event.event_id,
                    centroid=event.centroid,
                    windows=compute_weather_windows(event, hourly, daily),
                )
                weather_objects = weather_evidence(weather_bundle)
                weather_by_event[event.event_id] = weather_bundle
            weather_objects_by_event[event.event_id] = weather_objects
            raster = _load_cached_raster(event.event_id)
            peat = compute_peat_context(event, raster) if raster is not None else None
            peat_by_event[event.event_id] = peat
            direction = _wind_direction(weather_bundle)
            propagation = compare_event_progression(
                event, events, wind_direction_from_deg=direction
            )
            propagation_by_event[event.event_id] = propagation
            complexity_by_event[event.event_id] = compute_fire_complexity(
                event,
                observations,
                events=events,
                peat_context=peat,
                surface_propagation=propagation,
            )

        graph = build_fire_event_graph(events, weather_by_event=weather_by_event)
        serialized_events = []
        for event in events:
            triage = triage_by_id[event.event_id]
            complexity = complexity_by_event[event.event_id]
            priority = compute_investigation_priority(
                event,
                triage=triage,
                complexity=complexity,
                graph=graph,
                peat_context=peat_by_event[event.event_id],
                propagation=propagation_by_event[event.event_id],
            )
            relation, distance = scope_by_id[event.event_id]
            serialized_events.append(serialize_event(
                event,
                observations,
                audit.audit_id,
                relation,
                distance,
                triage,
                peat_by_event[event.event_id],
                complexity,
                priority,
                graph,
                weather_objects_by_event[event.event_id],
            ))
        serialized_events.sort(key=lambda item: (item["firstDetected"], item["id"]))
        triage_summary = summarize_triage(triage_results)
        history = {
            "auditId": audit.audit_id,
            "status": "complete",
            "events": serialized_events,
            "compression": {
                "rawObservations": len(observations),
                "qualifiedObservations": len(qualified_observations),
                "fireEvents": len(serialized_events),
                "stage1ReviewQueue": triage_summary.review_queue_count,
                "stage1StateCounts": triage_summary.state_counts,
            },
            "sourceRun": source_run,
            "graph": graph.to_dict(),
        }
        audit.history = history
        return history
