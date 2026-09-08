"""Standard result shape every normalized `sources/` adapter returns.

Five modules -- `nasa_firms`, `open_meteo`, `nasa_power`, `copernicus_cds`,
`global_peatland_database` -- return a `SourceResult` from their
`fetch_historical_sample()` entry point instead of a bespoke dict (or a bare
`None`), so `run_all.py` can report PASS/FAIL/SKIPPED without knowing
anything about a given source's internals.

`esa_worldcover.py`, `overpass_api.py`, and `sources/future/*` are not part
of this normalization (see issue #2's module checklist) and still print and
return `None`; `run_all.py` treats "ran without raising" as PASS for those,
same as it always has.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


class SourceStatus(str, Enum):
    """Mirrors the PASS / FAIL / SKIPPED labels `run_all.py` prints."""

    OK = "PASS"
    FAILED = "FAIL"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class Provenance:
    """Adapter-level record of the HTTP call(s) behind a result.

    This is not evidence provenance (a FireEvent's claims trace to an
    evidenceId, per `Environmental_Assurance_Spec.md`) -- it's just where
    this feasibility spike's sample data came from and when it was pulled.
    """

    endpoint: str
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    auth: Literal["none", "api_key", "oauth2"] = "none"


@dataclass
class SourceResult:
    """Normalized return value for a `sources/` adapter's
    `fetch_historical_sample()`."""

    source_name: str
    status: SourceStatus
    provenance: Provenance
    limitations: list[str] = field(default_factory=list)
    summary: str = ""
    data: Any = None
    error: str | None = None
