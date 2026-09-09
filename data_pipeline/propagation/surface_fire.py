"""A transparent, first-order surface-fire growth compatibility model.

This module asks a deliberately narrow question: given an origin, elapsed
time, and a historical wind direction, is a later hotspot cluster inside a
simple wind-oriented surface-fire envelope?  It is a plausibility screen, not
an operational fire forecast, forensic attribution model, or causal finding.

The envelope uses three caller-supplied rates.  Head and back spread define an
asymmetric major axis; flank spread defines the minor axis.  Wind directions
follow the meteorological convention (the direction the wind comes from), so
the ellipse is oriented 180 degrees from that value.  This model does not
represent underground peat propagation or infer it from a surface envelope.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from data_pipeline.clustering.firms_clustering import FireEvent

EARTH_RADIUS_KM = 6371.0088
ALGORITHM_VERSION = "surface-fire-ellipse-v1"
MODEL_LABEL = "First-order surface-fire compatibility estimate"
MODEL_LIMITATIONS = (
    "homogeneous fuel approximation",
    "simplified terrain and fuel behavior",
    "historical wind direction is treated as representative",
    "non-spotting model; isolated spotting may fall outside the envelope",
    "not a validated operational fire-behavior forecast",
    "does not model underground peat propagation",
)


def _normalize_degrees(value: float) -> float:
    normalized = value % 360.0
    return 0.0 if math.isclose(normalized, 360.0, abs_tol=1e-12) else normalized


class SurfaceFireCompatibility(StrEnum):
    """Compatibility routing, not a cause, responsibility, or legal finding."""

    COMPATIBLE = "COMPATIBLE"
    PARTIAL = "PARTIAL"
    INCOMPATIBLE = "INCOMPATIBLE"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class SurfaceFireSpreadParameters:
    """Configurable first-order spread rates in kilometres per hour."""

    head_spread_kmh: float = 5.0
    back_spread_kmh: float = 1.0
    flank_spread_kmh: float = 2.5

    def __post_init__(self) -> None:
        values = (self.head_spread_kmh, self.back_spread_kmh, self.flank_spread_kmh)
        if not all(
            math.isfinite(float(value)) and float(value) > 0 for value in values
        ):
            raise ValueError(
                "head, back, and flank spread rates must be positive and finite"
            )
        if self.head_spread_kmh < self.back_spread_kmh:
            raise ValueError("head_spread_kmh must be at least back_spread_kmh")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


DEFAULT_SPREAD_PARAMETERS = SurfaceFireSpreadParameters()


@dataclass(frozen=True)
class WindSample:
    """One historical wind observation; direction is where wind comes from."""

    observed_at: str
    direction_from_deg: float
    speed_kmh: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.direction_from_deg)):
            raise ValueError("wind direction must be finite")
        if self.speed_kmh is not None and (
            not math.isfinite(float(self.speed_kmh)) or self.speed_kmh < 0
        ):
            raise ValueError("wind speed must be finite and non-negative")


@dataclass(frozen=True)
class SurfaceFireEnvelope:
    """Projected ellipse at one elapsed time from an observed origin."""

    origin: tuple[float, float]  # latitude, longitude
    elapsed_hours: float
    orientation_deg: float  # downwind travel direction, clockwise from north
    head_distance_km: float
    back_distance_km: float
    flank_distance_km: float
    center_offset_km: float
    semi_major_km: float
    semi_minor_km: float
    origin_time: str | None = None
    model_version: str = ALGORITHM_VERSION
    label: str = MODEL_LABEL
    limitations: tuple[str, ...] = MODEL_LIMITATIONS

    def contains_point(
        self, point: tuple[float, float], tolerance_km: float = 0.0
    ) -> bool:
        """Return whether a lat/lon point falls inside this projected envelope."""

        east_km, north_km = _local_offset_km(self.origin, point)
        heading = math.radians(self.orientation_deg)
        along_axis = east_km * math.sin(heading) + north_km * math.cos(heading)
        across_axis = east_km * math.cos(heading) - north_km * math.sin(heading)
        major = self.semi_major_km + max(float(tolerance_km), 0.0)
        minor = self.semi_minor_km + max(float(tolerance_km), 0.0)
        if major <= 0 or minor <= 0:
            return math.hypot(along_axis, across_axis) <= max(float(tolerance_km), 0.0)
        normalized = ((along_axis - self.center_offset_km) / major) ** 2 + (
            across_axis / minor
        ) ** 2
        return normalized <= 1.0

    def to_polygon(self, n_points: int = 48) -> list[list[float]]:
        """Sample the envelope boundary as a closed ``[lon, lat]`` ring.

        Exact inverse of ``contains_point``'s rotated-ellipse test composed
        with the module's equirectangular ``_local_offset_km`` projection --
        not an approximation. The along/across -> east/north rotation matrix
        is its own inverse (its rows are orthonormal and its determinant is
        -1), so the same sin/cos pair used to build ``along_axis``/
        ``across_axis`` in ``contains_point`` maps a sampled ellipse point
        straight back to an east/north offset.
        """

        if n_points < 3:
            raise ValueError("n_points must be at least 3")
        heading = math.radians(self.orientation_deg)
        sin_h, cos_h = math.sin(heading), math.cos(heading)
        origin_lat, origin_lon = self.origin
        ring: list[list[float]] = []
        for index in range(n_points):
            theta = 2.0 * math.pi * index / n_points
            along = self.center_offset_km + self.semi_major_km * math.cos(theta)
            across = self.semi_minor_km * math.sin(theta)
            east_km = along * sin_h + across * cos_h
            north_km = along * cos_h - across * sin_h
            lat = origin_lat + math.degrees(north_km / EARTH_RADIUS_KM)
            mean_lat = math.radians((origin_lat + lat) / 2.0)
            lon = origin_lon + math.degrees(
                east_km / (EARTH_RADIUS_KM * math.cos(mean_lat))
            )
            ring.append([round(lon, 6), round(lat, 6)])
        ring.append(list(ring[0]))
        return ring

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["origin"] = list(self.origin)
        result["limitations"] = list(self.limitations)
        return result


@dataclass(frozen=True)
class SurfaceFireObservation:
    """A later cluster to compare with an origin envelope."""

    observation_id: str
    observed_at: str
    centroid: tuple[float, float]  # latitude, longitude


@dataclass(frozen=True)
class SurfaceFireObservationResult:
    observation_id: str
    observed_at: str
    elapsed_hours: float
    distance_km: float
    bearing_deg: float
    inside_expected_envelope: bool | None
    reason: str
    envelope: SurfaceFireEnvelope | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.envelope is not None:
            result["envelope"] = self.envelope.to_dict()
        return result


@dataclass(frozen=True)
class SurfaceFireCompatibilityResult:
    """Overall compatibility plus per-cluster, inspectable observations."""

    source_event_id: str
    compatibility: SurfaceFireCompatibility
    wind_direction_from_deg: float | None
    downwind_orientation_deg: float | None
    observations: tuple[SurfaceFireObservationResult, ...]
    observations_outside_expected_envelope: tuple[str, ...]
    model_version: str = ALGORITHM_VERSION
    model_label: str = MODEL_LABEL
    limitations: tuple[str, ...] = MODEL_LIMITATIONS

    @property
    def outside_observation_ids(self) -> tuple[str, ...]:
        """Short alias for map/report consumers."""

        return self.observations_outside_expected_envelope

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["compatibility"] = self.compatibility.value
        result["observations"] = [
            observation.to_dict() for observation in self.observations
        ]
        result["observations_outside_expected_envelope"] = list(
            self.observations_outside_expected_envelope
        )
        result["limitations"] = list(self.limitations)
        return result


def _validate_coordinate(point: tuple[float, float], name: str) -> tuple[float, float]:
    if len(point) != 2 or not all(math.isfinite(float(value)) for value in point):
        raise ValueError(f"{name} must contain two finite latitude/longitude values")
    latitude, longitude = float(point[0]), float(point[1])
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError(f"{name} contains an invalid latitude/longitude")
    return latitude, longitude


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed


def _haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = (math.radians(value) for value in (*first, *second))
    dlat, dlon = lat2 - lat1, lon2 - lon1
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


def _local_offset_km(
    origin: tuple[float, float], point: tuple[float, float]
) -> tuple[float, float]:
    """Return an equirectangular east/north offset for the local envelope."""

    mean_lat = math.radians((origin[0] + point[0]) / 2)
    east = math.radians(point[1] - origin[1]) * EARTH_RADIUS_KM * math.cos(mean_lat)
    north = math.radians(point[0] - origin[0]) * EARTH_RADIUS_KM
    return east, north


def project_surface_fire_envelope(
    origin: tuple[float, float],
    elapsed_hours: float,
    wind_direction_from_deg: float,
    parameters: SurfaceFireSpreadParameters = DEFAULT_SPREAD_PARAMETERS,
    *,
    origin_time: str | None = None,
) -> SurfaceFireEnvelope:
    """Project a wind-oriented head/back/flank ellipse from an origin."""

    origin = _validate_coordinate(origin, "origin")
    if not math.isfinite(float(elapsed_hours)) or elapsed_hours < 0:
        raise ValueError("elapsed_hours must be finite and non-negative")
    if not math.isfinite(float(wind_direction_from_deg)):
        raise ValueError("wind direction must be finite")

    elapsed_hours = float(elapsed_hours)
    head = parameters.head_spread_kmh * elapsed_hours
    back = parameters.back_spread_kmh * elapsed_hours
    flank = parameters.flank_spread_kmh * elapsed_hours
    return SurfaceFireEnvelope(
        origin=origin,
        elapsed_hours=elapsed_hours,
        orientation_deg=_normalize_degrees(float(wind_direction_from_deg) + 180.0),
        head_distance_km=head,
        back_distance_km=back,
        flank_distance_km=flank,
        center_offset_km=(head - back) / 2.0,
        semi_major_km=(head + back) / 2.0,
        semi_minor_km=flank,
        origin_time=origin_time,
    )


def _wind_sample_values(
    sample: WindSample | Mapping[str, Any] | float,
) -> tuple[float, float | None] | None:
    if isinstance(sample, WindSample):
        return float(sample.direction_from_deg), sample.speed_kmh
    if isinstance(sample, Mapping):
        direction = sample.get("direction_from_deg", sample.get("direction_deg"))
        if direction is None:
            direction = sample.get("dominant_wind_direction_deg")
        speed = sample.get("speed_kmh", sample.get("wind_speed_kmh"))
        if speed is None:
            speed_ms = sample.get("mean_wind_speed_ms")
            speed = None if speed_ms is None else float(speed_ms) * 3.6
    else:
        direction, speed = sample, None
    try:
        direction_value = float(direction)
        speed_value = None if speed is None else float(speed)
    except (TypeError, ValueError):
        return None
    if (
        not math.isfinite(direction_value)
        or speed_value is not None
        and (not math.isfinite(speed_value) or speed_value < 0)
    ):
        return None
    return direction_value, speed_value


def historical_wind_direction(
    history: Sequence[WindSample | Mapping[str, Any] | float],
) -> float | None:
    """Return a circular, speed-weighted mean meteorological wind direction."""

    values = [_wind_sample_values(sample) for sample in history]
    values = [value for value in values if value is not None]
    if not values:
        return None
    weights = [speed if speed is not None and speed > 0 else 1.0 for _, speed in values]
    x = sum(
        weight * math.sin(math.radians(direction))
        for (direction, _), weight in zip(values, weights)
    )
    y = sum(
        weight * math.cos(math.radians(direction))
        for (direction, _), weight in zip(values, weights)
    )
    if math.isclose(x, 0.0, abs_tol=1e-12) and math.isclose(y, 0.0, abs_tol=1e-12):
        return None
    return _normalize_degrees(math.degrees(math.atan2(x, y)))


def _observation_from_event(event: FireEvent) -> SurfaceFireObservation:
    return SurfaceFireObservation(
        observation_id=event.event_id,
        observed_at=event.first_detection,
        centroid=event.centroid,
    )


def compare_event_progression(
    source_event: FireEvent,
    subsequent_events: Sequence[FireEvent],
    *,
    wind_direction_from_deg: float | None = None,
    wind_history: Sequence[WindSample | Mapping[str, Any] | float] | None = None,
    parameters: SurfaceFireSpreadParameters = DEFAULT_SPREAD_PARAMETERS,
    tolerance_km: float = 0.0,
) -> SurfaceFireCompatibilityResult:
    """Compare later FireEvent centroids with envelopes projected from a source.

    Events that are not later than the source's first detection are ignored,
    preserving the distinction between a progression comparison and a raw
    proximity check.  If no historical wind direction is available, later
    observations are retained as ``NOT_EVALUATED`` rather than treated as
    outside evidence.
    """

    source_origin = _validate_coordinate(source_event.centroid, "source_event.centroid")
    source_time = _timestamp(source_event.first_detection)
    direction = wind_direction_from_deg
    if direction is None and wind_history:
        direction = historical_wind_direction(wind_history)
    if direction is not None and not math.isfinite(float(direction)):
        raise ValueError("wind direction must be finite")
    if not math.isfinite(float(tolerance_km)) or tolerance_km < 0:
        raise ValueError("tolerance_km must be finite and non-negative")

    observations: list[SurfaceFireObservationResult] = []
    for event in sorted(
        subsequent_events, key=lambda value: (value.first_detection, value.event_id)
    ):
        observed_at = _timestamp(event.first_detection)
        if observed_at <= source_time:
            continue
        elapsed_hours = (observed_at - source_time).total_seconds() / 3600.0
        point = _validate_coordinate(event.centroid, f"{event.event_id}.centroid")
        distance = _haversine_km(source_origin, point)
        bearing = _bearing_deg(source_origin, point)
        if direction is None:
            observations.append(
                SurfaceFireObservationResult(
                    observation_id=event.event_id,
                    observed_at=event.first_detection,
                    elapsed_hours=round(elapsed_hours, 3),
                    distance_km=round(distance, 3),
                    bearing_deg=round(bearing, 3),
                    inside_expected_envelope=None,
                    reason="Historical wind direction unavailable; compatibility not evaluated.",
                )
            )
            continue
        envelope = project_surface_fire_envelope(
            source_origin,
            elapsed_hours,
            direction,
            parameters,
            origin_time=source_event.first_detection,
        )
        inside = envelope.contains_point(point, tolerance_km=tolerance_km)
        observations.append(
            SurfaceFireObservationResult(
                observation_id=event.event_id,
                observed_at=event.first_detection,
                elapsed_hours=round(elapsed_hours, 3),
                distance_km=round(distance, 3),
                bearing_deg=round(bearing, 3),
                inside_expected_envelope=inside,
                reason=(
                    "Observed cluster falls inside the expected surface-fire envelope."
                    if inside
                    else "Observed cluster is outside the expected surface-fire envelope."
                ),
                envelope=envelope,
            )
        )

    outside = tuple(
        observation.observation_id
        for observation in observations
        if observation.inside_expected_envelope is False
    )
    evaluated = [observation.inside_expected_envelope for observation in observations]
    if direction is None or not evaluated:
        compatibility = SurfaceFireCompatibility.NOT_EVALUATED
    elif all(value is True for value in evaluated):
        compatibility = SurfaceFireCompatibility.COMPATIBLE
    elif any(value is True for value in evaluated):
        compatibility = SurfaceFireCompatibility.PARTIAL
    else:
        compatibility = SurfaceFireCompatibility.INCOMPATIBLE

    return SurfaceFireCompatibilityResult(
        source_event_id=source_event.event_id,
        compatibility=compatibility,
        wind_direction_from_deg=None
        if direction is None
        else _normalize_degrees(float(direction)),
        downwind_orientation_deg=None
        if direction is None
        else _normalize_degrees(float(direction) + 180.0),
        observations=tuple(observations),
        observations_outside_expected_envelope=outside,
    )
