"""The Process API request is pinned to the selected scene, and nothing is invented.

No network: the request builders are pure, and the generator takes a client
whose session is faked here. What matters is the exact JSON that would be
sent, and that a failure leaves an honest `.missing.json` rather than a
picture from some other date.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from data_pipeline import generate_processed_imagery as generator
from data_pipeline.imagery import process_api

EVENT = {
    "eventId": "FE-20190901-1ecb99d2e4",
    "centroid": {"lat": -3.439225, "lon": 116.26473333333333},
}


def scene_evidence(
    sensor: str, position: str, *, acquired: str, orbit_state: str = "descending"
) -> dict:
    product = (
        "S2A_MSIL2A_20190831T021601_N0500_R003_T50MMA"
        if sensor == "Sentinel-2"
        else "S1A_IW_GRDH_1SDV_20190830T215154"
    )
    return {
        "evidence_id": f"ENV_IMAGERY_{EVENT['eventId']}_{sensor}_{position}",
        "category": "imagery",
        "value": {
            "sensor": sensor,
            "position": position,
            "collection": "sentinel-2-l2a"
            if sensor == "Sentinel-2"
            else "sentinel-1-grd",
            "product_id": product,
            "acquisition_time": acquired,
            "orbit": {"state": orbit_state, "relative": 3, "absolute": 21879},
            "cloud_cover_pct": 15.31 if sensor == "Sentinel-2" else None,
            "temporal_distance_hours": 26.6,
            "catalogue_reference": f"https://stac.example/items/{product}",
        },
    }


def jpeg(fill: int, size: int = process_api.OUTPUT_PX) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), (fill, fill, fill)).save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeSession:
    """Answers the token exchange, then returns whatever image is queued."""

    def __init__(self, images: list[bytes | Exception]):
        self.images = list(images)
        self.requests: list[dict] = []

    def post(self, url, **kwargs):
        if url == process_api.OAUTH_ENDPOINT:
            return SimpleNamespace(status_code=200, json=lambda: {"access_token": "t"})
        self.requests.append(kwargs["json"])
        answer = self.images.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(status_code=200, content=answer, text="")


def test_aoi_is_a_ten_km_square_centred_on_the_event():
    west, south, east, north = process_api.aoi_bbox(-3.439225, 116.264733)

    assert north - south == pytest.approx(10 / 111.32, rel=1e-4)
    assert (east - west) > (
        north - south
    )  # longitude degrees are shorter off the equator
    assert (west + east) / 2 == pytest.approx(116.264733, abs=1e-5)
    assert (south + north) / 2 == pytest.approx(-3.439225, abs=1e-5)


def test_time_range_is_the_selected_scenes_utc_day():
    assert process_api.pin_time_range("2019-08-31T02:16:01.024000Z") == {
        "from": "2019-08-31T00:00:00Z",
        "to": "2019-08-31T23:59:59Z",
    }
    # A late-evening SAR pass stays on its own UTC date.
    assert (
        process_api.pin_time_range("2019-08-30T21:51:54.917759Z")["from"]
        == "2019-08-30T00:00:00Z"
    )


def test_sentinel2_request_asks_for_false_colour_over_the_pinned_day():
    evidence = scene_evidence(
        "Sentinel-2", "pre_event", acquired="2019-08-31T02:16:01.024000Z"
    )

    request = process_api.build_request(evidence["value"], [116.2, -3.5, 116.3, -3.4])

    data = request["input"]["data"][0]
    assert data["type"] == "sentinel-2-l2a"
    assert data["dataFilter"] == {
        "timeRange": {"from": "2019-08-31T00:00:00Z", "to": "2019-08-31T23:59:59Z"},
        "mosaickingOrder": "leastCC",
    }
    assert "orbitDirection" not in data["dataFilter"]
    assert request["output"] == {
        "width": 1024,
        "height": 1024,
        "responses": [
            {"identifier": "default", "format": {"type": "image/jpeg", "quality": 90}}
        ],
    }
    assert '"B12", "B08", "B04"' in request["evalscript"]
    assert request["input"]["bounds"]["properties"]["crs"].endswith("EPSG/0/4326")


def test_sentinel1_request_pins_orbit_direction_and_asks_cdse_for_terrain_correction():
    evidence = scene_evidence(
        "Sentinel-1",
        "post_event",
        acquired="2019-09-05T21:51:00Z",
        orbit_state="ascending",
    )

    request = process_api.build_request(evidence["value"], [116.2, -3.5, 116.3, -3.4])

    data = request["input"]["data"][0]
    assert data["type"] == "sentinel-1-grd"
    assert data["dataFilter"]["orbitDirection"] == "ASCENDING"
    assert data["dataFilter"]["acquisitionMode"] == "IW"
    assert data["dataFilter"]["polarization"] == "DV"
    assert data["processing"]["orthorectify"] is True
    assert data["processing"]["backCoeff"] == "GAMMA0_TERRAIN"
    assert data["processing"]["demInstance"] == "COPERNICUS_30"
    assert data["processing"]["speckleFilter"] == {
        "type": "LEE",
        "windowSizeX": 3,
        "windowSizeY": 3,
    }
    assert "10 * Math.log10" in request["evalscript"]


def test_request_is_deterministic_for_the_same_scene():
    evidence = scene_evidence(
        "Sentinel-1", "pre_event", acquired="2019-08-30T21:51:54Z"
    )
    bbox = process_api.aoi_bbox(EVENT["centroid"]["lat"], EVENT["centroid"]["lon"])

    first = json.dumps(
        process_api.build_request(evidence["value"], bbox), sort_keys=True
    )
    second = json.dumps(
        process_api.build_request(evidence["value"], bbox), sort_keys=True
    )

    assert first == second


def test_rendered_asset_carries_its_source_evidence_and_processing(tmp_path):
    evidence = scene_evidence(
        "Sentinel-2", "pre_event", acquired="2019-08-31T02:16:01.024000Z"
    )
    session = FakeSession([jpeg(120)])
    client = process_api.ProcessApiClient(session, "id", "secret")

    outcome = generator.render_scene(
        client,
        EVENT,
        evidence,
        tmp_path,
        force=False,
        generated_at="2026-09-10T12:00:00+00:00",
    )

    assert outcome == "rendered"
    entry = json.loads((tmp_path / EVENT["eventId"] / "s2-pre.json").read_text())
    assert entry["source_evidence_id"] == evidence["evidence_id"]
    assert entry["path"] == f"/imagery/{EVENT['eventId']}/s2-pre.jpg"
    assert entry["acquisition"]["product_id"] == evidence["value"]["product_id"]
    assert entry["acquisition"]["time_range"]["from"] == "2019-08-31T00:00:00Z"
    assert entry["processing"]["recipe_id"] == "s2-swir-false-colour-v1"
    assert (
        entry["processing"]["evalscript_sha256"]
        == process_api.S2_RECIPE.evalscript_sha256
    )
    assert entry["label"] == "Optical context"
    assert entry["width"] == entry["height"] == 1024
    assert entry["bytes"] == (tmp_path / EVENT["eventId"] / "s2-pre.jpg").stat().st_size
    assert any("not analytical imagery" in text for text in entry["limitations"])
    # The request that was actually sent is the one the builder describes.
    assert session.requests[0]["input"]["bounds"]["bbox"] == entry["aoi"]["bbox"]


def test_a_black_image_is_recorded_as_missing_not_served(tmp_path):
    """No data on the pinned day is a finding about coverage, not a picture."""
    evidence = scene_evidence(
        "Sentinel-1", "post_event", acquired="2019-09-05T21:51:00Z"
    )
    client = process_api.ProcessApiClient(FakeSession([jpeg(0)]), "id", "secret")

    outcome = generator.render_scene(
        client,
        EVENT,
        evidence,
        tmp_path,
        force=False,
        generated_at="2026-09-10T12:00:00+00:00",
    )

    assert outcome == "missing"
    folder = tmp_path / EVENT["eventId"]
    assert not (folder / "s1-post.jpg").exists()
    missing = json.loads((folder / "s1-post.missing.json").read_text())
    assert missing["source_evidence_id"] == evidence["evidence_id"]
    assert "does not cover" in missing["reason"]


def test_an_api_error_is_recorded_as_missing_with_the_apis_own_reason(tmp_path):
    evidence = scene_evidence(
        "Sentinel-2", "post_event", acquired="2019-09-05T02:16:09Z"
    )
    session = FakeSession([])
    session.post = lambda url, **kwargs: (
        SimpleNamespace(status_code=200, json=lambda: {"access_token": "t"})
        if url == process_api.OAUTH_ENDPOINT
        else SimpleNamespace(
            status_code=400,
            content=b"",
            text='{"error":{"message":"No data for time range"}}',
        )
    )
    client = process_api.ProcessApiClient(session, "id", "secret")

    outcome = generator.render_scene(
        client,
        EVENT,
        evidence,
        tmp_path,
        force=False,
        generated_at="2026-09-10T12:00:00+00:00",
    )

    assert outcome == "missing"
    missing = json.loads(
        (tmp_path / EVENT["eventId"] / "s2-post.missing.json").read_text()
    )
    assert "No data for time range" in missing["reason"]


def test_an_existing_asset_is_not_re_requested_unless_forced(tmp_path):
    evidence = scene_evidence(
        "Sentinel-2", "pre_event", acquired="2019-08-31T02:16:01Z"
    )
    session = FakeSession([jpeg(120), jpeg(130)])
    client = process_api.ProcessApiClient(session, "id", "secret")
    kwargs = {"force": False, "generated_at": "2026-09-10T12:00:00+00:00"}

    assert (
        generator.render_scene(client, EVENT, evidence, tmp_path, **kwargs)
        == "rendered"
    )
    assert (
        generator.render_scene(client, EVENT, evidence, tmp_path, **kwargs) == "skipped"
    )
    assert len(session.requests) == 1
    assert (
        generator.render_scene(
            client,
            EVENT,
            evidence,
            tmp_path,
            force=True,
            generated_at=kwargs["generated_at"],
        )
        == "rendered"
    )
    assert len(session.requests) == 2


def test_a_later_success_clears_the_missing_record(tmp_path):
    evidence = scene_evidence(
        "Sentinel-1", "pre_event", acquired="2019-08-30T21:51:54Z"
    )
    client = process_api.ProcessApiClient(
        FakeSession([jpeg(0), jpeg(90)]), "id", "secret"
    )
    kwargs = {"force": True, "generated_at": "2026-09-10T12:00:00+00:00"}

    assert (
        generator.render_scene(client, EVENT, evidence, tmp_path, **kwargs) == "missing"
    )
    assert (
        generator.render_scene(client, EVENT, evidence, tmp_path, **kwargs)
        == "rendered"
    )

    folder = tmp_path / EVENT["eventId"]
    assert not (folder / "s1-pre.missing.json").exists()
    assert (folder / "s1-pre.jpg").exists()


def test_manifest_is_assembled_from_what_is_on_disk(tmp_path):
    pre = scene_evidence("Sentinel-2", "pre_event", acquired="2019-08-31T02:16:01Z")
    post = scene_evidence("Sentinel-2", "post_event", acquired="2019-09-05T02:16:09Z")
    client = process_api.ProcessApiClient(
        FakeSession([jpeg(120), jpeg(0)]), "id", "secret"
    )
    kwargs = {"force": False, "generated_at": "2026-09-10T12:00:00+00:00"}
    generator.render_scene(client, EVENT, pre, tmp_path, **kwargs)
    generator.render_scene(client, EVENT, post, tmp_path, **kwargs)

    manifest = generator.write_manifest(tmp_path, "2026-09-10T12:30:00+00:00")

    assert (tmp_path / "manifest.json").exists()
    assert manifest["audit_id"] == "demo-2019-haze"
    assert set(manifest["recipes"]) == {
        "s2-swir-false-colour-v1",
        "s1-vvvh-db-composite-v1",
    }
    bucket = manifest["events"][EVENT["eventId"]]
    assert [asset["position"] for asset in bucket["assets"]] == ["pre_event"]
    assert [item["position"] for item in bucket["missing"]] == ["post_event"]

    # A hand-deleted image drops out of the manifest rather than being listed
    # as present.
    (tmp_path / EVENT["eventId"] / "s2-pre.jpg").unlink()
    assert (
        generator.write_manifest(tmp_path, "2026-09-10T12:31:00+00:00")["events"][
            EVENT["eventId"]
        ]["assets"]
        == []
    )


def test_generator_refuses_to_run_without_an_oauth_client(monkeypatch, capsys):
    monkeypatch.setattr(generator, "CDSE_CLIENT_ID", "")
    monkeypatch.setattr(generator, "CDSE_CLIENT_SECRET", "")

    assert generator.main([]) == 2
    assert "OAuth client" in capsys.readouterr().err


def test_the_committed_artifact_yields_the_demo_events_with_four_scenes_each():
    """The selector is 'has scene evidence', and today that is the 16 demo events."""
    events = generator.load_events_with_scenes()

    assert len(events) == 16
    for event, scenes in events:
        assert {(s["value"]["sensor"], s["value"]["position"]) for s in scenes} == {
            ("Sentinel-1", "pre_event"),
            ("Sentinel-1", "post_event"),
            ("Sentinel-2", "pre_event"),
            ("Sentinel-2", "post_event"),
        }, event["eventId"]
