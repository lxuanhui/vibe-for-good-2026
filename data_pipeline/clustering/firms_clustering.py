"""Group raw FIRMS hotspots into coherent FireEvents.

A single VIIRS/MODIS detection is one 375m (or 1km) pixel flagged hot for
one satellite overpass -- not an independently significant fire. A real
fire complex produces dozens to thousands of these over its lifetime as it
spreads and as the satellite re-passes. This module's job is exactly the
compression `Environmental_Assurance_Spec.md` (S9) calls for: raw
observations -> coherent FireEvents, with every event still linked back to
the observations it came from.

## Algorithm

Two detections are graph-connected if they are both:
  - within `spatial_threshold_km` of each other (great-circle distance,
    approximated via an equirectangular projection -- accurate enough at
    Indonesia's regional extent, not intended for polar or global use), AND
  - within `temporal_threshold_hours` of each other (acq_date + acq_time).

FireEvents are the connected components of that graph (single-linkage
spatiotemporal clustering, built with a cKDTree spatial index so this
doesn't degrade to an O(n^2) pairwise scan -- 21,519 points at 2km/72h
resolves in about a second). This is deliberately simple, not ST-DBSCAN or
a density-based method: a spike-appropriate baseline the real ingestion
worker can replace once there is a labelled validation set to tune against
(see issue #8, golden historical regression cases).

## Splitting temporally disconnected clusters

Requiring *both* constraints on every edge, not just spatial proximity,
is what makes this split correctly: two detections at the same location
90 days apart -- burn, go cold, reignite -- are NOT connected unless some
chain of intermediate detections bridges the gap within
`temporal_threshold_hours` at each hop. No separate "split" pass is needed;
it falls out of the graph construction.

## Known limitation: single-linkage chaining

Because connectivity is transitive, a long-lived, slowly-drifting fire
complex can walk kilometers from where it started over its lifetime and
still correctly form one event -- but the same chaining can, in principle,
bridge two genuinely distinct nearby fires if their detections happen to
interleave in space and time closely enough. This is a known tradeoff of
single-linkage clustering, not a solved problem here; `spatial_extent_km`
and `duration_hours` on the resulting event are exactly the signals a
human reviewer (or the Fire Complexity scoring in issue #12) would use to
notice an event that looks too sprawling to be one coherent episode.

## Field naming

Fields here are deliberately a *subset* of the canonical `FireEvent` type
(spec S9): `id`, `firstDetected`, `lastDetected`, `observationCount`,
`centroid`, `bbox`, `peakFrp` map directly (snake_case here, matching this
package's existing convention in `common/result.py` -- not the frontend's
camelCase, since data_pipeline does not serve the API yet). `scopeId` and
`scopeRelation` are intentionally absent: they need an audit scope, which
does not exist at this layer (see issues #56-63). `mean_frp`,
`duration_hours`, `spatial_extent_km`, and `sensor_mix` are additional
metrics this issue's acceptance criteria asked for, beyond the spec's
required fields.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

EARTH_RADIUS_KM = 6371.0088
# Bumped when the linking rule or the event summary changes in a way that
# would re-cluster the same observations differently. The parameters below
# are recorded next to it wherever events are written, so an artifact says
# what produced it.
ALGORITHM_VERSION = "firms-single-linkage-v1"

DEFAULT_SPATIAL_THRESHOLD_KM = 2.0
DEFAULT_TEMPORAL_THRESHOLD_HOURS = 72.0

# Guardrails, not tuning advice. A VIIRS pixel is 375 m, so a link radius
# well past a few km stops describing one fire and starts describing a
# district; 50 km also keeps cKDTree.query_pairs from producing a pair list
# that scales like n^2 over a 20k-point season. 720 h is 30 days, longer than
# any FIRMS fetch window this pipeline uses (day_range caps at 5) and long
# enough to chain a whole dry season into one event. Anything past these is
# a typo, not an experiment.
MAX_SPATIAL_THRESHOLD_KM = 50.0
MAX_TEMPORAL_THRESHOLD_HOURS = 720.0

# Development overrides, read only by `ClusteringParameters.from_env()`. The
# algorithm never reads the environment on its own: a caller that wants
# overrides asks for them explicitly, and says so in its output.
SPATIAL_ENV_VAR = "FIRMS_CLUSTER_SPATIAL_KM"
TEMPORAL_ENV_VAR = "FIRMS_CLUSTER_TEMPORAL_HOURS"


@dataclass(frozen=True)
class ClusteringParameters:
    """The two thresholds that decide whether two detections link.

    One place for both, so a demo run can widen or tighten them without
    editing the algorithm, and so whatever consumed the result can record
    which values produced it. Invalid values raise here, at construction,
    rather than surfacing as an empty or all-in-one event list later.
    """

    spatial_threshold_km: float = DEFAULT_SPATIAL_THRESHOLD_KM
    temporal_threshold_hours: float = DEFAULT_TEMPORAL_THRESHOLD_HOURS
    # Where the values came from: "default", "explicit" or "env". Diagnostic
    # only; two parameter sets with equal thresholds cluster identically.
    source: str = "default"

    def __post_init__(self) -> None:
        _check_threshold(
            "spatial_threshold_km", self.spatial_threshold_km, MAX_SPATIAL_THRESHOLD_KM
        )
        _check_threshold(
            "temporal_threshold_hours",
            self.temporal_threshold_hours,
            MAX_TEMPORAL_THRESHOLD_HOURS,
        )

    @property
    def is_default(self) -> bool:
        return (
            self.spatial_threshold_km == DEFAULT_SPATIAL_THRESHOLD_KM
            and self.temporal_threshold_hours == DEFAULT_TEMPORAL_THRESHOLD_HOURS
        )

    @classmethod
    def from_env(
        cls, environ: dict[str, str] | None = None
    ) -> ClusteringParameters:
        """Defaults, overridden by FIRMS_CLUSTER_SPATIAL_KM /
        FIRMS_CLUSTER_TEMPORAL_HOURS when set. A malformed value raises
        naming the variable, rather than silently falling back to the
        default, because a developer who set it meant it."""
        environ = os.environ if environ is None else environ
        values: dict[str, float] = {}
        for name, variable in (
            ("spatial_threshold_km", SPATIAL_ENV_VAR),
            ("temporal_threshold_hours", TEMPORAL_ENV_VAR),
        ):
            raw = environ.get(variable, "").strip()
            if not raw:
                continue
            try:
                values[name] = float(raw)
            except ValueError:
                raise ValueError(f"{variable} must be a number, got {raw!r}") from None
        if not values:
            return cls()
        return cls(**values, source="env")

    def to_dict(self) -> dict[str, Any]:
        return {
            "spatial_threshold_km": self.spatial_threshold_km,
            "temporal_threshold_hours": self.temporal_threshold_hours,
            "source": self.source,
            "algorithm_version": ALGORITHM_VERSION,
        }


def _check_threshold(name: str, value: Any, maximum: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {value!r}")
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")
    if value > maximum:
        raise ValueError(f"{name} must be at most {maximum:g}, got {value!r}")


def resolve_parameters(
    spatial_threshold_km: float | None = None,
    temporal_threshold_hours: float | None = None,
    *,
    parameters: ClusteringParameters | None = None,
) -> ClusteringParameters:
    """One rule for every entry point: a `parameters` object wins outright,
    explicit thresholds override the defaults one at a time, and nothing
    here reads the environment (see `ClusteringParameters.from_env`)."""
    if parameters is not None:
        if spatial_threshold_km is not None or temporal_threshold_hours is not None:
            raise ValueError("pass either parameters or individual thresholds, not both")
        return parameters
    if spatial_threshold_km is None and temporal_threshold_hours is None:
        return ClusteringParameters()
    return ClusteringParameters(
        spatial_threshold_km=(
            DEFAULT_SPATIAL_THRESHOLD_KM if spatial_threshold_km is None else spatial_threshold_km
        ),
        temporal_threshold_hours=(
            DEFAULT_TEMPORAL_THRESHOLD_HOURS
            if temporal_threshold_hours is None
            else temporal_threshold_hours
        ),
        source="explicit",
    )


@dataclass
class FireEvent:
    """One coherent cluster of FIRMS detections. `observation_indices` are
    positional indices into the observations DataFrame passed to
    `cluster_events` -- the link back to the raw points this event
    compresses, required so nothing downstream has to re-derive it."""

    event_id: str
    observation_indices: list[int]
    first_detection: str
    last_detection: str
    duration_hours: float
    observation_count: int
    centroid: tuple[float, float]  # (lat, lon)
    bbox: tuple[float, float, float, float]  # (west, south, east, north)
    spatial_extent_km: float
    max_frp: float | None
    mean_frp: float | None
    sensor_mix: list[str] = field(default_factory=list)
    # Why these observations are one event: how many accepted links hold the
    # component together, and the loosest of them. A large event whose
    # widest link sits right at both thresholds was chain-merged; one whose
    # links are all short and same-day is a compact complex. Zero links is a
    # singleton.
    link_count: int = 0
    max_link_gap_hours: float = 0.0
    max_link_distance_km: float = 0.0


class _UnionFind:
    """Disjoint-set with path compression + union by rank -- connected
    components of the spatiotemporal graph are the FireEvents."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _acq_datetime(acq_date: pd.Series, acq_time: pd.Series) -> pd.Series:
    """FIRMS acq_time is HHMM UTC as an int (e.g. 455 == 04:55); acq_date
    is a plain calendar date. Combine into one UTC timestamp per row."""
    hhmm = acq_time.astype(int).astype(str).str.zfill(4)
    return pd.to_datetime(
        acq_date.astype(str) + " " + hhmm.str[:2] + ":" + hhmm.str[2:], utc=True
    )


