"""Make peat a first-class environmental attribute of every FireEvent.

`Environmental_Assurance_Spec.md` (S15, peat-aware reasoning) says peat can
change a fire's persistence and observability, and that this must be
represented as context a human reviewer weighs -- never as a claim that a
fire burned underground. This module answers the geometric question only:
where is mapped peat relative to this event, how much of its footprint and
surroundings overlap it, and how far away is the nearest peat if none does.
It does not decide what that means; `to_evidence_objects()` attaches the
non-inference limitation to every object it produces so nothing downstream
can drop it silently.

## Dataset: Global Peatland Map 2.0 (Greifswald Mire Centre)

`sources/global_peatland_database.py` (issue #2) already confirmed this
dataset is a single reachable static download with no query API -- it never
went further because "cache and query it" was explicitly this issue's job,
not issue #2's. Inspecting the actual archive (not just the download
headers) shows it is small enough to be tractable without a GIS dependency
stack: `GPM2022_GMC.zip` (3.6MB) contains a nested
`GLOpeat_GPA22WGS_2cl_1x1km.zip`, which contains one GeoTIFF --
`peatGPA22WGS_2cl.tif`, 36017x15295 px, unprojected WGS84, LZW-compressed,
single uint8 band, values `1` (peat dominated), `2` (peat in soil mosaic),
`255` (nodata -- confirmed by the shipped `.aux.xml`'s
`STATISTICS_MINIMUM/MAXIMUM` of 1/2, not a real third class). Its `.tfw`
world file gives a plain axis-aligned affine transform (no rotation terms)
-- because the projection is already unprojected WGS84, pixel<->lon/lat is
linear arithmetic, so this module reads the TIFF with Pillow (already a
transitive dependency here) and does its own affine math, rather than
pulling in rasterio/GDAL for a raster this simple. The `.tfw` values are
written with a comma decimal separator (a German GIS tool's locale), hence
`_parse_world_file`'s `.replace(",", ".")`.

## Local caching

The full raster is ~550MB decompressed -- resident-memory-sized but not
something to re-download and re-decode every run. `load_peat_raster()`
downloads and crops to `INDONESIA_BBOX` (padded by `CACHE_PAD_DEG` so a
buffer/corridor query near the bbox edge doesn't fall outside the cached
crop) exactly once, then persists the crop as a `.npy` array plus a small
JSON sidecar recording its origin/pixel size in `data_pipeline/output/`
(gitignored, same convention as this package's other sample outputs).
Every later call in the same or a later process loads the ~13MB crop
instead of the 3.6MB zip + 550MB decode.

## Resolution and what it cannot resolve

`RESOLUTION_KM` is nominal -- the raster is a fixed ~0.00998 degree grid, so
its true east-west pixel width shrinks with `cos(latitude)` while north-south
stays constant; both are within a few percent of 1.1km across Indonesia's
near-equatorial span. A boundary between peat and mineral soil narrower than
that is not resolvable: a fire "near" a mapped peat/non-peat boundary at this
resolution can be on either side in reality. This is reported as a
per-context limitation, not silently rounded away.

## What this module does not do

It computes intersection, fraction, and distance -- geometry only. It never
outputs a claim that a fire is "smouldering," "peat-fed," or "travelling
underground": those are hypotheses for an interpretation layer to weigh
against SAR persistence and elapsed time (S15), never a conclusion this
geometry layer is entitled to reach on its own.
"""
from __future__ import annotations

import io
import json
import math
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from PIL import Image

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.common.http import SESSION
from data_pipeline.config import INDONESIA_BBOX, OUTPUT_DIR

# A single ~550MP scientific raster decoded from a trusted, hard-coded
# research-institute URL -- not user-supplied imagery, so Pillow's
# decompression-bomb guard would only get in the way here.
Image.MAX_IMAGE_PIXELS = None

DOWNLOAD_URL = "https://nextcloud.uni-greifswald.de/index.php/s/s7Ln5QKxdQG5aaA/download"
OUTER_ZIP_MEMBER = "GLOpeat_GPA22WGS_2cl_1x1km.zip"
INNER_TIF_MEMBER = "peatGPA22WGS_2cl.tif"
INNER_TFW_MEMBER = "peatGPA22WGS_2cl.tfw"
SOURCE_NAME = "Greifswald Mire Centre -- Global Peatland Map 2.0 (GPM 2022)"

