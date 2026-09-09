# Cached real-data demo record

The repeatable demo uses `frontend/public/pipeline/firms-2019-09.json`, a
committed NASA FIRMS historical export. The API serves the derived artifact
from `backend/app/data/` so the demo does not depend on live-source
availability.

Current artifact counts:

- 21,519 raw FIRMS observations
- 20,471 FIRMS observations entering deterministic clustering after the low-confidence gate
- 3,610 clustered FireEvents
- 396 events routed to human review; 3,214 remain visible as review-recommended
  after deterministic priority calibration
- scope compression is calculated only after a private audit boundary and context buffer are supplied
- selected events are read from the current audit evidence pack (0 at a fresh
  run, then incremented by actual pack actions)

`POST /api/audits/{audit_id}/history/build` returns `duration_ms` for each
run and labels the source as `cached_real_historical_dataset`. The console
displays that measured value next to the progression; it is a cache/build
handoff timing, not a claim about whole-audit time savings. Optional weather,
peat, imagery, and adversarial analysis remain explicit unavailable states in
this artifact.
Stage-1 classifies fire support; on this FIRMS-only haze-season artifact it is
not expected to remove events. Priority, evidence sufficiency, and human
workflow are separate, and the routing diagnostics expose the component
contributions and escalation reasons behind the human-review count.

Validation smoke record (2026-09-09, local Flask run): the complete
scope-to-report path returned a 293.21 ms cached build handoff. The timing is
machine- and cache-state-specific; it is recorded for demo repeatability, not
as a whole-audit benchmark.