def _project_to_km(lat: np.ndarray, lon: np.ndarray, ref_lat: float) -> tuple[np.ndarray, np.ndarray]:
    """Equirectangular approximation: x scaled by cos(ref_lat) so degrees
    of longitude near Indonesia's near-equatorial latitudes convert to a
    consistent km distance. Good enough for a country-scale bbox; not a
    general-purpose geodesy tool."""
    x_km = np.radians(lon) * EARTH_RADIUS_KM * np.cos(np.radians(ref_lat))
    y_km = np.radians(lat) * EARTH_RADIUS_KM
    return x_km, y_km


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r, lat2_r, lon2_r = (np.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return float(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a)))


def _sensor_mix(sub: pd.DataFrame) -> list[str]:
    if "satellite" in sub.columns and "instrument" in sub.columns:
        combos = sub["satellite"].astype(str) + "/" + sub["instrument"].astype(str)
    elif "instrument" in sub.columns:
        combos = sub["instrument"].astype(str)
    elif "satellite" in sub.columns:
        combos = sub["satellite"].astype(str)
    else:
        return []
    return sorted(combos.unique().tolist())


def _stable_event_id(sub: pd.DataFrame, first_dt: pd.Timestamp) -> str:
    """Deterministic across runs and independent of processing/row order:
    hashes the sorted set of constituent detections' own natural keys, so
    the same physical group of points always yields the same id."""
    keys = sorted(
        f"{row['latitude']:.5f},{row['longitude']:.5f},{row['acq_date']},{row['acq_time']}"
        for row in sub.to_dict("records")
    )
    # Not a security context -- just a short deterministic fingerprint of the
    # constituent keys, so usedforsecurity=False is accurate, not a suppression.
    digest = hashlib.sha1("|".join(keys).encode(), usedforsecurity=False).hexdigest()[:10]
    return f"FE-{first_dt.strftime('%Y%m%d')}-{digest}"


