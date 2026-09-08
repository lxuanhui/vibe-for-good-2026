import pandas as pd

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.enrichment.weather_enrichment import (
    WeatherEvidenceBundle,
    compute_weather_windows,
    to_evidence_objects,
    window_bounds,
)


def _event(first_detection: str, last_detection: str, event_id: str = "FE-TEST") -> FireEvent:
    return FireEvent(
        event_id=event_id,
        observation_indices=[0],
        first_detection=first_detection,
        last_detection=last_detection,
        duration_hours=0.0,
        observation_count=1,
        centroid=(-2.5, 114.0),
        bbox=(114.0, -2.5, 114.0, -2.5),
        spatial_extent_km=0.0,
        max_frp=10.0,
        mean_frp=10.0,
        sensor_mix=["N/VIIRS"],
    )


def _hourly(start: str, end: str, **columns) -> pd.DataFrame:
    """Synthetic Open-Meteo-shaped hourly frame: a `date` column plus
    whatever variable columns a test needs. Columns not passed are simply
    absent, same as a real response missing a requested variable."""
    dates = pd.date_range(start=start, end=end, freq="1h", tz="UTC", inclusive="left")
    data = {"date": dates}
    for name, value in columns.items():
        data[name] = [value] * len(dates) if not hasattr(value, "__len__") else value
    return pd.DataFrame(data)


def test_window_bounds_are_relative_to_event_timestamps():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-06T12:00:00+00:00")
    bounds = window_bounds(event)
    t0 = pd.Timestamp("2019-09-05T00:00:00+00:00")
    t_end = pd.Timestamp("2019-09-06T12:00:00+00:00")

    assert bounds["T-90d"] == (t0 - pd.Timedelta(days=90), t0)
    assert bounds["T-30d"] == (t0 - pd.Timedelta(days=30), t0)
    assert bounds["T-7d"] == (t0 - pd.Timedelta(days=7), t0)
    assert bounds["T-72h"] == (t0 - pd.Timedelta(hours=72), t0)
    assert bounds["T-24h"] == (t0 - pd.Timedelta(hours=24), t0)
    assert bounds["event_duration"] == (t0, t_end)
    assert bounds["T0_to_T+48h"] == (t0, t0 + pd.Timedelta(hours=48))


def test_rainfall_accumulation_and_dry_day_count_over_t24h():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T00:00:00+00:00")
    # Two days of hourly data feeding the T-24h window: last 24h has 5mm
    # total spread over a few hours, well above the 1mm/day threshold.
    precip = [0.0] * 47 + [5.0]
    hourly = _hourly("2019-09-03T00:00:00", "2019-09-05T00:00:00", precipitation=precip)

    windows = {w.window_name: w for w in compute_weather_windows(event, hourly)}
    assert windows["T-24h"].rainfall_mm == 5.0
    assert windows["T-24h"].rainfall_free_days == 0
    # T0_to_T+48h extends past where the synthetic data ends entirely --
    # must report None, not zero, for data that was never fetched.
    assert windows["T0_to_T+48h"].rainfall_mm is None
    assert "no Open-Meteo data available for this window" in windows["T0_to_T+48h"].limitations


def test_max_temp_and_mean_relative_humidity():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T12:00:00+00:00")
    hourly = _hourly(
        "2019-09-05T00:00:00", "2019-09-05T13:00:00",
        temperature_2m=[25.0, 30.0, 28.0] + [27.0] * 10,
        relative_humidity_2m=[80.0] * 13,
    )
    windows = {w.window_name: w for w in compute_weather_windows(event, hourly)}
    duration = windows["event_duration"]
    assert duration.max_temp_c == 30.0
    assert duration.mean_relative_humidity_pct == 80.0


def test_circular_mean_wind_direction_handles_wraparound():
    """Naive averaging of [350, 10] gives 180 (due south) -- exactly wrong.
    The vector mean must land near 0/360 (due north)."""
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T02:00:00+00:00")
    hourly = _hourly(
        "2019-09-05T00:00:00", "2019-09-05T02:00:00",
        wind_direction_10m=[350.0, 10.0],
        wind_speed_10m=[5.0, 5.0],
    )
    windows = {w.window_name: w for w in compute_weather_windows(event, hourly)}
    direction = windows["event_duration"].dominant_wind_direction_deg
    assert direction is not None
    assert direction < 15 or direction > 345


