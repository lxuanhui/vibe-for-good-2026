# vibe-for-good-2026

AI-driven investigative-efficiency tool for environmental assurance (ACCA
Challenge Statement #1, Vibe For Good 2026). It helps auditors triage
satellite fire detections in Indonesia and reconstruct evidence for human
review.

## The product boundary — read this first

The system does **not** determine blame, guilt, legal responsibility, intent,
or culpability. This is not a tone preference; it is the constraint the whole
architecture is built around. Before writing any user-facing text about a
fire event — report copy, hypothesis labels, agent prompts, UI strings —
load the **`evidence-framing`** skill.

The four layers never collapse into each other: observed evidence → derived
metrics → AI interpretation → human decision. Every AI factual claim traces
to an evidence ID.

## Layout

```
PRODUCT.md      Durable product truth: users, purpose, positioning, the safety
                boundary, and what must not be fabricated. Derived from the
                canonical spec, so the spec still wins on detail
docs/           Decision log, environment facts, and the running cost of every
                AWS service switched on — read before re-deciding anything
frontend/       Vite + React + TS console (MapLibre, Tailwind 4, zustand, recharts)
backend/        Flask API — runs locally via wsgi.py, on Lambda via lambda_handler.py
infra/          Terraform: Lambda + API Gateway HTTP API, applied by CI
data_pipeline/  Clustering, triage, graph, priority and analysis modules — plus
                the original source feasibility spike. Unit-tested; wired to nothing
DesignSpecs/    The specs. Environmental_Assurance_Spec.md is canonical; the
                other three are superseded legacy documents kept for history.
```

Read `Environmental_Assurance_Spec.md` — it is the single source of truth,
consolidating the original Claude Code build spec, the peatland-aware v2
architecture, and the UI spec into one audit-scope-first document. Where the
three legacy files (`environmental_assurance_claude_code_spec.md`,
`environmental_assurance_spec_v2.md`, `assurance_console_ui_spec.md`)
conflict with it, the canonical file wins. Each legacy file carries a
"2026-09-08 Canonical Audit-Workflow Update" banner pointing back here; don't
cite a legacy section number in new code or docs.

**The stack is AWS.** The canonical spec named Cloudflare Workers with
D1/R2/KV until 2026-09-08; it now says Flask on Lambda behind API Gateway,
which is what is actually deployed. The three legacy specs still say
Cloudflare — they are history, not instructions.

§8's persistence *roles* are canonical — durable/queryable metadata, bulky
immutable evidence, disposable cache — and the spec still names roles rather
than products. One role is now filled: **audit session state lives in
DynamoDB** (`aws_dynamodb_table.audit_state`, PAY_PER_REQUEST), because
Lambda served later register/graph/evidence calls from a different warm
container than the one that created the audit, so process-local dicts lost
the scope. That decision covers *session state only*. The **disposable
cache** role is filled too: `GET /api/firms/live` keeps the shared copy of
its 15-minute cache in S3 (`aws_s3_bucket.cache`, one gzipped object,
lifecycle-expired), because a cold container's process-local dict was empty
and every cold start refetched from NASA. Only the bulky-immutable-evidence
role is still unfilled.

**DynamoDB and S3 are now authorised** (owner's call, 2026-09-09), so filling
those roles no longer needs a fresh argument about the service — but it does
still need the *design* recorded in the decision log, and the new service
added to [`docs/infra.md`](docs/infra.md) with its cost in the same PR. The
older constraint is unchanged and unaffected by this: serverless by default,
and anything always-on needs justification before it is switched on.

Check [`docs/decision-log.md`](docs/decision-log.md) before changing anything
architectural — it records what was already tried and rejected, and why.
[`docs/environments.md`](docs/environments.md) has the AWS account, live URLs,
and what CI needs. Add an entry to the log when you make a decision worth not
re-litigating.

## Commands

```bash
# frontend
cd frontend && npm install && npm run dev      # :5173, proxies /api -> :5001
cd frontend && npm run lint && npm test && npm run build

# backend
cd backend && uv venv && uv pip install -e ".[dev]"
cd backend && .venv/bin/python wsgi.py          # :5001
cd backend && .venv/bin/ruff check . && .venv/bin/pytest -q

# infra — CI applies on merge to main; apply by hand only when you mean to
cd infra && ./scripts/build_lambda.sh && terraform plan

# data pipeline
python -m data_pipeline.run_all
```

## State of things

The console is **mostly** fixture-driven, and moving off fixtures happens one
endpoint at a time through the seam in `frontend/src/api/client.ts`. Keep that
seam intact: every function there mirrors `Environmental_Assurance_Spec.md`
§24 (API), so a caller cannot tell which are real.

Real: `GET /api/events` and `GET /api/events/{id}`, served by Flask from
`backend/app/data/events.json`, and `GET /api/firms/live`, which proxies the
NASA FIRMS area API for the landing map's live regional layer — the MAP_KEY
cannot be domain-restricted, so it is never shipped to the browser, and that
route is the one deliberate exception to the audit-scoped rule below because
it serves the screen that exists before a scope does. Note these are *flat* routes; the canonical
§24 API is audit-scoped (`/api/audits/{audit_id}/events`). The flat pair was
built before the canonical spec landed and is interim — build new endpoints
audit-scoped rather than extending the flat shape. Still fixtures in the browser:
`fetchOverlay`, `fetchReport`, and `generateReport` — the last of which fakes
the Investigator/Skeptic loop with `setTimeout`, and is where a real agent
goes.

The events `GET /api/events` serves are still *fixture cases*; that endpoint
is real, its data is invented.

`data_pipeline/` is no longer only a feasibility spike. It now holds the
analysis engine — `clustering/`, `triage/`, `graph/`, `priority/`,
`complexity/`, `enrichment/`, `propagation/`, `imagery/`, plus `benchmark/`
and `golden/` regression cases — across ~58 modules with unit tests.

The first of it reaches the API: `GET /api/audits/{id}/events` serves 3,610
FireEvents clustered from 20,471 FIRMS detections in the 2019 haze window and
run through Stage-1 triage. A session-created audit gets the subset of those
its own review period covers, and every count in the served scope is
recomputed from that subset — a narrowed register never carries the artifact's
unfiltered totals beside it, and `rawObservations` is `null` rather than a
figure a sub-window cannot know (decision log, 2026-09-10). Clustering happens offline in
`data_pipeline/export_audit_events.py` and the API serves the committed
artifact, because scipy/pandas would take the Lambda bundle to the edge of its
250 MB limit and the derivation is identical for every caller. The FIRMS
artifact itself is packaged and immutable — nothing writes to it. The one
thing that does persist is audit session state (`backend/app/audit_store.py`):
memory locally, the DynamoDB table when `AUDIT_STATE_TABLE` is set.

`GET /api/audits/{id}/graph` (`investigation_map`) now also serves real
`graph/fire_event_graph.py`/`propagation/surface_fire.py` output — a
wind-oriented surface-spread compatibility state and envelope polygon per
candidate edge, not the flat distance-only `RELATED_POSSIBLE` it used to
synthesize for every pair. `data_pipeline/enrich_fire_spread_audit_events.py`
precomputes this offline, same reasoning as clustering, and it only covers
the demo scope's 16 in-scope+buffer FireEvents — real historical wind was
only ever fetched for those. A candidate pair reaching outside that set (an
`EXTERNAL_CONTEXT` neighbour from the wider regional archive) still gets the
old distance-only synthesized edge; peatland-corridor uncertainty for any
edge remains unwired. The envelope's own drawn reach is capped under 10 km
by product decision, not physics — the model assumes wind alone moves a
fire, nothing else, so it is only honest at a short range; anything a
candidate needs to explain beyond that is AI interpretation's job. See
decision log, 2026-09-09.

Satellite context images for those same 16 events are static files under
`frontend/public/imagery/` (JPEG per scene plus `manifest.json`), rendered
once by `data_pipeline/generate_processed_imagery.py` through the CDSE
Process API and pinned to the scenes the evidence already names. They are
served by Amplify from the console's origin, not by the API, and never enter
the Lambda bundle. The evidence-drawer surface that displays them is #171.

The console consumes them. `components/scope/ScopedMapLanding.tsx` is the
map-first landing surface for the bounded demo scope, and
`components/audit/HistoricalInvestigation.tsx` is the register, investigation
map, evidence drawer and pack view. The console opens on
`components/scope/AuditLanding.tsx`: a deliberately event-free regional
Indonesia orientation map with a START AUDIT button. No FireEvent is drawn
until a scope exists — that is the point of the screen, not a loading state.
`AuditStart.tsx` is the scope-entry and history-build panel, shown over the
landing. `ConsoleContextPanel.tsx` exports both the panel and
`ConsoleContextModal`, the first-load dialog stating what the console does,
what it refuses to conclude, and which parts of this build are real —
dismissed per browser, reopened from the landing. Events are typed
`AuditEventSummary`, deliberately **not** `FireEvent` — that type
requires `location`, `peatClassification` and `currentConditions`, none of
which FIRMS-only data can honestly supply, and widening it with optionals
would make a real event and a fixture indistinguishable to the compiler. Keep
the two apart. The legacy `EventTable`/`ReportPanel` console is not mounted
anywhere and still reads fixtures. `MapView`/`EventMarkers`/`EventInfoCard`/
`TimelineScrubber` were the same kind of orphan and have been deleted
outright rather than left unmounted.

Stage-1 triage does not compress this dataset and is not meant to. On
FIRMS-only input `LIKELY_NON_FIRE` is unreachable (max non-fire score 2,
threshold 4), and supplying context would widen the fire set, not shrink the
queue — haze-season data has few false positives to remove. The efficiency
chain is observations → events → **in scope** → **ranked**; Stage-1 is a
label along it. Don't present its 1.0× as a gap more data would close, and
don't tune its thresholds to manufacture a reduction. Numbers and rejected
alternatives are in the decision log (2026-09-08, "Stage-1 is a
classifier"); the `audit-artifact` skill says how to re-measure.

The spike's negative results are still the valuable part of `sources/` (FIRMS
`day_range` caps at 5 not 10; Overpass attic queries silently return empty;
NASA FIRMS needs `truststore` for TLS).

The real derived 2019 FIRMS artifact now reaches the map through
`GET /api/audits/{id}/events` and the audit-scoped FIRMS Hotspots overlay,
framed to the demo audit scope, context buffer and observation date. The demo
must never blur which data is real and which is a fixture.

## Skills

| Skill | Load when |
|---|---|
| `evidence-framing` | Writing any text describing a fire event or an agent prompt |
| `ui-copy` | Writing or editing any text a console user sees, including fixtures and prompts. No em-dashes |
| `add-map-layer` | Adding or changing a console overlay layer |
| `add-data-source` | Adding or re-checking a source in `data_pipeline/` |
| `deploy-api` | Deploying or debugging the Lambda-hosted API |
| `branch-and-pr` | Before the first edit of any task, and again before merging |
| `decision-log` | Opening a PR or creating an issue — check whether a decision needs recording |
| `audit-artifact` | Regenerating, inspecting or measuring `backend/app/data/audit_events.json.gz` |

## Working in this repo

**Start from an issue.** `gh issue list --state open` before writing anything
— the backlog is real and specific, and most work already has an issue with
deliverables and acceptance criteria written down. Work to it rather than
beside it. If nothing covers the work, open one first; if the work
*contradicts* an existing issue, say so in the issue before building the
opposite of what it specifies. The documented queue `#56 → #57 → #58 → #59 →
#60 → #61 → #62 → #64` is **exhausted** — every one of those is closed — so
there is no running order to join any more. Pick the next issue on what the
demo needs, say in the PR why that one, and prefer work that does not deploy
when the demo is close: merging an `infra/**` or `backend/**` PR applies
Terraform. Exceptions and the full rule are in the `branch-and-pr` skill.

**Never commit to `main`.** Every change goes on a branch and lands through a
pull request, so the two of us can see what the other's Claude did before it
is in the trunk. Reference the issue in the PR body. Name the branch `<type>/<short-kebab-description>`, using the
same type you would put on the commit:

| Prefix | For |
|---|---|
| `feat/` | New behaviour a user could notice |
| `fix/` | Correcting behaviour that was already meant to work |
| `refactor/` | Restructuring without changing behaviour |
| `docs/` | Docs, specs, comments, `CLAUDE.md`, skills |
| `chore/` | Config, CI, dependencies, tooling |

Wait for CI before merging. Which workflow runs depends on the paths touched:

| Workflow | Runs on | Does |
|---|---|---|
| `CI` | every PR | frontend lint + Vitest + build, backend ruff + pytest, data pipeline pytest |
| `Security` | every PR, plus weekly | gitleaks over the full history; `npm audit` and `pip-audit` |
| `Infra` | `infra/**`, `backend/**`, or its own file | posts the Terraform plan as a PR comment, applies on merge to `main` |

**Read the plan comment before merging an infra PR** — merging is what
deploys.

A `Security` failure is not a formality. If gitleaks flags something, rotate
the credential first and clean the history second — a secret that reached
`origin` is compromised whether or not the commit is still reachable. Never
silence a finding with an allowlist entry without saying in the PR why the
match is not a real credential.

Do not run `terraform apply` by hand to ship something. It works, and it
races the pipeline; the pipeline holds the state lock and smoke-tests the
result afterwards. Apply locally only when you are deliberately recovering
something, and check `aws sts get-caller-identity` first — the active profile
comes from the environment, not from the repo.

Never commit a real `.env`, `*.tfvars`, Terraform state, `.terraform/`, or
`infra/build/`. [`.env.example`](.env.example) is the index of every
credential the project uses and where each one lives. There are no AWS access
keys anywhere in this repo by design — GitHub authenticates to AWS over OIDC.

**Close issues by merging, not by hand.** Put `Closes #n` in the PR so the
merge closes it and the trail survives; `Refs #n` when the work only advances
it. Never close an issue whose work is still on an unmerged branch — the
backlog is what the other person reads to know what exists. If you finish only
part, leave it open and comment on what is left. And when you find a real
problem that is not your task, open a linked issue for it rather than fixing
it quietly or leaving it in a PR comment.

**Keep "State of things" true in the PR that changes it.** That section is
the first thing a fresh session reads to learn what is real and what is a
fixture, and a stale line there is worse than no line: an agent told the
console is fixture-driven will build a second fixture path instead of
extending the real one. If your change makes a sentence there wrong, fix that
sentence in the same PR — usually one line, the same habit as adding a
decision-log entry.

Dependencies are Renovate's job, not yours. Do not hand-bump a version to fix
an unrelated problem; if a bump is genuinely required, say so in the PR.

## Conventions

- Comments explain *why*, not what. The existing code documents decisions and
  gotchas rather than restating the line below — match that.
- One colour scheme for confidence/status everywhere (`lib/layerColors.ts`,
  the Tailwind `--color-status-*` tokens). No inline hexes in components.
- Never build a public named-concession directory or render third-party
  concession geometry beyond an attribute-only lookup
  (`Environmental_Assurance_Spec.md` §4). An auditor's own uploaded
  management-unit boundary is different: it is legitimate private audit-scope
  data and may be stored tenant-scoped/encrypted (§6.2–6.3).
- Comments and commit messages are written for the other person on this team,
  who does not have your context. Say what was rejected and why, not only what
  was chosen.
