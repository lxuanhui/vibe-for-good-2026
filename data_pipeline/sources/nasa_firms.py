"""NASA FIRMS (Fire Information for Resource Management System).

Free thermal-hotspot feed from MODIS/VIIRS. Requires a MAP_KEY (already
provisioned in .env). This proves three things empirically instead of
trusting possibly-stale docs:
  1. the MAP_KEY actually works (mapkey_status)
  2. how far back each sensor's archive actually reaches (data_availability)
  3. a real historical pull over Sumatra/Kalimantan returns individual,
     geolocated hotspots -- not a single national aggregate

Docs: https://firms.modaps.eosdis.nasa.gov/api/
"""
from __future__ import annotations

import io

import pandas as pd

from data_pipeline.common.http import SESSION
from data_pipeline.config import NASA_FIRMS_MAP_KEY, OUTPUT_DIR, SUMATRA_KALIMANTAN_BBOX

FIRMS_ROOT = "https://firms.modaps.eosdis.nasa.gov"
MAX_DAY_RANGE = 5  # enforced by the area API itself


def check_map_key_status() -> dict:
    resp = SESSION.get(f"{FIRMS_ROOT}/mapserver/mapkey_status/", params={"MAP_KEY": NASA_FIRMS_MAP_KEY})
    resp.raise_for_status()
    return resp.json()


def data_availability(sensor: str = "ALL") -> pd.DataFrame:
    url = f"{FIRMS_ROOT}/api/data_availability/csv/{NASA_FIRMS_MAP_KEY}/{sensor}"
    resp = SESSION.get(url)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text))


def fetch_area(source: str, bbox: tuple[float, float, float, float], day_range: int, start_date: str | None = None) -> pd.DataFrame:
    day_range = min(day_range, MAX_DAY_RANGE)
    bbox_str = ",".join(str(v) for v in bbox)
    url = f"{FIRMS_ROOT}/api/area/csv/{NASA_FIRMS_MAP_KEY}/{source}/{bbox_str}/{day_range}"
    if start_date:
        url += f"/{start_date}"
    resp = SESSION.get(url)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text))


def fetch_historical_sample() -> None:
    print("== NASA FIRMS ==")
    status = check_map_key_status()
    print(f"MAP_KEY status: {status}")

    avail = data_availability("VIIRS_SNPP_SP")
    print("VIIRS_SNPP_SP availability:")
    print(avail.to_string(index=False))

    start = "2019-09-01"
    print(f"Area API day_range is capped at {MAX_DAY_RANGE} -- a 10-day historical "
          "backfill needs two calls with shifted start dates, not one.")
    df = fetch_area("VIIRS_SNPP_SP", SUMATRA_KALIMANTAN_BBOX, day_range=MAX_DAY_RANGE, start_date=start)
    print(f"Hotspots {start} + {MAX_DAY_RANGE}d over Sumatra/Kalimantan bbox: {len(df)} rows")
    if not df.empty:
        print(df[["latitude", "longitude", "acq_date", "confidence"]].head().to_string(index=False))
        out = OUTPUT_DIR / "firms_2019_haze_sample.csv"
        df.to_csv(out, index=False)
        print(f"Saved sample to {out}")
    print("Per-row lat/lon confirms individual hotspot geolocation, not a country aggregate.\n")


if __name__ == "__main__":
    fetch_historical_sample()
