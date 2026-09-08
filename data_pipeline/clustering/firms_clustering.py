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
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

EARTH_RADIUS_KM = 6371.0088

DEFAULT_SPATIAL_THRESHOLD_KM = 2.0
DEFAULT_TEMPORAL_THRESHOLD_HOURS = 72.0


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
    digest = hashlib.sha1("|".join(keys).encode()).hexdigest()[:10]
    return f"FE-{first_dt.strftime('%Y%m%d')}-{digest}"


def _summarize_cluster(observations: pd.DataFrame, acq_dt: pd.Series, indices: list[int]) -> FireEvent:
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
    )


def cluster_events(
    observations: pd.DataFrame,
    spatial_threshold_km: float = DEFAULT_SPATIAL_THRESHOLD_KM,
    temporal_threshold_hours: float = DEFAULT_TEMPORAL_THRESHOLD_HOURS,
) -> tuple[list[FireEvent], pd.DataFrame]:
    """Cluster `observations` (must have latitude/longitude/acq_date/
    acq_time; frp/satellite/instrument are used when present) into
    FireEvents.

    Returns `(events, annotated)`: `annotated` is `observations` with one
    added `event_id` column -- the original rows are otherwise untouched,
    so raw FIRMS observations stay available exactly as fetched, not just
    the compressed events. Render events and raw hotspots as two separate
    things using this pair, not one merged table.
    """
    observations = observations.reset_index(drop=True)
    n = len(observations)
    if n == 0:
        return [], observations.assign(event_id=pd.Series(dtype=str))

    acq_dt = _acq_datetime(observations["acq_date"], observations["acq_time"])
    ref_lat = float(observations["latitude"].mean())
    x_km, y_km = _project_to_km(
        observations["latitude"].to_numpy(), observations["longitude"].to_numpy(), ref_lat
    )

    tree = cKDTree(np.column_stack([x_km, y_km]))
    pairs = tree.query_pairs(r=spatial_threshold_km, output_type="ndarray")

    uf = _UnionFind(n)
    if len(pairs):
        times = acq_dt.to_numpy()
        gap_hours = np.abs((times[pairs[:, 0]] - times[pairs[:, 1]]) / np.timedelta64(1, "h"))
        for i, j in pairs[gap_hours <= temporal_threshold_hours]:
            uf.union(int(i), int(j))

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(uf.find(i), []).append(i)

    events: list[FireEvent] = []
    event_ids: list[str] = [""] * n
    for indices in clusters.values():
        fire_event = _summarize_cluster(observations, acq_dt, indices)
        events.append(fire_event)
        for i in indices:
            event_ids[i] = fire_event.event_id

    annotated = observations.copy()
    annotated["event_id"] = event_ids

    events.sort(key=lambda e: e.first_detection)
    return events, annotated


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

    events, annotated = cluster_events(observations)
    print(f"{len(observations)} FIRMS observations -> {len(events)} coherent FireEvents "
          f"(spatial_threshold={DEFAULT_SPATIAL_THRESHOLD_KM}km, temporal_threshold={DEFAULT_TEMPORAL_THRESHOLD_HOURS}h)")

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
