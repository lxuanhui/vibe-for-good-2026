"""Concurrency behaviour for the audit session store.

Both backends are exercised by the same test bodies. That is the point of the
parametrisation rather than tidiness: #146's acceptance criteria ask that the
local in-memory store and the DynamoDB store *agree on the semantics*, and the
only way to mean that is to run one set of assertions against both. A memory
store that serialised writers behind a lock would pass a test written for it
and still be a different contract from the deployed one.
"""

import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from typing import ClassVar

import pytest

from app import audit_store

AUDIT = "audit-1"


class ConditionalCheckFailed(Exception):
    response: ClassVar[dict[str, dict[str, str]]] = {
        "Error": {"Code": "ConditionalCheckFailedException"}
    }


class ProvisionedThroughputExceeded(Exception):
    """A DynamoDB error that is *not* a lost optimistic lock."""

    response: ClassVar[dict[str, dict[str, str]]] = {
        "Error": {"Code": "ProvisionedThroughputExceededException"}
    }


class FakeAuditStateTable:
    """Enough DynamoDB conditional-write behaviour to exercise a collision."""

    def __init__(self):
        self.item = None
        self.lock = Lock()
        self.writes = 0

    def get_item(self, *, Key):
        del Key
        with self.lock:
            return {"Item": copy.deepcopy(self.item)} if self.item else {}

    def put_item(self, *, Item, **kwargs):
        with self.lock:
            self.writes += 1
            condition = kwargs.get("ConditionExpression", "")
            if "attribute_not_exists(audit_id)" in condition:
                if self.item is not None:
                    raise ConditionalCheckFailed()
            elif re.search(r"#revision = :revision", condition):
                expected = kwargs["ExpressionAttributeValues"][":revision"]
                actual = self.item.get("revision") if self.item else None
                if actual is not None and actual != expected:
                    raise ConditionalCheckFailed()
            self.item = copy.deepcopy(Item)


@pytest.fixture(params=["memory", "dynamodb"])
def backend(request, monkeypatch):
    """Run a test body against whichever store the environment would give it."""
    audit_store._MEMORY.clear()
    if request.param == "memory":
        monkeypatch.setattr(audit_store, "_table", lambda: None)
        yield lambda: json.loads(audit_store._MEMORY[AUDIT]["state"]) if AUDIT in audit_store._MEMORY else None
    else:
        table = FakeAuditStateTable()
        monkeypatch.setattr(audit_store, "_table", lambda: table)
        yield lambda: json.loads(table.item["state"]) if table.item else None
    audit_store._MEMORY.clear()


def overlap_reads(monkeypatch, count: int) -> None:
    """Hold the first `count` readers until they have all read.

    Without this the writers almost always run one after another and the
    conditional write never has anything to collide with -- the test would
    pass against a store with no concurrency control at all.
    """
    barrier = Barrier(count)
    remaining = {"count": count}
    lock = Lock()
    original = audit_store._read_item

    def read(audit_id: str):
        item = original(audit_id)
        with lock:
            wait = remaining["count"] > 0
            if wait:
                remaining["count"] -= 1
        if wait:
            barrier.wait(timeout=5)
        return item

    monkeypatch.setattr(audit_store, "_read_item", read)


def entry(event_id: str, added_at: str) -> dict:
    return {"eventId": event_id, "note": "", "disposition": "", "addedAt": added_at}


def test_overlapping_pack_additions_retry_and_keep_every_selected_event(backend, monkeypatch):
    """Two Lambda requests can read the same session, then must both persist."""
    audit_store.create({"audit_id": AUDIT, "_pack": {}})
    overlap_reads(monkeypatch, 2)
    entries = [
        entry("FE-20190901-f0d0bb0675", "2019-09-01T00:00:00Z"),
        entry("FE-20190904-0fb85076c0", "2019-09-04T00:00:00Z"),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda item: audit_store.add_pack_entry(AUDIT, item), entries))

    assert set(backend()["_pack"]) == {item["eventId"] for item in entries}


