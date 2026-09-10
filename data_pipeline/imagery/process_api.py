"""Investigation-sized Sentinel-1/2 context images from the CDSE Process API.

The evidence drawer already knows *which* scene sits either side of each demo
FireEvent (`scene_selection`, ``ENV_IMAGERY_*`` EvidenceObjects). What it
lacked was a picture of it at a size an auditor can read: the catalogue
quicklook is a few hundred pixels of a 100 km tile.

This module turns one selected scene into one Process API request that
renders the event's own surroundings, server-side, at 1024 px. Two recipes:

* Sentinel-2 L2A as a SWIR/NIR/Red false colour. Burned and dry vegetation
  separate from live canopy far better than in true colour.
* Sentinel-1 GRD as a VV/VH decibel composite, with CDSE doing the
  calibration, thermal-noise removal, orthorectification, Gamma0 terrain
  correction (Copernicus DEM 30 m) and Lee speckle filtering before the
  pixels reach the evalscript. Raw SAR is unreadable; this is the standard
  radar display product.

Both stretches are *fixed*, not per-scene. `sentinel1_visualization` uses a
2-98% percentile stretch, which is right for one image on its own but makes
a before/after pair incomparable -- each image would be normalised to its own
contents. Here the whole point is the pair.

Everything here is deterministic given the scene: the request is pinned to
the selected product's acquisition day, so the rendered image is *of* the
scene the evidence names, rather than whichever date the API's mosaicking
would otherwise prefer. The request builders are pure so the exact JSON sent
can be asserted in tests without a network.

Docs: https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process.html
      https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html
      https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

GENERATOR_VERSION = "cdse-process-imagery-v1"

PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
# Public OAuth2 endpoint, not a credential. Sentinel Hub APIs on CDSE accept
# only client_credentials from a registered OAuth client -- the username/
# password pair the product-download path uses does not work here.
OAUTH_ENDPOINT = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

OUTPUT_PX = 1024
# 10 km square: at ~10 m/px this matches Sentinel-2's 10 m bands and S1 IW
# HIGH resolution, so nothing is invented by upsampling.
AOI_HALF_SIZE_KM = 5.0
JPEG_QUALITY = 90
# Below this share of non-black pixels the request found no data on the
# pinned day for this AOI (an orbit that clips the corner, a tile boundary).
# A black square is not evidence; it is recorded as missing instead.
MIN_COVERAGE_FRACTION = 0.05

CRS_WGS84 = "http://www.opengis.net/def/crs/EPSG/0/4326"

S2_EVALSCRIPT = """//VERSION=3
// SWIR/NIR/Red false colour. Fixed 2.5x gain on L2A reflectance, clipped,
// so a pre/post pair shares one stretch. No-data renders black.
function setup() {
  return {
    input: [{ bands: ["B12", "B08", "B04", "dataMask"] }],
    output: { bands: 3, sampleType: "AUTO" }
  };
}
function clip(v) { return Math.min(Math.max(v, 0), 1); }
function evaluatePixel(s) {
  if (s.dataMask === 0) return [0, 0, 0];
  return [clip(2.5 * s.B12), clip(2.5 * s.B08), clip(2.5 * s.B04)];
}
"""

S1_EVALSCRIPT = """//VERSION=3
// Gamma0 terrain-corrected backscatter in dB with fixed stretches:
// R = VV (-20..0 dB), G = VH (-25..-5 dB), B = VV-VH ratio (0..15 dB).
// Fixed rather than per-scene so a pre/post pair is comparable. No-data
// renders black.
function setup() {
  return {
    input: [{ bands: ["VV", "VH", "dataMask"] }],
    output: { bands: 3, sampleType: "AUTO" }
  };
}
function toDb(x) { return 10 * Math.log10(Math.max(x, 1e-6)); }
function stretch(v, lo, hi) { return Math.min(Math.max((v - lo) / (hi - lo), 0), 1); }
function evaluatePixel(s) {
  if (s.dataMask === 0) return [0, 0, 0];
  const vv = toDb(s.VV);
  const vh = toDb(s.VH);
  return [stretch(vv, -20, 0), stretch(vh, -25, -5), stretch(vv - vh, 0, 15)];
}
"""


@dataclass(frozen=True)
class Recipe:
    """One sensor's display product: what is asked of the API and how it is labelled."""

    recipe_id: str
    sensor: str
    collection: str
    label: str
    slug: str
    evalscript: str
    description: str
    processing: dict[str, Any]
    data_filter: dict[str, Any]
    limitations: tuple[str, ...]

    @property
    def evalscript_sha256(self) -> str:
        return hashlib.sha256(self.evalscript.encode()).hexdigest()