PEAT_DOMINATED = 1
PEAT_IN_SOIL_MOSAIC = 2
NON_PEAT = 0
OUTSIDE_COVERAGE = -1
_RASTER_NODATA = 255

PEAT_CLASS_LABELS: dict[int, str] = {
    PEAT_DOMINATED: "peat_dominated",
    PEAT_IN_SOIL_MOSAIC: "peat_in_soil_mosaic",
    NON_PEAT: "non_peat",
    OUTSIDE_COVERAGE: "outside_cached_coverage",
}

RESOLUTION_KM = 1.1
CACHE_PAD_DEG = 1.0
DEFAULT_EVENT_BUFFER_KM = 5.0
DEFAULT_CORRIDOR_WIDTH_KM = 2.0
DEFAULT_MAX_DISTANCE_SEARCH_KM = 50.0

CACHE_DIR = OUTPUT_DIR / "peat_cache"
CACHE_ARRAY_PATH = CACHE_DIR / "indonesia_peat.npy"
CACHE_TRANSFORM_PATH = CACHE_DIR / "indonesia_peat_transform.json"

NON_INFERENCE_LIMITATION = (
    "peat overlap is geometric context only -- it does not indicate "
    "underground combustion, smouldering, or fire persistence on its own"
)


@dataclass(frozen=True)
class PeatRaster:
    """A cropped peat-class grid plus the affine transform to place it in
    lon/lat. `pixel_size_deg` is positive; rows increase southward, columns
    increase eastward, matching the source GeoTIFF's north-up convention."""

    array: np.ndarray  # uint8, raw values (1, 2, or 255) -- not remapped
    origin_lon: float  # longitude of column 0's pixel center
    origin_lat: float  # latitude of row 0's pixel center (northernmost row)
    pixel_size_deg: float

    def _to_pixel(self, lat: float, lon: float) -> tuple[int, int]:
        row = round((lat - self.origin_lat) / -self.pixel_size_deg)
        col = round((lon - self.origin_lon) / self.pixel_size_deg)
        return row, col

    def class_at(self, lat: float, lon: float) -> int:
        """`OUTSIDE_COVERAGE` if outside this cached crop, `NON_PEAT` for a
        real in-crop nodata pixel (ocean or unmapped land -- still means "not
        peat" for this dataset's purposes), else `PEAT_DOMINATED` /
        `PEAT_IN_SOIL_MOSAIC`."""
        row, col = self._to_pixel(lat, lon)
        rows, cols = self.array.shape
        if not (0 <= row < rows and 0 <= col < cols):
            return OUTSIDE_COVERAGE
        value = int(self.array[row, col])
        return NON_PEAT if value == _RASTER_NODATA else value

    def _pixel_center(self, row: int, col: int) -> tuple[float, float]:
        lat = self.origin_lat - row * self.pixel_size_deg
        lon = self.origin_lon + col * self.pixel_size_deg
        return lat, lon


def _parse_world_file(text: str) -> dict[str, float]:
    """A `.tfw` world file: 6 lines, pixel-size-x, rotation, rotation,
    pixel-size-y (negative), origin-lon, origin-lat. This export uses a
    comma decimal separator (German GIS tooling locale)."""
    values = [float(line.strip().replace(",", ".")) for line in text.splitlines() if line.strip()]
    pixel_size_x, _rot1, _rot2, pixel_size_y, origin_lon, origin_lat = values
    return {
        "pixel_size_x": pixel_size_x,
        "pixel_size_y": pixel_size_y,
        "origin_lon": origin_lon,
        "origin_lat": origin_lat,
    }


