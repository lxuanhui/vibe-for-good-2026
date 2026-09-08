"""Build a deterministic relationship graph over coherent ``FireEvent``s.

Raw FIRMS detections are intentionally not accepted here.  Clustering has
already compressed those observations into event nodes, and this module only
compares event summaries and optional, already-derived environmental context.
That boundary keeps relationship candidates inspectable and makes it
impossible for a future agent call to silently turn a cloud of hotspots into a
causal-looking graph.

The model is a first-order screening graph, not a fire-cause or responsibility
model.  An edge says that two event histories are related, compatible with a
simple surface-spread explanation, or still need human review.  It does not
say who or what caused either event.

``build_fire_event_graph`` is pure: callers provide FireEvents and optional
weather, peat, environmental-episode, and recurrence context.  Network
acquisition belongs in the enrichment/source layer.  Missing context remains
``None`` rather than being turned into negative evidence.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from data_pipeline.clustering.firms_clustering import FireEvent

EARTH_RADIUS_KM = 6371.0088
ALGORITHM_VERSION = "fire-event-graph-v1"

DEFAULT_CANDIDATE_DISTANCE_KM = 50.0
DEFAULT_CANDIDATE_TIME_WINDOW_HOURS = 30.0 * 24.0
DEFAULT_EVENT_BUFFER_KM = 2.0
DEFAULT_MAX_SURFACE_SPREAD_KMH = 5.0
DEFAULT_WEAK_SURFACE_SPREAD_KMH = 20.0
WIND_ALIGNMENT_TOLERANCE_DEG = 60.0


class EdgeState(StrEnum):
    """Relationship routing states, not causal or legal conclusions."""

    RELATED_POSSIBLE = "RELATED_POSSIBLE"
    PROPAGATION_COMPATIBLE = "PROPAGATION_COMPATIBLE"
    PROPAGATION_WEAK = "PROPAGATION_WEAK"
    INDEPENDENT_PLAUSIBLE = "INDEPENDENT_PLAUSIBLE"
    UNRESOLVED = "UNRESOLVED"


class TemporalOrdering(StrEnum):
    A_BEFORE_B = "A_BEFORE_B"
    B_BEFORE_A = "B_BEFORE_A"
    OVERLAPPING = "OVERLAPPING"


class PropagationCompatibility(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    WEAK = "WEAK"
    INCOMPATIBLE = "INCOMPATIBLE"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class FireEventEdgeFeatures:
    """Inspectable deterministic features carried by one candidate edge.

    ``wind_alignment`` is the cosine of the angle between the bearing from
    event A to event B and the downwind travel direction.  It ranges from -1
    (upwind) to +1 (downwind); meteorological wind directions describe where
    wind comes from, so 180 degrees is applied before comparison.

    ``elapsed_time_hours`` is the non-negative gap from the earlier event's
    last detection to the later event's first detection.  It is zero for
    overlapping detection windows.  ``None`` means an optional environmental
    source was unavailable, never that the feature was absent.
    """

    geographic_distance_km: float
    elapsed_time_hours: float
    temporal_ordering: TemporalOrdering
    wind_alignment: float | None
    directional_compatibility: bool | None
    overlapping_event_buffers: bool
    peat_corridor_fraction: float | None
    shared_environmental_episode: bool | None
    historical_recurrence: bool | None
    propagation_compatibility: PropagationCompatibility

    @property
    def distance_km(self) -> float:
        """Short alias useful to map consumers and older callers."""

        return self.geographic_distance_km

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["temporal_ordering"] = self.temporal_ordering.value
        result["propagation_compatibility"] = self.propagation_compatibility.value
        return result


@dataclass(frozen=True)
class FireEventEdge:
    """One directed-in-time or undirected candidate relationship.

    ``source_event_id`` and ``target_event_id`` follow temporal ordering when
    the event windows do not overlap.  For overlapping windows the IDs are
    sorted for stable serialization and ``features.temporal_ordering`` is
    ``OVERLAPPING``; consumers must not interpret that pair as directional.
    """

    source_event_id: str
    target_event_id: str
    state: EdgeState
    features: FireEventEdgeFeatures
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    explanation: str = ""
    model_version: str = ALGORITHM_VERSION

    @property
    def from_event_id(self) -> str:
        return self.source_event_id

    @property
    def to_event_id(self) -> str:
        return self.target_event_id

    @property
    def geographic_distance_km(self) -> float:
        return self.features.geographic_distance_km

    @property
    def elapsed_time_hours(self) -> float:
        return self.features.elapsed_time_hours

    @property
    def propagation_compatibility(self) -> PropagationCompatibility:
        return self.features.propagation_compatibility

    @property
    def directed(self) -> bool:
        return self.features.temporal_ordering != TemporalOrdering.OVERLAPPING

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_event_id": self.source_event_id,
            "target_event_id": self.target_event_id,
            "state": self.state.value,
            "features": self.features.to_dict(),
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradicting_evidence_ids": list(self.contradicting_evidence_ids),
            "explanation": self.explanation,
            "model_version": self.model_version,
            "directed": self.directed,
        }


@dataclass
class FireEventGraph:
    """Graph nodes and candidate relationships for one event collection."""

    nodes: list[FireEvent]
    edges: list[FireEventEdge]
    model_version: str = ALGORITHM_VERSION
    candidate_distance_km: float = DEFAULT_CANDIDATE_DISTANCE_KM
    candidate_time_window_hours: float = DEFAULT_CANDIDATE_TIME_WINDOW_HOURS

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.event_id for node in self.nodes)

    def edges_for(self, event_id: str) -> list[FireEventEdge]:
        """Return incident edges in stable graph order."""

        return [
            edge
            for edge in self.edges
            if event_id in {edge.source_event_id, edge.target_event_id}
        ]

    def outgoing(self, event_id: str) -> list[FireEventEdge]:
        """Return edges where this event is the earlier source node."""

        return [edge for edge in self.edges if edge.source_event_id == event_id and edge.directed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "model_version": self.model_version,
            "candidate_distance_km": self.candidate_distance_km,
            "candidate_time_window_hours": self.candidate_time_window_hours,
        }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r, lat2_r, lon2_r = (math.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def _bearing_deg(from_event: FireEvent, to_event: FireEvent) -> float:
    lat1 = math.radians(from_event.centroid[0])
    lat2 = math.radians(to_event.centroid[0])
    delta_lon = math.radians(to_event.centroid[1] - from_event.centroid[1])
    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return math.degrees(math.atan2(x, y)) % 360.0


def _angular_difference_deg(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("FireEvent timestamps must include a timezone")
    return parsed


def _event_gap_hours(first: FireEvent, second: FireEvent) -> tuple[TemporalOrdering, float]:
    first_start, first_end = _timestamp(first.first_detection), _timestamp(first.last_detection)
    second_start, second_end = _timestamp(second.first_detection), _timestamp(second.last_detection)
    if first_end < second_start:
        return TemporalOrdering.A_BEFORE_B, (second_start - first_end).total_seconds() / 3600.0
    if second_end < first_start:
        return TemporalOrdering.B_BEFORE_A, (first_start - second_end).total_seconds() / 3600.0
    return TemporalOrdering.OVERLAPPING, 0.0


def _pair_key(first_id: str, second_id: str) -> frozenset[str]:
    return frozenset((first_id, second_id))


def _lookup_pair(mapping: Mapping[Any, Any] | None, first_id: str, second_id: str) -> Any:
    if not mapping:
        return None
    for key in ((first_id, second_id), (second_id, first_id), _pair_key(first_id, second_id)):
        try:
            if key in mapping:
                return mapping[key]
        except TypeError:
            continue
    return None


def _episode_relationship(
    episode_by_event: Mapping[str, Hashable] | None, first_id: str, second_id: str
) -> bool | None:
    if not episode_by_event:
        return None
    first_episode = episode_by_event.get(first_id)
    second_episode = episode_by_event.get(second_id)
    if first_episode is None or second_episode is None:
        return None
    return first_episode == second_episode


def _wind_values(value: Any) -> tuple[float | None, float | None, tuple[str, ...]]:
    """Read a weather bundle or serialized weather windows without coupling
    the graph to the network-facing weather source."""

    windows = getattr(value, "windows", None) if value is not None else None
    if windows is None and isinstance(value, Mapping):
        windows = value.get("windows")
    if windows is None and isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        windows = value
    if not windows:
        return None, None, ()

    event_id = getattr(value, "event_id", None)
    if event_id is None and isinstance(value, Mapping):
        event_id = value.get("event_id")

    preferred = list(windows)
    def _window_name(window: Any) -> str:
        if isinstance(window, Mapping):
            return str(window.get("window_name", "weather"))
        return str(getattr(window, "window_name", "weather"))

    preferred.sort(key=lambda window: 0 if _window_name(window) == "event_duration" else 1)
    for window in preferred:
        if isinstance(window, Mapping):
            direction = window.get("dominant_wind_direction_deg")
            speed = window.get("mean_wind_speed_ms")
            name = window.get("window_name", "weather")
        else:
            direction = getattr(window, "dominant_wind_direction_deg", None)
            speed = getattr(window, "mean_wind_speed_ms", None)
            name = getattr(window, "window_name", "weather")
        if direction is None:
            continue
        direction = float(direction) % 360.0
        speed_value = None if speed is None else float(speed)
        source_id = (
            f"ENV_WEATHER_{event_id}_{name}_wind_direction"
            if event_id
            else f"WEATHER_{name}_WIND_DIRECTION"
        )
        return direction, speed_value, (source_id,)
    return None, None, ()


def _peat_fraction(
    raster: Any, first: FireEvent, second: FireEvent
) -> tuple[float | None, tuple[str, ...]]:
    if raster is None:
        return None, ()
    # Import lazily so consumers that only build a graph from FireEvents do
    # not need to initialize the raster/source stack.
    from data_pipeline.enrichment.peat_context import peat_fraction_along_corridor

    fraction, _limitations = peat_fraction_along_corridor(raster, first.centroid, second.centroid)
    return fraction, ()


def _event_buffer_overlap(first: FireEvent, second: FireEvent, buffer_km: float, distance: float) -> bool:
    first_radius = max(float(first.spatial_extent_km) / 2.0, 0.0) + buffer_km
    second_radius = max(float(second.spatial_extent_km) / 2.0, 0.0) + buffer_km
    return distance <= first_radius + second_radius


def _explicit_pair_indices(
    recurrence: Mapping[Any, Any] | None, id_to_index: Mapping[str, int]
) -> set[tuple[int, int]]:
    """Keep explicitly supplied recurrence links even when they are not
    spatial or temporal neighbours."""

    pairs: set[tuple[int, int]] = set()
    for key in recurrence or {}:
        if isinstance(key, frozenset):
            pair_ids = tuple(key)
        elif isinstance(key, (tuple, list)) and len(key) == 2:
            pair_ids = (key[0], key[1])
        else:
            continue
        if len(pair_ids) != 2 or pair_ids[0] == pair_ids[1]:
            continue
        if pair_ids[0] not in id_to_index or pair_ids[1] not in id_to_index:
            continue
        pairs.add(tuple(sorted((id_to_index[pair_ids[0]], id_to_index[pair_ids[1]]))))
    return pairs


def _spatial_candidate_pairs(
    nodes: Sequence[FireEvent], candidate_distance_km: float, event_buffer_km: float
) -> set[tuple[int, int]]:
    """Use a projected spatial index before applying the time gate.

    The search radius includes the largest possible event-buffer overlap, so
    a large FireEvent cannot be lost merely because its centroid is farther
    than the ordinary neighbour radius.
    """

    if len(nodes) < 2:
        return set()
    ref_lat = float(np.mean([event.centroid[0] for event in nodes]))
    x = np.array(
        [
            math.radians(event.centroid[1])
            * EARTH_RADIUS_KM
            * math.cos(math.radians(ref_lat))
            for event in nodes
        ]
    )
    y = np.array([math.radians(event.centroid[0]) * EARTH_RADIUS_KM for event in nodes])
    tree = cKDTree(np.column_stack([x, y]))
    largest_radius = max(
        max(float(event.spatial_extent_km) / 2.0, 0.0) + event_buffer_km for event in nodes
    )
    search_radius = max(candidate_distance_km, 2.0 * largest_radius)
    return {
        (int(first), int(second))
        for first, second in tree.query_pairs(search_radius, output_type="ndarray")
    }


def _propagation_compatibility(
    ordering: TemporalOrdering,
    distance_km: float,
    elapsed_hours: float,
    max_surface_spread_kmh: float,
    weak_surface_spread_kmh: float,
) -> PropagationCompatibility:
    if ordering == TemporalOrdering.OVERLAPPING or elapsed_hours <= 0:
        return PropagationCompatibility.NOT_EVALUATED
    apparent_speed = distance_km / elapsed_hours
    if apparent_speed <= max_surface_spread_kmh:
        return PropagationCompatibility.COMPATIBLE
    if apparent_speed <= weak_surface_spread_kmh:
        return PropagationCompatibility.WEAK
    return PropagationCompatibility.INCOMPATIBLE


def _state_for_features(features: FireEventEdgeFeatures) -> tuple[EdgeState, str]:
    compatibility = features.propagation_compatibility
    direction_conflict = features.directional_compatibility is False
    downwind_support = features.wind_alignment is not None and features.wind_alignment >= 0.5
    upwind_conflict = features.wind_alignment is not None and features.wind_alignment <= -0.5
    context_support = (
        features.overlapping_event_buffers
        or features.peat_corridor_fraction is not None
        and features.peat_corridor_fraction >= 0.5
        or features.shared_environmental_episode is True
        or features.historical_recurrence is True
    )

    if features.temporal_ordering == TemporalOrdering.OVERLAPPING:
        if not features.overlapping_event_buffers and features.shared_environmental_episode is not True:
            return EdgeState.INDEPENDENT_PLAUSIBLE, "Overlapping event windows are spatially separate."
        return EdgeState.UNRESOLVED, "Event windows overlap, so temporal propagation direction is unresolved."

    if compatibility == PropagationCompatibility.COMPATIBLE and not direction_conflict and not upwind_conflict:
        if downwind_support or features.wind_alignment is None:
            return (
                EdgeState.PROPAGATION_COMPATIBLE,
                "Event ordering and apparent surface spread are compatible with a first-order propagation path."
                + (" Wind alignment supports the path." if downwind_support else " Wind evidence was unavailable."),
            )
        return EdgeState.PROPAGATION_COMPATIBLE, "Event ordering and apparent surface spread are compatible."

    if compatibility == PropagationCompatibility.WEAK and context_support and not direction_conflict:
        return EdgeState.PROPAGATION_WEAK, "The event pair is directionally possible but apparent spread is weak or context-limited."

    if compatibility == PropagationCompatibility.INCOMPATIBLE and (direction_conflict or upwind_conflict):
        return EdgeState.UNRESOLVED, "Spatial-temporal proximity conflicts with the available directional evidence."

    if compatibility == PropagationCompatibility.INCOMPATIBLE:
        if context_support:
            return EdgeState.RELATED_POSSIBLE, "The events share environmental or recurrence context, but the simple surface-spread speed bound is not compatible."
        return EdgeState.INDEPENDENT_PLAUSIBLE, "The event pair is close enough to screen but not compatible with the surface-spread speed bound."

    if context_support:
        return EdgeState.RELATED_POSSIBLE, "The events share spatial, temporal, or environmental context without a propagation-compatible path."

    return EdgeState.UNRESOLVED, "The candidate pair lacks enough compatible evidence to distinguish relationship from independence."


def _build_edge(
    first: FireEvent,
    second: FireEvent,
    *,
    weather_by_event: Mapping[str, Any] | None,
    peat_raster: Any,
    environmental_episode_by_event: Mapping[str, Hashable] | None,
    historical_recurrence: Mapping[Any, Any] | None,
    event_buffer_km: float,
    max_surface_spread_kmh: float,
    weak_surface_spread_kmh: float,
) -> FireEventEdge:
    ordering, elapsed = _event_gap_hours(first, second)
    if ordering == TemporalOrdering.B_BEFORE_A:
        source, target = second, first
    elif ordering == TemporalOrdering.A_BEFORE_B:
        source, target = first, second
    else:
        source, target = sorted((first, second), key=lambda event: event.event_id)

    distance = _haversine_km(
        first.centroid[0], first.centroid[1], second.centroid[0], second.centroid[1]
    )
    overlap = _event_buffer_overlap(first, second, event_buffer_km, distance)
    source_wind, source_speed, wind_source_ids = _wind_values(
        weather_by_event.get(source.event_id) if weather_by_event else None
    )
    wind_alignment = None
    directional_compatibility = None
    if source_wind is not None and ordering != TemporalOrdering.OVERLAPPING:
        bearing = _bearing_deg(source, target)
        downwind_direction = (source_wind + 180.0) % 360.0
        angular_difference = _angular_difference_deg(bearing, downwind_direction)
        wind_alignment = round(math.cos(math.radians(angular_difference)), 6)
        directional_compatibility = angular_difference <= WIND_ALIGNMENT_TOLERANCE_DEG
        if source_speed is not None and source_speed <= 0:
            directional_compatibility = None

    peat_fraction, peat_source_ids = _peat_fraction(peat_raster, source, target)
    episode_shared = _episode_relationship(
        environmental_episode_by_event, first.event_id, second.event_id
    )
    recurrence_value = _lookup_pair(historical_recurrence, first.event_id, second.event_id)
    recurrence = None if recurrence_value is None else bool(recurrence_value)
    compatibility = _propagation_compatibility(
        ordering,
        distance,
        elapsed,
        max_surface_spread_kmh,
        weak_surface_spread_kmh,
    )
    features = FireEventEdgeFeatures(
        geographic_distance_km=round(distance, 3),
        elapsed_time_hours=round(elapsed, 3),
        temporal_ordering=ordering,
        wind_alignment=wind_alignment,
        directional_compatibility=directional_compatibility,
        overlapping_event_buffers=overlap,
        peat_corridor_fraction=None if peat_fraction is None else round(peat_fraction, 6),
        shared_environmental_episode=episode_shared,
        historical_recurrence=recurrence,
        propagation_compatibility=compatibility,
    )
    state, explanation = _state_for_features(features)

    prefix = f"DERIVED_GRAPH_{source.event_id}_{target.event_id}_"
    supporting: list[str] = [
        prefix + "GEOGRAPHIC_DISTANCE",
        prefix + "ELAPSED_TIME",
    ]
    contradicting: list[str] = []
    if compatibility in {
        PropagationCompatibility.COMPATIBLE,
        PropagationCompatibility.WEAK,
    }:
        supporting.append(prefix + "PROPAGATION_COMPATIBILITY")
    elif compatibility == PropagationCompatibility.INCOMPATIBLE:
        contradicting.append(prefix + "PROPAGATION_COMPATIBILITY")
    if overlap:
        supporting.append(prefix + "EVENT_BUFFER_OVERLAP")
    else:
        contradicting.append(prefix + "EVENT_BUFFER_OVERLAP")
    if wind_alignment is not None:
        (supporting if wind_alignment >= 0 else contradicting).append(prefix + "WIND_ALIGNMENT")
        if directional_compatibility is not None:
            (supporting if directional_compatibility else contradicting).append(
                prefix + "DIRECTIONAL_COMPATIBILITY"
            )
    if peat_fraction is not None:
        (supporting if peat_fraction >= 0.5 else contradicting).append(prefix + "PEAT_CORRIDOR_FRACTION")
    if episode_shared is not None:
        (supporting if episode_shared else contradicting).append(prefix + "SHARED_ENVIRONMENTAL_EPISODE")
    if recurrence is not None:
        (supporting if recurrence else contradicting).append(prefix + "HISTORICAL_RECURRENCE")
    supporting.extend(wind_source_ids + peat_source_ids)

    return FireEventEdge(
        source_event_id=source.event_id,
        target_event_id=target.event_id,
        state=state,
        features=features,
        supporting_evidence_ids=tuple(dict.fromkeys(supporting)),
        contradicting_evidence_ids=tuple(dict.fromkeys(contradicting)),
        explanation=explanation,
    )


def build_fire_event_graph(
    events: Sequence[FireEvent],
    *,
    weather_by_event: Mapping[str, Any] | None = None,
    peat_raster: Any = None,
    environmental_episode_by_event: Mapping[str, Hashable] | None = None,
    historical_recurrence: Mapping[Any, Any] | None = None,
    candidate_distance_km: float = DEFAULT_CANDIDATE_DISTANCE_KM,
    candidate_time_window_hours: float = DEFAULT_CANDIDATE_TIME_WINDOW_HOURS,
    event_buffer_km: float = DEFAULT_EVENT_BUFFER_KM,
    max_surface_spread_kmh: float = DEFAULT_MAX_SURFACE_SPREAD_KMH,
    weak_surface_spread_kmh: float = DEFAULT_WEAK_SURFACE_SPREAD_KMH,
) -> FireEventGraph:
    """Build candidate edges without raw-point or LLM reasoning.

    A pair is a candidate when its centroids are within
    ``candidate_distance_km`` and its event windows are within
    ``candidate_time_window_hours`` (overlapping buffers and explicit
    recurrence links also qualify).  The spatial/time gate prevents an
    all-pairs graph from expanding quadratically over a historical archive;
    callers can raise either bound for a deliberate wider review.
    """

    if not math.isfinite(candidate_distance_km) or candidate_distance_km <= 0:
        raise ValueError("candidate_distance_km must be positive and finite")
    if not math.isfinite(candidate_time_window_hours) or candidate_time_window_hours < 0:
        raise ValueError("candidate_time_window_hours must be non-negative and finite")
    if not math.isfinite(event_buffer_km) or event_buffer_km < 0:
        raise ValueError("event_buffer_km must be non-negative and finite")
    if not math.isfinite(max_surface_spread_kmh) or max_surface_spread_kmh <= 0:
        raise ValueError("max_surface_spread_kmh must be positive and finite")
    if not math.isfinite(weak_surface_spread_kmh) or weak_surface_spread_kmh < max_surface_spread_kmh:
        raise ValueError("weak_surface_spread_kmh must be at least max_surface_spread_kmh")

    nodes = list(events)
    ids = [event.event_id for event in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("FireEvent IDs must be unique within a graph")
    for event in nodes:
        if len(event.centroid) != 2 or not all(math.isfinite(float(value)) for value in event.centroid):
            raise ValueError(f"FireEvent {event.event_id} requires finite centroid coordinates")
        if not math.isfinite(float(event.spatial_extent_km)) or event.spatial_extent_km < 0:
            raise ValueError(f"FireEvent {event.event_id} requires a finite non-negative spatial extent")
        first_detection = _timestamp(event.first_detection)
        last_detection = _timestamp(event.last_detection)
        if last_detection < first_detection:
            raise ValueError(f"FireEvent {event.event_id} has an inverted detection window")

    id_to_index = {event.event_id: index for index, event in enumerate(nodes)}
    pair_indices = _spatial_candidate_pairs(nodes, candidate_distance_km, event_buffer_km)
    pair_indices.update(_explicit_pair_indices(historical_recurrence, id_to_index))

    edges: list[FireEventEdge] = []
    for first_index, second_index in sorted(pair_indices):
        first, second = nodes[first_index], nodes[second_index]
        ordering, gap_hours = _event_gap_hours(first, second)
        distance = _haversine_km(
            first.centroid[0], first.centroid[1], second.centroid[0], second.centroid[1]
        )
        buffers_overlap = _event_buffer_overlap(first, second, event_buffer_km, distance)
        recurrence = _lookup_pair(historical_recurrence, first.event_id, second.event_id)
        is_candidate = (
            distance <= candidate_distance_km
            and (ordering == TemporalOrdering.OVERLAPPING or gap_hours <= candidate_time_window_hours)
        ) or buffers_overlap or recurrence is not None
        if not is_candidate:
            continue
        edges.append(
            _build_edge(
                first,
                second,
                weather_by_event=weather_by_event,
                peat_raster=peat_raster,
                environmental_episode_by_event=environmental_episode_by_event,
                historical_recurrence=historical_recurrence,
                event_buffer_km=event_buffer_km,
                max_surface_spread_kmh=max_surface_spread_kmh,
                weak_surface_spread_kmh=weak_surface_spread_kmh,
            )
        )

    edges.sort(key=lambda edge: (edge.source_event_id, edge.target_event_id))
    return FireEventGraph(
        nodes=nodes,
        edges=edges,
        candidate_distance_km=candidate_distance_km,
        candidate_time_window_hours=candidate_time_window_hours,
    )


# A short alias keeps the package pleasant to use while the explicit function
# name remains the documented API.
build_graph = build_fire_event_graph
