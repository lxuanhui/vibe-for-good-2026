"""Fetch weather and imagery-scene evidence for every committed demo
FireEvent, spatially batched so the request count depends on the geoshape's
size, not the event count -- and checkpointed to a local SQLite file so this
can run for a while, be interrupted with Ctrl+C at any point, and resumed
without re-querying anything already done.

Rework of the original per-event design after the first real run showed the
actual cost: 3,610 individual Open-Meteo point queries hit Open-Meteo's rate
limits repeatedly, and each hit was silently skipped rather than retried,
degrading data quality as the run went on. Two changes fix both problems at
once:

## Spatial grid, not one query per event

Open-Meteo's archive is a *reanalysis* grid already (ERA5/ERA5-Land, roughly
0.1-0.25 deg native resolution) -- querying it at a finer resolution than
that returns values snapped to the same underlying cell anyway. So: lay a
grid over the whole geoshape's bounding box at GRID_SPACING_DEG, fetch each
grid point's weather ONCE via Open-Meteo's multi-location batching (many
points in one HTTP call -- `sources/open_meteo.fetch_batch`, now requesting
hourly variables too, not just daily), then assign each FireEvent to its
nearest grid point. Different fires get different readings exactly where the
underlying data actually differs; nearby fires correctly share a fetch.
Verified live: a 3-point/2-variable/13-day batched request returned 200 in
one call, ~28 KB -- the mechanism works.

## Two windows, not seven, and no anomaly baseline

Per direct instruction: "current" (the event's own first-to-last detection)
and T-7d (the seven days before first detection), covering every available
Open-Meteo hourly variable rather than a curated seven-metric subset. This
also drops the 5-years-of-baseline-fetches-per-point that was the single
biggest driver of request volume in the original design (5 of 6 Open-Meteo
calls per point). What is lost: the "26% below the 5-year seasonal
baseline" framing from the original design -- these are raw values with no
normal-for-the-season comparison. If that framing is wanted later, add it
back as a second, explicit pass over the grid rather than reintroducing it
here.

## Satellite imagery: two searches per collection, not one pair per event

Same batching idea applied to Sentinel-1 (SAR) and Sentinel-2 (optical):
`sources.copernicus_cds.search()` is called ONCE per collection across the
whole geoshape's bbox and the whole event date range (+/- a margin), and
every event's pre/post scene selection (`scene_selection.select_scenes()`,
already a pure, no-network function) reuses those two shared feature lists.
3,610 events x 2 collections becomes 2 catalogue searches total.

## Rate limits: wait and retry, not skip

Open-Meteo returns a rate-limit hit as HTTP 200 with `{"error": true,
"reason": "...limit exceeded. Please try again in a minute/hour."}` --
`retry_requests`' HTTP-status-based retry never sees this as a failure, and
the original script's bare except just skipped and moved on, guaranteeing
more failures while the limit window was still open. This version parses
the reason text and sleeps the hinted duration before retrying the same
request. Because the grid collapses request count so much, this should
rarely trigger at all for one geoshape -- but if it does, it now waits
instead of producing gaps.

## Usage

    cd data_pipeline
    PYTHONPATH=.. ../.venv/Scripts/python.exe -m data_pipeline.enrich_audit_events --dry-run
        # prints the grid size and request-count estimate for the current
        # geoshape/spacing without fetching anything -- check this first

    PYTHONPATH=.. ../.venv/Scripts/python.exe -m data_pipeline.enrich_audit_events --limit 20
        # smoke test: fetch the grid, but only compute+checkpoint the first
        # 20 not-yet-done events

    PYTHONPATH=.. ../.venv/Scripts/python.exe -m data_pipeline.enrich_audit_events
        # the real run. Ctrl+C any time; rerun the same command to resume --
        # already-fetched grid points, imagery searches, and computed events
        # are all skipped, not redone.

    PYTHONPATH=.. ../.venv/Scripts/python.exe -m data_pipeline.enrich_audit_events --finalize
        # unchanged from the previous version: folds whatever has been
        # computed so far into the committed audit_triage_detail.json.gz.
        # Safe to run repeatedly.

(Run from the repo root instead, drop the ".." from PYTHONPATH and use
"./.venv" for the interpreter path -- both forms work.)

See docs/decision-log.md (2026-09-09) for why this stays a local checkpoint
rather than a new database, and why it runs offline rather than as a live
Lambda call.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data_pipeline.imagery.scene_selection import select_scenes
from data_pipeline.sources import copernicus_cds
from data_pipeline.sources.open_meteo import HOURLY_VARS, _hourly_to_df
from data_pipeline.sources.open_meteo import fetch_batch as _om_fetch_batch

REPO_ROOT = Path(__file__).parent.parent
EVENTS_PATH = REPO_ROOT / "backend" / "app" / "data" / "audit_events.json.gz"
DETAIL_PATH = REPO_ROOT / "backend" / "app" / "data" / "audit_triage_detail.json.gz"
CHECKPOINT_PATH = REPO_ROOT / "data_pipeline" / "output" / "enrichment_checkpoint.sqlite"
AUDIT_ID = "demo-2019-haze"

# The committed artifact's 3,610 events are the WHOLE unscoped
# Sumatra/Kalimantan regional FIRMS export -- its own `scope` metadata has
# no geometry or bbox at all (contextBufferKm: 0). "1 geoshape" is the
# actual small demo audit boundary the console shows when a user lands on
# AuditStart and submits no file -- frontend/src/lib/scope.ts's
# DEFAULT_MANAGEMENT_UNIT_GEOMETRY, buffered by the same default 25 km the
# real audit-creation flow uses. This must match that geometry, not be
# rederived from the full event set, or the grid covers the whole region
# instead of one geoshape (caught by --dry-run before any fetch ran: an
# unfiltered bbox produced a 12,560-point grid across two countries' worth
# of area).
DEMO_GEOSHAPE_BBOX = (115.75, -4.28, 116.75, -3.32)  # (minLon, minLat, maxLon, maxLat)

# ERA5/ERA5-Land's own native resolution is roughly 0.1-0.25 deg; sampling
# finer than that returns values snapped to the same grid cell, so this is
# not "coarser than the data supports", it is matched to it.
DEFAULT_GRID_SPACING_DEG = 0.15
DEFAULT_BATCH_SIZE = 20  # grid points per Open-Meteo request
LOOKBACK_DAYS = 7  # the "T-7d" window

# Small margin, not the whole search: a wide date range multiplies the STAC
# response size for no benefit once the shared search already covers every
# event's own window.
IMAGERY_SEARCH_MARGIN_DAYS = 30
STAC_SEARCH_LIMIT = 200  # generous: one search covers the whole scope + review period, not one event

# Variables where a sum (accumulation) is the meaningful figure, not a mean.
ACCUMULATIVE_VARS = {"precipitation", "rain"}
# Variables that are angles -- a plain mean of e.g. [350, 10] gives the
# wrong answer (180, due south) instead of the right one (due north).
DIRECTIONAL_VARS = {"wind_direction_10m", "wind_direction_100m"}
RAINFALL_FREE_THRESHOLD_MM = 1.0


def build_grid(min_lat: float, max_lat: float, min_lon: float, max_lon: float, spacing: float) -> list[tuple[float, float]]:
    lat_steps = max(1, round((max_lat - min_lat) / spacing) + 1)
    lon_steps = max(1, round((max_lon - min_lon) / spacing) + 1)
    lats = np.linspace(min_lat, max_lat, lat_steps) if lat_steps > 1 else [(min_lat + max_lat) / 2]
    lons = np.linspace(min_lon, max_lon, lon_steps) if lon_steps > 1 else [(min_lon + max_lon) / 2]
    return [(round(float(lat), 6), round(float(lon), 6)) for lat in lats for lon in lons]


def nearest_grid_point(lat: float, lon: float, grid_points: list[tuple[float, float]]) -> tuple[float, float]:
    # Euclidean in degrees, not great-circle -- fine at this scale (a single
    # geoshape, grid spacing in the tenths of a degree), and this runs once
    # per event against a grid of at most a few hundred points.
    return min(grid_points, key=lambda p: (p[0] - lat) ** 2 + (p[1] - lon) ** 2)


def _grid_key(lat: float, lon: float) -> str:
    return f"{lat:.6f},{lon:.6f}"


def _parse_rate_limit_wait(message: str) -> int | None:
    lowered = message.lower()
    if "limit exceeded" not in lowered:
        return None
    if "minute" in lowered:
        return 65
    if "hour" in lowered:
        return 61 * 60
    if "day" in lowered:
        return None  # do not silently sleep a whole day; surface it instead
    return None


def rate_limited_call(fn, *args, max_attempts: int = 6, **kwargs):
    """Call fn once; on Open-Meteo's own rate-limit response, sleep the
    duration it names and retry the SAME request instead of skipping it."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            wait = _parse_rate_limit_wait(str(exc))
            if wait is None or attempt == max_attempts:
                raise
            print(f"  rate limited ({exc}); waiting {wait}s before retry {attempt}/{max_attempts - 1}...", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")  # pragma: no cover


def load_event_summaries(bbox: tuple[float, float, float, float] = DEMO_GEOSHAPE_BBOX) -> list[dict[str, Any]]:
    with gzip.open(EVENTS_PATH, "rt", encoding="utf-8") as handle:
        artifact = json.load(handle)
    all_events = artifact["audits"][AUDIT_ID]["events"]
    min_lon, min_lat, max_lon, max_lat = bbox
    # Same centroid-in-bbox test app/audit_events.py's filter_events() uses
    # for GET .../events?bbox=... -- this is deliberately the one geoshape
    # the console actually shows, not the full committed artifact.
    return [
        e for e in all_events
        if min_lon <= e["centroid"]["lon"] <= max_lon and min_lat <= e["centroid"]["lat"] <= max_lat
    ]


def _db() -> sqlite3.Connection:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CHECKPOINT_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS weather_grid (
            grid_key TEXT PRIMARY KEY, lat REAL, lon REAL, hourly_json TEXT, fetched_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS imagery_search (
            collection TEXT PRIMARY KEY, features_json TEXT, fetched_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS enrichment (
            event_id TEXT PRIMARY KEY,
            weather_status TEXT, weather_evidence TEXT, weather_error TEXT,
            imagery_status TEXT, imagery_evidence TEXT, imagery_error TEXT,
            updated_at TEXT
        )"""
    )
    conn.commit()
    return conn


# --- Weather: fetch the grid once, compute per event from the cache -------


def fetch_weather_grid(conn: sqlite3.Connection, grid_points: list[tuple[float, float]], start_date: str, end_date: str, batch_size: int) -> None:
    done = {row[0] for row in conn.execute("SELECT grid_key FROM weather_grid")}
    todo = [(lat, lon) for lat, lon in grid_points if _grid_key(lat, lon) not in done]
    if not todo:
        print(f"Weather grid: all {len(grid_points)} points already fetched.")
        return
    print(f"Weather grid: fetching {len(todo)} of {len(grid_points)} points ({batch_size}/request)...")
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        points = {f"p{i}": (lat, lon) for i, (lat, lon) in enumerate(batch)}
        responses = rate_limited_call(_om_fetch_batch, points, start_date, end_date)
        for (lat, lon), response in zip(batch, responses):
            df = _hourly_to_df(response)
            conn.execute(
                "INSERT OR REPLACE INTO weather_grid (grid_key, lat, lon, hourly_json, fetched_at) VALUES (?, ?, ?, ?, datetime('now'))",
                (_grid_key(lat, lon), lat, lon, df.to_json(orient="split", date_format="iso")),
            )
        conn.commit()
        print(f"  {min(start + batch_size, len(todo))}/{len(todo)} grid points fetched", flush=True)


def _load_grid_hourly(conn: sqlite3.Connection, lat: float, lon: float) -> pd.DataFrame:
    row = conn.execute("SELECT hourly_json FROM weather_grid WHERE grid_key = ?", (_grid_key(lat, lon),)).fetchone()
    if row is None:
        raise KeyError(f"grid point {lat},{lon} was not fetched")
    # pd.read_json treats a bare str as a file path/URL, not JSON content --
    # StringIO is what makes it read the string itself. (Caught by an actual
    # end-to-end run: every grid-point lookup raised FileNotFoundError with
    # the entire JSON blob rendered as the "filename".)
    df = pd.read_json(io.StringIO(row[0]), orient="split")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df


def _slice(hourly: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if hourly.empty:
        return hourly
    return hourly[(hourly["date"] >= start) & (hourly["date"] < end)]


def _variable_evidence(sl: pd.DataFrame, column: str, window_name: str, event_id: str, time_window: str) -> list[dict[str, Any]]:
    if sl.empty or column not in sl.columns:
        return []
    series = sl[column].dropna()
    if series.empty:
        return []
    objects: list[dict[str, Any]] = []
    if column in ACCUMULATIVE_VARS:
        total = round(float(series.sum()), 2)
        objects.append(
            {
                "evidence_id": f"ENV_WEATHER_{event_id}_{window_name}_{column}_sum",
                "category": "weather",
                "type": column,
                "observation": f"{total} mm total {column} during {window_name}",
                "source": "Open-Meteo/ERA5",
                "time_window": time_window,
                "value": total,
                "unit": "mm",
                "quality": 0.82,
                "limitations": [],
                "retrieved_at": None,
                "algorithm_version": None,
                "raw_reference": None,
            }
        )
        if column == "precipitation":
            daily = sl.set_index("date")[column].resample("1D").sum()
            free_days = int((daily < RAINFALL_FREE_THRESHOLD_MM).sum())
            objects.append(
                {
                    "evidence_id": f"ENV_WEATHER_{event_id}_{window_name}_rainfall_free_days",
                    "category": "weather",
                    "type": "rainfall_free_days",
                    "observation": f"{free_days} rainfall-free days during {window_name}",
                    "source": "Open-Meteo/ERA5",
                    "time_window": time_window,
                    "value": free_days,
                    "unit": "days",
                    "quality": 0.82,
                    "limitations": [],
                    "retrieved_at": None,
                    "algorithm_version": None,
                    "raw_reference": None,
                }
            )
        return objects
    if column in DIRECTIONAL_VARS:
        rad = np.radians(series.to_numpy())
        weight_col = column.replace("direction", "speed")
        weights = sl.loc[series.index, weight_col].fillna(0).to_numpy() if weight_col in sl.columns else None
        if weights is not None and weights.sum() <= 0:
            weights = None
        x, y = np.average(np.cos(rad), weights=weights), np.average(np.sin(rad), weights=weights)
        if x == 0 and y == 0:
            return []
        mean_deg = round(float(np.degrees(np.arctan2(y, x)) % 360), 1)
        return [
            {
                "evidence_id": f"ENV_WEATHER_{event_id}_{window_name}_{column}",
                "category": "weather",
                "type": column,
                "observation": f"dominant {column.replace('_', ' ')} of {mean_deg} deg during {window_name}",
                "source": "Open-Meteo/ERA5",
                "time_window": time_window,
                "value": mean_deg,
                "unit": "deg",
                "quality": 0.82,
                "limitations": [],
                "retrieved_at": None,
                "algorithm_version": None,
                "raw_reference": None,
            }
        ]
    mean_v, min_v, max_v = round(float(series.mean()), 2), round(float(series.min()), 2), round(float(series.max()), 2)
    return [
        {
            "evidence_id": f"ENV_WEATHER_{event_id}_{window_name}_{column}",
            "category": "weather",
            "type": column,
            "observation": f"mean {column.replace('_', ' ')} of {mean_v} during {window_name} (range {min_v} to {max_v})",
            "source": "Open-Meteo/ERA5",
            "time_window": time_window,
            "value": {"mean": mean_v, "min": min_v, "max": max_v},
            "unit": None,
            "quality": 0.82,
            "limitations": [],
            "retrieved_at": None,
            "algorithm_version": None,
            "raw_reference": None,
        }
    ]


def compute_weather_evidence(conn: sqlite3.Connection, grid_points: list[tuple[float, float]], event: dict[str, Any]) -> list[dict[str, Any]]:
    lat, lon = event["centroid"]["lat"], event["centroid"]["lon"]
    grid_lat, grid_lon = nearest_grid_point(lat, lon, grid_points)
    hourly = _load_grid_hourly(conn, grid_lat, grid_lon)

    first = pd.Timestamp(event["firstDetection"])
    last = pd.Timestamp(event["lastDetection"])
    # Open-Meteo's archive is hourly -- one row per :00. A single-detection
    # event (first == last) padded by only a minute defines a window that
    # almost never contains an actual row (a detection at :55 needs the
    # window to reach the next hour boundary at :00), so it silently came
    # back empty for every variable. Found by checking real output: 12 of
    # 16 events had zero "current" evidence, only the multi-detection ones
    # (naturally spanning >=1 hour boundary) had any. 2 hours guarantees at
    # least one hourly row regardless of where in the hour the event fell.
    windows = {
        "current": (first, max(last, first + pd.Timedelta(hours=2))),
        "T-7d": (first - pd.Timedelta(days=LOOKBACK_DAYS), first),
    }

    evidence: list[dict[str, Any]] = []
    for window_name, (start, end) in windows.items():
        sl = _slice(hourly, start, end)
        time_window = f"{start.isoformat()} to {end.isoformat()}"
        for column in HOURLY_VARS:
            evidence.extend(_variable_evidence(sl, column, window_name, event["eventId"], time_window))
    return evidence


# --- Imagery: two scope-wide searches, per-event selection is local -------


def fetch_imagery_searches(conn: sqlite3.Connection, bbox: tuple[float, float, float, float], start_date: str, end_date: str) -> None:
    for collection in ("sentinel-1-grd", "sentinel-2-l2a"):
        existing = conn.execute("SELECT 1 FROM imagery_search WHERE collection = ?", (collection,)).fetchone()
        if existing:
            continue
        print(f"Imagery: searching {collection} across the whole geoshape + review period...")
        features = rate_limited_call(copernicus_cds.search, collection, bbox, start_date, end_date, limit=STAC_SEARCH_LIMIT)
        conn.execute(
            "INSERT OR REPLACE INTO imagery_search (collection, features_json, fetched_at) VALUES (?, ?, datetime('now'))",
            (collection, json.dumps(features)),
        )
        conn.commit()
        count = len(features.get("features", [])) if isinstance(features, dict) else 0
        print(f"  {collection}: {count} scene(s) found for the whole geoshape.")


def compute_imagery_evidence(conn: sqlite3.Connection, event: dict[str, Any]) -> list[dict[str, Any]]:
    s1_row = conn.execute("SELECT features_json FROM imagery_search WHERE collection = 'sentinel-1-grd'").fetchone()
    s2_row = conn.execute("SELECT features_json FROM imagery_search WHERE collection = 'sentinel-2-l2a'").fetchone()
    if not s1_row or not s2_row:
        raise RuntimeError("imagery searches have not been fetched yet")
    s1_features = json.loads(s1_row[0])
    s2_features = json.loads(s2_row[0])
    selection = select_scenes(s1_features, s2_features, event["firstDetection"], event["lastDetection"])
    objects = []
    for scene in selection.selected_scenes:
        evidence = scene.to_evidence_object(f"ENV_IMAGERY_{event['eventId']}_{scene.sensor}_{scene.position.value}")
        # scene_selection's own default is "remote-sensing"; the console's
        # evidence drawer and evidence_for_event()'s availability check both
        # use "imagery" -- align here rather than touch either shipped call site.
        evidence["category"] = "imagery"
        objects.append(evidence)
    return objects


# --- Orchestration ----------------------------------------------------------


def scope_bounds(events: list[dict[str, Any]]) -> tuple[float, float, float, float, str, str]:
    lats = [e["centroid"]["lat"] for e in events]
    lons = [e["centroid"]["lon"] for e in events]
    starts = [e["firstDetection"] for e in events]
    ends = [e["lastDetection"] for e in events]
    return min(lats), max(lats), min(lons), max(lons), min(starts), max(ends)


def run(limit: int | None, grid_spacing: float, batch_size: int, dry_run: bool) -> None:
    events = load_event_summaries()
    min_lat, max_lat, min_lon, max_lon, earliest, latest = scope_bounds(events)
    grid_points = build_grid(min_lat, max_lat, min_lon, max_lon, grid_spacing)

    weather_start = (pd.Timestamp(earliest) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    weather_end = pd.Timestamp(latest).strftime("%Y-%m-%d")
    imagery_bbox = (min_lon, min_lat, max_lon, max_lat)
    imagery_start = (pd.Timestamp(earliest) - pd.Timedelta(days=IMAGERY_SEARCH_MARGIN_DAYS)).strftime("%Y-%m-%d")
    imagery_end = (pd.Timestamp(latest) + pd.Timedelta(days=IMAGERY_SEARCH_MARGIN_DAYS)).strftime("%Y-%m-%d")

    print(
        f"Geoshape: {len(events)} events, bbox [{min_lon:.3f},{min_lat:.3f},{max_lon:.3f},{max_lat:.3f}], "
        f"{earliest} .. {latest}"
    )
    print(f"Weather grid: {len(grid_points)} points at {grid_spacing} deg spacing, {(len(grid_points) + batch_size - 1) // batch_size} request(s)")
    print(f"Weather window fetched per grid point: {weather_start} .. {weather_end}")
    print(f"Imagery: 2 searches total (sentinel-1-grd, sentinel-2-l2a), {imagery_start} .. {imagery_end}, bbox as above")
    if dry_run:
        print("Dry run -- nothing fetched.")
        return

    conn = _db()
    try:
        fetch_weather_grid(conn, grid_points, weather_start, weather_end, batch_size)
        fetch_imagery_searches(conn, imagery_bbox, imagery_start, imagery_end)

        done_ids = {row[0] for row in conn.execute("SELECT event_id FROM enrichment WHERE weather_status = 'ok' AND imagery_status = 'ok'")}
        todo = [e for e in events if e["eventId"] not in done_ids]
        print(f"Computing per-event evidence: {len(todo)} of {len(events)} remaining (grid + imagery already fetched, this part is local/fast).")

        processed = ok_weather = err_weather = ok_imagery = err_imagery = 0
        for event in todo:
            try:
                weather_evidence = compute_weather_evidence(conn, grid_points, event)
                weather_status, weather_error = "ok", None
                ok_weather += 1
            except Exception as exc:  # noqa: BLE001 -- one event's failure must not stop the run
                weather_evidence, weather_status, weather_error = None, "error", f"{type(exc).__name__}: {exc}"
                err_weather += 1
            try:
                imagery_evidence = compute_imagery_evidence(conn, event)
                imagery_status, imagery_error = "ok", None
                ok_imagery += 1
            except Exception as exc:  # noqa: BLE001
                imagery_evidence, imagery_status, imagery_error = None, "error", f"{type(exc).__name__}: {exc}"
                err_imagery += 1

            conn.execute(
                """INSERT INTO enrichment
                     (event_id, weather_status, weather_evidence, weather_error,
                      imagery_status, imagery_evidence, imagery_error, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(event_id) DO UPDATE SET
                     weather_status = excluded.weather_status,
                     weather_evidence = excluded.weather_evidence,
                     weather_error = excluded.weather_error,
                     imagery_status = excluded.imagery_status,
                     imagery_evidence = excluded.imagery_evidence,
                     imagery_error = excluded.imagery_error,
                     updated_at = excluded.updated_at""",
                (
                    event["eventId"],
                    weather_status, json.dumps(weather_evidence) if weather_evidence is not None else None, weather_error,
                    imagery_status, json.dumps(imagery_evidence) if imagery_evidence is not None else None, imagery_error,
                ),
            )
            conn.commit()
            processed += 1
            if processed == 1 or processed % 100 == 0:
                print(f"[{processed}/{len(todo)}] weather ok={ok_weather} err={err_weather} | imagery ok={ok_imagery} err={err_imagery} | last={event['eventId']}", flush=True)
            if limit and processed >= limit:
                print(f"Stopping at --limit {limit}. Rerun without --limit to continue from here.")
                break
        print(f"Done: {processed} events computed this run ({ok_weather} weather ok, {ok_imagery} imagery ok). --finalize to write into the committed artifact.")
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing lost -- rerun the same command to resume (grid points, imagery searches, and computed events already done are skipped).")
    finally:
        conn.close()


def finalize() -> None:
    conn = _db()
    rows = conn.execute(
        "SELECT event_id, weather_status, weather_evidence, imagery_status, imagery_evidence FROM enrichment"
    ).fetchall()
    conn.close()
    if not rows:
        print("No checkpointed results yet -- run without --finalize first.")
        return

    with gzip.open(DETAIL_PATH, "rt", encoding="utf-8") as handle:
        detail = json.load(handle)
    demo = detail[AUDIT_ID]

    updated = 0
    for event_id, weather_status, weather_evidence, imagery_status, imagery_evidence in rows:
        if event_id not in demo:
            continue  # stale checkpoint row for an event no longer in the artifact
        new_items: list[dict[str, Any]] = []
        if weather_status == "ok" and weather_evidence:
            new_items.extend(json.loads(weather_evidence))
        if imagery_status == "ok" and imagery_evidence:
            new_items.extend(json.loads(imagery_evidence))
        if not new_items:
            continue
        existing = demo[event_id].get("evidence", [])
        # Idempotent on category, not identity: drop whatever a previous
        # --finalize already appended, then append the current checkpoint
        # state. Safe to rerun as more events complete.
        kept = [item for item in existing if item.get("category") not in ("weather", "imagery")]
        demo[event_id]["evidence"] = kept + new_items
        updated += 1

    body = json.dumps(detail, separators=(",", ":"), sort_keys=True).encode("utf-8")
    with gzip.GzipFile(DETAIL_PATH, "wb", mtime=0) as handle:
        handle.write(body)
    print(f"Finalized {updated} event(s) into {DETAIL_PATH.relative_to(REPO_ROOT)} ({DETAIL_PATH.stat().st_size / 1_000_000:.1f} MB).")
    print("audit_events.json.gz (summaries) is untouched -- only per-event evidence changed.")
    print("Run the data_pipeline and backend test suites, then commit the regenerated artifact when you're happy with coverage.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Stop after N newly-computed events this run (smoke test)")
    parser.add_argument("--grid-spacing", type=float, default=DEFAULT_GRID_SPACING_DEG, help=f"Degrees between weather grid points (default {DEFAULT_GRID_SPACING_DEG}, matched to ERA5's native resolution)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"Grid points per Open-Meteo request (default {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--dry-run", action="store_true", help="Print grid size and request-count estimate, fetch nothing")
    parser.add_argument("--finalize", action="store_true", help="Do not fetch anything -- fold checkpointed results into the committed artifact instead")
    args = parser.parse_args()

    if args.finalize:
        finalize()
        return
    run(limit=args.limit, grid_spacing=args.grid_spacing, batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