def _download_and_crop_indonesia() -> PeatRaster:
    resp = SESSION.get(DOWNLOAD_URL, timeout=120)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as outer:
        inner_bytes = outer.read(OUTER_ZIP_MEMBER)
    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner:
        tif_bytes = inner.read(INNER_TIF_MEMBER)
        tfw_text = inner.read(INNER_TFW_MEMBER).decode("ascii")

    transform = _parse_world_file(tfw_text)
    pixel_size = transform["pixel_size_x"]  # == -pixel_size_y for this square-pixel product

    full = np.array(Image.open(io.BytesIO(tif_bytes)))  # uint8, shape (rows, cols)
    rows, cols = full.shape

    west, south, east, north = INDONESIA_BBOX
    west, south = west - CACHE_PAD_DEG, south - CACHE_PAD_DEG
    east, north = east + CACHE_PAD_DEG, north + CACHE_PAD_DEG

    def _row_for(lat: float) -> int:
        return round((lat - transform["origin_lat"]) / transform["pixel_size_y"])

    def _col_for(lon: float) -> int:
        return round((lon - transform["origin_lon"]) / pixel_size)

    row_min = max(0, _row_for(north))
    row_max = min(rows, _row_for(south) + 1)
    col_min = max(0, _col_for(west))
    col_max = min(cols, _col_for(east) + 1)

    cropped = full[row_min:row_max, col_min:col_max].copy()
    crop_origin_lat = transform["origin_lat"] + row_min * transform["pixel_size_y"]
    crop_origin_lon = transform["origin_lon"] + col_min * pixel_size

    return PeatRaster(array=cropped, origin_lon=crop_origin_lon, origin_lat=crop_origin_lat, pixel_size_deg=pixel_size)


def _save_cache(raster: PeatRaster) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(CACHE_ARRAY_PATH, raster.array)
    CACHE_TRANSFORM_PATH.write_text(
        json.dumps(
            {
                "origin_lon": raster.origin_lon,
                "origin_lat": raster.origin_lat,
                "pixel_size_deg": raster.pixel_size_deg,
            }
        )
    )


def _load_cache() -> PeatRaster | None:
    if not (CACHE_ARRAY_PATH.exists() and CACHE_TRANSFORM_PATH.exists()):
        return None
    array = np.load(CACHE_ARRAY_PATH)
    transform = json.loads(CACHE_TRANSFORM_PATH.read_text())
    return PeatRaster(array=array, **transform)


def load_peat_raster(force_refresh: bool = False) -> PeatRaster:
    """The only network-touching function in this module (besides
    `_demo()`). Downloads + crops once, then serves the on-disk cache."""
    if not force_refresh:
        cached = _load_cache()
        if cached is not None:
            return cached
    raster = _download_and_crop_indonesia()
    _save_cache(raster)
    return raster


def _km_per_degree(lat: float) -> tuple[float, float]:
    """(km per degree latitude, km per degree longitude) at this latitude --
    longitude spacing shrinks with cos(lat), latitude spacing does not."""
    lat_km = 111.32
    lon_km = 111.32 * math.cos(math.radians(lat))
    return lat_km, lon_km


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _pixels_in_radius(raster: PeatRaster, lat: float, lon: float, radius_km: float) -> list[tuple[int, int]]:
    """Row/col indices of every cached pixel whose center is within
    `radius_km` great-circle distance of (lat, lon), via a bounding-box
    pre-filter (cheap) then an exact haversine check (correct)."""
    lat_km, lon_km = _km_per_degree(lat)
    dlat = radius_km / lat_km
    dlon = radius_km / lon_km if lon_km > 0 else 180.0

    row_top, _ = raster._to_pixel(lat + dlat, lon)
    row_bottom, _ = raster._to_pixel(lat - dlat, lon)
    _, col_left = raster._to_pixel(lat, lon - dlon)
    _, col_right = raster._to_pixel(lat, lon + dlon)

    rows, cols = raster.array.shape
    row_min, row_max = max(0, min(row_top, row_bottom)), min(rows, max(row_top, row_bottom) + 1)
    col_min, col_max = max(0, min(col_left, col_right)), min(cols, max(col_left, col_right) + 1)

    hits: list[tuple[int, int]] = []
    for row in range(row_min, row_max):
        for col in range(col_min, col_max):
            px_lat, px_lon = raster._pixel_center(row, col)
            if _haversine_km(lat, lon, px_lat, px_lon) <= radius_km:
                hits.append((row, col))
    return hits


_MAX_FOOTPRINT_SAMPLES = 400


