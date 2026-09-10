"""Render investigation-sized Sentinel-1/2 context images for the demo FireEvents.

For every FireEvent in the committed artifact that carries scene-selection
evidence (the 16 demo in-scope+buffer events `enrich_audit_events` covered),
ask the CDSE Process API for one picture per selected scene -- Sentinel-2
SWIR false colour and Sentinel-1 VV/VH dB composite, pre and post event --
and write them where the console serves static files:

    frontend/public/imagery/<eventId>/<s2|s1>-<pre|post>.jpg      the image
    frontend/public/imagery/<eventId>/<s2|s1>-<pre|post>.json     its provenance
    frontend/public/imagery/<eventId>/<...>.missing.json          why it could not be made
    frontend/public/imagery/manifest.json                         all of the above, per event

Why this shape (issue #191):

* The images are committed and served by Amplify next to `public/pipeline/`,
  the existing path for pipeline output the console fetches at runtime. They
  never enter the Lambda bundle (which is already near its size limit) or
  the JS bundle.
* Each request is pinned to the acquisition day of the scene the evidence
  already names, so the picture and the drawer's scene metadata agree. See
  `imagery/process_api.py` for the recipes and the reasoning.
* Re-running is safe: an asset already on disk is skipped unless --force,
  and the manifest is rebuilt from whatever the directory holds. A scene
  that cannot be rendered gets a `.missing.json` stating why, never a
  substitute from another date.

Run it by hand, once, with a CDSE OAuth client in data_pipeline/.env:

    cd data_pipeline && python -m data_pipeline.generate_processed_imagery [--limit N] [--event FE-...] [--force]
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from data_pipeline.config import CDSE_CLIENT_ID, CDSE_CLIENT_SECRET, ROOT
from data_pipeline.imagery import process_api

AUDIT_ID = "demo-2019-haze"
BACKEND_DATA = ROOT.parent / "backend" / "app" / "data"
EVENTS_ARTIFACT = BACKEND_DATA / "audit_events.json.gz"
DETAIL_ARTIFACT = BACKEND_DATA / "audit_triage_detail.json.gz"
OUTPUT_ROOT = ROOT.parent / "frontend" / "public" / "imagery"
# What the console prefixes the manifest's `path` with: nothing. It is
# fetched from the console's own origin, like /pipeline/firms-2019-09.json.
PUBLIC_PREFIX = "/imagery"


def load_events_with_scenes() -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Every event that has selected scenes, with those scene EvidenceObjects.

    "Has scene-selection evidence" is the selector on purpose: it is exactly
    the input this generator needs, and it is what `enrich_audit_events`
    wrote for the demo geoshape. No separate list of event ids to drift.
    """
    with gzip.open(EVENTS_ARTIFACT) as handle:
        events = json.load(handle)["audits"][AUDIT_ID]["events"]
    with gzip.open(DETAIL_ARTIFACT) as handle:
        detail = json.load(handle)[AUDIT_ID]
    selected = []
    for event in sorted(events, key=lambda row: row["eventId"]):
        scenes = [
            item
            for item in detail.get(event["eventId"], {}).get("evidence", [])
            if item.get("category") == "imagery"
        ]
        if scenes:
            selected.append(
                (
                    event,
                    sorted(
                        scenes,
                        key=lambda item: (
                            item["value"]["sensor"],
                            item["value"]["position"],
                        ),
                    ),
                )
            )
    return selected