S2_RECIPE = Recipe(
    recipe_id="s2-swir-false-colour-v1",
    sensor="Sentinel-2",
    collection="sentinel-2-l2a",
    label="Optical context",
    slug="s2",
    evalscript=S2_EVALSCRIPT,
    description=(
        "Sentinel-2 L2A surface reflectance rendered as SWIR2 (B12) / NIR (B08) / Red (B04) "
        "false colour with a fixed 2.5x gain; bilinear resampling to 1024 px over a 10 km square; "
        "no-data black. No per-scene stretch, so the pre- and post-event images share one scale."
    ),
    processing={"upsampling": "BILINEAR", "downsampling": "BILINEAR"},
    data_filter={"mosaickingOrder": "leastCC"},
    limitations=(
        (
            "A display product for human orientation; it is not analytical imagery and no burned "
            "area, cause, or responsibility is derived from it."
        ),
        (
            "Cloud and smoke in the image are what the sensor saw on that date; the catalogue "
            "cloud percentage is for the whole tile, not this 10 km square."
        ),
        (
            "Colour differences between the pre- and post-event images may reflect atmospheric "
            "conditions, sun angle, or different tiles as well as surface change."
        ),
    ),
)

S1_RECIPE = Recipe(
    recipe_id="s1-vvvh-db-composite-v1",
    sensor="Sentinel-1",
    collection="sentinel-1-grd",
    label="Radar context",
    slug="s1",
    evalscript=S1_EVALSCRIPT,
    description=(
        "Sentinel-1 GRD IW dual-polarisation, calibrated by CDSE to Gamma0 with terrain "
        "correction (Copernicus DEM 30 m), orthorectified, thermal noise removed, Lee 3x3 speckle "
        "filter; rendered as VV dB (-20..0) / VH dB (-25..-5) / VV-VH dB (0..15) with fixed "
        "stretches; bilinear resampling to 1024 px over a 10 km square; no-data black."
    ),
    processing={
        "orthorectify": True,
        "backCoeff": "GAMMA0_TERRAIN",
        "demInstance": "COPERNICUS_30",
        "speckleFilter": {"type": "LEE", "windowSizeX": 3, "windowSizeY": 3},
        "upsampling": "BILINEAR",
        "downsampling": "BILINEAR",
    },
    data_filter={"acquisitionMode": "IW", "polarization": "DV", "resolution": "HIGH"},
    limitations=(
        (
            "Radar backscatter is surface and structural context, cloud-independent; it does not "
            "observe sub-surface peat combustion, and a backscatter change is not a burn map."
        ),
        (
            "A display product for human orientation; it is not analytical imagery and no burned "
            "area, cause, or responsibility is derived from it."
        ),
        (
            "Pre- and post-event images from different orbit directions or relative orbits are not "
            "directly comparable pixel for pixel; the orbit is recorded with each image."
        ),
    ),
)

RECIPES: dict[str, Recipe] = {S2_RECIPE.sensor: S2_RECIPE, S1_RECIPE.sensor: S1_RECIPE}

POSITION_SLUG = {"pre_event": "pre", "post_event": "post"}