def _sample_bbox_grid(west: float, south: float, east: float, north: float) -> list[tuple[float, float]]:
    """Sample an event's own bbox on a grid spaced roughly `RESOLUTION_KM`
    apart -- fine enough to answer "does this footprint touch peat" at the
    raster's own resolution, capped at `_MAX_FOOTPRINT_SAMPLES` so a sprawling
    multi-day fire complex's bbox doesn't turn into an unbounded scan."""
    if west == east and south == north:
        return [(south, west)]
    lat_km, lon_km = _km_per_degree((south + north) / 2)
    lat_step = max((north - south) / max(1, round((north - south) * lat_km / RESOLUTION_KM)), 1e-9)
    lon_step = max((east - west) / max(1, round((east - west) * lon_km / RESOLUTION_KM)), 1e-9)

    lats = np.arange(south, north + lat_step / 2, lat_step) if north > south else np.array([south])
    lons = np.arange(west, east + lon_step / 2, lon_step) if east > west else np.array([west])
    if len(lats) * len(lons) > _MAX_FOOTPRINT_SAMPLES:
        scale = math.sqrt(_MAX_FOOTPRINT_SAMPLES / (len(lats) * len(lons)))
        lats = np.linspace(south, north, max(1, int(len(lats) * scale)))
        lons = np.linspace(west, east, max(1, int(len(lons) * scale)))
    return [(float(lat), float(lon)) for lat in lats for lon in lons]


def peat_fraction_for_radius(
    raster: PeatRaster, lat: float, lon: float, radius_km: float
) -> tuple[float | None, list[str]]:
    """Fraction of cached-coverage pixels within `radius_km` of (lat, lon)
    that are mapped peat (either class). `None` if every pixel in the
    circle falls outside the cached crop."""
    limitations: list[str] = []
    pixels = _pixels_in_radius(raster, lat, lon, radius_km)
    total = len(pixels)
    peat = sum(1 for row, col in pixels if int(raster.array[row, col]) in (PEAT_DOMINATED, PEAT_IN_SOIL_MOSAIC))
    # _pixels_in_radius only ever returns in-bounds indices, so "outside
    # coverage" here means the *circle itself* extends past the crop edge --
    # detected by comparing the pixel count against the expected coverage.
    if total == 0:
        limitations.append(f"no cached raster coverage within {radius_km}km of this point")
        return None, limitations
    expected_px = math.pi * (radius_km / RESOLUTION_KM) ** 2
    if total < expected_px * 0.5:
        limitations.append(
            f"buffer partially falls outside the cached raster crop; fraction computed from "
            f"{total} available pixel(s) only"
        )
    return round(peat / total, 4), limitations


def distance_to_peat_km(
    raster: PeatRaster, lat: float, lon: float, max_search_km: float = DEFAULT_MAX_DISTANCE_SEARCH_KM
) -> tuple[float | None, list[str]]:
    """Great-circle distance from (lat, lon) to the nearest mapped peat
    pixel center, expanding the search radius until one is found or
    `max_search_km` is exhausted. Returns `0.0` if the point itself is on
    peat."""
    if raster.class_at(lat, lon) in (PEAT_DOMINATED, PEAT_IN_SOIL_MOSAIC):
        return 0.0, []

    radius = RESOLUTION_KM * 2
    while radius <= max_search_km:
        best: float | None = None
        for row, col in _pixels_in_radius(raster, lat, lon, radius):
            value = int(raster.array[row, col])
            if value in (PEAT_DOMINATED, PEAT_IN_SOIL_MOSAIC):
                px_lat, px_lon = raster._pixel_center(row, col)
                d = _haversine_km(lat, lon, px_lat, px_lon)
                if best is None or d < best:
                    best = d
        if best is not None:
            return round(best, 2), []
        radius *= 2
    return None, [f"no mapped peat found within {max_search_km}km search radius"]