def render_scene(
    client: process_api.ProcessApiClient,
    event: dict[str, Any],
    evidence: dict[str, Any],
    root: Path,
    *,
    force: bool,
    generated_at: str,
) -> str:
    """Render one scene to disk. Returns 'skipped', 'rendered' or 'missing'."""
    scene = evidence["value"]
    event_id = event["eventId"]
    slug = process_api.asset_slug(scene["sensor"], scene["position"])
    folder = root / event_id
    image_path = folder / f"{slug}.jpg"
    sidecar_path = folder / f"{slug}.json"
    missing_path = folder / f"{slug}.missing.json"
    if image_path.exists() and sidecar_path.exists() and not force:
        return "skipped"

    bbox = process_api.aoi_bbox(event["centroid"]["lat"], event["centroid"]["lon"])
    request = process_api.build_request(scene, bbox)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        image = client.render(request)
        coverage = process_api.coverage_fraction(image)
        if coverage < process_api.MIN_COVERAGE_FRACTION:
            raise process_api.ProcessApiError(
                200,
                f"only {coverage:.1%} of the 10 km square carried data on {request['input']['data'][0]['dataFilter']['timeRange']['from'][:10]}; "
                "the selected product does not cover this event's surroundings",
            )
    except process_api.ProcessApiError as exc:
        missing_path.write_text(
            json.dumps(
                process_api.missing_entry(event_id, evidence, exc.detail, generated_at),
                indent=2,
            )
        )
        for stale in (image_path, sidecar_path):
            stale.unlink(missing_ok=True)
        return "missing"

    width, height = process_api.image_size(image)
    if (width, height) != (process_api.OUTPUT_PX, process_api.OUTPUT_PX):
        raise RuntimeError(
            f"{event_id} {slug}: API returned {width}x{height}, expected {process_api.OUTPUT_PX} square"
        )
    image_path.write_bytes(image)
    entry = process_api.manifest_entry(
        event_id,
        evidence,
        request,
        f"{PUBLIC_PREFIX}/{event_id}/{slug}.jpg",
        len(image),
        coverage,
        generated_at,
    )
    sidecar_path.write_text(json.dumps(entry, indent=2))
    missing_path.unlink(missing_ok=True)
    return "rendered"


def write_manifest(root: Path, generated_at: str) -> dict[str, Any]:
    manifest = process_api.build_manifest(root, AUDIT_ID, generated_at)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after N newly rendered images (smoke test)",
    )
    parser.add_argument(
        "--event", action="append", default=None, help="Only this event id (repeatable)"
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-render images already on disk"
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Rebuild manifest.json from disk; no API calls",
    )
    args = parser.parse_args(argv)

    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    if args.manifest_only:
        manifest = write_manifest(OUTPUT_ROOT, generated_at)
        print(f"manifest.json rebuilt: {len(manifest['events'])} event(s)")
        return 0

    if not (CDSE_CLIENT_ID and CDSE_CLIENT_SECRET):
        print(
            "CDSE_CLIENT_ID / CDSE_CLIENT_SECRET are not set in data_pipeline/.env.\n"
            "Sentinel Hub APIs on CDSE need a registered OAuth client (client_credentials), not the\n"
            "CDSE_USERNAME/CDSE_PASSWORD pair: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings",
            file=sys.stderr,
        )
        return 2

    from data_pipeline.common.http import SESSION  # network only from here on

    client = process_api.ProcessApiClient(SESSION, CDSE_CLIENT_ID, CDSE_CLIENT_SECRET)
    counts = {"rendered": 0, "skipped": 0, "missing": 0}
    for event, scenes in load_events_with_scenes():
        if args.event and event["eventId"] not in args.event:
            continue
        for evidence in scenes:
            if args.limit is not None and counts["rendered"] >= args.limit:
                break
            outcome = render_scene(
                client,
                event,
                evidence,
                OUTPUT_ROOT,
                force=args.force,
                generated_at=generated_at,
            )
            counts[outcome] += 1
            scene = evidence["value"]
            print(
                f"{outcome:8} {event['eventId']} {scene['sensor']} {scene['position']} {scene['product_id']}"
            )
    manifest = write_manifest(OUTPUT_ROOT, generated_at)
    total_bytes = sum(
        asset["bytes"]
        for bucket in manifest["events"].values()
        for asset in bucket["assets"]
    )
    total_assets = sum(len(bucket["assets"]) for bucket in manifest["events"].values())
    total_missing = sum(
        len(bucket["missing"]) for bucket in manifest["events"].values()
    )
    print(
        f"Done: {counts['rendered']} rendered, {counts['skipped']} skipped, {counts['missing']} missing this run. "
        f"On disk: {total_assets} assets ({total_bytes / 1e6:.1f} MB), {total_missing} missing, {len(manifest['events'])} events."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
