"""Select usable Copernicus scenes around a FireEvent.

The Copernicus STAC catalogue returns scene metadata, not a decision about
which products belong in an evidence pack.  This module makes that decision
deterministic and inspectable: Sentinel-2 scenes must pass a caller-visible
cloud threshold, Sentinel-1 scenes are selected without an optical cloud
filter, and each sensor gets the closest available pre-event and post-event
scene.

The selector is deliberately pure.  Callers fetch STAC features through
``sources.copernicus_cds.search`` and pass the frozen response here.  That
keeps network access, selection, and later imagery processing as separate
pipeline stages and makes a selection reproducible from the STAC response.
Scene metadata is environmental evidence provenance only; it is not a causal
or responsibility finding.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

STAC_SEARCH_ENDPOINT = "https://stac.dataspace.copernicus.eu/v1/search"
ALGORITHM_VERSION = "copernicus-scene-selector-v1"
DEFAULT_MAX_CLOUD_COVER_PCT = 50.0


class ScenePosition(StrEnum):
    """The event-relative position of a selected acquisition."""

    PRE_EVENT = "pre_event"
    POST_EVENT = "post_event"

    @classmethod
    def _missing_(cls, value: object) -> ScenePosition | None:
        aliases = {
            "pre": cls.PRE_EVENT,
            "before": cls.PRE_EVENT,
            "post": cls.POST_EVENT,
            "after": cls.POST_EVENT,
        }
        return aliases.get(str(value).lower())


@dataclass(frozen=True)
class SelectedScene:
    """A selected STAC item with enough metadata to reproduce its use later."""

    product_id: str
    acquisition_time: str
    sensor: str
    position: ScenePosition
    orbit: dict[str, Any]
    cloud_cover_pct: float | None
    temporal_distance_hours: float
    product_reference: str | None
    download_reference: str | None
    catalogue_reference: str | None
    collection: str
    provenance: dict[str, Any]
    # A small (few hundred px) preview JPEG the catalogue already generated --
    # confirmed publicly fetchable with no CDSE auth (a plain GET follows one
    # redirect to a ~40 KB JPEG). Genuinely more useful at a glance than
    # acquisition metadata alone; still just a quicklook, not the product.
    thumbnail_url: str | None = None
    algorithm_version: str = ALGORITHM_VERSION

    @property
    def cloud_cover(self) -> float | None:
        """Compatibility alias used by consumers that omit the ``_pct`` suffix."""

        return self.cloud_cover_pct

    @property
    def temporal_distance_days(self) -> float:
        return self.temporal_distance_hours / 24.0

    @property
    def product_download_reference(self) -> str | None:
        """The best product reference for a later downloader."""

        return self.download_reference or self.product_reference

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["position"] = self.position.value
        result["orbit"] = dict(self.orbit)
        result["provenance"] = dict(self.provenance)
        result["temporal_distance_days"] = round(self.temporal_distance_days, 6)
        # Keep both names because STAC calls this a product asset while the
        # evidence pack describes the same pointer as a download reference.
        result["product_download_reference"] = self.product_download_reference
        result["cloud_cover"] = self.cloud_cover_pct
        if self.collection.lower().replace("_", "-").startswith("sentinel-1"):
            # A STAC thumbnail is intentionally only a fallback preview.  A
            # later authenticated RTC/GRD processor can replace its URL while
            # preserving this scene id, time, and event relationship.
            result["product"] = "Sentinel-1 GRD"
            result["polarisation"] = "VV / VH (when available)"
            result["display_processing"] = "catalogue quicklook fallback; not analytical backscatter"
            result["preferred_visualization"] = "RTC or terrain-corrected GRD; linear VV/VH → dB; 2–98% percentile stretch"
        return result

    def to_evidence_object(self, evidence_id: str) -> dict[str, Any]:
        """Represent this selection as one provenance-bearing EvidenceObject."""

        return {
            "evidence_id": evidence_id,
            "category": "remote-sensing",
            "type": "imagery-scene",
            "observation": (
                f"{self.sensor} {self.position.value.replace('_', '-')} scene "
                f"{self.product_id} acquired at {self.acquisition_time}"
            ),
            "source": "Copernicus Data Space Ecosystem",
            "time_window": self.acquisition_time,
            "value": self.to_dict(),
            "quality": None,
            "limitations": [
                "Scene-level metadata does not establish pixel-level usability or change.",
                "A scene's cloud percentage is an acquisition-level catalogue value, not an event-footprint cloud mask.",
            ],
            "retrieved_at": None,
            "algorithm_version": self.algorithm_version,
            "raw_reference": self.catalogue_reference or self.product_download_reference,
        }


@dataclass(frozen=True)
class CopernicusSceneSelection:
    """The four independent pre/post selection slots for Sentinel-1 and -2."""

    event_start: str
    event_end: str
    max_cloud_cover_pct: float
    sentinel2_pre_event: SelectedScene | None
    sentinel2_post_event: SelectedScene | None
    sentinel1_pre_event: SelectedScene | None
    sentinel1_post_event: SelectedScene | None
    algorithm_version: str = ALGORITHM_VERSION

    @property
    def pre_event_sentinel2(self) -> SelectedScene | None:
        return self.sentinel2_pre_event

    @property
    def post_event_sentinel2(self) -> SelectedScene | None:
        return self.sentinel2_post_event

    @property
    def pre_event_sentinel1(self) -> SelectedScene | None:
        return self.sentinel1_pre_event

    @property
    def post_event_sentinel1(self) -> SelectedScene | None:
        return self.sentinel1_post_event

    @property
    def selected_scenes(self) -> tuple[SelectedScene, ...]:
        return tuple(
            scene
            for scene in (
                self.sentinel2_pre_event,
                self.sentinel2_post_event,
                self.sentinel1_pre_event,
                self.sentinel1_post_event,
            )
            if scene is not None
        )

    def to_dict(self) -> dict[str, Any]:
        def scene_dict(scene: SelectedScene | None) -> dict[str, Any] | None:
            return None if scene is None else scene.to_dict()

        return {
            "event_start": self.event_start,
            "event_end": self.event_end,
            "max_cloud_cover_pct": self.max_cloud_cover_pct,
            "sentinel2": {
                "pre_event": scene_dict(self.sentinel2_pre_event),
                "post_event": scene_dict(self.sentinel2_post_event),
            },
            "sentinel1": {
                "pre_event": scene_dict(self.sentinel1_pre_event),
                "post_event": scene_dict(self.sentinel1_post_event),
            },
            "algorithm_version": self.algorithm_version,
        }


def _parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_text(value: str | datetime) -> str:
    """Keep supplied ISO text stable while normalising datetime inputs."""

    if isinstance(value, str):
        _parse_timestamp(value)
        return value
    return _parse_timestamp(value).isoformat().replace("+00:00", "Z")


def _event_window(
    event_start: str | datetime | Mapping[str, Any] | Any,
    event_end: str | datetime | None,
) -> tuple[datetime, datetime, str, str]:
    if event_end is None:
        if isinstance(event_start, Mapping):
            start_value = event_start.get("first_detection", event_start.get("firstDetected"))
            end_value = event_start.get("last_detection", event_start.get("lastDetected"))
        else:
            start_value = getattr(
                event_start,
                "first_detection",
                getattr(event_start, "firstDetected", None),
            )
            end_value = getattr(
                event_start,
                "last_detection",
                getattr(event_start, "lastDetected", None),
            )
        if start_value is not None:
            event_start = start_value
            event_end = end_value or start_value

    if event_end is None:
        event_end = event_start
    start_dt = _parse_timestamp(event_start)
    end_dt = _parse_timestamp(event_end)
    if end_dt < start_dt:
        raise ValueError("event_end must not be earlier than event_start")
    return start_dt, end_dt, _timestamp_text(event_start), _timestamp_text(event_end)


def _numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _cloud_cover(properties: Mapping[str, Any]) -> float | None:
    for key in ("eo:cloud_cover", "cloud_cover_pct", "cloud_cover"):
        if key in properties:
            value = _numeric(properties[key])
            return value if value is not None and 0 <= value <= 100 else None
    return None


def _href(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, Mapping):
        return None
    if isinstance(value.get("href"), str):
        return value["href"]
    for key in ("https", "download", "product", "alternate"):
        found = _href(value.get(key))
        if found:
            return found
    return None


def _feature_list(
    features: Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> Sequence[Mapping[str, Any]]:
    """Accept either a STAC feature list or a complete FeatureCollection."""

    if isinstance(features, Mapping):
        features = features.get("features", ())
    if isinstance(features, Sequence) and not isinstance(features, (str, bytes)):
        return features
    return ()


def _acquisition_value(properties: Mapping[str, Any]) -> Any:
    for key in ("datetime", "start_datetime", "end_datetime"):
        value = properties.get(key)
        if value:
            return value
    return None


def _asset_reference(feature: Mapping[str, Any]) -> str | None:
    assets = feature.get("assets")
    if isinstance(assets, Mapping):
        for name in ("Product", "product", "PRODUCT", "data", "download"):
            reference = _href(assets.get(name))
            if reference:
                return reference
    links = feature.get("links")
    if isinstance(links, Sequence) and not isinstance(links, (str, bytes)):
        for link in links:
            if isinstance(link, Mapping) and link.get("rel") in {"download", "product"}:
                reference = _href(link)
                if reference:
                    return reference
    return None


def _thumbnail_reference(feature: Mapping[str, Any]) -> str | None:
    assets = feature.get("assets")
    if isinstance(assets, Mapping):
        for name in ("thumbnail", "preview", "quicklook"):
            reference = _href(assets.get(name))
            if reference:
                return reference
    return None


def _catalogue_reference(feature: Mapping[str, Any]) -> str | None:
    links = feature.get("links")
    if isinstance(links, Sequence) and not isinstance(links, (str, bytes)):
        for link in links:
            if isinstance(link, Mapping) and link.get("rel") == "self":
                reference = _href(link)
                if reference:
                    return reference
    return None


def _orbit_metadata(properties: Mapping[str, Any]) -> dict[str, Any]:
    orbit: dict[str, Any] = {}
    if isinstance(properties.get("orbit"), Mapping):
        orbit.update(properties["orbit"])
    for output_name, property_name in (
        ("state", "sat:orbit_state"),
        ("absolute", "sat:absolute_orbit"),
        ("relative", "sat:relative_orbit"),
        ("cycle", "sat:orbit_cycle"),
    ):
        if properties.get(property_name) is not None:
            orbit[output_name] = properties[property_name]
    return orbit


def _sensor_name(collection: str, properties: Mapping[str, Any]) -> str:
    constellation = str(properties.get("constellation", "")).lower()
    normalized_collection = collection.lower().replace("_", "-")
    if "sentinel-1" in constellation or normalized_collection.startswith("sentinel-1"):
        return "Sentinel-1"
    if "sentinel-2" in constellation or normalized_collection.startswith("sentinel-2"):
        return "Sentinel-2"
    return constellation or collection


def _feature_scene(
    feature: Mapping[str, Any],
    collection: str,
    position: ScenePosition,
    event_boundary: datetime,
) -> SelectedScene | None:
    properties = feature.get("properties")
    if not isinstance(properties, Mapping):
        properties = {}
    product_id = (
        feature.get("id")
        or properties.get("id")
        or properties.get("product:id")
        or properties.get("product_id")
    )
    acquisition_value = _acquisition_value(properties)
    if not product_id or not acquisition_value:
        return None
    try:
        acquisition_dt = _parse_timestamp(str(acquisition_value))
    except (TypeError, ValueError):
        return None

    cloud_cover = _cloud_cover(properties)
    product_reference = _asset_reference(feature)
    catalogue_reference = _catalogue_reference(feature)
    provenance = {
        "source": "Copernicus Data Space Ecosystem",
        "catalogue_endpoint": STAC_SEARCH_ENDPOINT,
        "catalogue_item": catalogue_reference,
        "collection": collection,
        "product_id": str(product_id),
    }
    return SelectedScene(
        product_id=str(product_id),
        acquisition_time=str(acquisition_value),
        sensor=_sensor_name(collection, properties),
        position=position,
        orbit=_orbit_metadata(properties),
        cloud_cover_pct=cloud_cover,
        temporal_distance_hours=round(
            abs((acquisition_dt - event_boundary).total_seconds()) / 3600.0, 6
        ),
        product_reference=product_reference,
        download_reference=product_reference,
        catalogue_reference=catalogue_reference,
        collection=collection,
        provenance=provenance,
        thumbnail_url=_thumbnail_reference(feature),
    )


def _select_for_position(
    features: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    collection: str,
    position: ScenePosition,
    event_boundary: datetime,
    *,
    max_cloud_cover_pct: float,
    apply_cloud_filter: bool,
) -> SelectedScene | None:
    candidates: list[SelectedScene] = []
    for feature in _feature_list(features):
        if not isinstance(feature, Mapping):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            properties = {}
        acquisition_value = _acquisition_value(properties)
        try:
            acquisition_dt = _parse_timestamp(str(acquisition_value))
        except (TypeError, ValueError):
            continue
        if position is ScenePosition.PRE_EVENT and acquisition_dt > event_boundary:
            continue
        if position is ScenePosition.POST_EVENT and acquisition_dt < event_boundary:
            continue

        cloud_cover = _cloud_cover(properties)
        if apply_cloud_filter and (cloud_cover is None or cloud_cover > max_cloud_cover_pct):
            continue
        scene = _feature_scene(feature, collection, position, event_boundary)
        if scene is not None:
            candidates.append(scene)

    return min(
        candidates,
        key=lambda scene: (
            scene.temporal_distance_hours,
            scene.cloud_cover_pct if scene.cloud_cover_pct is not None else math.inf,
            scene.acquisition_time,
            scene.product_id,
        ),
        default=None,
    )


def select_closest_scene(
    features: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    event_start: str | datetime | Mapping[str, Any] | Any,
    position: ScenePosition | str,
    *,
    collection: str,
    event_end: str | datetime | None = None,
    max_cloud_cover_pct: float = DEFAULT_MAX_CLOUD_COVER_PCT,
) -> SelectedScene | None:
    """Select one closest usable scene for one sensor and event position."""

    if not math.isfinite(float(max_cloud_cover_pct)) or not 0 <= max_cloud_cover_pct <= 100:
        raise ValueError("max_cloud_cover_pct must be finite and between 0 and 100")
    start_dt, end_dt, _, _ = _event_window(event_start, event_end)
    selected_position = ScenePosition(position)
    boundary = start_dt if selected_position is ScenePosition.PRE_EVENT else end_dt
    is_sentinel2 = collection.lower().replace("_", "-").startswith("sentinel-2")
    return _select_for_position(
        features,
        collection,
        selected_position,
        boundary,
        max_cloud_cover_pct=float(max_cloud_cover_pct),
        apply_cloud_filter=is_sentinel2,
    )


def select_scenes(
    sentinel1_features: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    sentinel2_features: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    event_start: str | datetime | Mapping[str, Any] | Any,
    event_end: str | datetime | None = None,
    *,
    max_cloud_cover_pct: float = DEFAULT_MAX_CLOUD_COVER_PCT,
    cloud_cover_threshold_pct: float | None = None,
) -> CopernicusSceneSelection:
    """Select pre/post Sentinel scenes around an event.

    ``event_start`` and ``event_end`` may be timestamps, a FireEvent-like
    object, or a mapping with ``first_detection``/``last_detection`` fields.
    A point-in-time event uses the same timestamp for both boundaries.  The
    cloud threshold applies only to Sentinel-2 and scenes without a usable
    catalogue cloud value are conservatively excluded.
    """

    if cloud_cover_threshold_pct is not None:
        max_cloud_cover_pct = cloud_cover_threshold_pct
    if not math.isfinite(float(max_cloud_cover_pct)) or not 0 <= max_cloud_cover_pct <= 100:
        raise ValueError("max_cloud_cover_pct must be finite and between 0 and 100")
    start_dt, end_dt, start_text, end_text = _event_window(event_start, event_end)

    return CopernicusSceneSelection(
        event_start=start_text,
        event_end=end_text,
        max_cloud_cover_pct=float(max_cloud_cover_pct),
        sentinel2_pre_event=select_closest_scene(
            sentinel2_features,
            start_dt,
            ScenePosition.PRE_EVENT,
            collection="sentinel-2-l2a",
            event_end=end_dt,
            max_cloud_cover_pct=float(max_cloud_cover_pct),
        ),
        sentinel2_post_event=select_closest_scene(
            sentinel2_features,
            start_dt,
            ScenePosition.POST_EVENT,
            collection="sentinel-2-l2a",
            event_end=end_dt,
            max_cloud_cover_pct=float(max_cloud_cover_pct),
        ),
        sentinel1_pre_event=select_closest_scene(
            sentinel1_features,
            start_dt,
            ScenePosition.PRE_EVENT,
            collection="sentinel-1-grd",
            event_end=end_dt,
            max_cloud_cover_pct=float(max_cloud_cover_pct),
        ),
        sentinel1_post_event=select_closest_scene(
            sentinel1_features,
            start_dt,
            ScenePosition.POST_EVENT,
            collection="sentinel-1-grd",
            event_end=end_dt,
            max_cloud_cover_pct=float(max_cloud_cover_pct),
        ),
    )


select_copernicus_scenes = select_scenes
select_pre_post_scenes = select_scenes