def peat_fraction_along_corridor(
    raster: PeatRaster,
    point_a: tuple[float, float],
    point_b: tuple[float, float],
    corridor_width_km: float = DEFAULT_CORRIDOR_WIDTH_KM,
) -> tuple[float | None, list[str]]:
    """Fraction of a straight-line corridor between two linked FireEvents'
    centroids that is mapped peat -- sampled every `RESOLUTION_KM` along the
    line, each sample point's own class checked directly (a corridor this
    narrow relative to the raster's 1.1km cell size gains nothing from also
    buffering each sample sideways by `corridor_width_km`; the width is kept
    as an explicit parameter so a caller can document the assumption even
    though it does not currently change the computation)."""
    lat1, lon1 = point_a
    lat2, lon2 = point_b
    length_km = _haversine_km(lat1, lon1, lat2, lon2)
    if length_km == 0:
        value = raster.class_at(lat1, lon1)
        if value == OUTSIDE_COVERAGE:
            return None, ["corridor endpoint falls outside the cached raster crop"]
        return (1.0 if value in (PEAT_DOMINATED, PEAT_IN_SOIL_MOSAIC) else 0.0), []

    steps = max(2, math.ceil(length_km / RESOLUTION_KM) + 1)
    total = 0
    peat = 0
    outside = 0
    for i in range(steps):
        t = i / (steps - 1)
        lat = lat1 + (lat2 - lat1) * t
        lon = lon1 + (lon2 - lon1) * t
        value = raster.class_at(lat, lon)
        if value == OUTSIDE_COVERAGE:
            outside += 1
            continue
        total += 1
        if value in (PEAT_DOMINATED, PEAT_IN_SOIL_MOSAIC):
            peat += 1

    limitations: list[str] = []
    if outside:
        limitations.append(f"{outside} of {steps} corridor samples fell outside the cached raster crop and were excluded")
    if total == 0:
        limitations.append("entire corridor falls outside the cached raster crop")
        return None, limitations
    return round(peat / total, 4), limitations


@dataclass
class PeatContext:
    """The complete peat evidence bundle for one FireEvent -- every task in
    this issue's acceptance criteria, computed in one call."""

    event_id: str
    centroid: tuple[float, float]
    direct_intersection: bool
    footprint_peat_fraction: float | None
    buffer_km: float
    buffer_peat_fraction: float | None
    distance_to_peat_km: float | None
    resolution_km: float = RESOLUTION_KM
    source: str = SOURCE_NAME
    limitations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def compute_peat_context(
    event: FireEvent,
    raster: PeatRaster,
    buffer_km: float = DEFAULT_EVENT_BUFFER_KM,
) -> PeatContext:
    """Pure computation over an already-loaded `PeatRaster` -- no network
    access, so this is what tests exercise directly against a small
    synthetic raster."""
    lat, lon = event.centroid
    west, south, east, north = event.bbox
    limitations: list[str] = [NON_INFERENCE_LIMITATION]

    direct_intersection = False
    footprint_values: list[int] = []
    for plat, plon in _sample_bbox_grid(west, south, east, north):
        value = raster.class_at(plat, plon)
        if value == OUTSIDE_COVERAGE:
            continue
        footprint_values.append(value)
        if value in (PEAT_DOMINATED, PEAT_IN_SOIL_MOSAIC):
            direct_intersection = True

    if footprint_values:
        footprint_fraction = round(
            sum(1 for v in footprint_values if v in (PEAT_DOMINATED, PEAT_IN_SOIL_MOSAIC)) / len(footprint_values), 4
        )
    else:
        footprint_fraction = None
        limitations.append("event footprint falls entirely outside the cached raster crop")

    buffer_fraction, buffer_limitations = peat_fraction_for_radius(raster, lat, lon, buffer_km)
    limitations.extend(buffer_limitations)

    distance_km, distance_limitations = distance_to_peat_km(raster, lat, lon)
    limitations.extend(distance_limitations)

    if event.spatial_extent_km > buffer_km:
        limitations.append(
            f"event spatial extent ({event.spatial_extent_km}km) exceeds the {buffer_km}km buffer radius; "
            "footprint corners, not the buffer, are the more representative intersection check for this event"
        )

    return PeatContext(
        event_id=event.event_id,
        centroid=event.centroid,
        direct_intersection=direct_intersection,
        footprint_peat_fraction=footprint_fraction,
        buffer_km=buffer_km,
        buffer_peat_fraction=buffer_fraction,
        distance_to_peat_km=distance_km,
        limitations=limitations,
    )