def test_soil_moisture_absent_when_column_missing():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T01:00:00+00:00")
    hourly = _hourly("2019-09-05T00:00:00", "2019-09-05T01:00:00", temperature_2m=[25.0])
    windows = {w.window_name: w for w in compute_weather_windows(event, hourly)}
    assert windows["event_duration"].mean_soil_moisture_m3m3 is None


def test_soil_moisture_present_when_column_available():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T01:00:00+00:00")
    hourly = _hourly("2019-09-05T00:00:00", "2019-09-05T01:00:00", soil_moisture_0_to_7cm=[0.35])
    windows = {w.window_name: w for w in compute_weather_windows(event, hourly)}
    assert windows["event_duration"].mean_soil_moisture_m3m3 == 0.35


def test_single_detection_event_has_zero_length_duration_window():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T00:00:00+00:00")
    hourly = _hourly("2019-09-04T00:00:00", "2019-09-06T00:00:00", temperature_2m=25.0)
    windows = {w.window_name: w for w in compute_weather_windows(event, hourly)}
    duration = windows["event_duration"]
    assert duration.rainfall_mm is None
    assert "single-detection event has a zero-length event_duration window" in duration.limitations


def test_source_disagreement_computed_when_power_data_present():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T02:00:00+00:00")
    hourly = _hourly(
        "2019-09-05T00:00:00", "2019-09-05T02:00:00",
        precipitation=[2.0, 2.0],
        temperature_2m=[30.0, 30.0],
    )
    power_daily = pd.DataFrame(
        {"PRECTOTCORR": [1.0], "T2M": [28.0]},
        index=pd.to_datetime(["2019-09-05"], utc=True),
    )
    windows = {w.window_name: w for w in compute_weather_windows(event, hourly, power_daily)}
    duration = windows["event_duration"]
    # om rainfall 4.0mm vs power 1.0mm -> disagreement +3.0
    assert duration.source_disagreement["rainfall_mm"] == 3.0
    assert duration.source_disagreement["mean_temp_c"] == 2.0


def test_source_disagreement_empty_when_power_data_absent():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T01:00:00+00:00")
    hourly = _hourly("2019-09-05T00:00:00", "2019-09-05T01:00:00", precipitation=[2.0])
    windows = {w.window_name: w for w in compute_weather_windows(event, hourly)}
    assert windows["event_duration"].source_disagreement == {}


def test_rainfall_anomaly_computed_against_baseline():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T02:00:00+00:00")
    hourly = _hourly("2019-09-05T00:00:00", "2019-09-05T02:00:00", precipitation=[10.0, 10.0])
    baseline = {"event_duration": [10.0, 20.0]}  # mean 15 -> actual 20 is +33.3%
    windows = {w.window_name: w for w in compute_weather_windows(event, hourly, baseline_rainfall_by_window=baseline)}
    assert windows["event_duration"].rainfall_anomaly_pct == 33.3


def test_evidence_objects_skip_none_metrics_and_include_disagreement_as_limitation():
    event = _event("2019-09-05T00:00:00+00:00", "2019-09-05T02:00:00+00:00")
    hourly = _hourly(
        "2019-09-05T00:00:00", "2019-09-05T02:00:00",
        precipitation=[2.0, 2.0],
    )
    power_daily = pd.DataFrame({"PRECTOTCORR": [0.0]}, index=pd.to_datetime(["2019-09-05"], utc=True))
    windows = compute_weather_windows(event, hourly, power_daily)
    bundle = WeatherEvidenceBundle(event_id=event.event_id, centroid=event.centroid, windows=windows)

    objects = to_evidence_objects(bundle)
    assert all(obj["value"] is not None for obj in objects)
    rainfall_objs = [o for o in objects if o["type"] == "rainfall" and "event_duration" in o["evidence_id"]]
    assert len(rainfall_objs) == 1
    assert any("NASA POWER disagrees" in limitation for limitation in rainfall_objs[0]["limitations"])
    # every evidence object traces to this event via its evidence_id
    assert all(event.event_id in obj["evidence_id"] for obj in objects)
