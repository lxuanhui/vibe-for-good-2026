"""Concurrency behaviour for the DynamoDB-backed audit session."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from typing import ClassVar

from app import audit_store


class ConditionalCheckFailed(Exception):
    response: ClassVar[dict[str, dict[str, str]]] = {
        "Error": {"Code": "ConditionalCheckFailedException"}
    }


class FakeAuditStateTable:
    """Enough DynamoDB conditional-write behaviour to exercise a collision."""

    def __init__(self):
        self.item = None
        self.lock = Lock()
        self.initial_read_barrier = None
        self.initial_reads_remaining = 0

    def get_item(self, *, Key):
        del Key
        with self.lock:
            wait = self.initial_reads_remaining > 0
            if wait:
                self.initial_reads_remaining -= 1
            item = copy.deepcopy(self.item)
        if wait:
            assert self.initial_read_barrier is not None
            self.initial_read_barrier.wait(timeout=2)
        return {"Item": item} if item else {}

    def put_item(self, *, Item, **kwargs):
        with self.lock:
            if kwargs.get("ConditionExpression"):
                expected = kwargs["ExpressionAttributeValues"][":revision"]
                actual = self.item.get("revision") if self.item else None
                if actual is not None and actual != expected:
                    raise ConditionalCheckFailed()
            self.item = copy.deepcopy(Item)


def test_overlapping_pack_additions_retry_and_keep_every_selected_event(monkeypatch):
    """Two Lambda requests can read the same session, then must both persist."""
    table = FakeAuditStateTable()
    monkeypatch.setattr(audit_store, "_table", lambda: table)
    audit_store.put({"audit_id": "audit-1", "_pack": {}})

    table.initial_read_barrier = Barrier(2)
    table.initial_reads_remaining = 2
    entries = [
        {
            "eventId": "FE-20190901-f0d0bb0675",
            "note": "",
            "disposition": "",
            "addedAt": "2019-09-01T00:00:00Z",
        },
        {
            "eventId": "FE-20190904-0fb85076c0",
            "note": "",
            "disposition": "",
            "addedAt": "2019-09-04T00:00:00Z",
        },
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda entry: audit_store.add_pack_entry("audit-1", entry), entries))

    persisted = json.loads(table.item["state"])["_pack"]
    assert set(persisted) == {entry["eventId"] for entry in entries}
