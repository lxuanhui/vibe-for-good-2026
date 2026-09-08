import numpy as np
import pytest

from data_pipeline.clustering.firms_clustering import FireEvent
from data_pipeline.enrichment.peat_context import (
    NON_INFERENCE_LIMITATION,
    NON_PEAT,
    OUTSIDE_COVERAGE,
    PEAT_DOMINATED,
    PeatRaster,
    compute_peat_context,
    distance_to_peat_km,
    peat_fraction_along_corridor,
    peat_fraction_for_radius,
    to_evidence_objects,
)

# A 21x21 grid, origin at the northwest corner (1.0, 100.0), 0.01deg pixels --
# covers lat [0.80, 1.0], lon [100.0, 100.20]. One nodata pixel at the corner,
# one peat pixel dead center, everything else genuine non-peat.
_PIXEL_SIZE = 0.01
_ORIGIN_LAT = 1.0
_ORIGIN_LON = 100.0
_PEAT_ROW, _PEAT_COL = 10, 10
_PEAT_LAT, _PEAT_LON = 0.90, 100.10


def _raster() -> PeatRaster:
    array = np.zeros((21, 21), dtype="uint8")
    array[0, 0] = 255  # nodata, distinct from genuine non-peat
    array[_PEAT_ROW, _PEAT_COL] = PEAT_DOMINATED
    return PeatRaster(array=array, origin_lon=_ORIGIN_LON, origin_lat=_ORIGIN_LAT, pixel_size_deg=_PIXEL_SIZE)


def _uniform_raster(value: int) -> PeatRaster:
    array = np.full((21, 21), value, dtype="uint8")
    return PeatRaster(array=array, origin_lon=_ORIGIN_LON, origin_lat=_ORIGIN_LAT, pixel_size_deg=_PIXEL_SIZE)


def _event(
    bbox: tuple[float, float, float, float],
    centroid: tuple[float, float],
    spatial_extent_km: float = 0.0,
    event_id: str = "FE-TEST",
) -> FireEvent:
    return FireEvent(
        event_id=event_id,
        observation_indices=[0],
        first_detection="2019-09-05T00:00:00+00:00",
        last_detection="2019-09-05T00:00:00+00:00",
        duration_hours=0.0,
        observation_count=1,
        centroid=centroid,
        bbox=bbox,
        spatial_extent_km=spatial_extent_km,
        max_frp=10.0,
        mean_frp=10.0,
        sensor_mix=["N/VIIRS"],
    )


def test_class_at_outside_cached_coverage():
    raster = _raster()
    assert raster.class_at(5.0, 5.0) == OUTSIDE_COVERAGE


def test_class_at_nodata_pixel_reads_as_non_peat():
    raster = _raster()
    assert raster.class_at(_ORIGIN_LAT, _ORIGIN_LON) == NON_PEAT


def test_class_at_peat_pixel():
    raster = _raster()
    assert raster.class_at(_PEAT_LAT, _PEAT_LON) == PEAT_DOMINATED


def test_peat_fraction_for_radius_all_peat():
    raster = _uniform_raster(PEAT_DOMINATED)
    fraction, limitations = peat_fraction_for_radius(raster, _PEAT_LAT, _PEAT_LON, radius_km=2.0)
    assert fraction == 1.0
    assert limitations == []


def test_peat_fraction_for_radius_all_non_peat():
    raster = _uniform_raster(NON_PEAT)
    fraction, limitations = peat_fraction_for_radius(raster, _PEAT_LAT, _PEAT_LON, radius_km=2.0)
    assert fraction == 0.0
    assert limitations == []


def test_peat_fraction_for_radius_none_outside_cached_coverage():
    raster = _raster()
    fraction, limitations = peat_fraction_for_radius(raster, 50.0, 50.0, radius_km=2.0)
    assert fraction is None
    assert any("no cached raster coverage" in m for m in limitations)


def test_peat_fraction_for_radius_flags_partial_coverage_near_crop_edge():
    raster = _raster()
    fraction, limitations = peat_fraction_for_radius(raster, _ORIGIN_LAT, _ORIGIN_LON, radius_km=5.0)
    assert fraction is not None
    assert any("partially falls outside" in m for m in limitations)


def test_distance_to_peat_km_zero_when_point_is_on_peat():
    raster = _raster()
    distance, limitations = distance_to_peat_km(raster, _PEAT_LAT, _PEAT_LON)
    assert distance == 0.0
    assert limitations == []


def test_distance_to_peat_km_finds_nearest_pixel():
    raster = _raster()
    # 3 rows north of the peat pixel, same column -> ~3.34km great-circle.
    query_lat = _ORIGIN_LAT - (_PEAT_ROW - 3) * _PIXEL_SIZE
    distance, limitations = distance_to_peat_km(raster, query_lat, _PEAT_LON)
    assert distance == pytest.approx(3.34, abs=0.05)
    assert limitations == []


