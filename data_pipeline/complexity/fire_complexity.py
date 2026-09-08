"""Derive inspectable Fire Complexity evidence from reconstructed events.

Fire Complexity describes how poorly one FireEvent is explained by a single,
straightforward surface-fire episode.  This module deliberately returns one
named, provenance-bearing field for every candidate feature in the canonical
specification.  It does not combine the fields into a score: a reviewer can
see which observations support further scrutiny, which context is missing,
and which result is only a first-order model comparison.

The computation is pure.  Raw FIRMS observations, reconstructed FireEvents,
and already-derived peat/weather/propagation context are supplied by the
caller; this module performs no network or filesystem access.  Missing
optional context is represented as ``NOT_EVALUATED`` rather than absence or
negative evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.propagation.surface_fire import (
    DEFAULT_SPREAD_PARAMETERS,
    SurfaceFireCompatibilityResult,
    SurfaceFireSpreadParameters,
    historical_wind_direction,
    project_surface_fire_envelope,
)

EARTH_RADIUS_KM = 6371.0088
ALGORITHM_VERSION = "fire-complexity-evidence-v1"
FIELD_NAMES = (
    "duration",
    "observation_count",
    "spatial_extent",
    "centroid_movement",
    "directional_consistency",
    "wind_alignment",
    "frp_variability",
    "distinct_thermal_lobes",
    "peat_overlap",
    "nearby_event_count",
    "historical_recurrence",
    "unexplained_detections",
    "surface_propagation_mismatch",
)

DEFAULT_LOBE_DISTANCE_KM = 2.0
DEFAULT_NEARBY_EVENT_DISTANCE_KM = 10.0
DEFAULT_NEARBY_EVENT_WINDOW_HOURS = 72.0
DEFAULT_RECURRENCE_DISTANCE_KM = 2.0


class ComplexityEvidenceStatus(StrEnum):
    """Whether a complexity field was computed from supplied evidence."""

    EVALUATED = "EVALUATED"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class ComplexityField:
    """One individually inspectable Fire Complexity evidence field."""

    name: str
    value: float | int | bool | None
    unit: str
    status: ComplexityEvidenceStatus
    observation: str
    source: str
    evidence_id: str
    quality: float
    limitations: tuple[str, ...] = ()
    time_window: str | None = None
    algorithm_version: str = ALGORITHM_VERSION
    raw_reference: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def metric(self) -> str:
        """Alias for consumers that call evidence fields metrics."""

        return self.name

    def to_evidence_object(self) -> dict[str, Any]:
        """Serialize to the canonical EvidenceObject shape."""

        result = asdict(self)
        result["status"] = self.status.value
        result["limitations"] = list(self.limitations)
        return result

    def to_dict(self) -> dict[str, Any]:
        return self.to_evidence_object()


@dataclass(frozen=True)
class FireComplexityEvidence:
    """All 13 named complexity fields for one reconstructed FireEvent.

    There is intentionally no aggregate ``score`` member.  Downstream
    screening or an auditor may use these fields, but this result never turns
    missing context or a model mismatch into an opaque numerical conclusion.
    """

    event_id: str
    duration: ComplexityField
    observation_count: ComplexityField
    spatial_extent: ComplexityField
    centroid_movement: ComplexityField
    directional_consistency: ComplexityField
    wind_alignment: ComplexityField
    frp_variability: ComplexityField
    distinct_thermal_lobes: ComplexityField
    peat_overlap: ComplexityField
    nearby_event_count: ComplexityField
    historical_recurrence: ComplexityField
    unexplained_detections: ComplexityField
    surface_propagation_mismatch: ComplexityField
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    algorithm_version: str = ALGORITHM_VERSION

    @property
    def fields(self) -> tuple[ComplexityField, ...]:
        """Return fields in the stable order used by reports and exports."""

        return tuple(getattr(self, name) for name in FIELD_NAMES)

    @property
    def features(self) -> dict[str, ComplexityField]:
        """Named lookup that keeps individual fields visible to callers."""

        return {name: getattr(self, name) for name in FIELD_NAMES}

    # Metric-name aliases make the units explicit for callers while keeping
    # the EvidenceObject field names short and stable for report layouts.
    @property
    def duration_hours(self) -> ComplexityField:
        return self.duration

    @property
    def spatial_extent_km(self) -> ComplexityField:
        return self.spatial_extent

    @property
    def centroid_movement_km(self) -> ComplexityField:
        return self.centroid_movement

    @property
    def thermal_lobe_count(self) -> ComplexityField:
        return self.distinct_thermal_lobes

    @property
    def evidence(self) -> list[dict[str, Any]]:
        """EvidenceObjects in stable feature order."""

        return [field.to_evidence_object() for field in self.fields]

    def to_evidence_objects(self) -> list[dict[str, Any]]:
        return self.evidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "features": {
                name: feature.to_dict() for name, feature in self.features.items()
            },
            "evaluated_at": self.evaluated_at,
            "algorithm_version": self.algorithm_version,
        }


def _haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = (math.radians(value) for value in (*first, *second))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def _bearing_deg(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lat2 = math.radians(first[0]), math.radians(second[0])
    delta_lon = math.radians(second[1] - first[1])
    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        delta_lon
    )
    return math.degrees(math.atan2(x, y)) % 360.0


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("FireEvent timestamps must include a timezone")
    return parsed


def _event_window(event: FireEvent) -> tuple[datetime, datetime]:
    first, last = _timestamp(event.first_detection), _timestamp(event.last_detection)
    if last < first:
        raise ValueError(f"FireEvent {event.event_id} has an inverted detection window")
    return first, last


def _field(
    event: FireEvent,
    name: str,
    value: float | bool | None,
    unit: str,
    observation: str,
    source: str,
    evaluated_at: str,
    *,
    quality: float = 0.82,
    limitations: Sequence[str] = (),
    details: Mapping[str, Any] | None = None,
) -> ComplexityField:
    if not 0 <= quality <= 1:
        raise ValueError("complexity evidence quality must be between 0 and 1")
    status = (
        ComplexityEvidenceStatus.EVALUATED
        if value is not None
        else ComplexityEvidenceStatus.NOT_EVALUATED
    )
    return ComplexityField(
        name=name,
        value=value,
        unit=unit,
        status=status,
        observation=observation,
        source=source,
        evidence_id=f"DERIVED_COMPLEXITY_{event.event_id}_{name}",
        quality=quality,
        limitations=tuple(limitations),
        time_window=f"{event.first_detection} to {event.last_detection}",
        raw_reference=event.event_id,
        details=dict(details or {}),
    )


def _not_evaluated(
    event: FireEvent,
    name: str,
    reason: str,
    source: str,
    evaluated_at: str,
    *,
    limitations: Sequence[str] = (),
) -> ComplexityField:
    return _field(
        event,
        name,
        None,
        "unknown",
        f"Not evaluated: {reason}",
        source,
        evaluated_at,
        quality=0.0,
        limitations=limitations,
    )


def _event_observations(event: FireEvent, observations: pd.DataFrame) -> pd.DataFrame:
    required = {"latitude", "longitude", "acq_date", "acq_time"}
    missing = required - set(observations.columns)
    if missing:
        raise ValueError(
            f"complexity observations are missing columns: {', '.join(sorted(missing))}"
        )
    if not event.observation_indices:
        raise ValueError("FireEvent must contain at least one observation index")
    if min(event.observation_indices) < 0 or max(event.observation_indices) >= len(
        observations
    ):
        raise IndexError(
            "FireEvent observation_indices do not match supplied observations"
        )
    event_observations = observations.iloc[event.observation_indices].copy()
    if len(event_observations) != event.observation_count:
        raise ValueError(
            "FireEvent observation_count does not match observation_indices"
        )
    for column in ("latitude", "longitude"):
        values = pd.to_numeric(event_observations[column], errors="coerce").to_numpy(
            dtype=float
        )
        if not np.isfinite(values).all():
            raise ValueError(f"complexity observations require finite {column} values")
    hhmm = pd.to_numeric(event_observations["acq_time"], errors="coerce")
    if hhmm.isna().any():
        raise ValueError("complexity observations require parseable acq_time values")
    hhmm_text = hhmm.astype(int).astype(str).str.zfill(4)
    times = pd.to_datetime(
        event_observations["acq_date"].astype(str)
        + " "
        + hhmm_text.str[:2]
        + ":"
        + hhmm_text.str[2:],
        errors="coerce",
        utc=True,
    )
    if times.isna().any():
        raise ValueError(
            "complexity observations require parseable acq_date/acq_time values"
        )
    event_observations["_complexity_time"] = times
    return event_observations.sort_values(["_complexity_time"], kind="stable")


def _coordinates(event_observations: pd.DataFrame) -> list[tuple[float, float]]:
    return [
        (float(row.latitude), float(row.longitude))
        for row in event_observations[["latitude", "longitude"]].itertuples(index=False)
    ]


def _movement_segments(
    points: Sequence[tuple[float, float]],
) -> tuple[list[float], list[float]]:
    distances: list[float] = []
    bearings: list[float] = []
    for first, second in pairwise(points):
        distance = _haversine_km(first, second)
        distances.append(distance)
        bearings.append(_bearing_deg(first, second) if distance > 0 else 0.0)
    return distances, bearings


def _project_xy(points: Sequence[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    ref_lat = float(np.mean([point[0] for point in points]))
    x = np.array(
        [
            math.radians(point[1]) * EARTH_RADIUS_KM * math.cos(math.radians(ref_lat))
            for point in points
        ]
    )
    y = np.array([math.radians(point[0]) * EARTH_RADIUS_KM for point in points])
    return x, y


def _spatial_components(
    points: Sequence[tuple[float, float]], threshold_km: float
) -> int:
    if not math.isfinite(threshold_km) or threshold_km <= 0:
        raise ValueError("lobe distance must be positive and finite")
    if not points:
        return 0
    x, y = _project_xy(points)
    tree = cKDTree(np.column_stack([x, y]))
    parent = list(range(len(points)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    for first, second in tree.query_pairs(r=threshold_km):
        union(first, second)
    return len({find(index) for index in range(len(points))})


def _wind_direction(
    wind_direction_from_deg: float | None,
    wind_history: Sequence[Any] | None,
    surface_propagation: SurfaceFireCompatibilityResult | None,
) -> float | None:
    direction = wind_direction_from_deg
    if direction is None and surface_propagation is not None:
        direction = surface_propagation.wind_direction_from_deg
    if direction is None and wind_history:
        direction = historical_wind_direction(wind_history)
    if direction is None:
        return None
    if not math.isfinite(float(direction)):
        raise ValueError("wind direction must be finite")
    return float(direction) % 360.0


def _lookup_event_value(mapping: Mapping[Any, Any], event_id: str) -> Any:
    if event_id in mapping:
        return mapping[event_id]
    return None


def _recurrence_value_for_event(mapping: Mapping[Any, Any], event_id: str) -> Any:
    """Read direct counts and graph-style pair recurrence context."""

    direct = _lookup_event_value(mapping, event_id)
    if direct is not None:
        return direct
    matches = []
    for key, value in mapping.items():
        if isinstance(key, (tuple, frozenset, set)) and event_id in key:
            matches.append(value)
    if not matches:
        return None
    return sum(_count_from_recurrence(value) for value in matches)


def _count_from_recurrence(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        if (
            not math.isfinite(float(value))
            or float(value) < 0
            or not float(value).is_integer()
        ):
            raise ValueError(
                "historical recurrence count must be a non-negative integer"
            )
        return int(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return len(value)
    raise TypeError("historical recurrence must be a boolean, count, or sequence")


def _raw_surface_evaluation(
    event_observations: pd.DataFrame,
    points: Sequence[tuple[float, float]],
    direction: float | None,
    parameters: SurfaceFireSpreadParameters,
) -> tuple[int, int, list[str]] | None:
    if direction is None or len(points) < 2:
        return None
    origin = points[0]
    origin_time = event_observations["_complexity_time"].iloc[0]
    outside = 0
    evaluated = 0
    outside_indices: list[str] = []
    for position, point in enumerate(points[1:], start=1):
        elapsed_hours = (
            event_observations["_complexity_time"].iloc[position] - origin_time
        ).total_seconds() / 3600.0
        envelope = project_surface_fire_envelope(
            origin,
            max(elapsed_hours, 0.0),
            direction,
            parameters,
            origin_time=origin_time.isoformat(),
        )
        evaluated += 1
        if not envelope.contains_point(point):
            outside += 1
            outside_indices.append(str(event_observations.index[position]))
    return outside, evaluated, outside_indices


def _surface_result_evaluation(
    result: SurfaceFireCompatibilityResult,
) -> tuple[int, int]:
    evaluated = sum(
        observation.inside_expected_envelope is not None
        for observation in result.observations
    )
    outside = sum(
        observation.inside_expected_envelope is False
        for observation in result.observations
    )
    return outside, evaluated


def compute_fire_complexity(
    event: FireEvent,
    observations: pd.DataFrame,
    *,
    events: Sequence[FireEvent] | None = None,
    wind_direction_from_deg: float | None = None,
    wind_history: Sequence[Any] | None = None,
    peat_context: Any = None,
    historical_recurrence: Mapping[Any, Any] | None = None,
    surface_propagation: SurfaceFireCompatibilityResult | None = None,
    unexplained_observation_indices: Sequence[int] | None = None,
    surface_parameters: SurfaceFireSpreadParameters = DEFAULT_SPREAD_PARAMETERS,
    lobe_distance_km: float = DEFAULT_LOBE_DISTANCE_KM,
    nearby_event_distance_km: float = DEFAULT_NEARBY_EVENT_DISTANCE_KM,
    nearby_event_window_hours: float = DEFAULT_NEARBY_EVENT_WINDOW_HOURS,
    recurrence_distance_km: float = DEFAULT_RECURRENCE_DISTANCE_KM,
) -> FireComplexityEvidence:
    """Compute named complexity evidence for one clustered FireEvent.

    ``events`` is the reconstructed collection used for nearby-event and
    recurrence context.  ``peat_context``, ``historical_recurrence``, and
    ``surface_propagation`` must be already-derived inputs; their acquisition
    is intentionally outside this pure function.  If no context is supplied,
    that field remains explicitly ``NOT_EVALUATED``.
    """

    evaluated_at = datetime.now(timezone.utc).isoformat()
    event_observations = _event_observations(event, observations)
    points = _coordinates(event_observations)
    direction = _wind_direction(
        wind_direction_from_deg, wind_history, surface_propagation
    )
    first_time, last_time = _event_window(event)

    duration = _field(
        event,
        "duration",
        round(event.duration_hours, 6),
        "hours",
        f"The reconstructed event spans {event.duration_hours:.2f} hours from first to last detection.",
        "NASA FIRMS / reconstructed FireEvent",
        evaluated_at,
    )
    observation_count = _field(
        event,
        "observation_count",
        event.observation_count,
        "observations",
        f"The reconstructed event contains {event.observation_count} linked FIRMS observations.",
        "NASA FIRMS / reconstructed FireEvent",
        evaluated_at,
    )
    spatial_extent = _field(
        event,
        "spatial_extent",
        round(event.spatial_extent_km, 6),
        "km",
        f"The event bounding-box diagonal spans approximately {event.spatial_extent_km:.2f} km.",
        "NASA FIRMS / reconstructed FireEvent",
        evaluated_at,
        limitations=(
            "Bounding-box diagonal is an extent summary, not burned-area geometry.",
        ),
    )

    distances, bearings = _movement_segments(points)
    net_movement = _haversine_km(points[0], points[-1]) if len(points) > 1 else 0.0
    path_length = sum(distances)
    if len(points) < 2 or path_length == 0:
        centroid_movement = _not_evaluated(
            event,
            "centroid_movement",
            "fewer than two spatially distinct ordered observations were available",
            "NASA FIRMS",
            evaluated_at,
        )
        directional_consistency = _not_evaluated(
            event,
            "directional_consistency",
            "fewer than one spatial movement segment was available",
            "NASA FIRMS",
            evaluated_at,
        )
    else:
        centroid_movement = _field(
            event,
            "centroid_movement",
            round(net_movement, 6),
            "km",
            f"The first-to-last detection displacement is {net_movement:.2f} km; cumulative ordered path length is {path_length:.2f} km.",
            "NASA FIRMS",
            evaluated_at,
            limitations=(
                "Movement uses ordered detection coordinates, not a tracked fire perimeter.",
            ),
            details={
                "path_length_km": round(path_length, 6),
                "segment_count": len(distances),
            },
        )
        weighted_sin = sum(
            distance * math.sin(math.radians(bearing))
            for distance, bearing in zip(distances, bearings)
        )
        weighted_cos = sum(
            distance * math.cos(math.radians(bearing))
            for distance, bearing in zip(distances, bearings)
        )
        consistency = math.hypot(weighted_sin, weighted_cos) / path_length
        directional_consistency = _field(
            event,
            "directional_consistency",
            round(consistency, 6),
            "circular_resultant",
            f"Ordered movement directions have a weighted circular consistency of {consistency:.2f} (1 is one direction; 0 cancels).",
            "NASA FIRMS",
            evaluated_at,
            limitations=(
                "Segment bearings are a first-order summary of point-to-point movement.",
            ),
            details={
                "segment_count": len(distances),
                "path_length_km": round(path_length, 6),
            },
        )

    if direction is None or not distances or path_length == 0:
        wind_alignment = _not_evaluated(
            event,
            "wind_alignment",
            "historical wind direction or spatial movement was unavailable",
            "NASA FIRMS + historical weather",
            evaluated_at,
        )
    else:
        downwind = (direction + 180.0) % 360.0
        alignment = (
            sum(
                distance
                * math.cos(math.radians((bearing - downwind + 180.0) % 360.0 - 180.0))
                for distance, bearing in zip(distances, bearings)
            )
            / path_length
        )
        wind_alignment = _field(
            event,
            "wind_alignment",
            round(alignment, 6),
            "cosine",
            f"Movement alignment with the downwind direction ({downwind:.1f}°) is {alignment:.2f}; +1 is aligned and -1 is opposed.",
            "NASA FIRMS + historical weather",
            evaluated_at,
            limitations=(
                "Wind direction is treated as representative of the event window; alignment is not a cause finding.",
            ),
            details={
                "wind_direction_from_deg": round(direction, 6),
                "downwind_direction_deg": round(downwind, 6),
            },
        )

    frp_values: list[float] = []
    if "frp" in event_observations.columns:
        raw_frp = pd.to_numeric(event_observations["frp"], errors="coerce").to_numpy(
            dtype=float
        )
        frp_values = [
            float(value) for value in raw_frp if math.isfinite(value) and value >= 0
        ]
    if len(frp_values) < 2:
        frp_variability = _not_evaluated(
            event,
            "frp_variability",
            "fewer than two finite, non-negative FRP observations were available",
            "NASA FIRMS",
            evaluated_at,
        )
    else:
        mean_frp = float(np.mean(frp_values))
        std_frp = float(np.std(frp_values))
        coefficient = 0.0 if mean_frp == 0 else std_frp / mean_frp
        frp_variability = _field(
            event,
            "frp_variability",
            round(coefficient, 6),
            "coefficient_of_variation",
            f"Finite FRP values have mean {mean_frp:.2f} MW, standard deviation {std_frp:.2f} MW, and coefficient of variation {coefficient:.2f}.",
            "NASA FIRMS",
            evaluated_at,
            limitations=(
                "FRP is sensor- and pixel-dependent radiative power, not burned area or heat release for the whole event.",
            ),
            details={
                "sample_count": len(frp_values),
                "mean_frp_mw": round(mean_frp, 6),
                "std_frp_mw": round(std_frp, 6),
            },
        )

    lobes = _spatial_components(points, lobe_distance_km)
    distinct_thermal_lobes = _field(
        event,
        "distinct_thermal_lobes",
        lobes,
        "spatial_components",
        f"A {lobe_distance_km:g} km spatial connectivity check finds {lobes} distinct thermal lobe(s) among the event observations.",
        "NASA FIRMS",
        evaluated_at,
        limitations=(
            "Lobes are spatially connected observation components, not independently confirmed fires.",
        ),
        details={"connectivity_distance_km": lobe_distance_km},
    )

    if peat_context is None:
        peat_overlap = _not_evaluated(
            event,
            "peat_overlap",
            "no already-derived peat context was supplied",
            "peat context",
            evaluated_at,
        )
    else:
        context_value = (
            peat_context if isinstance(peat_context, Mapping) else vars(peat_context)
        )
        fraction = context_value.get("footprint_peat_fraction")
        direct = context_value.get("direct_intersection")
        limitations = tuple(context_value.get("limitations", ()))
        source = str(context_value.get("source", "peat context"))
        if fraction is not None:
            fraction = float(fraction)
            if not 0 <= fraction <= 1:
                raise ValueError("peat footprint fraction must be between 0 and 1")
            peat_overlap = _field(
                event,
                "peat_overlap",
                round(fraction, 6),
                "fraction",
                f"{fraction * 100:.1f}% of sampled event footprint points are mapped peat.",
                source,
                evaluated_at,
                quality=0.7,
                limitations=limitations,
                details={"direct_intersection": direct},
            )
        elif direct is not None:
            peat_overlap = _field(
                event,
                "peat_overlap",
                bool(direct),
                "bool",
                f"The event footprint {'intersects' if direct else 'does not intersect'} mapped peat.",
                source,
                evaluated_at,
                quality=0.7,
                limitations=limitations,
            )
        else:
            peat_overlap = _not_evaluated(
                event,
                "peat_overlap",
                "the supplied peat context had no intersection or footprint fraction",
                source,
                evaluated_at,
                limitations=limitations,
            )

    if events is None:
        nearby_event_count = _not_evaluated(
            event,
            "nearby_event_count",
            "no reconstructed FireEvent collection was supplied",
            "reconstructed FireEvents",
            evaluated_at,
        )
        historical_auto_count = None
    else:
        if not math.isfinite(nearby_event_distance_km) or nearby_event_distance_km <= 0:
            raise ValueError("nearby event distance must be positive and finite")
        if (
            not math.isfinite(nearby_event_window_hours)
            or nearby_event_window_hours < 0
        ):
            raise ValueError("nearby event window must be non-negative and finite")
        if not math.isfinite(recurrence_distance_km) or recurrence_distance_km <= 0:
            raise ValueError("recurrence distance must be positive and finite")
        nearby = 0
        historical_auto_count = 0
        for other in events:
            if other.event_id == event.event_id:
                continue
            other_first, other_last = _event_window(other)
            distance = _haversine_km(event.centroid, other.centroid)
            gap_hours = max(
                0.0,
                (other_first - last_time).total_seconds() / 3600.0,
                (first_time - other_last).total_seconds() / 3600.0,
            )
            if (
                distance <= nearby_event_distance_km
                and gap_hours <= nearby_event_window_hours
            ):
                nearby += 1
            if other_last < first_time and distance <= recurrence_distance_km:
                historical_auto_count += 1
        nearby_event_count = _field(
            event,
            "nearby_event_count",
            nearby,
            "events",
            f"{nearby} other reconstructed FireEvent(s) fall within {nearby_event_distance_km:g} km and {nearby_event_window_hours:g} hours of this event window.",
            "reconstructed FireEvents",
            evaluated_at,
            limitations=(
                "Count is limited to the supplied reconstructed event collection and thresholds.",
            ),
            details={
                "distance_km": nearby_event_distance_km,
                "window_hours": nearby_event_window_hours,
            },
        )

    if historical_recurrence is not None:
        explicit_value = _recurrence_value_for_event(
            historical_recurrence, event.event_id
        )
        recurrence_count = (
            0 if explicit_value is None else _count_from_recurrence(explicit_value)
        )
        recurrence_source = "supplied historical recurrence context"
        recurrence_limitations = (
            "Recurrence reflects only the supplied historical context.",
        )
    elif historical_auto_count is not None:
        recurrence_count = historical_auto_count
        recurrence_source = "reconstructed FireEvents"
        recurrence_limitations = (
            f"Recurrence uses earlier event centroids within {recurrence_distance_km:g} km; it is not proof of the same physical fire.",
        )
    else:
        recurrence_count = None
        recurrence_source = "historical recurrence context"
        recurrence_limitations = ()
    if recurrence_count is None:
        historical_recurrence = _not_evaluated(
            event,
            "historical_recurrence",
            "no reconstructed history or recurrence context was supplied",
            recurrence_source,
            evaluated_at,
        )
    else:
        historical_recurrence = _field(
            event,
            "historical_recurrence",
            recurrence_count > 0,
            "bool",
            f"{recurrence_count} earlier reconstructed event(s) matched the supplied recurrence rule.",
            recurrence_source,
            evaluated_at,
            limitations=recurrence_limitations,
            details={"matching_event_count": recurrence_count},
        )

    raw_surface = (
        None
        if surface_propagation is not None
        else _raw_surface_evaluation(
            event_observations, points, direction, surface_parameters
        )
    )
    if unexplained_observation_indices is not None:
        indices = list(unexplained_observation_indices)
        valid_indices = set(event.observation_indices)
        if any(index not in valid_indices for index in indices):
            raise ValueError(
                "unexplained_observation_indices must belong to the FireEvent"
            )
        unexplained_count = len(indices)
        unexplained_detections = _field(
            event,
            "unexplained_detections",
            unexplained_count,
            "observations",
            f"{unexplained_count} event observation(s) were explicitly supplied as unexplained by the caller.",
            "caller-supplied derived context",
            evaluated_at,
            limitations=(
                "The caller's explanation rule is preserved as context; this module does not infer cause or responsibility.",
            ),
        )
    elif raw_surface is not None:
        outside, evaluated, outside_indices = raw_surface
        unexplained_detections = _field(
            event,
            "unexplained_detections",
            outside,
            "observations",
            f"{outside} of {evaluated} post-origin observations fall outside the first-order surface envelope.",
            "NASA FIRMS + first-order surface-fire model",
            evaluated_at,
            limitations=(
                "Outside-envelope observations are unresolved surface-model mismatches, not evidence of a separate fire or cause.",
                "The model does not represent underground peat propagation.",
            ),
            details={
                "evaluated_observation_count": evaluated,
                "outside_observation_indices": outside_indices,
            },
        )
    elif surface_propagation is not None:
        outside, evaluated = _surface_result_evaluation(surface_propagation)
        if evaluated:
            unexplained_detections = _field(
                event,
                "unexplained_detections",
                outside,
                "event_clusters",
                f"{outside} later event-cluster observation(s) fall outside the supplied surface envelope comparison.",
                "first-order surface-fire model",
                evaluated_at,
                limitations=(
                    "This fallback is event-cluster level because raw observations were not supplied to the propagation result.",
                ),
                details={"evaluated_cluster_count": evaluated},
            )
        else:
            unexplained_detections = _not_evaluated(
                event,
                "unexplained_detections",
                "the supplied surface propagation result has no evaluated observations",
                "first-order surface-fire model",
                evaluated_at,
            )
    else:
        unexplained_detections = _not_evaluated(
            event,
            "unexplained_detections",
            "no explicit unexplained-observation set or surface comparison was supplied",
            "surface propagation context",
            evaluated_at,
        )

    if surface_propagation is not None:
        outside, evaluated = _surface_result_evaluation(surface_propagation)
        if evaluated:
            mismatch_value = outside / evaluated
            surface_propagation_mismatch = _field(
                event,
                "surface_propagation_mismatch",
                round(mismatch_value, 6),
                "fraction",
                f"{outside} of {evaluated} evaluated comparison observation(s) fall outside the supplied surface envelope ({mismatch_value:.2f}).",
                "first-order surface-fire model",
                evaluated_at,
                limitations=tuple(surface_propagation.limitations)
                + (
                    "This is a compatibility mismatch, not a cause or responsibility finding.",
                ),
                details={
                    "outside_count": outside,
                    "evaluated_count": evaluated,
                    "compatibility": surface_propagation.compatibility.value,
                },
            )
        else:
            surface_propagation_mismatch = _not_evaluated(
                event,
                "surface_propagation_mismatch",
                "the supplied surface propagation result has no evaluated observations",
                "first-order surface-fire model",
                evaluated_at,
                limitations=surface_propagation.limitations,
            )
    elif raw_surface is not None:
        outside, evaluated, _outside_indices = raw_surface
        surface_propagation_mismatch = _field(
            event,
            "surface_propagation_mismatch",
            round(outside / evaluated, 6),
            "fraction",
            f"{outside} of {evaluated} post-origin observations fall outside the first-order surface envelope ({outside / evaluated:.2f}).",
            "NASA FIRMS + first-order surface-fire model",
            evaluated_at,
            limitations=(
                "This is a first-order compatibility mismatch, not a cause or responsibility finding.",
                "The model does not represent underground peat propagation.",
            ),
            details={"outside_count": outside, "evaluated_count": evaluated},
        )
    else:
        surface_propagation_mismatch = _not_evaluated(
            event,
            "surface_propagation_mismatch",
            "no surface propagation comparison or historical wind direction was supplied",
            "surface propagation context",
            evaluated_at,
        )

    return FireComplexityEvidence(
        event_id=event.event_id,
        duration=duration,
        observation_count=observation_count,
        spatial_extent=spatial_extent,
        centroid_movement=centroid_movement,
        directional_consistency=directional_consistency,
        wind_alignment=wind_alignment,
        frp_variability=frp_variability,
        distinct_thermal_lobes=distinct_thermal_lobes,
        peat_overlap=peat_overlap,
        nearby_event_count=nearby_event_count,
        historical_recurrence=historical_recurrence,
        unexplained_detections=unexplained_detections,
        surface_propagation_mismatch=surface_propagation_mismatch,
        evaluated_at=evaluated_at,
    )


compute_complexity_evidence = compute_fire_complexity


def to_evidence_objects(result: FireComplexityEvidence) -> list[dict[str, Any]]:
    """Module-level serializer matching the enrichment modules' API."""

    return result.to_evidence_objects()


__all__ = [
    "ALGORITHM_VERSION",
    "FIELD_NAMES",
    "ComplexityEvidenceStatus",
    "ComplexityField",
    "FireComplexityEvidence",
    "compute_complexity_evidence",
    "compute_fire_complexity",
    "to_evidence_objects",
]