def test_a_scope_write_landing_mid_pack_edit_does_not_drop_the_pack_entry(backend, monkeypatch):
    """The gap #183 left open: scope setup used to overwrite the whole blob.

    Re-uploading a boundary or rebuilding history is a session write like any
    other. It used to be an unconditional put, so landing between another
    writer's read and its write silently discarded that writer's change --
    a pack entry, or a completed assessment.
    """
    audit_store.create({"audit_id": AUDIT, "status": "SCOPE_READY", "_pack": {}})
    overlap_reads(monkeypatch, 2)

    def rebuild_history():
        audit_store.update(AUDIT, lambda session: session.update({"status": "HISTORY_BUILD_READY"}))

    def select_event():
        audit_store.add_pack_entry(AUDIT, entry("FE-20190901-f0d0bb0675", "2019-09-01T00:00:00Z"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        for future in [executor.submit(rebuild_history), executor.submit(select_event)]:
            future.result()

    persisted = backend()
    assert persisted["status"] == "HISTORY_BUILD_READY"
    assert "FE-20190901-f0d0bb0675" in persisted["_pack"]


def test_an_analysis_result_and_a_pack_edit_both_survive(backend, monkeypatch):
    """The race the issue was filed for: worker versus API, one item."""
    audit_store.create({"audit_id": AUDIT, "_pack": {}})
    overlap_reads(monkeypatch, 2)
    analysis = {"FE-20190901-f0d0bb0675": {"event_id": "FE-20190901-f0d0bb0675"}}

    with ThreadPoolExecutor(max_workers=2) as executor:
        for future in [
            executor.submit(audit_store.update_analysis, AUDIT, analysis),
            executor.submit(
                audit_store.add_pack_entry, AUDIT, entry("FE-20190904-0fb85076c0", "2019-09-04T00:00:00Z")
            ),
        ]:
            future.result()

    persisted = backend()
    assert persisted["_analysis"] == analysis
    assert "FE-20190904-0fb85076c0" in persisted["_pack"]


def test_create_refuses_to_overwrite_a_live_session(backend):
    """An id collision is a bug elsewhere; overwriting would discard a scope."""
    audit_store.create({"audit_id": AUDIT, "status": "SCOPE_READY", "_pack": {"FE-1": {}}})

    with pytest.raises(audit_store.RevisionConflict):
        audit_store.create({"audit_id": AUDIT, "status": "AWAITING_SCOPE"})

    assert backend()["_pack"] == {"FE-1": {}}


def test_updating_a_session_that_does_not_exist_reports_absence(backend):
    """404 is the caller's answer to give, not a row this layer invents."""
    assert audit_store.update("audit-missing", lambda session: session.update({"a": 1})) is None
    assert backend() is None


def test_a_job_row_is_created_on_first_write_and_merged_after(backend):
    """`create_if_missing` is the job state machine's first transition."""
    audit_store.update(AUDIT, lambda row: row.update({"jobStatus": "RUNNING"}), create_if_missing=True)
    audit_store.update(AUDIT, lambda row: row.update({"jobStatus": "COMPLETE"}), create_if_missing=True)

    assert backend() == {"jobStatus": "COMPLETE"}


def test_a_write_that_never_wins_fails_loudly_rather_than_silently(backend, monkeypatch):
    """Exhausting the retries raises. A silent drop is the bug being fixed."""
    audit_store.create({"audit_id": AUDIT, "_pack": {}})
    monkeypatch.setattr(
        audit_store,
        "_write_item",
        lambda *args, **kwargs: (_ for _ in ()).throw(audit_store.RevisionConflict(AUDIT)),
    )

    with pytest.raises(RuntimeError, match="changed too frequently"):
        audit_store.add_pack_entry(AUDIT, entry("FE-20190901-f0d0bb0675", "2019-09-01T00:00:00Z"))


def test_a_session_written_before_revisions_existed_still_mutates(monkeypatch):
    """Items predating the revision attribute migrate on first write.

    DynamoDB only: the memory store is empty on every cold start, so there is
    no legacy item there to migrate.
    """
    table = FakeAuditStateTable()
    monkeypatch.setattr(audit_store, "_table", lambda: table)
    table.item = {"audit_id": AUDIT, "state": json.dumps({"audit_id": AUDIT, "_pack": {}})}

    audit_store.add_pack_entry(AUDIT, entry("FE-20190901-f0d0bb0675", "2019-09-01T00:00:00Z"))

    assert table.item["revision"] == 1
    assert "FE-20190901-f0d0bb0675" in json.loads(table.item["state"])["_pack"]


def test_a_throughput_error_is_raised_rather_than_retried_as_a_collision(monkeypatch):
    """The retry is for a lost optimistic lock only, not for every failure."""
    table = FakeAuditStateTable()
    monkeypatch.setattr(audit_store, "_table", lambda: table)
    audit_store.create({"audit_id": AUDIT, "_pack": {}})

    def throttle(**kwargs):
        raise ProvisionedThroughputExceeded()

    monkeypatch.setattr(table, "put_item", throttle)

    with pytest.raises(ProvisionedThroughputExceeded):
        audit_store.add_pack_entry(AUDIT, entry("FE-20190901-f0d0bb0675", "2019-09-01T00:00:00Z"))