def test_distance_to_peat_km_none_when_search_radius_exhausted():
    raster = _uniform_raster(NON_PEAT)
    distance, limitations = distance_to_peat_km(raster, _PEAT_LAT, _PEAT_LON, max_search_km=2.0)
    assert distance is None
    assert any("no mapped peat found within 2.0km" in m for m in limitations)


def test_corridor_zero_length_on_peat_pixel():
    raster = _raster()
    fraction, limitations = peat_fraction_along_corridor(raster, (_PEAT_LAT, _PEAT_LON), (_PEAT_LAT, _PEAT_LON))
    assert fraction == 1.0
    assert limitations == []


def test_corridor_zero_length_on_non_peat_pixel():
    raster = _raster()
    point = (0.95, 100.05)
    fraction, limitations = peat_fraction_along_corridor(raster, point, point)
    assert fraction == 0.0
    assert limitations == []


def test_corridor_zero_length_outside_coverage():
    raster = _raster()
    point = (50.0, 50.0)
    fraction, limitations = peat_fraction_along_corridor(raster, point, point)
    assert fraction is None
    assert any("outside the cached raster crop" in m for m in limitations)


def test_corridor_crossing_peat_pixel_is_detected():
    raster = _raster()
    # Straight line along the peat pixel's own row, spanning the full crop --
    # dense enough sampling (~1.1km spacing) to land on the peat column.
    fraction, limitations = peat_fraction_along_corridor(raster, (_PEAT_LAT, 100.0), (_PEAT_LAT, 100.20))
    assert fraction is not None
    assert fraction > 0.0
    assert limitations == []


def test_corridor_entirely_outside_coverage():
    raster = _raster()
    fraction, limitations = peat_fraction_along_corridor(raster, (50.0, 50.0), (51.0, 51.0))
    assert fraction is None
    assert any("entire corridor falls outside" in m for m in limitations)


def test_compute_peat_context_direct_intersection_no_other_limitations():
    raster = _raster()
    event = _event(bbox=(_PEAT_LON, _PEAT_LAT, _PEAT_LON, _PEAT_LAT), centroid=(_PEAT_LAT, _PEAT_LON))
    context = compute_peat_context(event, raster, buffer_km=5.0)

    assert context.direct_intersection is True
    assert context.footprint_peat_fraction == 1.0
    assert context.distance_to_peat_km == 0.0
    assert context.limitations == [NON_INFERENCE_LIMITATION]


def test_compute_peat_context_event_entirely_outside_crop():
    raster = _raster()
    event = _event(bbox=(50.0, 50.0, 50.0, 50.0), centroid=(50.0, 50.0))
    context = compute_peat_context(event, raster, buffer_km=5.0)

    assert context.direct_intersection is False
    assert context.footprint_peat_fraction is None
    assert context.buffer_peat_fraction is None
    assert context.distance_to_peat_km is None
    assert context.limitations[0] == NON_INFERENCE_LIMITATION
    assert any("event footprint falls entirely outside" in m for m in context.limitations)
    assert any("no mapped peat found within" in m for m in context.limitations)


def test_compute_peat_context_flags_extent_exceeding_buffer():
    raster = _raster()
    event = _event(
        bbox=(100.0, 0.90, 100.05, 0.95),
        centroid=(0.925, 100.025),
        spatial_extent_km=7.87,
    )
    context = compute_peat_context(event, raster, buffer_km=1.0)
    assert any("exceeds the 1.0km buffer radius" in m for m in context.limitations)


def test_to_evidence_objects_includes_non_inference_limitation_on_every_object():
    raster = _raster()
    event = _event(bbox=(_PEAT_LON, _PEAT_LAT, _PEAT_LON, _PEAT_LAT), centroid=(_PEAT_LAT, _PEAT_LON))
    context = compute_peat_context(event, raster, buffer_km=5.0)

    objects = to_evidence_objects(context)
    assert len(objects) == 4
    assert all(NON_INFERENCE_LIMITATION in obj["limitations"] for obj in objects)
    assert all(event.event_id in obj["evidence_id"] for obj in objects)
    assert all(obj["category"] == "peat" for obj in objects)


def test_to_evidence_objects_skips_none_metrics():
    raster = _raster()
    event = _event(bbox=(50.0, 50.0, 50.0, 50.0), centroid=(50.0, 50.0))
    context = compute_peat_context(event, raster, buffer_km=5.0)

    objects = to_evidence_objects(context)
    # footprint/buffer/distance are all None for an event entirely outside
    # the cached crop -- only the always-present direct_intersection object.
    assert len(objects) == 1
    assert objects[0]["type"] == "peat_intersection"
