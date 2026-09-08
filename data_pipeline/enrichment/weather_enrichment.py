"""Reconstruct the weather context around a FireEvent without a manual API
query per event.

A `FireEvent` (from `clustering/firms_clustering.py`) only says where and
when detections happened. Deciding whether an event is "compatible with
ordinary dry-season conditions" or "occurred after weeks with no rain"
needs weather -- and pulling that by hand per event does not scale past a
handful of cases. `fetch_weather_evidence_for_event()` is the automation
this issue asks for: one call, one event, one structured bundle.

## Windows

Seven windows relative to the event's own timestamps, not a fixed calendar
range, so the same function works for a five-minute single-detection event
and a five-day fire complex:

  T-90d, T-30d, T-7d, T-72h, T-24h        -- lookback windows, each ending
                                              at T0 (`event.first_detection`)
  event_duration                          -- T0 to `event.last_detection`
  T0_to_T+48h                             -- T0 to T0+48h (does the weather
                                              *after* first detection explain
                                              continued spread?)

A single-detection event has `first_detection == last_detection`, so
`event_duration` is a zero-length window. That is not a bug: it means there
is nothing to report for that window, and every metric for it comes back
`None` with a limitation noting why, rather than a fabricated value.

## Sources and why two

Open-Meteo (ERA5/ERA5-Land reanalysis, hourly) is the primary source --
hourly resolution covers every window down to T-24h without gaps, and its
hourly variables include soil moisture, which NASA POWER's parameter set
here does not. NASA POWER (daily) is not a second primary source; it exists
only to compute **source disagreement** -- the derived metric this issue
explicitly asks for. Two independent reanalysis products estimating the
same window from the same station-sparse region should roughly agree, and
by how much they *don't* is itself evidence-relevant: it tells a reviewer
how much to trust either number, which single-source presentation would
hide. Comparison is truncated to whole days because POWER's daily archive
has no finer resolution -- documented per-window as a limitation, not
silently approximated.

## Local historical anomaly

Computed for rainfall accumulation only, not every metric: rainfall is the
one variable this project's evidence-framing treats as fire-relevant on its
own (a fire following weeks of anomalously low rainfall is a materially
different observation than one following a normal wet season), and adding
five more anomaly series per window for temperature/RH/wind would multiply
network calls for metrics nobody downstream asks for yet. The baseline is
the mean rainfall of the same window shape (same length, same
day-of-year span) across the `baseline_years` preceding years at the same
point -- a single extra Open-Meteo call per baseline year, reused across
all seven windows, not one call per window per year.

## Output shape

`compute_weather_windows()` is pure -- it takes already-fetched DataFrames
and returns `WeatherWindowMetrics`, so it is unit-testable against
synthetic data without a network call. `fetch_weather_evidence_for_event()`
does the actual fetching and is the only network-touching function in this
module (besides its `_demo()`). `to_evidence_objects()` converts a bundle
into the `EvidenceObject` shape from `Environmental_Assurance_Spec.md` §16
-- one object per (window, metric) pair, each independently traceable, so a
downstream agent cites a specific evidence_id rather than "the weather
bundle" as an undifferentiated blob.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.sources.nasa_power import fetch_daily as _power_fetch_daily
from data_pipeline.sources.open_meteo import _hourly_to_df
from data_pipeline.sources.open_meteo import fetch_point as _om_fetch_point

RAINFALL_FREE_THRESHOLD_MM = 1.0
DEFAULT_BASELINE_YEARS = 5

# NASA POWER's documented fill value for a missing daily observation.
POWER_FILL_VALUE = -999.0

WINDOW_NAMES = ["T-90d", "T-30d", "T-7d", "T-72h", "T-24h", "event_duration", "T0_to_T+48h"]


@dataclass
class WeatherWindowMetrics:
    """Derived weather metrics for one window around a FireEvent. A `None`
    value means the underlying data was unavailable for that window/metric,
    never a fabricated placeholder -- always check `limitations` first."""

    window_name: str
    start: str
    end: str
    rainfall_mm: float | None
    rainfall_free_days: int | None
    max_temp_c: float | None
    mean_relative_humidity_pct: float | None
    mean_wind_speed_ms: float | None
    dominant_wind_direction_deg: float | None
    mean_soil_moisture_m3m3: float | None
    rainfall_anomaly_pct: float | None
    source_disagreement: dict[str, float | None] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


@dataclass
class WeatherEvidenceBundle:
    """The complete weather evidence bundle for one FireEvent -- every
    window this issue's acceptance criteria requires, computed in one
    call."""

    event_id: str
    centroid: tuple[float, float]
    windows: list[WeatherWindowMetrics]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def window_bounds(event: FireEvent) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """The seven windows' (start, end) bounds for one event, derived purely
    from its own first/last detection timestamps."""
    t0 = pd.Timestamp(event.first_detection)
    t_end = pd.Timestamp(event.last_detection)
    return {
        "T-90d": (t0 - pd.Timedelta(days=90), t0),
        "T-30d": (t0 - pd.Timedelta(days=30), t0),
        "T-7d": (t0 - pd.Timedelta(days=7), t0),
        "T-72h": (t0 - pd.Timedelta(hours=72), t0),
        "T-24h": (t0 - pd.Timedelta(hours=24), t0),
        "event_duration": (t0, t_end),
        "T0_to_T+48h": (t0, t0 + pd.Timedelta(hours=48)),
    }


def _slice_hourly(hourly: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if hourly.empty:
        return hourly
    return hourly[(hourly["date"] >= start) & (hourly["date"] < end)]


def _rainfall_mm(sl: pd.DataFrame) -> float | None:
    if sl.empty or "precipitation" not in sl.columns:
        return None
    return float(sl["precipitation"].sum())


def _rainfall_free_days(sl: pd.DataFrame) -> int | None:
    if sl.empty or "precipitation" not in sl.columns:
        return None
    daily = sl.set_index("date")["precipitation"].resample("1D").sum()
    return int((daily < RAINFALL_FREE_THRESHOLD_MM).sum())


def _max_temp(sl: pd.DataFrame) -> float | None:
    if sl.empty or "temperature_2m" not in sl.columns:
        return None
    return float(sl["temperature_2m"].max())


def _mean_column(sl: pd.DataFrame, column: str) -> float | None:
    if sl.empty or column not in sl.columns:
        return None
    value = sl[column].mean()
    return float(value) if pd.notna(value) else None


def _circular_mean_wind_direction(sl: pd.DataFrame) -> float | None:
    """Vector mean weighted by wind speed, not a naive average of degrees --
    a naive mean of [350, 10] gives 180 (due south), the opposite of the
    correct answer (due north)."""
    if sl.empty or "wind_direction_10m" not in sl.columns:
        return None
    directions = sl["wind_direction_10m"].dropna()
    if directions.empty:
        return None
    rad = np.radians(directions.to_numpy())
    weights = None
    if "wind_speed_10m" in sl.columns:
        speeds = sl.loc[directions.index, "wind_speed_10m"].fillna(0.0).to_numpy()
        if speeds.sum() > 0:
            weights = speeds
    x = np.average(np.cos(rad), weights=weights)
    y = np.average(np.sin(rad), weights=weights)
    if x == 0 and y == 0:
        return None
    return float(np.degrees(np.arctan2(y, x)) % 360)


def _mean_soil_moisture(sl: pd.DataFrame) -> float | None:
    # Shallowest layer -- most responsive to recent rainfall, the layer most
    # relevant to a fire-context window; deeper layers are in the raw
    # DataFrame but not summarized here.
    return _mean_column(sl, "soil_moisture_0_to_7cm")


def _power_json_to_df(power_json: dict) -> pd.DataFrame:
    params = power_json.get("properties", {}).get("parameter", {})
    if not params:
        return pd.DataFrame()
    df = pd.DataFrame(params)
    df.index = pd.to_datetime(df.index, format="%Y%m%d", utc=True)
    return df.replace(POWER_FILL_VALUE, np.nan)


def _slice_power(power_daily: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if power_daily.empty:
        return power_daily
    # Day-granularity only -- POWER's daily archive has no finer resolution,
    # so an hourly window boundary (e.g. T-24h) is truncated to whole days.
    return power_daily[(power_daily.index >= start.normalize()) & (power_daily.index <= end.normalize())]


def _power_disagreement(om_sl: pd.DataFrame, power_sl: pd.DataFrame, om_rainfall: float | None) -> dict[str, float | None]:
    if power_sl.empty:
        return {}

    def _delta(om_value: float | None, power_series: str) -> float | None:
        if om_value is None or power_series not in power_sl.columns:
            return None
        power_value = power_sl[power_series].mean()
        if pd.isna(power_value):
            return None
        return round(om_value - float(power_value), 2)

    power_rainfall = float(power_sl["PRECTOTCORR"].sum()) if "PRECTOTCORR" in power_sl.columns else None
    disagreement: dict[str, float | None] = {}
    if om_rainfall is not None and power_rainfall is not None:
        disagreement["rainfall_mm"] = round(om_rainfall - power_rainfall, 2)
    disagreement["mean_temp_c"] = _delta(_mean_column(om_sl, "temperature_2m"), "T2M")
    disagreement["mean_relative_humidity_pct"] = _delta(_mean_column(om_sl, "relative_humidity_2m"), "RH2M")
    disagreement["mean_wind_speed_ms"] = _delta(_mean_column(om_sl, "wind_speed_10m"), "WS10M")
    return {k: v for k, v in disagreement.items() if v is not None}


def _rainfall_anomaly_pct(actual_mm: float | None, baseline_values: list[float]) -> float | None:
    if actual_mm is None or not baseline_values:
        return None
    baseline_mean = float(np.mean(baseline_values))
    if baseline_mean == 0:
        return None
    return round((actual_mm - baseline_mean) / baseline_mean * 100.0, 1)


def compute_weather_windows(
    event: FireEvent,
    om_hourly: pd.DataFrame,
    power_daily: pd.DataFrame | None = None,
    baseline_rainfall_by_window: dict[str, list[float]] | None = None,
) -> list[WeatherWindowMetrics]:
    """Pure computation over already-fetched data -- no network access, so
    this is what tests exercise directly against synthetic DataFrames."""
    bounds = window_bounds(event)
    baseline_rainfall_by_window = baseline_rainfall_by_window or {}
    power_daily = power_daily if power_daily is not None else pd.DataFrame()

    windows = []
    for name, (start, end) in bounds.items():
        sl = _slice_hourly(om_hourly, start, end)
        limitations: list[str] = []
        if sl.empty:
            reason = (
                "single-detection event has a zero-length event_duration window"
                if name == "event_duration" and start == end
                else "no Open-Meteo data available for this window"
            )
            limitations.append(reason)

        rainfall = _rainfall_mm(sl)
        power_sl = _slice_power(power_daily, start, end)
        disagreement = _power_disagreement(sl, power_sl, rainfall)
        if not sl.empty and power_sl.empty and not power_daily.empty:
            limitations.append("no NASA POWER data available for this window; source disagreement not computed")

        windows.append(
            WeatherWindowMetrics(
                window_name=name,
                start=start.isoformat(),
                end=end.isoformat(),
                rainfall_mm=rainfall,
                rainfall_free_days=_rainfall_free_days(sl),
                max_temp_c=_max_temp(sl),
                mean_relative_humidity_pct=_mean_column(sl, "relative_humidity_2m"),
                mean_wind_speed_ms=_mean_column(sl, "wind_speed_10m"),
                dominant_wind_direction_deg=_circular_mean_wind_direction(sl),
                mean_soil_moisture_m3m3=_mean_soil_moisture(sl),
                rainfall_anomaly_pct=_rainfall_anomaly_pct(rainfall, baseline_rainfall_by_window.get(name, [])),
                source_disagreement=disagreement,
                limitations=limitations,
            )
        )
    return windows


def fetch_weather_evidence_for_event(
    event: FireEvent,
    lat: float,
    lon: float,
    baseline_years: int = DEFAULT_BASELINE_YEARS,
) -> WeatherEvidenceBundle:
    """The one call this issue asks for: FireEvent in, complete weather
    evidence bundle out, no manual API query. `lat`/`lon` are taken
    separately from `event.centroid` so a caller can enrich at the
    detection centroid, the audit-scope point of interest, or any other
    coordinate the event is relevant to."""
    bounds = window_bounds(event)
    range_start = min(s for s, _ in bounds.values())
    range_end = max(e for _, e in bounds.values())

    om_response = _om_fetch_point(lat, lon, range_start.strftime("%Y-%m-%d"), range_end.strftime("%Y-%m-%d"))
    om_hourly = _hourly_to_df(om_response)

    power_json = _power_fetch_daily(lat, lon, range_start.strftime("%Y%m%d"), range_end.strftime("%Y%m%d"))
    power_daily = _power_json_to_df(power_json)

    baseline_rainfall_by_window: dict[str, list[float]] = {name: [] for name in bounds}
    for years_back in range(1, baseline_years + 1):
        shifted_start = range_start - pd.DateOffset(years=years_back)
        shifted_end = range_end - pd.DateOffset(years=years_back)
        try:
            shifted_response = _om_fetch_point(
                lat, lon, shifted_start.strftime("%Y-%m-%d"), shifted_end.strftime("%Y-%m-%d")
            )
        except Exception as exc:  # noqa: BLE001 -- baseline is best-effort; a missing year just narrows the sample
            print(f"  (baseline year -{years_back}: skipped, {exc})")
            continue
        shifted_hourly = _hourly_to_df(shifted_response)
        for name, (start, end) in bounds.items():
            sl = _slice_hourly(shifted_hourly, start - pd.DateOffset(years=years_back), end - pd.DateOffset(years=years_back))
            rainfall = _rainfall_mm(sl)
            if rainfall is not None:
                baseline_rainfall_by_window[name].append(rainfall)

    windows = compute_weather_windows(event, om_hourly, power_daily, baseline_rainfall_by_window)
    return WeatherEvidenceBundle(event_id=event.event_id, centroid=(lat, lon), windows=windows)


_EVIDENCE_METRICS: list[tuple[str, str, str, str]] = [
    # (attribute, type, unit, observation template)
    ("rainfall_mm", "rainfall", "mm", "{value} mm rainfall during {window}"),
    ("rainfall_free_days", "rainfall_free_days", "days", "{value} rainfall-free days during {window}"),
    ("max_temp_c", "max_temperature", "degC", "maximum temperature of {value} degC during {window}"),
    ("mean_relative_humidity_pct", "relative_humidity", "pct", "mean relative humidity of {value}% during {window}"),
    ("mean_wind_speed_ms", "wind_speed", "m/s", "mean wind speed of {value} m/s during {window}"),
    ("dominant_wind_direction_deg", "wind_direction", "deg", "dominant wind direction of {value} deg during {window}"),
    ("mean_soil_moisture_m3m3", "soil_moisture", "m3/m3", "mean topsoil moisture of {value} m3/m3 during {window}"),
]


# Single-sourced count of possible weather evidence objects per FireEvent
# (7 windows x this many metrics) -- used by the benchmark in issue #7 to
# compute evidence-field completeness without duplicating the "7" as a
# separate magic number.
EVIDENCE_METRICS_PER_WINDOW = len(_EVIDENCE_METRICS)


def to_evidence_objects(bundle: WeatherEvidenceBundle) -> list[dict]:
    """Convert a bundle into `EvidenceObject`s (`Environmental_Assurance_Spec.md`
    §16) -- one per (window, metric) that actually has a value, each with
    its own evidence_id so an AI interpretation layer cites a specific
    number rather than "the weather bundle" as a whole."""
    objects: list[dict] = []
    for window in bundle.windows:
        for attr, metric_type, unit, template in _EVIDENCE_METRICS:
            value = getattr(window, attr)
            if value is None:
                continue
            limitations = list(window.limitations)
            if attr == "rainfall_mm" and window.rainfall_anomaly_pct is not None:
                direction = "above" if window.rainfall_anomaly_pct >= 0 else "below"
                limitations.append(
                    f"{abs(window.rainfall_anomaly_pct)}% {direction} the "
                    f"{DEFAULT_BASELINE_YEARS}-year seasonal baseline for this window"
                )
            if attr in window.source_disagreement:
                limitations.append(
                    f"NASA POWER disagrees by {window.source_disagreement[attr]} {unit} for this window"
                )
            objects.append(
                {
                    "evidence_id": f"ENV_WEATHER_{bundle.event_id}_{window.window_name}_{metric_type}",
                    "category": "weather",
                    "type": metric_type,
                    "observation": template.format(value=value, window=window.window_name),
                    "source": "Open-Meteo/ERA5",
                    "time_window": f"{window.start} to {window.end}",
                    "value": value,
                    "unit": unit,
                    "quality": 0.6 if limitations else 0.82,
                    "limitations": limitations,
                    "retrieved_at": bundle.generated_at,
                    "algorithm_version": None,
                    "raw_reference": None,
                }
            )
    return objects


def _demo() -> None:
    import json

    from data_pipeline.clustering.firms_clustering import cluster_events
    from data_pipeline.config import OUTPUT_DIR

    print("== Historical weather-window enrichment ==")
    sample_path = OUTPUT_DIR / "firms_2019_haze_sample.csv"
    if sample_path.exists():
        observations = pd.read_csv(sample_path)
    else:
        from data_pipeline.config import SUMATRA_KALIMANTAN_BBOX
        from data_pipeline.sources.nasa_firms import fetch_area

        observations = fetch_area("VIIRS_SNPP_SP", SUMATRA_KALIMANTAN_BBOX, day_range=5, start_date="2019-09-01")

    events, _ = cluster_events(observations)
    event = max(events, key=lambda e: e.observation_count)
    lat, lon = event.centroid
    print(f"Enriching {event.event_id} ({event.observation_count} obs, centroid={event.centroid}) ...")

    bundle = fetch_weather_evidence_for_event(event, lat, lon)
    for window in bundle.windows:
        print(
            f"  {window.window_name:15s} rainfall={window.rainfall_mm}mm "
            f"dry_days={window.rainfall_free_days} max_temp={window.max_temp_c}C "
            f"anomaly={window.rainfall_anomaly_pct}% disagreement={window.source_disagreement} "
            f"limitations={window.limitations}"
        )

    evidence = to_evidence_objects(bundle)
    out = OUTPUT_DIR / f"weather_evidence_{event.event_id}.json"
    out.write_text(json.dumps(evidence, indent=2))
    print(f"Saved {len(evidence)} evidence objects to {out}\n")


if __name__ == "__main__":
    _demo()
