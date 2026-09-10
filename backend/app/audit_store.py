"""Small durable store for audit sessions and evidence-pack selections.

Local development deliberately uses memory.  Lambda uses the DynamoDB table
declared in ``infra/api.tf``; storing JSON keeps the private GeoJSON intact
without inventing a second scope representation or changing FireEvent data.

Every write here is revision-checked.  There is no unconditional whole-blob
write left to call, because #143 gave this store a second concurrent writer:
the analysis worker runs in its own Lambda while the API function keeps
serving the console, and both touch the same audit session.  A read/modify/
write that does not check the revision it read loses the other writer's
change silently -- no error, no conflict, nothing in the log.  So a caller
picks between two intents: `create` a session that must not already exist, or
`update` one that does.
"""

from __future__ import annotations

import json
import os
from threading import Lock
from typing import Any

# Items are held in the DynamoDB shape even locally -- `{audit_id, state,
# revision}` -- so the two backends run the same code above this line and
# differ only in how they read and compare-and-set one item.
_MEMORY: dict[str, dict[str, Any]] = {}
_MEMORY_LOCK = Lock()

# Enough to clear a burst of contention, few enough to fail loudly rather than
# hold an API Gateway request open. Each attempt is one extra read and write.
MAX_ATTEMPTS = 8


class RevisionConflict(Exception):
    """The item changed between the read and the write."""


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


def _conditional_failure(error: Exception) -> bool:
    """Keep the retry narrowly scoped to DynamoDB's optimistic-lock miss."""
    response = getattr(error, "response", {})
    return (
        isinstance(response, dict)
        and response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"
    )


def _read_item(audit_id: str) -> dict[str, Any] | None:
    table = _table()
    if table is None:
        with _MEMORY_LOCK:
            item = _MEMORY.get(audit_id)
            return dict(item) if item else None
    return table.get_item(Key={"audit_id": audit_id}).get("Item")


def _write_item(audit_id: str, state: dict[str, Any], expected: int | None) -> None:
    """Compare-and-set one item, or raise `RevisionConflict`.

    `expected` is None for a create -- the item must not exist -- and
    otherwise the revision the caller read.  A missing `revision` attribute
    still satisfies the check so sessions written before this store had
    revisions migrate on their first mutation rather than needing a backfill.
    """
    revision = 0 if expected is None else expected + 1
    item = {"audit_id": audit_id, "state": json.dumps(state), "revision": revision}
    table = _table()

    if table is None:
        # The lock covers only the compare-and-set, which is the whole of what
        # DynamoDB's conditional put does atomically. Holding it across the
        # caller's read and mutate instead would serialise every writer, so
        # the retry path would never run locally and the two backends would
        # agree only by never being tested against each other.
        with _MEMORY_LOCK:
            current = _MEMORY.get(audit_id)
            if expected is None:
                if current is not None:
                    raise RevisionConflict(audit_id)
            elif current is None or int(current.get("revision", expected)) != expected:
                raise RevisionConflict(audit_id)
            _MEMORY[audit_id] = item
        return

    if expected is None:
        condition = "attribute_not_exists(audit_id)"
        names = None
        values = None
    else:
        condition = "attribute_not_exists(#revision) OR #revision = :revision"
        names = {"#revision": "revision"}
        values = {":revision": expected}

    kwargs: dict[str, Any] = {"Item": item, "ConditionExpression": condition}
    if names:
        kwargs["ExpressionAttributeNames"] = names
    if values:
        kwargs["ExpressionAttributeValues"] = values
    try:
        table.put_item(**kwargs)
    except Exception as error:
        if _conditional_failure(error):
            raise RevisionConflict(audit_id) from error
        raise


def get(audit_id: str) -> dict[str, Any] | None:
    item = _read_item(audit_id)
    return json.loads(item["state"]) if item else None


def create(session: dict[str, Any]) -> None:
    """Write a session that must not already exist.

    Audit ids are 96 bits of `token_urlsafe`, so a collision here is a bug
    somewhere else -- a retried create, or an id reused deliberately -- and
    overwriting whatever is there would discard a live audit's scope.
    """
    _write_item(session["audit_id"], session, None)


def update(
    audit_id: str, mutate, *, create_if_missing: bool = False
) -> dict[str, Any] | None:
    """Apply a session mutation without letting another Lambda erase it.

    `mutate` is called on the state as it was *just read* and may run more
    than once, so it must be a pure function of the session it is handed.
    Every mutation in this module qualifies: they add, remove or replace one
    key from arguments fixed before the loop starts.

    Returns None when the item does not exist and `create_if_missing` is not
    set -- absence is the caller's answer to give (a 404), not this layer's.
    """
    for _ in range(MAX_ATTEMPTS):
        item = _read_item(audit_id)
        if item is None:
            if not create_if_missing:
                return None
            session: dict[str, Any] = {}
            expected = None
        else:
            session = json.loads(item["state"])
            expected = int(item.get("revision", 0))
        mutate(session)
        try:
            _write_item(audit_id, session, expected)
            return session
        except RevisionConflict:
            continue
    raise RuntimeError(f"Audit session {audit_id} changed too frequently to persist a write")


def add_pack_entry(audit_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Merge one selected FireEvent into the engagement pack atomically."""
    event_id = entry["eventId"]

    def mutate(session: dict[str, Any]) -> None:
        pack = session.setdefault("_pack", {})
        existing = pack.get(event_id, {})
        pack[event_id] = {**entry, "addedAt": existing.get("addedAt", entry["addedAt"])}

    session = update(audit_id, mutate)
    return None if session is None else session["_pack"][event_id]


def remove_pack_entry(audit_id: str, event_id: str) -> bool | None:
    def mutate(session: dict[str, Any]) -> None:
        session.setdefault("_pack", {}).pop(event_id, None)

    return None if update(audit_id, mutate) is None else True


def pack(audit_id: str) -> dict[str, dict[str, Any]]:
    return dict((get(audit_id) or {}).get("_pack", {}))


def update_analysis(audit_id: str, analyses: dict[str, dict[str, Any]]) -> None:
    update(audit_id, lambda session: session.__setitem__("_analysis", analyses))


def analyses(audit_id: str) -> dict[str, dict[str, Any]]:
    return dict((get(audit_id) or {}).get("_analysis", {}))
