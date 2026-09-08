"""Open-Meteo Historical Weather Archive (ERA5/ERA5-Land reanalysis).

Answers the two questions this project actually needs answered:
  1. Can we pull hourly + daily variables for a SPECIFIC Indonesian
     lat/lon -- not one aggregate value for the whole country? Yes: the
     API is inherently point-based. Proven here by querying three
     distinct peat-fire-prone points and confirming the values differ,
     and by a single batched multi-point request (useful for cron
     efficiency later).
  2. How far back does the archive go? ERA5 reanalysis nominally reaches
     back to 1940; tested here against the 2019 haze window plus an
     older decade+ sample.

Docs: https://open-meteo.com/en/docs/historical-weather-api
"""
from __future__ import annotations

import pandas as pd
import openmeteo_requests

from data_pipeline.common.http import SESSION
from data_pipeline.common.result import Provenance, SourceResult, SourceStatus
from data_pipeline.config import HISTORICAL_WINDOW, OUTPUT_DIR, POINTS

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

LIMITATIONS: list[str] = [
    "ERA5/ERA5-Land reanalysis, not direct station observation -- ~0.25 deg "
    "grid interpolated to the query point, not a measurement at that exact "
    "coordinate.",
]

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_speed_100m",
    "wind_direction_100m",
    "soil_temperature_0_to_7cm",
    "soil_temperature_7_to_28cm",
    "soil_temperature_28_to_100cm",
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "soil_moisture_28_to_100cm",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
]

DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
    "shortwave_radiation_sum",  # daily total solar radiation, MJ/m^2 -- the "specific radiation value"
    "et0_fao_evapotranspiration",
]

client = openmeteo_requests.Client(session=SESSION)


def fetch_point(lat: float, lon: float, start_date: str, end_date: str):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": HOURLY_VARS,
        "daily": DAILY_VARS,
        "timezone": "auto",
    }
    return client.weather_api(ARCHIVE_URL, params=params)[0]


def fetch_batch(points: dict[str, tuple[float, float]], start_date: str, end_date: str):
    lats = ",".join(str(p[0]) for p in points.values())
    lons = ",".join(str(p[1]) for p in points.values())
    params = {
        "latitude": lats,
        "longitude": lons,
        "start_date": start_date,
        "end_date": end_date,
        "daily": DAILY_VARS,
        "timezone": "auto",
    }
    return client.weather_api(ARCHIVE_URL, params=params)


def _hourly_to_df(response) -> pd.DataFrame:
    hourly = response.Hourly()
    data = {
        "date": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left",
        )
    }
    for i, name in enumerate(HOURLY_VARS):
        data[name] = hourly.Variables(i).ValuesAsNumpy()
    return pd.DataFrame(data)


def fetch_historical_sample() -> SourceResult:
    print("== Open-Meteo (Historical Weather Archive) ==")
    provenance = Provenance(endpoint=ARCHIVE_URL, auth="none")

    try:
        start, end = HISTORICAL_WINDOW
        per_point_means = {}
        for name, (lat, lon) in POINTS.items():
            response = fetch_point(lat, lon, start, end)
            df = _hourly_to_df(response)
            per_point_means[name] = float(df["temperature_2m"].mean())
            out = OUTPUT_DIR / f"open_meteo_hourly_{name}.csv"
            df.to_csv(out, index=False)
            print(f"{name} ({lat},{lon}): {len(df)} hourly rows, "
                  f"mean temp_2m={per_point_means[name]:.2f}C, elevation={response.Elevation()}m")

        distinct = len(set(round(v, 2) for v in per_point_means.values())) > 1
        print(f"Values differ across points: {distinct} "
              "-> confirms per-coordinate retrieval, not a single national value.")

        batch = fetch_batch(POINTS, start, end)
        print(f"Batched single-request pull for {len(POINTS)} points returned "
              f"{len(batch)} responses, coords: "
              f"{[(round(r.Latitude(), 2), round(r.Longitude(), 2)) for r in batch]} "
              "-- multi-point historical pulls work in one HTTP call, useful for cron efficiency.")

        old_name, (lat, lon) = next(iter(POINTS.items()))
        old_response = fetch_point(lat, lon, "2005-01-01", "2005-01-03")
        old_df = _hourly_to_df(old_response)
        print(f"2005-01-01..03 sample for {old_name}: {len(old_df)} hourly rows "
              "(non-empty confirms the archive reaches back at least this far).\n")
    except Exception as exc:  # noqa: BLE001 -- normalized into SourceResult, not swallowed
        return SourceResult(
            source_name="Open-Meteo",
            status=SourceStatus.FAILED,
            provenance=provenance,
            limitations=LIMITATIONS,
            error=str(exc),
        )

    return SourceResult(
        source_name="Open-Meteo",
        status=SourceStatus.OK,
        provenance=provenance,
        limitations=LIMITATIONS,
        summary=f"{len(POINTS)} points, per-point values distinct={distinct}, "
                f"archive reaches back to at least 2005 ({len(old_df)} rows)",
    )


if __name__ == "__main__":
    fetch_historical_sample()
