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
    table.put_item(Item={"audit_id": session["audit_id"], "state": json.dumps(session)})


def update_pack(audit_id: str, pack: dict[str, dict[str, Any]]) -> None:
    session = get(audit_id)
    if session is None:
        return
    session["_pack"] = pack
    put(session)


def pack(audit_id: str) -> dict[str, dict[str, Any]]:
    return dict((get(audit_id) or {}).get("_pack", {}))


def update_analysis(audit_id: str, analyses: dict[str, dict[str, Any]]) -> None:
    session = get(audit_id)
    if session is None:
        return
    session["_analysis"] = analyses
    put(session)


def analyses(audit_id: str) -> dict[str, dict[str, Any]]:
    return dict((get(audit_id) or {}).get("_analysis", {}))