class ProcessApiError(RuntimeError):
    """The API answered, but not with an image."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"Process API returned {status}: {detail}")
        self.status = status
        self.detail = detail


def aoi_bbox(
    lat: float, lon: float, half_size_km: float = AOI_HALF_SIZE_KM
) -> list[float]:
    """A square of side 2*half_size_km centred on the point, as WGS84 [w, s, e, n].

    Longitude degrees shrink with latitude; at 3.5°S the correction is 0.2%,
    but applying it costs nothing and keeps the square square anywhere.
    """
    dlat = half_size_km / 111.32
    dlon = half_size_km / (111.32 * math.cos(math.radians(lat)))
    return [
        round(lon - dlon, 6),
        round(lat - dlat, 6),
        round(lon + dlon, 6),
        round(lat + dlat, 6),
    ]


def pin_time_range(acquisition_time: str) -> dict[str, str]:
    """The UTC calendar day of the selected acquisition.

    One day, not the scene's exact timestamp: the API matches acquisitions
    whose time falls inside the range, and a Sentinel-2 datatake spans
    minutes across its tiles. One day is narrow enough that only the named
    product's orbit can answer.
    """
    day = (
        datetime.fromisoformat(acquisition_time.replace("Z", "+00:00"))
        .astimezone(UTC)
        .date()
    )
    return {
        "from": f"{day.isoformat()}T00:00:00Z",
        "to": f"{day.isoformat()}T23:59:59Z",
    }


def build_request(scene: dict[str, Any], bbox: list[float]) -> dict[str, Any]:
    """The Process API body for one selected scene, rendered over `bbox`.

    `scene` is the `value` of an ``ENV_IMAGERY_*`` EvidenceObject; only its
    sensor, acquisition time and orbit direction are used.
    """
    recipe = RECIPES[scene["sensor"]]
    data_filter: dict[str, Any] = {
        "timeRange": pin_time_range(scene["acquisition_time"]),
        **recipe.data_filter,
    }
    orbit_state = (scene.get("orbit") or {}).get("state")
    if recipe.sensor == "Sentinel-1" and orbit_state:
        # Pinning the orbit direction as well as the day means a pass from the
        # other direction on the same date cannot be mosaicked in.
        data_filter["orbitDirection"] = str(orbit_state).upper()
    return {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": CRS_WGS84}},
            "data": [
                {
                    "type": recipe.collection,
                    "dataFilter": data_filter,
                    "processing": recipe.processing,
                }
            ],
        },
        "output": {
            "width": OUTPUT_PX,
            "height": OUTPUT_PX,
            "responses": [
                {
                    "identifier": "default",
                    "format": {"type": "image/jpeg", "quality": JPEG_QUALITY},
                }
            ],
        },
        "evalscript": recipe.evalscript,
    }


def asset_slug(sensor: str, position: str) -> str:
    return f"{RECIPES[sensor].slug}-{POSITION_SLUG[position]}"


def asset_id(event_id: str, sensor: str, position: str) -> str:
    return f"IMG_{event_id}_{RECIPES[sensor].recipe_id}_{position}"


def coverage_fraction(image_bytes: bytes) -> float:
    """Share of pixels that are not pure black, i.e. that carried data."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        grey = image.convert("L")
        histogram = grey.histogram()
    total = sum(histogram)
    return 0.0 if total == 0 else 1.0 - histogram[0] / total


def image_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(image_bytes)) as image:
        return image.size


def manifest_entry(
    event_id: str,
    evidence: dict[str, Any],
    request: dict[str, Any],
    path: str,
    size_bytes: int,
    coverage: float,
    generated_at: str,
) -> dict[str, Any]:
    """Everything a reader needs to know what this picture is and is not.

    `source_evidence_id` is the seam: it names the scene EvidenceObject this
    was rendered from, so the image can later be folded into the evidence
    response as a display attribute of that object rather than as a new,
    untraceable claim.
    """
    scene = evidence["value"]
    recipe = RECIPES[scene["sensor"]]
    data = request["input"]["data"][0]
    return {
        "asset_id": asset_id(event_id, scene["sensor"], scene["position"]),
        "event_id": event_id,
        "source_evidence_id": evidence["evidence_id"],
        "sensor": scene["sensor"],
        "position": scene["position"],
        "label": recipe.label,
        "path": path,
        "format": "image/jpeg",
        "width": request["output"]["width"],
        "height": request["output"]["height"],
        "bytes": size_bytes,
        "coverage_fraction": round(coverage, 4),
        "aoi": {
            "bbox": request["input"]["bounds"]["bbox"],
            "crs": "EPSG:4326",
            "half_size_km": AOI_HALF_SIZE_KM,
        },
        "acquisition": {
            "collection": scene["collection"],
            "product_id": scene["product_id"],
            "acquisition_time": scene["acquisition_time"],
            "time_range": data["dataFilter"]["timeRange"],
            "orbit": scene.get("orbit"),
            "cloud_cover_pct": scene.get("cloud_cover_pct"),
            "temporal_distance_hours": scene.get("temporal_distance_hours"),
            "catalogue_reference": scene.get("catalogue_reference"),
        },
        "processing": {
            "recipe_id": recipe.recipe_id,
            "description": recipe.description,
            "evalscript_sha256": recipe.evalscript_sha256,
            "data_filter": data["dataFilter"],
            "options": data["processing"],
            "request_sha256": hashlib.sha256(
                json.dumps(request, sort_keys=True).encode()
            ).hexdigest(),
        },
        "limitations": list(recipe.limitations),
        "source": "Copernicus Data Space Ecosystem, Sentinel Hub Process API",
        "generator_version": GENERATOR_VERSION,
        "generated_at": generated_at,
    }


