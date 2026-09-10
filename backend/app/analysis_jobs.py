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
import secrets
from datetime import UTC, datetime
from typing import Any

from data_pipeline.analysis.investigator_skeptic import AnalysisPhase

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

# What a poll sees while the work runs. A two-round assessment is near a
# minute, and a disabled button for that long is indistinguishable from a
# hung one (#198); the stage is the honest alternative to a fake progress
# bar. Text a console user reads, so it follows the ui-copy skill.
STARTING_STAGE = "Starting"
PHASE_LABELS = {
    AnalysisPhase.INDEPENDENT_ASSESSMENT: "independent assessment",
    AnalysisPhase.REBUTTAL: "rebuttal",
    AnalysisPhase.FINAL_ASSESSMENT: "final assessment",
}


def stage_label(round_number: int, total_rounds: int, phase: AnalysisPhase) -> str:
    return f"Round {round_number} of {total_rounds}: {PHASE_LABELS[phase]}"


def job_key(audit_id: str, event_id: str) -> str:
    return f"job#{audit_id}#{event_id}"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _envelope(record: dict[str, Any]) -> dict[str, Any]:
    # audit_id is the storage key, not part of the API contract.
    return {key: value for key, value in record.items() if key != "audit_id"}


class JobSuperseded(Exception):
    """The row now belongs to a later job; this writer's job was re-dispatched."""