def _summarize_cluster(
    observations: pd.DataFrame,
    acq_dt: pd.Series,
    indices: list[int],
    links: tuple[int, float, float] = (0, 0.0, 0.0),
) -> FireEvent:
    sub = observations.iloc[indices]
    times = acq_dt.iloc[indices]
    first_dt, last_dt = times.min(), times.max()

    lat, lon = sub["latitude"], sub["longitude"]
    bbox = (float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max()))

    has_frp = "frp" in sub.columns and sub["frp"].notna().any()

    return FireEvent(
        event_id=_stable_event_id(sub, first_dt),
        observation_indices=list(indices),
        first_detection=first_dt.isoformat(),
        last_detection=last_dt.isoformat(),
        duration_hours=(last_dt - first_dt).total_seconds() / 3600.0,
        observation_count=len(indices),
        centroid=(float(lat.mean()), float(lon.mean())),
        bbox=bbox,
        spatial_extent_km=_haversine_km(bbox[1], bbox[0], bbox[3], bbox[2]),
        max_frp=float(sub["frp"].max()) if has_frp else None,
        mean_frp=float(sub["frp"].mean()) if has_frp else None,
        sensor_mix=_sensor_mix(sub),
        link_count=links[0],
        max_link_gap_hours=links[1],
        max_link_distance_km=links[2],
    )