def missing_entry(
    event_id: str, evidence: dict[str, Any], reason: str, generated_at: str
) -> dict[str, Any]:
    """An honest record of a picture that could not be made.

    The consumer shows this as unavailable. Nothing from another date or
    sensor is substituted for it.
    """
    scene = evidence["value"]
    return {
        "asset_id": asset_id(event_id, scene["sensor"], scene["position"]),
        "event_id": event_id,
        "source_evidence_id": evidence["evidence_id"],
        "sensor": scene["sensor"],
        "position": scene["position"],
        "label": RECIPES[scene["sensor"]].label,
        "product_id": scene["product_id"],
        "acquisition_time": scene["acquisition_time"],
        "reason": reason,
        "generator_version": GENERATOR_VERSION,
        "generated_at": generated_at,
    }


def build_manifest(root: Path, audit_id: str, generated_at: str) -> dict[str, Any]:
    """Assemble the manifest from the sidecars on disk.

    A pure function of the directory, so a partial run, a re-run, or a hand
    deletion all produce a manifest that matches what is actually there.
    """
    events: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for sidecar in sorted(root.glob("*/*.json")):
        entry = json.loads(sidecar.read_text())
        bucket = events.setdefault(entry["event_id"], {"assets": [], "missing": []})
        if sidecar.name.endswith(".missing.json"):
            bucket["missing"].append(entry)
        elif (root / entry["path"].removeprefix("/imagery/")).exists():
            bucket["assets"].append(entry)
    return {
        "generator_version": GENERATOR_VERSION,
        "generated_at": generated_at,
        "audit_id": audit_id,
        "source": "Copernicus Data Space Ecosystem, Sentinel Hub Process API",
        "recipes": {
            recipe.recipe_id: {
                "sensor": recipe.sensor,
                "label": recipe.label,
                "description": recipe.description,
                "evalscript_sha256": recipe.evalscript_sha256,
                "limitations": list(recipe.limitations),
            }
            for recipe in RECIPES.values()
        },
        "events": dict(sorted(events.items())),
    }


class ProcessApiClient:
    """Token exchange plus one call. Takes a session so tests can hand in a fake."""

    def __init__(
        self,
        session: Any,
        client_id: str,
        client_secret: str,
        *,
        timeout: float = 120.0,
    ):
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout
        self._token: str | None = None

    def token(self) -> str:
        if self._token is None:
            response = self._session.post(
                OAUTH_ENDPOINT,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=self._timeout,
            )
            if response.status_code != 200:
                raise ProcessApiError(
                    response.status_code,
                    "token exchange failed; check CDSE_CLIENT_ID / CDSE_CLIENT_SECRET",
                )
            self._token = response.json()["access_token"]
        return self._token

    def render(self, request: dict[str, Any]) -> bytes:
        response = self._session.post(
            PROCESS_URL,
            json=request,
            headers={"Authorization": f"Bearer {self.token()}", "Accept": "image/jpeg"},
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise ProcessApiError(response.status_code, response.text[:500])
        return response.content
