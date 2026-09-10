"""Explain why a window of FIRMS observations produced N FireEvents.

Single-linkage clustering is easy to run and hard to read: three events out
of a ten-day window may be a real spatiotemporal structure or a radius that
chained a province together, and nothing in the event list says which.
This module turns one `cluster_run` into the numbers that do say which, and
a threshold sweep that shows how sensitive the count is to the two knobs.

Nothing here re-clusters or splits anything. The summary reads the events
and link statistics the clustering pass already produced; the sweep calls
the same `cluster_run` with different parameters. A count reported here is
always what the algorithm would give the console for those parameters.

Run against the committed 2019 export:

    PYTHONPATH=. .venv/bin/python -m data_pipeline.clustering.diagnostics \\
        --start 2019-09-01 --end 2019-09-05 [--spatial-km 2 --temporal-hours 72] [--sweep]

Output goes to stdout and to data_pipeline/output/clustering_diagnostics.json
(gitignored). The API never serves this; it is a developer's view of the
derivation, and the artifact only carries the parameters that produced it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from statistics import mean, median
from typing import Any

import numpy as np
import pandas as pd

from data_pipeline.clustering.firms_clustering import (
    DEFAULT_LOBE_DISTANCE_KM,
    ClusteringParameters,
    ClusteringRun,
    FireEvent,
    cluster_run,
    event_lobes,
)

# Above this many observations an event is worth reading as a complex. It is
# the same line the audit-artifact skill's sanity table draws; nothing
# decides anything with it.
LARGE_EVENT_OBSERVATIONS = 100
DEFAULT_TOP_EVENTS = 5
# The sweep grid brackets the defaults (2 km, 72 h) on both sides. It is a
# reading aid; the defaults stay what they are unless a decision-log entry
# moves them.
DEFAULT_SWEEP_SPATIAL_KM = (1.0, 2.0, 3.0, 5.0)
DEFAULT_SWEEP_TEMPORAL_HOURS = (24.0, 48.0, 72.0, 120.0)


def _spread(values: list[float]) -> dict[str, float | None]:
    """min / median / mean / p90 / max, or Nones for an empty list. Empty is
    a legitimate result (a window with no qualified detections), not an
    error, so it must round-trip to JSON like any other."""
    if not values:
        return {"min": None, "median": None, "mean": None, "p90": None, "max": None}
    # Two decimals: the summary is read by a person, and 47.38333333333333 h
    # says nothing 47.38 does not.
    return {
        "min": round(float(min(values)), 2),
        "median": round(float(median(values)), 2),
        "mean": float(mean(values)),
        "p90": float(np.percentile(values, 90)),
        "max": float(max(values)),
    }


@dataclass(frozen=True)
class LobeSummary:
    observation_count: int
    first_detection: str
    last_detection: str
    duration_hours: float
    spatial_extent_km: float
    max_frp: float | None
    centroid: tuple[float, float]


@dataclass(frozen=True)
class LargeEventSummary:
    """One event big enough to explain: what holds it together, and how it
    reads as lobes. `max_link_*` against the thresholds is the tell: a
    widest link at the limit on both axes means the component was chained,
    a short same-day one means it is compact."""

    event_id: str
    observation_count: int
    first_detection: str
    last_detection: str
    duration_hours: float
    spatial_extent_km: float
    max_frp: float | None
    link_count: int
    max_link_gap_hours: float
    max_link_distance_km: float
    lobe_distance_km: float
    lobes: list[LobeSummary]


@dataclass(frozen=True)
class ClusteringDiagnostics:
    parameters: dict[str, Any]
    raw_observation_count: int | None
    qualified_observation_count: int
    event_count: int
    # qualified observations per event; None when there are no events, never
    # 1.0 or 0, because a ratio over nothing is not a measurement.
    compression_ratio: float | None
    singleton_count: int
    multi_observation_event_count: int
    observations_per_event: dict[str, float | None]
    duration_hours: dict[str, float | None]
    spatial_extent_km: dict[str, float | None]
    large_event_threshold: int
    large_event_count: int
    large_event_observations: int
    large_event_observation_share: float | None
    links: dict[str, float | int]
    largest_events: list[LargeEventSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _lobe_summary(lobe: FireEvent) -> LobeSummary:
    return LobeSummary(
        observation_count=lobe.observation_count,
        first_detection=lobe.first_detection,
        last_detection=lobe.last_detection,
        duration_hours=round(lobe.duration_hours, 2),
        spatial_extent_km=round(lobe.spatial_extent_km, 3),
        max_frp=lobe.max_frp,
        centroid=(round(lobe.centroid[0], 5), round(lobe.centroid[1], 5)),
    )


def summarize_large_event(
    event: FireEvent,
    observations: pd.DataFrame,
    lobe_distance_km: float = DEFAULT_LOBE_DISTANCE_KM,
) -> LargeEventSummary:
    return LargeEventSummary(
        event_id=event.event_id,
        observation_count=event.observation_count,
        first_detection=event.first_detection,
        last_detection=event.last_detection,
        duration_hours=round(event.duration_hours, 2),
        spatial_extent_km=round(event.spatial_extent_km, 3),
        max_frp=event.max_frp,
        link_count=event.link_count,
        max_link_gap_hours=round(event.max_link_gap_hours, 2),
        max_link_distance_km=round(event.max_link_distance_km, 3),
        lobe_distance_km=lobe_distance_km,
        lobes=[
            _lobe_summary(lobe)
            for lobe in event_lobes(event, observations, lobe_distance_km)
        ],
    )


def diagnose(
    run: ClusteringRun,
    *,
    raw_observation_count: int | None = None,
    top: int = DEFAULT_TOP_EVENTS,
    lobe_distance_km: float = DEFAULT_LOBE_DISTANCE_KM,
) -> ClusteringDiagnostics:
    """Summarise one clustering run. `raw_observation_count` is whatever the
    caller counted before its own qualification gate (the export drops
    low-confidence detections); the run itself only ever sees qualified
    rows, so it cannot know the raw figure and reports None without it."""
    events = run.events
    sizes = [e.observation_count for e in events]
    large = [e for e in events if e.observation_count >= LARGE_EVENT_OBSERVATIONS]
    large_observations = sum(e.observation_count for e in large)
    qualified = len(run.annotated)
    biggest = sorted(
        events, key=lambda e: (-e.observation_count, e.first_detection, e.event_id)
    )[: max(top, 0)]
    return ClusteringDiagnostics(
        parameters=run.parameters.to_dict(),
        raw_observation_count=raw_observation_count,
        qualified_observation_count=qualified,
        event_count=len(events),
        compression_ratio=(qualified / len(events)) if events else None,
        singleton_count=sum(1 for size in sizes if size == 1),
        multi_observation_event_count=sum(1 for size in sizes if size > 1),
        observations_per_event=_spread(sizes),
        duration_hours=_spread([e.duration_hours for e in events]),
        spatial_extent_km=_spread([e.spatial_extent_km for e in events]),
        large_event_threshold=LARGE_EVENT_OBSERVATIONS,
        large_event_count=len(large),
        large_event_observations=large_observations,
        large_event_observation_share=(large_observations / qualified) if qualified else None,
        links={
            "spatial_pairs": run.links.spatial_pairs,
            "accepted_pairs": run.links.accepted_pairs,
            "rejected_by_time_pairs": run.links.rejected_by_time_pairs,
            "max_accepted_gap_hours": round(run.links.max_accepted_gap_hours, 2),
            "max_accepted_distance_km": round(run.links.max_accepted_distance_km, 3),
        },
        largest_events=[
            summarize_large_event(e, run.annotated, lobe_distance_km) for e in biggest
        ],
    )


def threshold_sweep(
    observations: pd.DataFrame,
    spatial_values: tuple[float, ...] = DEFAULT_SWEEP_SPATIAL_KM,
    temporal_values: tuple[float, ...] = DEFAULT_SWEEP_TEMPORAL_HOURS,
) -> list[dict[str, Any]]:
    """Event counts across a grid of thresholds, one real clustering run per
    cell. This is how to tell "the data has three episodes" from "72 h
    chains everything": if the count barely moves across the grid the
    structure is in the data; if it collapses along one axis, that axis is
    doing the merging."""
    rows = []
    for spatial in spatial_values:
        for temporal in temporal_values:
            run = cluster_run(
                observations,
                ClusteringParameters(spatial, temporal, source="sweep"),
            )
            sizes = [e.observation_count for e in run.events]
            rows.append(
                {
                    "spatial_threshold_km": spatial,
                    "temporal_threshold_hours": temporal,
                    "event_count": len(run.events),
                    "singleton_count": sum(1 for size in sizes if size == 1),
                    "large_event_count": sum(
                        1 for size in sizes if size >= LARGE_EVENT_OBSERVATIONS
                    ),
                    "largest_event_observations": max(sizes) if sizes else 0,
                    "accepted_pairs": run.links.accepted_pairs,
                }
            )
    return rows


def window(observations: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    """Restrict to acq_date in [start, end], inclusive ISO dates."""
    selected = observations
    if start:
        selected = selected[selected["acq_date"] >= start]
    if end:
        selected = selected[selected["acq_date"] <= end]
    return selected.reset_index(drop=True)


def format_summary(diagnostics: ClusteringDiagnostics) -> str:
    d = diagnostics
    p = d.parameters
    raw = "unknown" if d.raw_observation_count is None else f"{d.raw_observation_count:,}"
    ratio = "n/a" if d.compression_ratio is None else f"{d.compression_ratio:.1f}x"
    share = (
        "n/a"
        if d.large_event_observation_share is None
        else f"{d.large_event_observation_share:.0%}"
    )
    lines = [
        (
            f"parameters: {p['spatial_threshold_km']:g} km / {p['temporal_threshold_hours']:g} h "
            f"({p['source']}, {p['algorithm_version']})"
        ),
        (
            f"observations: raw {raw} -> qualified {d.qualified_observation_count:,} "
            f"-> {d.event_count:,} FireEvents ({ratio})"
        ),
        (
            f"singletons: {d.singleton_count:,}; multi-observation events: "
            f"{d.multi_observation_event_count:,}"
        ),
        (
            f"observations per event: median {d.observations_per_event['median']}, "
            f"p90 {d.observations_per_event['p90']}, max {d.observations_per_event['max']}"
        ),
        (
            f"duration h: median {d.duration_hours['median']}, p90 {d.duration_hours['p90']}, "
            f"max {d.duration_hours['max']}"
        ),
        (
            f"extent km: median {d.spatial_extent_km['median']}, p90 {d.spatial_extent_km['p90']}, "
            f"max {d.spatial_extent_km['max']}"
        ),
        (
            f"events >= {d.large_event_threshold} observations: {d.large_event_count:,}, "
            f"holding {d.large_event_observations:,} observations ({share})"
        ),
        (
            f"links: {d.links['spatial_pairs']:,} pairs within radius, "
            f"{d.links['accepted_pairs']:,} accepted, "
            f"{d.links['rejected_by_time_pairs']:,} kept apart by time; "
            f"widest accepted link {d.links['max_accepted_distance_km']} km / "
            f"{d.links['max_accepted_gap_hours']} h"
        ),
    ]
    for e in d.largest_events:
        lines.append(
            f"  {e.event_id}: {e.observation_count:,} obs, {e.duration_hours} h, "
            f"{e.spatial_extent_km} km, {e.link_count:,} links "
            f"(widest {e.max_link_distance_km} km / {e.max_link_gap_hours} h), "
            f"{len(e.lobes)} lobe(s) at {e.lobe_distance_km:g} km"
        )
    return "\n".join(lines)


def format_sweep(rows: list[dict[str, Any]]) -> str:
    header = f"{'km':>5} {'hours':>6} {'events':>8} {'single':>8} {'>=100':>6} {'largest':>8} {'links':>9}"
    body = [
        f"{r['spatial_threshold_km']:>5g} {r['temporal_threshold_hours']:>6g} "
        f"{r['event_count']:>8,} {r['singleton_count']:>8,} {r['large_event_count']:>6,} "
        f"{r['largest_event_observations']:>8,} {r['accepted_pairs']:>9,}"
        for r in rows
    ]
    return "\n".join([header, *body])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--start", help="first acq_date to include (YYYY-MM-DD)")
    parser.add_argument("--end", help="last acq_date to include (YYYY-MM-DD)")
    parser.add_argument("--spatial-km", type=float, default=None)
    parser.add_argument("--temporal-hours", type=float, default=None)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_EVENTS)
    parser.add_argument("--lobe-km", type=float, default=DEFAULT_LOBE_DISTANCE_KM)
    parser.add_argument("--sweep", action="store_true", help="also run the threshold grid")
    parser.add_argument("--json", default=None, help="output path (default: data_pipeline/output/)")
    args = parser.parse_args(argv)

    # Imported here so the pure functions above stay importable without the
    # export module's file-system constants.
    from data_pipeline.config import OUTPUT_DIR
    from data_pipeline.export_audit_events import (
        load_observations,
        load_raw_observation_count,
    )

    if args.spatial_km is None and args.temporal_hours is None:
        parameters = ClusteringParameters.from_env()
    else:
        from data_pipeline.clustering.firms_clustering import resolve_parameters

        parameters = resolve_parameters(args.spatial_km, args.temporal_hours)

    observations = window(load_observations(), args.start, args.end)
    # The raw count is only comparable when the window is the whole export;
    # a sub-window's raw figure is not something the export file can supply.
    raw = load_raw_observation_count() if not (args.start or args.end) else None

    run = cluster_run(observations, parameters)
    diagnostics = diagnose(run, raw_observation_count=raw, top=args.top, lobe_distance_km=args.lobe_km)
    print(format_summary(diagnostics))
    payload: dict[str, Any] = {
        "window": {"start": args.start, "end": args.end},
        "diagnostics": diagnostics.to_dict(),
    }
    if args.sweep:
        rows = threshold_sweep(observations)
        payload["sweep"] = rows
        print("\nthreshold sweep:")
        print(format_sweep(rows))

    out = args.json or (OUTPUT_DIR / "clustering_diagnostics.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