@dataclass(frozen=True)
class LinkStatistics:
    """What the linking pass saw before components were formed. The gap
    between `spatial_pairs` and `accepted_pairs` is the temporal rule doing
    work: pairs close enough in space that were kept apart by time."""

    spatial_pairs: int
    accepted_pairs: int
    max_accepted_gap_hours: float
    max_accepted_distance_km: float

    @property
    def rejected_by_time_pairs(self) -> int:
        return self.spatial_pairs - self.accepted_pairs


@dataclass(frozen=True)
class ClusteringRun:
    """`cluster_events` plus the linking statistics it would otherwise throw
    away. Same events, same annotated frame; nothing is re-derived."""

    events: list[FireEvent]
    annotated: pd.DataFrame
    parameters: ClusteringParameters
    links: LinkStatistics


def cluster_run(
    observations: pd.DataFrame,
    parameters: ClusteringParameters | None = None,
) -> ClusteringRun:
    """Cluster `observations` (must have latitude/longitude/acq_date/
    acq_time; frp/satellite/instrument are used when present) into
    FireEvents, keeping the per-event and per-run link statistics.

    `cluster_events` is the same computation with the statistics dropped;
    prefer this when the caller will report why a window produced N events.
    """
    parameters = ClusteringParameters() if parameters is None else parameters
    observations = observations.reset_index(drop=True)
    n = len(observations)
    if n == 0:
        return ClusteringRun(
            [],
            observations.assign(event_id=pd.Series(dtype=str)),
            parameters,
            LinkStatistics(0, 0, 0.0, 0.0),
        )

    acq_dt = _acq_datetime(observations["acq_date"], observations["acq_time"])
    ref_lat = float(observations["latitude"].mean())
    x_km, y_km = _project_to_km(
        observations["latitude"].to_numpy(), observations["longitude"].to_numpy(), ref_lat
    )

    tree = cKDTree(np.column_stack([x_km, y_km]))
    pairs = tree.query_pairs(r=parameters.spatial_threshold_km, output_type="ndarray")

    uf = _UnionFind(n)
    accepted = np.empty((0, 2), dtype=int)
    accepted_gaps = np.empty(0)
    accepted_distances = np.empty(0)
    if len(pairs):
        times = acq_dt.to_numpy()
        gap_hours = np.abs((times[pairs[:, 0]] - times[pairs[:, 1]]) / np.timedelta64(1, "h"))
        keep = gap_hours <= parameters.temporal_threshold_hours
        accepted = pairs[keep]
        accepted_gaps = gap_hours[keep]
        # Same planar metric the tree searched with, so a reported distance
        # is the one the threshold was compared against.
        accepted_distances = np.hypot(
            x_km[accepted[:, 0]] - x_km[accepted[:, 1]],
            y_km[accepted[:, 0]] - y_km[accepted[:, 1]],
        )
        for i, j in accepted:
            uf.union(int(i), int(j))

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(uf.find(i), []).append(i)

    # Per-component link stats, attributed by either endpoint's root (both
    # endpoints share one by construction).
    link_stats: dict[int, list[float]] = {}
    for (i, _j), gap, distance in zip(accepted, accepted_gaps, accepted_distances, strict=True):
        stats = link_stats.setdefault(uf.find(int(i)), [0, 0.0, 0.0])
        stats[0] += 1
        stats[1] = max(stats[1], float(gap))
        stats[2] = max(stats[2], float(distance))

    events: list[FireEvent] = []
    event_ids: list[str] = [""] * n
    for root, indices in clusters.items():
        count, gap, distance = link_stats.get(root, [0, 0.0, 0.0])
        fire_event = _summarize_cluster(
            observations, acq_dt, indices, (int(count), gap, distance)
        )
        events.append(fire_event)
        for i in indices:
            event_ids[i] = fire_event.event_id

    annotated = observations.copy()
    annotated["event_id"] = event_ids

    events.sort(key=lambda e: e.first_detection)
    return ClusteringRun(
        events,
        annotated,
        parameters,
        LinkStatistics(
            spatial_pairs=len(pairs),
            accepted_pairs=len(accepted),
            max_accepted_gap_hours=float(accepted_gaps.max()) if len(accepted) else 0.0,
            max_accepted_distance_km=(
                float(accepted_distances.max()) if len(accepted) else 0.0
            ),
        ),
    )


