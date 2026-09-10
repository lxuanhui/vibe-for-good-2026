"""Small durable store for audit sessions and evidence-pack selections.

Local development deliberately uses memory.  Lambda uses the DynamoDB table
declared in ``infra/api.tf``; storing JSON keeps the private GeoJSON intact
without inventing a second scope representation or changing FireEvent data.
"""

from __future__ import annotations

import json
import os
from typing import Any

_MEMORY: dict[str, dict[str, Any]] = {}


def _table_name() -> str | None:
    return os.environ.get("AUDIT_STATE_TABLE") or None


def _table():
    """Import boto3 only in the deployed configuration.

    boto3 is supplied by the Lambda Python runtime but is intentionally not a
    local development dependency.
    """
    name = _table_name()
    if not name:
        return None
    import boto3  # type: ignore[import-not-found]

    return boto3.resource("dynamodb").Table(name)


def get(audit_id: str) -> dict[str, Any] | None:
    table = _table()
    if table is None:
        value = _MEMORY.get(audit_id)
        return dict(value) if value else None
    item = table.get_item(Key={"audit_id": audit_id}).get("Item")
    return json.loads(item["state"]) if item else None


def put(session: dict[str, Any]) -> None:
    table = _table()
    if table is None:
        _MEMORY[session["audit_id"]] = dict(session)
        return
    # Preserve the revision even for the scope/history writes that predate
    # pack selection. Otherwise one of those writes could remove the revision
    # between a pack read and its conditional write, making a stale selection
    # look safe to persist.
    existing = table.get_item(Key={"audit_id": session["audit_id"]}).get("Item")
    revision = int(existing.get("revision", 0)) if existing else 0
    table.put_item(
        Item={
            "audit_id": session["audit_id"],
            "state": json.dumps(session),
            "revision": revision + 1,
        }
    )


def _conditional_failure(error: Exception) -> bool:
    """Keep the retry narrowly scoped to DynamoDB's optimistic-lock miss."""
    response = getattr(error, "response", {})
    return (
        isinstance(response, dict)
        and response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"
    )


def _update_session(audit_id: str, mutate) -> dict[str, Any] | None:
    """Apply a session mutation without letting another Lambda erase it.

    Pack selections share a DynamoDB item with the audit scope and analysis.
    A plain read/modify/write loses a selection whenever two requests read the
    same item before either writes.  The revision is deliberately stored beside
    the JSON blob so existing sessions with no revision migrate on their first
    mutation.
    """
    table = _table()
    if table is None:
        session = _MEMORY.get(audit_id)
        if session is None:
            return None
        updated = dict(session)
        mutate(updated)
        _MEMORY[audit_id] = updated
        return updated

    for _ in range(8):
        item = table.get_item(Key={"audit_id": audit_id}).get("Item")
        if item is None:
            return None
        session = json.loads(item["state"])
        mutate(session)
        revision = int(item.get("revision", 0))
        try:
            table.put_item(
                Item={"audit_id": audit_id, "state": json.dumps(session), "revision": revision + 1},
                ConditionExpression="attribute_not_exists(#revision) OR #revision = :revision",
                ExpressionAttributeNames={"#revision": "revision"},
                ExpressionAttributeValues={":revision": revision},
            )
            return session
        except Exception as error:
            if not _conditional_failure(error):
                raise
    raise RuntimeError("Audit session changed too frequently to persist the pack selection")


def add_pack_entry(audit_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Merge one selected FireEvent into the engagement pack atomically."""
    event_id = entry["eventId"]

    def mutate(session: dict[str, Any]) -> None:
        pack = session.setdefault("_pack", {})
        existing = pack.get(event_id, {})
        pack[event_id] = {**entry, "addedAt": existing.get("addedAt", entry["addedAt"])}

    session = _update_session(audit_id, mutate)
    return None if session is None else session["_pack"][event_id]


def remove_pack_entry(audit_id: str, event_id: str) -> bool | None:
    def mutate(session: dict[str, Any]) -> None:
        session.setdefault("_pack", {}).pop(event_id, None)

    return None if _update_session(audit_id, mutate) is None else True


def pack(audit_id: str) -> dict[str, dict[str, Any]]:
    return dict((get(audit_id) or {}).get("_pack", {}))


def update_analysis(audit_id: str, analyses: dict[str, dict[str, Any]]) -> None:
    _update_session(audit_id, lambda session: session.__setitem__("_analysis", analyses))


def analyses(audit_id: str) -> dict[str, dict[str, Any]]:
    return dict((get(audit_id) or {}).get("_analysis", {}))
