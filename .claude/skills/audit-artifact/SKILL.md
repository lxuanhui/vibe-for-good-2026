---
name: audit-artifact
description: Regenerate, inspect or measure the committed pipeline artifact backend/app/data/audit_events.json.gz that GET /api/audits/{id}/events serves. Use when changing anything in data_pipeline/ that feeds the export (clustering, Stage-1, complexity, priority), when a number on the console needs checking against the data, or before claiming any compression or workload figure. Covers the offline venv, determinism caveats, the sanity numbers, and what the artifact structurally cannot show.
---

# The audit artifact

`GET /api/audits/{audit_id}/events` does not compute anything. It serves
`backend/app/data/audit_events.json.gz` (summaries) and
`audit_triage_detail.json.gz` (per-event rules and evidence), both written
offline by `data_pipeline/export_audit_events.py` from the one real
observation file in the repo, `frontend/public/pipeline/firms-2019-09.json`.
The decision log entry "Clustering runs offline" says why: scipy and pandas
would take the Lambda bundle to its limit, and the derivation is identical
for every caller.

So any change to clustering, triage, complexity or priority reaches the
product only when someone re-runs the export and commits the result. This
skill is that procedure, plus the checks that stop a bad artifact landing.

**This may stop being the only path.** PR #78 adds a Flask history adapter
that runs the same pipeline in-request, and #89 decides whether that ships
(zip, Lambda container image, or EC2). If it does, the artifact becomes the
demo fallback rather than the source of truth — but the sanity numbers and
the structural limits below still hold, because they are properties of the
data and the rules, not of where the code runs.

## Running the export

The pipeline is not part of the backend venv. It needs its own:

```bash
uv venv .venv && uv pip install --python .venv -r data_pipeline/requirements.txt pytest
PYTHONPATH=. .venv/bin/python -m data_pipeline.export_audit_events
PYTHONPATH=. .venv/bin/python -m pytest data_pipeline/tests -q
cd backend && .venv/bin/pytest -q     # the API tests read the artifact
```

`PYTHONPATH=.` is required — `data_pipeline` is not installed as a package,
and the `ModuleNotFoundError` without it is the first thing every fresh
session hits. A repo-root `.venv/` is gitignored; `backend/.venv` is a
different, thinner environment that cannot run the pipeline.

## Determinism — read before committing a regenerated artifact

The export writes gzip with `mtime=0`, so the bytes depend only on content.
The content is *not* stable across runs: Stage-1's `evaluated_at` and each
evidence item's `retrieved_at` are stamped at run time, so a regenerated
artifact always diffs even when nothing changed. Therefore:

- Regenerate only when the derivation changed. Never as a side effect of
  an unrelated PR.
- Say in the PR which module changed and what the count deltas are. A diff
  of a 600 KB gzipped file tells the reviewer nothing; the numbers below do.
- If the counts moved and you did not expect them to, that is the finding.
  Stop and work out why before committing.

## Sanity numbers for the 2019 demo scope

These are what `demo-2019-haze` produces at the current algorithm versions
(`stage1-rules-v1`). A regenerated artifact that departs from them without a
deliberate change is wrong.

| Measure | Value |
|---|---|
| Observations used | 20,471 |
| FireEvents | 3,610 (5.7×) |
| Singletons | 1,768 (49%) |
| Events ≥100 observations | 22, holding 6,485 observations (32%) |
| Largest event | `FE-20190901-392b394abd`: 1,103 obs, 107 h, 20.5 km |
| LIKELY_FIRE / AMBIGUOUS / LIKELY_NON_FIRE | 396 / 3,214 / 0 |
| Max FRP ≥20 MW | 582 |
| `fireSpreadEdges` (demo scope, 16 in-scope+buffer events) | 82 candidate edges, 59 with a real wind-oriented envelope |

Recompute them in a few lines rather than trusting this table:

```python
import gzip, json
from collections import Counter
d = json.load(gzip.open("backend/app/data/audit_events.json.gz"))
ev = d["audits"]["demo-2019-haze"]["events"]
print(len(ev), sum(e["observationCount"] for e in ev))
print(Counter(e["triage"]["state"] for e in ev))
print(Counter(e["triage"]["fireSupportScore"] for e in ev))
```

## What the artifact cannot show you

**Stage-1 compression is 1.0× by construction, not by accident.** On
FIRMS-only input the highest non-fire score any event can reach is 2
(singleton +1, FRP ≤2 MW +1) against a threshold of 4. Only a persistent
heat source or a volcano within 3 km (+5 each) flips an event alone. And
adding context would *widen* LIKELY_FIRE (the vegetated and dry-rainfall
rules would promote ~979 AMBIGUOUS events) while the queue stays at 3,610,
because LIKELY_FIRE and AMBIGUOUS both remain in review. Do not tune
thresholds to manufacture a reduction; do not write UI copy implying
missing context would shrink the queue. Decision log, 2026-09-08.

**Compression lives in scope.** A 30×30 km unit plus 10 km buffer at the
densest cell holds 80 events (2.2%). Measure scope compression against a
boundary; without one, report "not measurable", never 1.0×.

**The workload benchmark does not run here.** `data_pipeline.benchmark.report`
fetches FIRMS live and 400s on an empty key; its numbers also would not
reconcile with the artifact. #83 tracks pointing it at the artifact.

## Adding a derived field to the artifact

1. Run the module in `export_audit_events.py` after Stage-1, per event.
   Summary fields go on the event; anything bulky (components, evidence
   lists) goes in the detail artifact next to `triageDetail`, fetched lazily
   by `GET /audits/{id}/events/{eventId}`.
2. Extend `AuditEvent` in `frontend/src/api/types.ts` — never `FireEvent`.
   Widening `FireEvent` with optionals would make a real event and a fixture
   indistinguishable to the compiler (PR #79).
3. Modules that score with missing inputs must say so in the output.
   `compute_investigation_priority` already does (`evidence_coverage`,
   `NOT_EVALUATED` factors); surface that, don't hide it.
4. Text describing the field follows `evidence-framing`. A priority score is
   review routing; the module's `_FORBIDDEN_KEYS` is the boundary.
5. Add the new sanity number to the table above.
