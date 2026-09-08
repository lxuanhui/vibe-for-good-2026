"""Timed run of the automated pipeline for one representative FireEvent case.

Chains the pieces this repo already has -- FIRMS retrieval, spatio-temporal
clustering (issue #4), weather-window enrichment (issue #5), peat context
(issue #6) -- plus two pieces built only for this benchmark, scoped
narrowly on purpose:

- `find_neighbouring_events` is a lightweight, benchmark-local proximity
  lookup, NOT the `FireEventGraph` relationship model (issue #10). It only
  answers "how many other events are close enough in space and time that a
  manual analyst would have to notice them," with no relationship typing.
- Imagery metadata search reuses `sources/copernicus_cds.search()` directly
  rather than adding a scene-selection module (issue #13's job).

Every stage is timed independently with `time.perf_counter()` so
`AutomatedBenchmarkResult.stage_timings` shows where automated time actually
goes, not just a single opaque total. `find_neighbouring_events` and
`evidence_field_completeness` are pure (no network) and are what the tests
exercise directly; `run_automated_benchmark` is the only network-touching
entry point (besides its `_demo()`).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import pandas as pd

from data_pipeline.clustering.firms_clustering import FireEvent, cluster_events
from data_pipeline.config import OUTPUT_DIR, SUMATRA_KALIMANTAN_BBOX
from data_pipeline.enrichment import peat_context, weather_enrichment
from data_pipeline.sources import copernicus_cds
from data_pipeline.triage.stage1 import summarize_triage, triage_events

EARTH_RADIUS_KM = 6371.0088
DEFAULT_NEIGHBOUR_RADIUS_KM = 50.0
DEFAULT_NEIGHBOUR_WINDOW_DAYS = 30.0
DEFAULT_PEAT_BUFFER_KM = 5.0
PEAT_EVIDENCE_FIELDS_POSSIBLE = (
    4  # direct_intersection, footprint_fraction, buffer_fraction, distance_to_peat
)

# One command invocation runs the whole chain below; the only human
# interaction the automated path requires is selecting which FireEvent to
# investigate (here: the largest event in the cached sample, matching the
# case weather_enrichment/peat_context already demo against).
MANUAL_INTERACTIONS = 1

EVENTS_TO_REVIEW_QUEUE_NOTE = (
    "Stage-1 queue compression in this benchmark uses FIRMS confidence, FRP, and repeat "
    "observations plus spatially and temporally nearby FIRMS detections for every event. Optional "
    "land-cover, settlement, persistent heat-source, volcano/geothermal, and recent-rainfall "
    "context is not supplied for the full event collection; rules without evidence remain "
    "NOT_EVALUATED, and LIKELY_FIRE plus AMBIGUOUS events remain in the review queue."
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import numpy as np

    lat1_r, lon1_r, lat2_r, lon2_r = (np.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return float(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a)))


@dataclass(frozen=True)
class NeighbouringEvent:
    event_id: str
    distance_km: float
    time_gap_hours: float
    observation_count: int


def find_neighbouring_events(
    target: FireEvent,
    events: list[FireEvent],
    radius_km: float = DEFAULT_NEIGHBOUR_RADIUS_KM,
    window_days: float = DEFAULT_NEIGHBOUR_WINDOW_DAYS,
) -> list[NeighbouringEvent]:
    """Other events within `radius_km` of `target`'s centroid whose detection
    window is within `window_days` of `target`'s (0 gap if the windows
    overlap). Sorted nearest-first. Pure -- no network, no clustering."""
    target_start = pd.Timestamp(target.first_detection)
    target_end = pd.Timestamp(target.last_detection)

    neighbours: list[NeighbouringEvent] = []
    for e in events:
        if e.event_id == target.event_id:
            continue
        distance = _haversine_km(
            target.centroid[0], target.centroid[1], e.centroid[0], e.centroid[1]
        )
        if distance > radius_km:
            continue
        e_start = pd.Timestamp(e.first_detection)
        e_end = pd.Timestamp(e.last_detection)
        gap = max(e_start - target_end, target_start - e_end, pd.Timedelta(0))
        gap_hours = gap.total_seconds() / 3600.0
        if gap_hours > window_days * 24:
            continue
        neighbours.append(
            NeighbouringEvent(
                event_id=e.event_id,
                distance_km=round(distance, 3),
                time_gap_hours=round(gap_hours, 1),
                observation_count=e.observation_count,
            )
        )
    neighbours.sort(key=lambda n: n.distance_km)
    return neighbours


def evidence_field_completeness(
    weather_objects: list[dict], peat_objects: list[dict]
) -> dict:
    """Fraction of possible evidence fields actually populated for this
    FireEvent. A missing field means the underlying source genuinely had no
    data for that window/metric (both modules document `None` as never
    fabricated -- see their docstrings), not a bug here."""
    max_weather = (
        len(weather_enrichment.WINDOW_NAMES)
        * weather_enrichment.EVIDENCE_METRICS_PER_WINDOW
    )
    max_peat = PEAT_EVIDENCE_FIELDS_POSSIBLE
    weather_count = len(weather_objects)
    peat_count = len(peat_objects)
    total_possible = max_weather + max_peat
    total_present = weather_count + peat_count
    return {
        "weather_fields_present": weather_count,
        "weather_fields_possible": max_weather,
        "peat_fields_present": peat_count,
        "peat_fields_possible": max_peat,
        "completeness_fraction": round(total_present / total_possible, 4)
        if total_possible
        else None,
    }


@dataclass(frozen=True)
class StageTiming:
    stage: str
    seconds: float


@dataclass
class AutomatedBenchmarkResult:
    event_id: str
    observation_count: int
    event_count: int
    stage_timings: list[StageTiming]
    total_seconds: float
    observations_to_events_compression: float | None
    events_to_review_queue_compression: float | None
    review_queue_count: int
    triage_state_counts: dict[str, int]
    events_to_review_queue_note: str
    evidence_completeness: dict
    neighbouring_event_count: int
    imagery_scene_count: dict
    manual_interactions: int
    evidence_summary_path: str
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stage_timings"] = [
            {"stage": s.stage, "seconds": round(s.seconds, 3)}
            for s in self.stage_timings
        ]
        d["total_seconds"] = round(self.total_seconds, 3)
        return d


def _event_row(e: FireEvent) -> dict:
    return {
        "event_id": e.event_id,
        "first_detection": e.first_detection,
        "last_detection": e.last_detection,
        "duration_hours": round(e.duration_hours, 2),
        "observation_count": e.observation_count,
        "centroid": e.centroid,
        "bbox": e.bbox,
        "spatial_extent_km": round(e.spatial_extent_km, 3),
        "max_frp": e.max_frp,
        "mean_frp": e.mean_frp,
        "sensor_mix": e.sensor_mix,
    }


def run_automated_benchmark(
    buffer_km: float = DEFAULT_PEAT_BUFFER_KM,
) -> AutomatedBenchmarkResult:
    timings: list[StageTiming] = []
    t_start = time.perf_counter()

    def _stage(name, fn, *args, **kwargs):
        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        timings.append(StageTiming(name, time.perf_counter() - t0))
        return result

    sample_path = OUTPUT_DIR / "firms_2019_haze_sample.csv"
    if sample_path.exists():
        observations = _stage("retrieve_firms_observations", pd.read_csv, sample_path)
    else:
        from data_pipeline.sources.nasa_firms import fetch_area

        observations = _stage(
            "retrieve_firms_observations",
            fetch_area,
            "VIIRS_SNPP_SP",
            SUMATRA_KALIMANTAN_BBOX,
            day_range=5,
            start_date="2019-09-01",
        )

    events, _annotated = _stage(
        "reconstruct_event_chronology", cluster_events, observations
    )
    triage_results = _stage(
        "deterministic_stage1_triage", triage_events, events, observations
    )
    triage_summary = summarize_triage(triage_results)
    target = max(events, key=lambda e: e.observation_count)
    target_triage = next(
        result for result in triage_results if result.event_id == target.event_id
    )

    weather_bundle = _stage(
        "retrieve_historical_weather",
        weather_enrichment.fetch_weather_evidence_for_event,
        target,
        target.centroid[0],
        target.centroid[1],
    )
    weather_objects = weather_enrichment.to_evidence_objects(weather_bundle)

    peat_ctx = _stage(
        "inspect_peat_context",
        peat_context.get_peat_context_for_event,
        target,
        buffer_km,
    )
    peat_objects = peat_context.to_evidence_objects(peat_ctx)

    neighbours = _stage(
        "identify_neighbouring_events", find_neighbouring_events, target, events
    )

    west, south, east, north = target.bbox
    pad_deg = 0.2  # a small cluster's own bbox is far smaller than one Sentinel tile footprint
    imagery_bbox = (west - pad_deg, south - pad_deg, east + pad_deg, north + pad_deg)
    imagery_start = pd.Timestamp(target.first_detection).strftime("%Y-%m-%d")
    imagery_end = (pd.Timestamp(target.last_detection) + pd.Timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )

    def _search_imagery():
        s1 = copernicus_cds.search(
            "sentinel-1-grd", imagery_bbox, imagery_start, imagery_end
        )
        s2 = copernicus_cds.search(
            "sentinel-2-l2a", imagery_bbox, imagery_start, imagery_end
        )
        return s1.get("features", []), s2.get("features", [])

    s1_features, s2_features = _stage("find_imagery_metadata", _search_imagery)

    def _assemble_summary():
        return {
            "event": _event_row(target),
            "stage1_triage": target_triage.to_dict(),
            "weather_evidence": weather_objects,
            "peat_evidence": peat_objects,
            "neighbouring_events": [asdict(n) for n in neighbours],
            "imagery_candidates": {
                "sentinel1_grd": [
                    {"id": f["id"], "datetime": f["properties"].get("datetime")}
                    for f in s1_features[:10]
                ],
                "sentinel2_l2a": [
                    {
                        "id": f["id"],
                        "datetime": f["properties"].get("datetime"),
                        "cloud_cover_pct": f["properties"].get("eo:cloud_cover"),
                    }
                    for f in s2_features[:10]
                ],
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    evidence_summary = _stage("assemble_evidence_summary", _assemble_summary)

    total_seconds = time.perf_counter() - t_start

    out_path = OUTPUT_DIR / f"evidence_summary_{target.event_id}.json"
    out_path.write_text(json.dumps(evidence_summary, indent=2, default=str))

    return AutomatedBenchmarkResult(
        event_id=target.event_id,
        observation_count=len(observations),
        event_count=len(events),
        stage_timings=timings,
        total_seconds=total_seconds,
        observations_to_events_compression=round(len(observations) / len(events), 2)
        if events
        else None,
        events_to_review_queue_compression=triage_summary.events_to_review_queue_compression,
        review_queue_count=triage_summary.review_queue_count,
        triage_state_counts=triage_summary.state_counts,
        events_to_review_queue_note=EVENTS_TO_REVIEW_QUEUE_NOTE,
        evidence_completeness=evidence_field_completeness(
            weather_objects, peat_objects
        ),
        neighbouring_event_count=len(neighbours),
        imagery_scene_count={
            "sentinel1_grd": len(s1_features),
            "sentinel2_l2a": len(s2_features),
        },
        manual_interactions=MANUAL_INTERACTIONS,
        evidence_summary_path=str(out_path),
    )


def _demo() -> None:
    print("== Automated evidence-reconstruction run ==")
    result = run_automated_benchmark()
    for s in result.stage_timings:
        print(f"  {s.seconds:6.2f}s  {s.stage}")
    print(f"Total: {result.total_seconds:.2f}s for event {result.event_id}")
    print(
        f"{result.observation_count} observations -> {result.event_count} FireEvents "
        f"(compression {result.observations_to_events_compression}x)"
    )
    print(f"Neighbouring events found: {result.neighbouring_event_count}")
    print(f"Imagery candidates: {result.imagery_scene_count}")
    print(f"Evidence completeness: {result.evidence_completeness}")
    print(f"Saved evidence summary to {result.evidence_summary_path}\n")


if __name__ == "__main__":
    _demo()
