"""Cluster and triage the committed FIRMS export into an audit-scoped artifact
the API can serve.

Usage:
    python -m data_pipeline.export_audit_events

Reads frontend/public/pipeline/firms-2019-09.json (the 2019-09-01..05
Sumatra/Kalimantan haze window, the only real observation data committed to
this repo) and writes backend/app/data/audit_events.json.

This runs offline, on purpose. Clustering needs pandas, numpy and scipy, which
together are most of a Lambda deployment package; the API stays thin by
serving a precomputed artifact instead. Clustering 21,519 detections per
request would also be the wrong shape regardless of what it weighed -- the
work is the same for every caller and the input only changes when a source
run does.
"""

import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from data_pipeline.clustering.firms_clustering import FireEvent, cluster_events
from data_pipeline.triage.stage1 import Stage1TriageResult, summarize_triage, triage_events

REPO_ROOT = Path(__file__).parent.parent
SOURCE_JSON = REPO_ROOT / "frontend" / "public" / "pipeline" / "firms-2019-09.json"
DATA_DIR = REPO_ROOT / "backend" / "app" / "data"
# Two files, because they are read on different paths. The register table
# needs every summary on the first request; the rule-by-rule triage detail is
# read one event at a time, when an auditor opens one, and is five times the
# size. Parsing it into a 512 MB Lambda at import to serve a list request
# would be paying for it on every cold start.
DEST_EVENTS = DATA_DIR / "audit_events.json.gz"
DEST_TRIAGE = DATA_DIR / "audit_triage_detail.json.gz"

AUDIT_ID = "demo-2019-haze"

# The one audit scope that exists. There is no scope persistence yet, so this
# is defined here rather than created through POST /api/audits (spec §24) --
# the read half of the audit-scoped API can be real before the write half is.
SCOPE = {
    "id": AUDIT_ID,
    "label": "2019 Sumatra/Kalimantan haze window (demo scope)",
    "reviewStart": "2019-09-01",
    "reviewEnd": "2019-09-05",
    "contextBufferKm": 0,
}


def load_observations() -> pd.DataFrame:
    """Rebuild the columns `cluster_events` needs from the exported GeoJSON.

    The CSV this GeoJSON was exported from lives in the gitignored
    data_pipeline/output/, so the GeoJSON is the only committed copy and
    therefore the reproducible input.
    """
    with SOURCE_JSON.open(encoding="utf-8") as handle:
        by_date: dict[str, dict[str, Any]] = json.load(handle)

    rows = []
    for collection in by_date.values():
        for feature in collection["features"]:
            lon, lat = feature["geometry"]["coordinates"]
            props = feature["properties"]
            # Low confidence detections are more often flares or sensor noise
            # than fires; the console's raw FIRMS layer drops them too, so
            # keeping them here would make the two views disagree.
            if props["confidence"] == "low":
                continue
            acquired = datetime.fromisoformat(props["acquiredAt"])
            rows.append(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "acq_date": acquired.strftime("%Y-%m-%d"),
                    "acq_time": acquired.hour * 100 + acquired.minute,
                    "frp": props["frp"],
                    "confidence": props["confidence"],
                }
            )
    return pd.DataFrame(rows)


def event_summary(event: FireEvent, triage: Stage1TriageResult) -> dict[str, Any]:
    """List-view shape: what the Historical Fire Register table needs (§11).

    Deliberately excludes the rule-by-rule breakdown and evidence objects --
    those belong to the single-event view, and carrying them per row would
    make the list response an order of magnitude larger for data no table
    column shows.
    """
    lat, lon = event.centroid
    summary = {
        "eventId": event.event_id,
        "auditId": AUDIT_ID,
        "firstDetection": event.first_detection,
        "lastDetection": event.last_detection,
        "durationHours": round(event.duration_hours, 2),
        "observationCount": event.observation_count,
        "centroid": {"lat": lat, "lon": lon},
        "bbox": list(event.bbox),
        "spatialExtentKm": round(event.spatial_extent_km, 3),
        "maxFrp": event.max_frp,
        "meanFrp": round(event.mean_frp, 2) if event.mean_frp is not None else None,
        "triage": {
            "state": triage.state.value,
            "fireSupportScore": triage.fire_support_score,
            "nonFireSupportScore": triage.non_fire_support_score,
            "requiresAiReview": triage.requires_ai_review,
            "deeperInvestigationEligible": triage.deeper_investigation_eligible,
            "decisiveRuleIds": triage.decisive_rule_ids,
            "decisionReasons": triage.decision_reasons,
            "budgetReason": triage.budget_reason,
            "algorithmVersion": triage.algorithm_version,
        },
    }
    # The static 2019 export carries no satellite/instrument column, so sensor
    # mix is unknown rather than empty. Emitting `[]` would let the console
    # render "no sensors" over real detections; an absent key cannot.
    if event.sensor_mix:
        summary["sensorMix"] = event.sensor_mix
    return summary


def main() -> None:
    observations = load_observations()
    print(f"==> {len(observations):,} usable detections from {SOURCE_JSON.name}")

    events, _annotated = cluster_events(observations)
    print(f"==> {len(events):,} FireEvents after clustering")

    triage_results = triage_events(events, observations)
    summary = summarize_triage(triage_results)
    print(f"==> triage states: {summary.state_counts}")

    by_id = {result.event_id: result for result in triage_results}
    artifact = {
        # Deliberately no `generatedAt`: the triage detail already carries the
        # engine's own `evaluated_at`/`retrieved_at` stamps, and the source
        # window plus algorithmVersion answer "what is this and how was it
        # derived". When the export ran adds nothing.
        # Provenance, so a reader of the artifact alone can tell what it is
        # and that the observations behind it are real.
        "source": {
            "dataset": "NASA FIRMS VIIRS/MODIS",
            "window": "2019-09-01..2019-09-05",
            "region": "Sumatra / Kalimantan",
            "file": str(SOURCE_JSON.relative_to(REPO_ROOT)),
            "observationsUsed": len(observations),
            "excluded": "low-confidence detections",
            "note": "Real observations. Clustering and Stage-1 triage are derived, not observed.",
        },
        "audits": {
            AUDIT_ID: {
                "scope": {
                    **SCOPE,
                    "eventCount": len(events),
                    "reviewQueueCount": summary.review_queue_count,
                    "compression": summary.events_to_review_queue_compression,
                },
                "events": [event_summary(e, by_id[e.event_id]) for e in events],
            }
        },
    }
    triage_detail = {
        AUDIT_ID: {result.event_id: result.to_dict() for result in triage_results}
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path, payload in ((DEST_EVENTS, artifact), (DEST_TRIAGE, triage_detail)):
        # Compact and gzipped: 23 MB of highly repetitive JSON becomes 850 KB,
        # which is the difference between something that can live in git
        # history and ride into the Lambda bundle and something that cannot.
        # mtime=0 keeps gzip's own header out of the diff.
        #
        # The payload is still not byte-reproducible: `triage_events` stamps
        # every evidence object with its retrieval time, so re-running this
        # rewrites both files whether or not any derived value changed. That
        # is why the artifacts are committed rather than built in CI -- a CI
        # build would churn the Lambda bundle's source_code_hash on every run.
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        with gzip.GzipFile(path, "wb", mtime=0) as handle:
            handle.write(body)
        print(f"==> wrote {path.relative_to(REPO_ROOT)} ({path.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    main()
