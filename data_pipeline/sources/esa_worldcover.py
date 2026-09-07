"""ESA WorldCover -- static 10m global land-cover map (2020 v100, 2021 v200).

No API, no auth: it's a public S3 bucket of 3x3-degree Cloud-Optimized
GeoTIFF tiles named by their lower-left corner, e.g.
ESA_WorldCover_10m_2021_v200_S03E102_Map.tif. This computes the tile name
for each Indonesian point of interest and confirms via HTTP HEAD that the
corresponding tile actually exists in both epochs.

There is no "historical" dimension beyond the two available epochs (2020,
2021) -- that's a real limitation to flag for the project, not a gap in
this script.

Docs: https://github.com/ESA-WorldCover/esa-worldcover-datasets
"""
from __future__ import annotations

import math

from data_pipeline.common.http import SESSION
from data_pipeline.config import POINTS

BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com"
EPOCHS = {
    "v100/2020": "ESA_WorldCover_10m_2020_v100",
    "v200/2021": "ESA_WorldCover_10m_2021_v200",
}


def tile_name(lat: float, lon: float) -> str:
    lat_floor = int(math.floor(lat / 3.0) * 3)
    lon_floor = int(math.floor(lon / 3.0) * 3)
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    return f"{ns}{abs(lat_floor):02d}{ew}{abs(lon_floor):03d}"


def tile_url(path_prefix: str, product_prefix: str, tile: str) -> str:
    return f"{BASE}/{path_prefix}/map/{product_prefix}_{tile}_Map.tif"


def fetch_historical_sample() -> None:
    print("== ESA WorldCover ==")
    for name, (lat, lon) in POINTS.items():
        tile = tile_name(lat, lon)
        for path_prefix, product_prefix in EPOCHS.items():
            url = tile_url(path_prefix, product_prefix, tile)
            resp = SESSION.head(url)
            print(f"{name} ({lat},{lon}) -> tile {tile} [{path_prefix}]: HTTP {resp.status_code} -- {url}")
    print("Only two epochs exist (2020, 2021) -- not a time series; flag this "
          "if the product needs finer-grained land-cover history.\n")


if __name__ == "__main__":
    fetch_historical_sample()
