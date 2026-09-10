from __future__ import annotations

from types import SimpleNamespace

from data_pipeline.imagery.scene_selection import (
    ScenePosition,
    select_closest_scene,
    select_scenes,
)


def _feature(
    product_id: str,
    acquired_at: str,
    *,
    cloud_cover: float | None = None,
    collection: str = "sentinel-2-l2a",
    orbit_state: str = "descending",
    relative_orbit: int = 42,
) -> dict:
    properties = {
        "datetime": acquired_at,
        "constellation": "sentinel-2" if collection.startswith("sentinel-2") else "sentinel-1",
        "sat:orbit_state": orbit_state,
        "sat:relative_orbit": relative_orbit,
        "sat:absolute_orbit": 12345,
    }
    if cloud_cover is not None:
        properties["eo:cloud_cover"] = cloud_cover
    return {
        "id": product_id,
        "properties": properties,
        "assets": {"Product": {"href": f"https://download.example/{product_id}"}},
        "links": [{"rel": "self", "href": f"https://stac.example/items/{product_id}"}],
    }


EVENT_START = "2026-01-10T12:00:00Z"
EVENT_END = "2026-01-12T12:00:00Z"


def test_selects_closest_usable_optical_pre_and_post_scenes_with_cloud_filter():
    s2 = [
        _feature("S2-PRE-CLOSE-BUT-CLOUDY", "2026-01-10T11:00:00Z", cloud_cover=90),
        _feature("S2-PRE", "2026-01-10T10:00:00Z", cloud_cover=10),
        _feature("S2-PRE-FAR", "2026-01-09T10:00:00Z", cloud_cover=1),
        _feature("S2-DURING", "2026-01-11T00:00:00Z", cloud_cover=1),
        _feature("S2-POST-CLOSE-BUT-CLOUDY", "2026-01-12T13:00:00Z", cloud_cover=80),
        _feature("S2-POST", "2026-01-12T14:00:00Z", cloud_cover=20),
    ]

    result = select_scenes([], s2, EVENT_START, EVENT_END, max_cloud_cover_pct=50)

    assert result.sentinel2_pre_event is not None
    assert result.sentinel2_pre_event.product_id == "S2-PRE"
    assert result.sentinel2_pre_event.temporal_distance_hours == 2.0
    assert result.sentinel2_post_event is not None
    assert result.sentinel2_post_event.product_id == "S2-POST"
    assert result.sentinel2_post_event.temporal_distance_hours == 2.0


def test_sentinel1_selection_keeps_orbit_and_download_provenance():
    s1 = [
        _feature(
            "S1-PRE",
            "2026-01-09T12:00:00Z",
            collection="sentinel-1-grd",
            relative_orbit=120,
        ),
        _feature(
            "S1-POST",
            "2026-01-13T12:00:00Z",
            collection="sentinel-1-grd",
            relative_orbit=121,
        ),
    ]

    result = select_scenes(s1, [], EVENT_START, EVENT_END)
    pre = result.sentinel1_pre_event
    post = result.sentinel1_post_event

    assert pre is not None and post is not None
    assert pre.sensor == "Sentinel-1"
    assert pre.orbit == {"state": "descending", "absolute": 12345, "relative": 120}
    assert pre.product_reference == "https://download.example/S1-PRE"
    assert pre.download_reference == pre.product_reference
    assert pre.catalogue_reference.endswith("/S1-PRE")
    assert post.temporal_distance_hours == 24.0


def test_missing_optical_cloud_metadata_is_not_treated_as_cloud_free():
    scene = _feature("S2-NO-CLOUD-METADATA", "2026-01-10T00:00:00Z")

    selected = select_closest_scene(
        [scene],
        EVENT_START,
        ScenePosition.PRE_EVENT,
        collection="sentinel-2-l2a",
    )

    assert selected is None


def test_selection_accepts_fire_event_like_mapping_and_serializes_provenance():
    result = select_scenes(
        [],
        [_feature("S2-PRE", "2026-01-10T00:00:00Z", cloud_cover=10)],
        {"first_detection": EVENT_START, "last_detection": EVENT_START},
    )

    scene = result.sentinel2_pre_event
    assert scene is not None
    serialized = scene.to_dict()
    assert serialized["product_id"] == "S2-PRE"
    assert serialized["product_download_reference"].endswith("/S2-PRE")
    assert serialized["provenance"]["catalogue_endpoint"].endswith("/v1/search")
    evidence = scene.to_evidence_object("ENV_S2_PRE")
    assert evidence["evidence_id"] == "ENV_S2_PRE"
    assert evidence["raw_reference"].endswith("/S2-PRE")


def test_selection_accepts_stac_feature_collections_and_canonical_event_fields():
    event = SimpleNamespace(
        firstDetected=EVENT_START,
        lastDetected=EVENT_END,
    )
    response = {
        "type": "FeatureCollection",
        "features": [
            _feature("S2-PRE", "2026-01-10T00:00:00Z", cloud_cover=10),
            "malformed feature",
        ],
    }

    result = select_scenes([], response, event, cloud_cover_threshold_pct=10)

    assert result.sentinel2_pre_event is not None
    assert result.sentinel2_pre_event.product_id == "S2-PRE"
    assert result.event_start == EVENT_START
    assert result.event_end == EVENT_END


