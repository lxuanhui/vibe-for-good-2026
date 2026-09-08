"""NASA POWER -- point-based agroclimatology/radiation archive.

Already point-based by design (no "national aggregate" ambiguity like
Open-Meteo raised). Tested for: (a) daily radiation + weather back into
the 1990s, (b) hourly resolution for a recent window, both for a specific
Indonesian peatland coordinate.

Docs: https://power.larc.nasa.gov/docs/services/api/
"""
from __future__ import annotations

import pandas as pd

from data_pipeline.common.http import SESSION
from data_pipeline.common.result import Provenance, SourceResult, SourceStatus
from data_pipeline.config import OUTPUT_DIR, POINTS

DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
HOURLY_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"

LIMITATIONS: list[str] = []

# T2M/RH2M/PRECTOTCORR/WS10M/WD10M = weather; ALLSKY_SFC_SW_DWN/CLRSKY_SFC_SW_DWN/
# ALLSKY_SFC_LW_DWN = the specific radiation values the spec calls for.
PARAMS = "T2M,RH2M,PRECTOTCORR,WS10M,WD10M,ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_SFC_LW_DWN"


def _query(url: str, lat: float, lon: float, start: str, end: str) -> dict:
    params = {
        "parameters": PARAMS,
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start,
        "end": end,
        "format": "JSON",
    }
    resp = SESSION.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def fetch_daily(lat: float, lon: float, start: str, end: str) -> dict:
    return _query(DAILY_URL, lat, lon, start, end)


def fetch_hourly(lat: float, lon: float, start: str, end: str) -> dict:
    return _query(HOURLY_URL, lat, lon, start, end)


def fetch_historical_sample() -> SourceResult:
    print("== NASA POWER ==")
    provenance = Provenance(endpoint=DAILY_URL, auth="none")

    try:
        name, (lat, lon) = next(iter(POINTS.items()))

        old = fetch_daily(lat, lon, "19900101", "19900105")
        old_series = old["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
        print(f"Daily shortwave radiation for {name}, Jan 1990: {old_series} "
              "(non-empty confirms the archive reaches back into the early record).")

        haze = fetch_daily(lat, lon, "20190901", "20190910")
        df = pd.DataFrame(haze["properties"]["parameter"])
        out = OUTPUT_DIR / f"nasa_power_daily_{name}_2019haze.csv"
        df.to_csv(out)
        print(f"2019 haze window daily pull for {name}: {len(df)} days, saved to {out}")

        hourly = fetch_hourly(lat, lon, "20190901", "20190903")
        hourly_temp = hourly["properties"]["parameter"]["T2M"]
        print(f"Hourly T2M sample count for {name}: {len(hourly_temp)} "
              "(point-based by construction -- one query per coordinate).\n")
    except Exception as exc:  # noqa: BLE001 -- normalized into SourceResult, not swallowed
        return SourceResult(
            source_name="NASA POWER",
            status=SourceStatus.FAILED,
            provenance=provenance,
            limitations=LIMITATIONS,
            error=str(exc),
        )

    return SourceResult(
        source_name="NASA POWER",
        status=SourceStatus.OK,
        provenance=provenance,
        limitations=LIMITATIONS,
        summary=f"daily archive reaches 1990, {len(df)}-day 2019 haze pull, "
                f"{len(hourly_temp)} hourly T2M rows",
        data=df,
    )


if __name__ == "__main__":
    fetch_historical_sample()
