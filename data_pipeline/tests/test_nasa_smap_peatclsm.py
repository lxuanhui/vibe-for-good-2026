import json

import numpy as np
import pytest

from data_pipeline.sources import nasa_smap_peatclsm as smap


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "feed": {
                "entry": [{
                    "id": "SPL4SMGP-demo",
                    "time_start": "2019-09-01T00:00:00.000Z",
                    "links": [{"href": "https://example.test/granule"}],
                }]
            }
        }


class _Session:
    def get(self, *args, **kwargs):
        return _Response()


def test_search_granules_has_bounded_demo_query():
    seen = {}

    class Session(_Session):
        def get(self, url, **kwargs):
            seen.update(kwargs["params"])
            return super().get(url, **kwargs)

    records = smap.search_granules(session=Session())
    assert records[0]["id"] == "SPL4SMGP-demo"
    assert seen["short_name"] == "SPL4SMGP"
    assert seen["version"] == "7"
    assert seen["bounding_box"] == "116.0,-4.05,116.5,-3.55"
    assert seen["temporal"].startswith("2019-09-01T00:00:00Z")


def test_extract_clipped_rows_preserves_units_and_drops_outside_or_nan(tmp_path):
    h5py = pytest.importorskip("h5py")
    source = tmp_path / "subset.h5"
    with h5py.File(source, "w") as handle:
        handle["latitude"] = np.array([-3.8, -3.8, -5.0])
        handle["longitude"] = np.array([116.2, 116.3, 116.2])
        handle["sm_surface"] = np.array([0.31, np.nan, 0.4])
        handle["sm_rootzone"] = np.array([0.42, 0.52, -9999.0])
        handle["depth_to_water_table_from_surface_in_peat"] = np.array([0.8, -1.2, -9999.0])

    rows = smap.extract_clipped_rows(source)
    assert rows == [{
        "latitude": -3.8,
        "longitude": 116.2,
        "surface_soil_moisture_m3_m3": 0.31,
        "root_zone_soil_moisture_m3_m3": 0.42,
        "depth_to_water_table_from_surface_in_peat_m": 0.8,
    }, {
        "latitude": -3.8,
        "longitude": 116.3,
        "root_zone_soil_moisture_m3_m3": 0.52,
        "depth_to_water_table_from_surface_in_peat_m": -1.2,
    }]


def test_cache_records_groundwater_unavailable_without_fabrication(tmp_path):
    result = smap.build_cache(tmp_path, session=_Session())
    assert result.status == smap.SourceStatus.SKIPPED
    manifest = json.loads((tmp_path / "smap_peatclsm_2019_demo.metadata.json").read_text())
    groundwater = manifest["variables"]["groundwater_water_table_depth"]
    assert groundwater["status"] == "unavailable"
    assert groundwater["unit"] is None
    assert "No valid PEATCLSM" in groundwater["reason"]
    assert any(artifact.get("status") == "not_downloaded" for artifact in manifest["artifacts"])


def test_cache_marks_peatclsm_water_level_available(tmp_path):
    h5py = pytest.importorskip("h5py")
    source = tmp_path / "subset.h5"
    with h5py.File(source, "w") as handle:
        handle["latitude"] = np.array([-3.8])
        handle["longitude"] = np.array([116.2])
        handle["sm_surface"] = np.array([0.31])
        handle["depth_to_water_table_from_surface_in_peat"] = np.array([0.8])

    result = smap.build_cache(tmp_path, source_file=source, session=_Session())
    assert result.status == smap.SourceStatus.OK
    manifest = json.loads((tmp_path / "smap_peatclsm_2019_demo.metadata.json").read_text())
    assert manifest["variables"]["groundwater_water_table_depth"]["status"] == "available"
    assert json.loads((tmp_path / "groundwater_context_2019_demo.json").read_text())["status"] == "available"