class _JobAlreadyRunning(Exception):
    """Raised inside the claim's mutate to abandon the write without touching the row."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("jobId"))
        self.record = record


def _write(
    audit_id: str, event_id: str, *, job_id: str | None = None, **fields: Any
) -> dict[str, Any]:
    """Replace the job row, keeping the fields an earlier transition set.

    Conditional, like every other write to this store (#146). The API
    function writes RUNNING here and the worker writes the terminal status,
    and while the normal order is sequential, a re-dispatched stale job puts
    two writers on one row. The revision check alone does not settle that:
    `audit_store.update` re-reads and re-applies the mutation when it loses,
    so a dead worker's late COMPLETE would still land on the new job's row.
    A writer that names its `job_id` therefore gets `JobSuperseded` instead
    of a write once the row belongs to a different job.
    """
    key = job_key(audit_id, event_id)

    def mutate(record: dict[str, Any]) -> None:
        if job_id is not None and record.get("jobId") != job_id:
            raise JobSuperseded(key)
        record.update({"audit_id": key, "auditId": audit_id, "eventId": event_id, **fields})

    record = audit_store.update(key, mutate, create_if_missing=True)
    if record is None:
        # Unreachable: `create_if_missing` returns None only for an absent
        # item, which it has just created. Stated as a raise rather than an
        # `assert` because asserts are stripped under -O, and this narrows the
        # type for the line below -- silently passing None on would surface as
        # a confusing envelope failure instead of the invariant that broke.
        raise RuntimeError(f"Audit store returned no row for job {key}")
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


def claim(audit_id: str, event_id: str) -> tuple[dict[str, Any], bool]:
    """Take the job for this event, or learn who already has it.

    Returns the envelope and whether this caller now owns the work. The
    decision is made inside the store's compare-and-set: the mutation sees
    the row as it was just read, and if it loses the write it is re-run
    against the winner's row, where it finds the RUNNING job and gives up
    without writing (#189). A read followed by `start` had a window between
    the two in which a second request could also read NOT_RUN, and each
    then billed the same two rounds.

    A stale RUNNING row is claimable: its worker has been dead longer than
    Lambda allows a function to live. The new `jobId` is what stops that
    worker's terminal write, should it somehow arrive, landing on this job.
    """
    key = job_key(audit_id, event_id)
    job_id = secrets.token_urlsafe(8)

    def mutate(record: dict[str, Any]) -> None:
        if record.get("jobStatus") == RUNNING and not _is_stale(record):
            raise _JobAlreadyRunning(dict(record))
        record.update(
            {
                "audit_id": key,
                "auditId": audit_id,
                "eventId": event_id,
                "jobId": job_id,
                "jobStatus": RUNNING,
                "stage": STARTING_STAGE,
                "startedAt": _now(),
                "pollAfterSeconds": POLL_AFTER_SECONDS,
                "completedAt": None,
                "error": None,
                "analysis": None,
            }
        )

    try:
        record = audit_store.update(key, mutate, create_if_missing=True)
    except _JobAlreadyRunning as running:
        return _envelope(running.record), False
    if record is None:
        # Unreachable, as in `_write`; raised rather than asserted for the
        # same reason.
        raise RuntimeError(f"Audit store returned no row for job {key}")
    return _envelope(record), True


def complete(
    audit_id: str, event_id: str, analysis: dict[str, Any], *, job_id: str | None = None
) -> dict[str, Any]:
    return _write(
        audit_id,
        event_id,
        job_id=job_id,
        jobStatus=COMPLETE,
        stage=None,
        completedAt=_now(),
        analysis=analysis,
        error=None,
    )


def fail(audit_id: str, event_id: str, message: str, *, job_id: str | None = None) -> dict[str, Any]:
    return _write(
        audit_id,
        event_id,
        job_id=job_id,
        jobStatus=FAILED,
        stage=None,
        completedAt=_now(),
        error=message,
        analysis=None,
    )


def run(
    audit_id: str, event_id: str, *, provider: Any = None, job_id: str | None = None
) -> dict[str, Any]:
    """Do the work and record the outcome.

    Called in the worker Lambda, or inline where no worker is configured.
    Every exit path writes a terminal job status: the worker has no caller to
    raise to, and an unrecorded crash reads as an assessment that is still
    being prepared.

    `job_id` is the claim this worker is running under. When the row has
    since been re-claimed (the job was judged stale and dispatched again),
    the outcome is dropped rather than written over the newer job: the
    assessment is already persisted on the session by `analyse_event`, so
    nothing is lost but this row's say in it. None, which an invocation
    queued before this field existed would send, writes unconditionally.
    """

    def record_stage(round_number: int, total_rounds: int, phase: AnalysisPhase) -> None:
        # A progress note must never cost the assessment: if the store
        # refuses the write, the rounds still run and the outcome still lands.
        try:
            _write(audit_id, event_id, job_id=job_id, stage=stage_label(round_number, total_rounds, phase))
        except JobSuperseded:
            logger.warning("Job %s was re-dispatched; not recording a stage for the old run", job_key(audit_id, event_id))
        except Exception:
            logger.warning("Could not record stage for job %s", job_key(audit_id, event_id), exc_info=True)

    try:
        try:
            analysis = audit_events.analyse_event(
                audit_id, event_id, investigator=provider, skeptic=provider, on_round=record_stage
            )
        except AnalysisProviderUnavailable as exc:
            return fail(audit_id, event_id, str(exc), job_id=job_id)
        except (TypeError, ValueError) as exc:
            # The pipeline rejected malformed provider output or an evidence
            # reference the pack does not contain. `analyse_event` persists
            # only a fully validated result, so nothing partial survives this.
            return fail(audit_id, event_id, f"Structured analysis was rejected: {exc}", job_id=job_id)
        except Exception:
            # Broad on purpose: the worker has no caller, so an unhandled type
            # here would surface only as a job stuck at RUNNING forever.
            logger.exception("Analysis job %s failed", job_key(audit_id, event_id))
            return fail(audit_id, event_id, "Investigation analysis failed unexpectedly.", job_id=job_id)
        if analysis is None:
            return fail(audit_id, event_id, f"No evidence for event {event_id} in audit {audit_id}", job_id=job_id)
        return complete(audit_id, event_id, analysis, job_id=job_id)
    except JobSuperseded:
        logger.warning("Job %s was re-dispatched while this run was in flight; its outcome is not recorded", job_key(audit_id, event_id))
        return read(audit_id, event_id)


def _invoke_worker(function_name: str, audit_id: str, event_id: str, job_id: str) -> None:
    import boto3  # Lambda supplies boto3; local runs never reach this branch.

    boto3.client("lambda").invoke(
        FunctionName=function_name,
        # 'Event' is what takes the work off the request path: Lambda queues
        # the invocation and returns immediately, and the worker then has its
        # own timeout budget rather than API Gateway's 30s.
        InvocationType="Event",
        Payload=json.dumps({"auditId": audit_id, "eventId": event_id, "jobId": job_id}).encode(),
    )


def dispatch(audit_id: str, event_id: str, *, provider: Any = None) -> dict[str, Any] | None:
    """Start analysis, or return the job already running for this event.

    None means there is no evidence to analyse -- the caller answers 404
    rather than recording a job that could never have succeeded.
    """
    if audit_events.analysis_evidence(audit_id, event_id) is None:
        return None

    job, owned = claim(audit_id, event_id)
    if not owned:
        # Idempotent under a double press or a retry. A second job would run
        # the same two rounds and bill a second time for the same result.
        return job
    worker = os.environ.get("ANALYSIS_WORKER_FUNCTION")
    if not worker:
        # Local development and tests have no second function to invoke and
        # no 30s cap to fit under. Running inline keeps the endpoint honest
        # rather than reporting RUNNING for work nothing will ever perform.
        return run(audit_id, event_id, provider=provider, job_id=job["jobId"])
    try:
        _invoke_worker(worker, audit_id, event_id, job["jobId"])
    except Exception:
        # boto3 raises several unrelated types for an invoke that never left
        # the ground; all of them mean the same thing to the auditor.
        logger.exception("Could not invoke analysis worker %s", worker)
        return fail(audit_id, event_id, "Investigation analysis could not be started.", job_id=job["jobId"])
    return job