def test_sentinel1_does_not_apply_optical_cloud_threshold():
    s1 = [
        _feature(
            "S1-CLOUDY-BUT-USABLE",
            "2026-01-10T11:00:00Z",
            cloud_cover=99,
            collection="sentinel-1-grd",
        )
    ]

    result = select_scenes(s1, [], EVENT_START, EVENT_END, max_cloud_cover_pct=0)

    assert result.sentinel1_pre_event is not None
    assert result.sentinel1_pre_event.product_id == "S1-CLOUDY-BUT-USABLE"
    assert result.sentinel1_pre_event.cloud_cover_pct == 99


# The #193 shape: a scope-bbox search returns tiles that touch the box, and
# the tile closest in time to an event can stop short of the event itself.
def _square(west: float, south: float, east: float, north: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }


EVENT_LOCATION = (-3.455, 115.903)  # (lat, lon): the western-edge demo event


def test_a_scene_whose_footprint_excludes_the_event_is_not_selected_even_when_closest_in_time():
    closest_but_elsewhere = _feature("S2-EAST", "2026-01-10T06:00:00Z", cloud_cover=5)
    closest_but_elsewhere["geometry"] = _square(116.0, -4.0, 117.0, -3.0)
    covering = _feature("S2-WEST", "2026-01-08T06:00:00Z", cloud_cover=5)
    covering["geometry"] = _square(115.0, -4.0, 116.0, -3.0)

    result = select_scenes([], [closest_but_elsewhere, covering], EVENT_START, EVENT_END, location=EVENT_LOCATION)

    scene = result.sentinel2_pre_event
    assert scene is not None
    assert scene.product_id == "S2-WEST"
    assert scene.provenance["footprint_check"] == {
        "performed": True,
        "method": "geometry",
        "event_centroid": {"lat": -3.455, "lon": 115.903},
        "contains_event_centroid": True,
    }
    assert scene.algorithm_version == "copernicus-scene-selector-v2"


def test_no_covering_scene_means_no_scene_rather_than_the_nearest_wrong_one():
    elsewhere = _feature("S1-EAST", "2026-01-10T06:00:00Z", collection="sentinel-1-grd")
    elsewhere["geometry"] = _square(116.0, -4.0, 117.0, -3.0)
    no_footprint = _feature("S1-UNKNOWN", "2026-01-09T06:00:00Z", collection="sentinel-1-grd")

    result = select_scenes([elsewhere, no_footprint], [], EVENT_START, EVENT_END, location=EVENT_LOCATION)

    assert result.sentinel1_pre_event is None
    assert result.sentinel1_post_event is None


def test_footprint_check_falls_back_to_bbox_and_handles_multipolygons_with_holes():
    by_bbox = _feature("S2-BBOX", "2026-01-13T06:00:00Z", cloud_cover=5)
    by_bbox["bbox"] = [115.0, -4.0, 116.0, -3.0]
    holed = _feature("S2-HOLE", "2026-01-13T05:00:00Z", cloud_cover=5)
    holed["geometry"] = {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [[115.0, -4.0], [116.0, -4.0], [116.0, -3.0], [115.0, -3.0], [115.0, -4.0]],
                [[115.8, -3.6], [116.0, -3.6], [116.0, -3.3], [115.8, -3.3], [115.8, -3.6]],  # hole around the event
            ]
        ],
    }

    result = select_scenes([], [by_bbox, holed], EVENT_START, EVENT_END, location={"lat": -3.455, "lon": 115.903})

    scene = result.sentinel2_post_event
    assert scene is not None
    assert scene.product_id == "S2-BBOX"
    assert scene.provenance["footprint_check"]["method"] == "bbox"


def test_a_fire_event_like_mapping_supplies_its_own_centroid():
    elsewhere = _feature("S2-EAST", "2026-01-10T06:00:00Z", cloud_cover=5)
    elsewhere["geometry"] = _square(116.0, -4.0, 117.0, -3.0)
    event = {"first_detection": EVENT_START, "last_detection": EVENT_END, "centroid": {"lat": -3.455, "lon": 115.903}}

    assert select_scenes([], [elsewhere], event).sentinel2_pre_event is None
    assert select_closest_scene([elsewhere], event, ScenePosition.PRE_EVENT, collection="sentinel-2-l2a") is None


def test_without_a_location_selection_is_by_time_alone_and_says_so():
    elsewhere = _feature("S2-EAST", "2026-01-10T06:00:00Z", cloud_cover=5)
    elsewhere["geometry"] = _square(116.0, -4.0, 117.0, -3.0)

    scene = select_scenes([], [elsewhere], EVENT_START, EVENT_END).sentinel2_pre_event

    assert scene is not None
    assert scene.provenance["footprint_check"] == {"performed": False}
