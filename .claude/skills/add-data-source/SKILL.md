---
name: add-data-source
description: Add or modify a data source in data_pipeline/. Use when wiring a new environmental/satellite/weather API into the feasibility spike, when a source moves from "pending account" to live, or when an existing source's historical availability needs re-checking. Covers the module contract, the shared HTTP session, and the negative-result documentation the spike exists to produce.
---

# Adding a data source to the pipeline

`data_pipeline/` is a **feasibility spike**, not the ingestion system. Its job
is to answer one question per source, empirically: *can this be pulled, and
can it be pulled historically?* Nothing writes to a database. Do not add
persistence here — that belongs in the ingestion worker (see `infra/`).

The point of the spike is the **negative results**. A module that only proves
the happy path has done half the job.

## Module contract

Every source is one file in `data_pipeline/sources/` exposing
`fetch_historical_sample() -> None` which prints what it found. Sources still
waiting on an account go in `sources/future/` with the same signature,
returning a "skipped" message until the key is set.

```python
"""<Source name>.

<What it is. What auth it needs. What this module proves empirically
instead of trusting possibly-stale docs.>

Docs: <url>
"""
from __future__ import annotations

from data_pipeline.common.http import SESSION
from data_pipeline.config import HISTORICAL_WINDOW, POINTS

def fetch_historical_sample() -> None:
    print("== <Source name> ==")
    ...
```

## Rules

- **Always use `SESSION`** from `data_pipeline.common.http`. Never `requests`
  directly. It carries request caching (don't hammer free APIs while
  iterating), retries, an explicit User-Agent (Overpass returns 406 for
  `python-requests/x.y`), and `truststore` (NASA FIRMS omits its intermediate
  cert chain and fails OpenSSL verification without it).
- **Query real Indonesian coordinates** from `config.POINTS`, never a country
  centroid — several of these APIs will happily return a national aggregate
  and look like they worked.
- **Test against `config.HISTORICAL_WINDOW`** (the 2019 haze crisis). If the
  archive doesn't reach it, that is the finding.
- **Cross-check a "successful" historical query against a control point** with
  known dense data. Overpass returned HTTP 200 with zero features for every
  `[date:...]` query — a silent fail-closed that looks identical to "no data
  in that area".
- **Write samples to `config.OUTPUT_DIR`** (gitignored), never into the repo.
- Credentials come from `config.py` reading `.env`. Add the new key to both
  `config.py` and `.env.example`; never commit the value.

## Wiring it up

1. Create `sources/<name>.py` (or `sources/future/<name>.py`).
2. Register it in `run_all.py` — `LIVE_SOURCES` or `PENDING_ACCOUNT_SOURCES`.
3. Add a row to the **Sources covered** table in `data_pipeline/README.md`
   with an explicit Historical? verdict: **Confirmed** / **No** / the caveat.
4. Add its cadence to the **Planned cron cadence** table — including "static,
   not pollable" where that is the truth (ESA WorldCover, Global Peatland
   Database).
5. Record anything surprising under **Notes / gotchas**. This section is the
   most valuable part of the module.
6. Run `python -m data_pipeline.sources.<name>`, then
   `python -m data_pipeline.run_all` to confirm the summary still passes.

## Getting pipeline output onto the map

`export_web_geojson.py` is the only path from a pipeline pull to the console:
it converts an `output/` CSV into a static GeoJSON at
`frontend/public/pipeline/`, fetched at runtime rather than bundled. Keep new
exports on that pattern, and keep the file out of the JS bundle — the existing
FIRMS export is already 3.8 MB.
