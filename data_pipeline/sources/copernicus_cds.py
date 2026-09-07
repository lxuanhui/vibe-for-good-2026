"""Copernicus Data Space Ecosystem -- Sentinel-1/2 catalogue via STAC.

Catalogue SEARCH does not require authentication (confirmed against
https://documentation.dataspace.copernicus.eu/APIs/STAC.html); only actual
product *download* needs an OAuth2 token from a free CDSE account. This
proves the search path works for a historical Sumatra/Kalimantan query
and, if CDSE_USERNAME/CDSE_PASSWORD are set in .env, that the token
exchange also works.

Docs: https://documentation.dataspace.copernicus.eu/APIs/STAC.html
      https://documentation.dataspace.copernicus.eu/APIs/Token.html
"""
from __future__ import annotations

from data_pipeline.common.http import SESSION
from data_pipeline.config import CDSE_PASSWORD, CDSE_USERNAME, SUMATRA_KALIMANTAN_BBOX

STAC_URL = "https://stac.dataspace.copernicus.eu/v1/search"
# S105 matches the variable name, not the value: this is the public OAuth2
# endpoint, not a credential.
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"  # noqa: S105


def search(collection: str, bbox: tuple[float, float, float, float], start: str, end: str, limit: int = 20) -> dict:
    payload = {
        "collections": [collection],
        "bbox": list(bbox),
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": limit,
    }
    resp = SESSION.post(STAC_URL, json=payload)
    resp.raise_for_status()
    return resp.json()


def get_access_token() -> str | None:
    if not (CDSE_USERNAME and CDSE_PASSWORD):
        return None
    resp = SESSION.post(
        TOKEN_URL,
        data={
            "client_id": "cdse-public",
            "username": CDSE_USERNAME,
            "password": CDSE_PASSWORD,
            "grant_type": "password",
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_historical_sample() -> None:
    print("== Copernicus Data Space Ecosystem (STAC) ==")
    start, end = "2019-09-01", "2019-09-10"

    s1 = search("sentinel-1-grd", SUMATRA_KALIMANTAN_BBOX, start, end)
    s1_features = s1.get("features", [])
    print(f"Sentinel-1 GRD scenes over Sumatra/Kalimantan, {start}..{end}: {len(s1_features)}")
    for f in s1_features[:3]:
        print(" -", f["id"], f["properties"].get("datetime"))

    s2 = search("sentinel-2-l2a", SUMATRA_KALIMANTAN_BBOX, start, end)
    print(f"Sentinel-2 L2A scenes same window: {len(s2.get('features', []))} "
          "-- search worked with zero authentication.")

    token = get_access_token()
    if token:
        print("CDSE_USERNAME/PASSWORD set -- OAuth2 token exchange succeeded, "
              "product download is unlocked.\n")
    else:
        print("No CDSE credentials in .env yet -- catalogue search works "
              "without them; only bulk product download needs the free account.\n")


if __name__ == "__main__":
    fetch_historical_sample()