def cluster_events(
    observations: pd.DataFrame,
    spatial_threshold_km: float | None = None,
    temporal_threshold_hours: float | None = None,
    *,
    parameters: ClusteringParameters | None = None,
) -> tuple[list[FireEvent], pd.DataFrame]:
    """Cluster `observations` (must have latitude/longitude/acq_date/
    acq_time; frp/satellite/instrument are used when present) into
    FireEvents.

    Returns `(events, annotated)`: `annotated` is `observations` with one
    added `event_id` column -- the original rows are otherwise untouched,
    so raw FIRMS observations stay available exactly as fetched, not just
    the compressed events. Render events and raw hotspots as two separate
    things using this pair, not one merged table.

    Thresholds may be given individually (the original signature) or as one
    `ClusteringParameters`; both validate the same way. Callers that want to
    explain the result use `cluster_run`, which returns the link statistics
    this discards.
    """
    run = cluster_run(
        observations,
        resolve_parameters(spatial_threshold_km, temporal_threshold_hours, parameters=parameters),
    )
    return run.events, run.annotated


DEFAULT_LOBE_DISTANCE_KM = 1.0


def event_lobes(
    event: FireEvent,
    observations: pd.DataFrame,
    lobe_distance_km: float = DEFAULT_LOBE_DISTANCE_KM,
) -> list[FireEvent]:
    """Split one event's own detections into spatial lobes, for reading a
    mega-event as "1 complex, N lobes" without re-clustering anything.

    Lobes are connected components under a spatial-only rule at
    `lobe_distance_km`, ignoring time, over exactly the observations the
    event already owns. Cluster membership is untouched: the lobes partition
    the event, and their ids are derived from their own detections so they
    are stable across runs.

    The lobe distance has to be *below* the clustering radius to show
    anything. Every pair the clustering linked was within
    `spatial_threshold_km`, so a spatial-only pass at that same radius
    always returns one lobe. 1 km against the 2 km default is a meaningful
    split at VIIRS resolution (375 m pixels); it is a reading aid, not a
    second clustering, and nothing downstream should treat a lobe as an
    event.
    """
    _check_threshold("lobe_distance_km", lobe_distance_km, MAX_SPATIAL_THRESHOLD_KM)
    observations = observations.reset_index(drop=True)
    indices = list(event.observation_indices)
    if not indices:
        return []
    sub = observations.iloc[indices]
    acq_dt = _acq_datetime(observations["acq_date"], observations["acq_time"])
    ref_lat = float(sub["latitude"].mean())
    x_km, y_km = _project_to_km(sub["latitude"].to_numpy(), sub["longitude"].to_numpy(), ref_lat)
    tree = cKDTree(np.column_stack([x_km, y_km]))
    uf = _UnionFind(len(indices))
    for i, j in tree.query_pairs(r=lobe_distance_km, output_type="ndarray"):
        uf.union(int(i), int(j))
    components: dict[int, list[int]] = {}
    for position, index in enumerate(indices):
        components.setdefault(uf.find(position), []).append(index)
    lobes = [_summarize_cluster(observations, acq_dt, members) for members in components.values()]
    lobes.sort(key=lambda lobe: (-lobe.observation_count, lobe.first_detection, lobe.event_id))
    return lobes


