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

from collections.abc import Mapping, Sequence
from typing import Any

from data_pipeline.common.http import SESSION
from data_pipeline.common.result import Provenance, SourceResult, SourceStatus
from data_pipeline.config import CDSE_PASSWORD, CDSE_USERNAME, SUMATRA_KALIMANTAN_BBOX
from data_pipeline.imagery.scene_selection import CopernicusSceneSelection
from data_pipeline.imagery.scene_selection import select_scenes as select_scene_metadata

STAC_URL = "https://stac.dataspace.copernicus.eu/v1/search"
# S105 matches the variable name, not the value: this is the public OAuth2
# endpoint, not a credential.
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

LIMITATIONS: list[str] = [
    (
        "Catalogue search needs no authentication; bulk product download needs "
        "a free CDSE account and an OAuth2 token."
    ),
]


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


def select_scenes(
    sentinel1_features: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    sentinel2_features: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    event_start: Any,
    event_end: Any = None,
    *,
    max_cloud_cover_pct: float = 50.0,
    cloud_cover_threshold_pct: float | None = None,
) -> CopernicusSceneSelection:
    """Select closest usable pre/post scenes from already-fetched STAC items.

    The STAC request remains separate from this pure mapping step so callers
    can freeze the catalogue response and reproduce the later selection.
    """

    return select_scene_metadata(
        sentinel1_features,
        sentinel2_features,
        event_start,
        event_end,
        max_cloud_cover_pct=max_cloud_cover_pct,
        cloud_cover_threshold_pct=cloud_cover_threshold_pct,
    )


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


def fetch_historical_sample() -> SourceResult:
    print("== Copernicus Data Space Ecosystem (STAC) ==")
    provenance = Provenance(endpoint=STAC_URL, auth="none")

    try:
        start, end = "2019-09-01", "2019-09-10"

        s1 = search("sentinel-1-grd", SUMATRA_KALIMANTAN_BBOX, start, end)
        s1_features = s1.get("features", [])
        print(f"Sentinel-1 GRD scenes over Sumatra/Kalimantan, {start}..{end}: {len(s1_features)}")
        for f in s1_features[:3]:
            print(" -", f["id"], f["properties"].get("datetime"))

        s2 = search("sentinel-2-l2a", SUMATRA_KALIMANTAN_BBOX, start, end)
        s2_features = s2.get("features", [])
        print(f"Sentinel-2 L2A scenes same window: {len(s2_features)} "
              "-- search worked with zero authentication.")

        token = get_access_token()
        if token:
            provenance = Provenance(endpoint=STAC_URL, auth="oauth2")
            print("CDSE_USERNAME/PASSWORD set -- OAuth2 token exchange succeeded, "
                  "product download is unlocked.\n")
        else:
            print("No CDSE credentials in .env yet -- catalogue search works "
                  "without them; only bulk product download needs the free account.\n")
    except Exception as exc:  # noqa: BLE001 -- normalized into SourceResult, not swallowed
        return SourceResult(
            source_name="Copernicus Data Space Ecosystem",
            status=SourceStatus.FAILED,
            provenance=provenance,
            limitations=LIMITATIONS,
            error=str(exc),
        )

    return SourceResult(
        source_name="Copernicus Data Space Ecosystem",
        status=SourceStatus.OK,
        provenance=provenance,
        limitations=LIMITATIONS,
        summary=f"{len(s1_features)} Sentinel-1 + {len(s2_features)} Sentinel-2 scenes, "
                f"token={'obtained' if token else 'not requested (no credentials)'}",
    )


if __name__ == "__main__":
    fetch_historical_sample()
