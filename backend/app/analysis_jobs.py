"""Async job records for the explicit Investigator/Skeptic analysis action.

A two-round assessment measures ~51s against a real evidence pack and a
single round ~30s (docs/decision-log.md, 2026-09-10). API Gateway's HTTP API
caps a response at 30s, so the work does not fit on the request path in any
arrangement of rounds -- and the rounds are the product's adversarial
substance, not a latency dial. `POST .../analyse` therefore records a job and
returns; the work runs in a second Lambda built from the same artifact; `GET`
polls the record.

Job rows live in the existing audit-state table under a namespaced
``job#<audit_id>#<event_id>`` hash key rather than a table of their own. The
key attribute and item shape are identical, so `audit_store` needs no change
and no new service is switched on. They are deliberately *not* nested inside
the audit session, so a slow analysis job never holds up a pack review. Its
completed analysis is attached to the session separately with the store's
revision-checked mutation.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from app import audit_events, audit_store
from app.analysis_provider import AnalysisProviderUnavailable

logger = logging.getLogger(__name__)

NOT_RUN = "NOT_RUN"
RUNNING = "RUNNING"
COMPLETE = "COMPLETE"
FAILED = "FAILED"

# What the console waits between polls. A two-round assessment measures ~51s,
# so a tighter interval spends requests to learn nothing.
POLL_AFTER_SECONDS = 5

# A worker that dies without recording an outcome -- an out-of-memory kill, a
# deploy mid-flight -- would otherwise leave a job RUNNING forever, which the
# console cannot distinguish from slow work and which blocks every retry.
# 900s is Lambda's hard ceiling, so nothing this old is still executing.
STALE_AFTER_SECONDS = 900


def job_key(audit_id: str, event_id: str) -> str:
    return f"job#{audit_id}#{event_id}"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _envelope(record: dict[str, Any]) -> dict[str, Any]:
    # audit_id is the storage key, not part of the API contract.
    return {key: value for key, value in record.items() if key != "audit_id"}


def _write(audit_id: str, event_id: str, **fields: Any) -> dict[str, Any]:
    """Replace the job row, keeping the fields an earlier transition set.

    Conditional, like every other write to this store (#146). The API
    function writes RUNNING here and the worker writes the terminal status,
    and while the normal order is sequential, a re-dispatched stale job puts
    two writers on one row -- so a read/modify/write that ignored the
    revision could drop a recorded outcome.
    """
    key = job_key(audit_id, event_id)

    def mutate(record: dict[str, Any]) -> None:
        record.update({"audit_id": key, "auditId": audit_id, "eventId": event_id, **fields})

    record = audit_store.update(key, mutate, create_if_missing=True)
    assert record is not None  # create_if_missing never returns None
    return _envelope(record)


def _seconds_since(timestamp: Any) -> float | None:
    if not isinstance(timestamp, str):
        return None
    try:
        started = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    return (datetime.now(UTC) - started).total_seconds()


def _is_stale(record: dict[str, Any]) -> bool:
    elapsed = _seconds_since(record.get("startedAt"))
    return elapsed is None or elapsed > STALE_AFTER_SECONDS


def read(audit_id: str, event_id: str) -> dict[str, Any]:
    """The current job envelope. Never spends provider tokens."""
    record = audit_store.get(job_key(audit_id, event_id))
    if record is not None:
        return _envelope(record)
    # An analysis persisted before this endpoint had jobs -- or written
    # straight into the session -- is still a completed assessment. Reporting
    # NOT_RUN for it would invite an auditor to pay for it a second time.
    analysis = audit_events.analysis_for_event(audit_id, event_id)
    if analysis is not None:
        return {"auditId": audit_id, "eventId": event_id, "jobStatus": COMPLETE, "analysis": analysis}
    return {"auditId": audit_id, "eventId": event_id, "jobStatus": NOT_RUN}


def start(audit_id: str, event_id: str) -> dict[str, Any]:
    return _write(
        audit_id,
        event_id,
        jobStatus=RUNNING,
        startedAt=_now(),
        pollAfterSeconds=POLL_AFTER_SECONDS,
        completedAt=None,
        error=None,
        analysis=None,
    )


def complete(audit_id: str, event_id: str, analysis: dict[str, Any]) -> dict[str, Any]:
    return _write(audit_id, event_id, jobStatus=COMPLETE, completedAt=_now(), analysis=analysis, error=None)


def fail(audit_id: str, event_id: str, message: str) -> dict[str, Any]:
    return _write(audit_id, event_id, jobStatus=FAILED, completedAt=_now(), error=message, analysis=None)


def run(audit_id: str, event_id: str, *, provider: Any = None) -> dict[str, Any]:
    """Do the work and record the outcome.

    Called in the worker Lambda, or inline where no worker is configured.
    Every exit path writes a terminal job status: the worker has no caller to
    raise to, and an unrecorded crash reads as an assessment that is still
    being prepared.
    """
    try:
        analysis = audit_events.analyse_event(
            audit_id, event_id, investigator=provider, skeptic=provider
        )
    except AnalysisProviderUnavailable as exc:
        return fail(audit_id, event_id, str(exc))
    except (TypeError, ValueError) as exc:
        # The pipeline rejected malformed provider output or an evidence
        # reference the pack does not contain. `analyse_event` persists only a
        # fully validated result, so nothing partial survives this.
        return fail(audit_id, event_id, f"Structured analysis was rejected: {exc}")
    except Exception:
        # Broad on purpose: the worker has no caller, so an unhandled type
        # here would surface only as a job stuck at RUNNING forever.
        logger.exception("Analysis job %s failed", job_key(audit_id, event_id))
        return fail(audit_id, event_id, "Investigation analysis failed unexpectedly.")
    if analysis is None:
        return fail(audit_id, event_id, f"No evidence for event {event_id} in audit {audit_id}")
    return complete(audit_id, event_id, analysis)


def _invoke_worker(function_name: str, audit_id: str, event_id: str) -> None:
    import boto3  # Lambda supplies boto3; local runs never reach this branch.

    boto3.client("lambda").invoke(
        FunctionName=function_name,
        # 'Event' is what takes the work off the request path: Lambda queues
        # the invocation and returns immediately, and the worker then has its
        # own timeout budget rather than API Gateway's 30s.
        InvocationType="Event",
        Payload=json.dumps({"auditId": audit_id, "eventId": event_id}).encode(),
    )


def dispatch(audit_id: str, event_id: str, *, provider: Any = None) -> dict[str, Any] | None:
    """Start analysis, or return the job already running for this event.

    None means there is no evidence to analyse -- the caller answers 404
    rather than recording a job that could never have succeeded.
    """
    existing = read(audit_id, event_id)
    if existing["jobStatus"] == RUNNING and not _is_stale(existing):
        # Idempotent under a double press or a retry. A second job would run
        # the same two rounds and bill a second time for the same result.
        return existing
    if audit_events.analysis_evidence(audit_id, event_id) is None:
        return None

    job = start(audit_id, event_id)
    worker = os.environ.get("ANALYSIS_WORKER_FUNCTION")
    if not worker:
        # Local development and tests have no second function to invoke and
        # no 30s cap to fit under. Running inline keeps the endpoint honest
        # rather than reporting RUNNING for work nothing will ever perform.
        return run(audit_id, event_id, provider=provider)
    try:
        _invoke_worker(worker, audit_id, event_id)
    except Exception:
        # boto3 raises several unrelated types for an invoke that never left
        # the ground; all of them mean the same thing to the auditor.
        logger.exception("Could not invoke analysis worker %s", worker)
        return fail(audit_id, event_id, "Investigation analysis could not be started.")
    return job
