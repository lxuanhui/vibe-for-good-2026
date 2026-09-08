"""FIRMS historical backfill -- turns the Area API's 5-day day_range cap
into an implementation detail behind one call.

`nasa_firms.fetch_area()` already proves a single <=5-day pull works. This
module chains as many of those calls as an arbitrary date range needs,
merges them into one deduplicated result, retries a window that fails
independently of the shared session's own `retry_requests` backoff (which
only covers transient HTTP-level failures within one request, not "this
specific 5-day window errored 3 times in a row and the rest of the backfill
should still finish"), and separates hotspots into two named sets instead
of one:

  observations       -- inside the analysis region (default: all Indonesia)
  external_context    -- inside the queried bbox but *outside* the analysis
                          region: nearby detections kept for corroborating
                          context, never silently dropped and never merged
                          into the same set as in-scope observations

Both are raw FIRMS observations, not FireEvents -- per-point hotspots, not
independently significant fires. Grouping them into FireEvents is issue #4.

`analysis_region` is a bounding box, not a political boundary -- Kalimantan
is shared with Malaysia and Brunei, so a rectangular Indonesia box cannot
precisely separate "Indonesian" from "Malaysian" hotspots sitting inside
the same rectangle near the border. Treat the observations/external_context
split as "inside vs. near the analysis area," not a territorial
determination -- geographic intersection is context, never responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd
import requests_cache

from data_pipeline.config import INDONESIA_BBOX, OUTPUT_DIR, SUMATRA_KALIMANTAN_BBOX
from data_pipeline.sources.nasa_firms import MAX_DAY_RANGE, fetch_area

# FIRMS Near-Real-Time rows can still be corrected for a few days after
# acquisition; only cache a window forever once it's safely past that
# revision window. Standard Processing products (the "_SP" suffix) revise
# less aggressively than NRT, but this stays conservative across both.
STABLE_AFTER_DAYS = 7

# Columns that uniquely identify one physical hotspot detection, used to
# drop duplicates at window boundaries -- falls back to whatever subset of
# these a given FIRMS product's CSV actually has.
DEDUP_COLUMNS = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument"]


@dataclass
class BackfillWindow:
    """One <=5-day Area API call that made up a larger backfill request."""

    start_date: str
    end_date: str
    attempts: int
    status: str  # "ok" | "failed"
    rows: int = 0
    error: str | None = None


@dataclass
class FirmsBackfillResult:
    """One normalized result set for an arbitrary-length historical range --
    the 5-day paging a caller would otherwise have to do by hand is already
    resolved by the time this comes back."""

    observations: pd.DataFrame
    external_context: pd.DataFrame
    windows: list[BackfillWindow] = field(default_factory=list)
    source: str = ""
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    analysis_region: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    start_date: str = ""
    end_date: str = ""

    @property
    def failed_windows(self) -> list[BackfillWindow]:
        return [w for w in self.windows if w.status == "failed"]


def _chunk_date_range(start_date: str, end_date: str, chunk_days: int):
    """Yield consecutive (window_start, window_end) date strings covering
    [start_date, end_date] inclusive, each spanning at most `chunk_days`."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if start > end:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}")
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=chunk_days - 1), end)
        yield cursor.isoformat(), window_end.isoformat()
        cursor = window_end + timedelta(days=1)


def _cache_policy(window_end: str) -> int | None:
    """None leaves the shared session's normal 1-hour default in place;
    NEVER_EXPIRE is used once a window can no longer be revised upstream."""
    end = datetime.strptime(window_end, "%Y-%m-%d").date()
    if end <= date.today() - timedelta(days=STABLE_AFTER_DAYS):
        return requests_cache.NEVER_EXPIRE
    return None


def _in_bbox(lat: pd.Series, lon: pd.Series, bbox: tuple[float, float, float, float]) -> pd.Series:
    west, south, east, north = bbox
    return lat.between(south, north) & lon.between(west, east)


def fetch_historical_range(
    bbox: tuple[float, float, float, float],
    start_date: str,
    end_date: str,
    source: str = "VIIRS_SNPP_SP",
    analysis_region: tuple[float, float, float, float] = INDONESIA_BBOX,
    max_retries: int = 3,
) -> FirmsBackfillResult:
    """Fetch every FIRMS hotspot in `bbox` for [start_date, end_date],
    paging the Area API's 5-day cap transparently. Returns one deduplicated
    result set split into `observations` (inside `analysis_region`) and
    `external_context` (inside `bbox` but outside it).

    A window that fails is retried up to `max_retries` times; if it still
    fails, it's recorded in `result.failed_windows` and the backfill
    continues with the remaining windows rather than aborting the whole
    request over one bad window.
    """
    windows: list[BackfillWindow] = []
    frames: list[pd.DataFrame] = []

    for window_start, window_end in _chunk_date_range(start_date, end_date, MAX_DAY_RANGE):
        day_range = (
            datetime.strptime(window_end, "%Y-%m-%d").date()
            - datetime.strptime(window_start, "%Y-%m-%d").date()
        ).days + 1
        expire_after = _cache_policy(window_end)

        attempts = 0
        last_error: str | None = None
        df: pd.DataFrame | None = None
        while attempts < max_retries:
            attempts += 1
            try:
                df = fetch_area(
                    source, bbox, day_range=day_range, start_date=window_start, expire_after=expire_after
                )
                break
            except Exception as exc:  # noqa: BLE001 -- retried in-loop, recorded either way
                last_error = str(exc)

        if df is None:
            windows.append(BackfillWindow(window_start, window_end, attempts, "failed", error=last_error))
            continue

        windows.append(BackfillWindow(window_start, window_end, attempts, "ok", rows=len(df)))
        if not df.empty:
            frames.append(df)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if not combined.empty:
        # Original acq_date/acq_time/satellite/instrument columns pass
        # through untouched -- only paging and de-duplication happen here.
        combined = combined[(combined["acq_date"] >= start_date) & (combined["acq_date"] <= end_date)]
        dedup_subset = [c for c in DEDUP_COLUMNS if c in combined.columns]
        combined = combined.drop_duplicates(subset=dedup_subset or None).reset_index(drop=True)
        in_region = _in_bbox(combined["latitude"], combined["longitude"], analysis_region)
        observations = combined[in_region].reset_index(drop=True)
        external_context = combined[~in_region].reset_index(drop=True)
    else:
        observations = combined
        external_context = combined.copy()

    return FirmsBackfillResult(
        observations=observations,
        external_context=external_context,
        windows=windows,
        source=source,
        bbox=bbox,
        analysis_region=analysis_region,
        start_date=start_date,
        end_date=end_date,
    )


def _demo() -> None:
    print("== NASA FIRMS historical backfill ==")
    result = fetch_historical_range(
        bbox=SUMATRA_KALIMANTAN_BBOX,
        start_date="2019-08-01",
        end_date="2019-10-31",
    )
    total_raw = sum(w.rows for w in result.windows)
    print(f"{len(result.windows)} windows chained (day_range<=5 each), {total_raw} raw rows before dedup")
    print(f"observations (inside Indonesia analysis region): {len(result.observations)}")
    print(f"external_context (inside bbox, outside analysis region): {len(result.external_context)}")
    if result.failed_windows:
        print("failed windows (retried, still unrecovered):")
        for w in result.failed_windows:
            print(f"  {w.start_date}..{w.end_date}: {w.error}")
    else:
        print("no failed windows.")

    out = OUTPUT_DIR / "firms_backfill_2019_aug_oct.csv"
    result.observations.to_csv(out, index=False)
    print(f"Saved deduplicated observations to {out}\n")


if __name__ == "__main__":
    _demo()