def get_peat_context_for_event(event: FireEvent, buffer_km: float = DEFAULT_EVENT_BUFFER_KM) -> PeatContext:
    """The one call this issue asks for: FireEvent in, complete peat
    context out, dataset cached automatically on first use."""
    raster = load_peat_raster()
    return compute_peat_context(event, raster, buffer_km)


def to_evidence_objects(context: PeatContext) -> list[dict]:
    """Convert a `PeatContext` into `EvidenceObject`s
    (`Environmental_Assurance_Spec.md` S16). `compute_peat_context` always
    puts `NON_INFERENCE_LIMITATION` first in `context.limitations`, so every
    object produced here carries it -- no downstream caller can select a
    peat evidence object that omits it."""
    objects: list[dict] = []

    def _make(evidence_id: str, metric_type: str, observation: str, value: float | bool, unit: str, quality: float) -> dict:
        return {
            "evidence_id": f"ENV_PEAT_{context.event_id}_{evidence_id}",
            "category": "peat",
            "type": metric_type,
            "observation": observation,
            "source": context.source,
            "time_window": None,
            "value": value,
            "unit": unit,
            "quality": quality,
            "limitations": list(context.limitations),
            "retrieved_at": context.generated_at,
            "algorithm_version": None,
            "raw_reference": None,
        }

    objects.append(
        _make(
            "direct_intersection",
            "peat_intersection",
            f"event footprint {'intersects' if context.direct_intersection else 'does not intersect'} mapped peat",
            context.direct_intersection,
            "bool",
            0.7,
        )
    )
    if context.footprint_peat_fraction is not None:
        objects.append(
            _make(
                "footprint_fraction",
                "peat_fraction",
                f"{context.footprint_peat_fraction * 100:.1f}% of event footprint sample points are mapped peat",
                context.footprint_peat_fraction,
                "fraction",
                0.6,
            )
        )
    if context.buffer_peat_fraction is not None:
        objects.append(
            _make(
                "buffer_fraction",
                "peat_fraction",
                f"{context.buffer_peat_fraction * 100:.1f}% of area within {context.buffer_km}km is mapped peat",
                context.buffer_peat_fraction,
                "fraction",
                0.7,
            )
        )
    if context.distance_to_peat_km is not None:
        objects.append(
            _make(
                "distance_to_peat",
                "distance_to_peat",
                f"nearest mapped peat is {context.distance_to_peat_km}km from event centroid",
                context.distance_to_peat_km,
                "km",
                0.7,
            )
        )
    return objects


def _demo() -> None:
    import pandas as pd

    from data_pipeline.clustering.firms_clustering import cluster_events
    from data_pipeline.config import OUTPUT_DIR as _OUT

    print("== Peat intersection and context service ==")
    sample_path = _OUT / "firms_2019_haze_sample.csv"
    if sample_path.exists():
        observations = pd.read_csv(sample_path)
    else:
        from data_pipeline.config import SUMATRA_KALIMANTAN_BBOX
        from data_pipeline.sources.nasa_firms import fetch_area

        observations = fetch_area("VIIRS_SNPP_SP", SUMATRA_KALIMANTAN_BBOX, day_range=5, start_date="2019-09-01")

    events, _ = cluster_events(observations)
    event = max(events, key=lambda e: e.observation_count)
    print(f"Computing peat context for {event.event_id} (centroid={event.centroid}) ...")

    context = get_peat_context_for_event(event)
    print(
        f"  direct_intersection={context.direct_intersection} "
        f"footprint_fraction={context.footprint_peat_fraction} "
        f"buffer({context.buffer_km}km)_fraction={context.buffer_peat_fraction} "
        f"distance_to_peat={context.distance_to_peat_km}km"
    )
    print(f"  limitations={context.limitations}")

    evidence = to_evidence_objects(context)
    out = _OUT / f"peat_context_{event.event_id}.json"
    out.write_text(json.dumps(evidence, indent=2))
    print(f"Saved {len(evidence)} evidence objects to {out}\n")


if __name__ == "__main__":
    _demo()