def _event_row(e: FireEvent) -> dict:
    return {
        "event_id": e.event_id,
        "observation_count": e.observation_count,
        "first_detection": e.first_detection,
        "last_detection": e.last_detection,
        "duration_hours": round(e.duration_hours, 2),
        "centroid_lat": e.centroid[0],
        "centroid_lon": e.centroid[1],
        "bbox_west": e.bbox[0],
        "bbox_south": e.bbox[1],
        "bbox_east": e.bbox[2],
        "bbox_north": e.bbox[3],
        "spatial_extent_km": round(e.spatial_extent_km, 3),
        "max_frp": e.max_frp,
        "mean_frp": round(e.mean_frp, 2) if e.mean_frp is not None else None,
        "sensor_mix": "|".join(e.sensor_mix),
        "link_count": e.link_count,
        "max_link_gap_hours": round(e.max_link_gap_hours, 2),
        "max_link_distance_km": round(e.max_link_distance_km, 3),
    }


def _demo() -> None:
    # Imported here, not at module level, so `cluster_events` stays usable
    # without pulling in the FIRMS fetch/config stack for callers who
    # already have an observations DataFrame from somewhere else.
    from data_pipeline.config import OUTPUT_DIR, SUMATRA_KALIMANTAN_BBOX
    from data_pipeline.sources.nasa_firms import fetch_area

    print("== FIRMS spatio-temporal clustering ==")
    sample_path = OUTPUT_DIR / "firms_2019_haze_sample.csv"
    if sample_path.exists():
        observations = pd.read_csv(sample_path)
        print(f"Loaded {len(observations)} observations from {sample_path}")
    else:
        print("No cached sample on disk -- fetching 2019-09-01 + 5d over Sumatra/Kalimantan from FIRMS.")
        observations = fetch_area("VIIRS_SNPP_SP", SUMATRA_KALIMANTAN_BBOX, day_range=5, start_date="2019-09-01")

    parameters = ClusteringParameters.from_env()
    events, annotated = cluster_events(observations, parameters=parameters)
    print(f"{len(observations)} FIRMS observations -> {len(events)} coherent FireEvents "
          f"(spatial_threshold={parameters.spatial_threshold_km}km, "
          f"temporal_threshold={parameters.temporal_threshold_hours}h, "
          f"parameters from {parameters.source})")

    sizes = sorted((e.observation_count for e in events), reverse=True)
    singleton_count = sum(1 for s in sizes if s == 1)
    print(f"largest 5 events by observation count: {sizes[:5]}")
    print(f"singleton events (no spatiotemporal neighbor at all): {singleton_count}")

    biggest = max(events, key=lambda e: e.observation_count)
    print(
        f"largest event: {biggest.event_id}, {biggest.observation_count} obs, "
        f"{biggest.first_detection} -> {biggest.last_detection} ({biggest.duration_hours:.1f}h), "
        f"centroid={biggest.centroid}, spatial_extent_km={biggest.spatial_extent_km:.1f}, "
        f"max_frp={biggest.max_frp}, sensor_mix={biggest.sensor_mix}"
    )

    events_out = OUTPUT_DIR / "firms_events_2019_haze_sample.csv"
    pd.DataFrame([_event_row(e) for e in events]).to_csv(events_out, index=False)
    observations_out = OUTPUT_DIR / "firms_observations_with_event_id.csv"
    annotated.to_csv(observations_out, index=False)
    print(f"Saved {len(events)} events to {events_out}")
    print(f"Saved {len(annotated)} annotated observations (raw + event_id) to {observations_out}\n")


if __name__ == "__main__":
    _demo()
