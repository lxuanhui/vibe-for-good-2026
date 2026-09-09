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
docs/           Decision log and environment facts — read before re-deciding anything
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
immutable evidence, disposable cache — but the AWS services behind them are
deliberately **not chosen yet**, so the spec names roles rather than products.
Nothing persists today, so nothing forces the decision; don't quietly settle
it by writing DynamoDB or S3 into the spec. Serverless only when it is made,
and anything always-on needs justification first.

Check [`docs/decision-log.md`](docs/decision-log.md) before changing anything
architectural — it records what was already tried and rejected, and why.
[`docs/environments.md`](docs/environments.md) has the AWS account, live URLs,
and what CI needs. Add an entry to the log when you make a decision worth not
re-litigating.

## Commands

```bash
# frontend
cd frontend && npm install && npm run dev      # :5173, proxies /api -> :5001
cd frontend && npm run lint && npm run build

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
`backend/app/data/events.json`. Note these are *flat* routes; the canonical
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
run through Stage-1 triage. Clustering happens offline in
`data_pipeline/export_audit_events.py` and the API serves the committed
artifact, because scipy/pandas would take the Lambda bundle to the edge of its
250 MB limit and the derivation is identical for every caller. Nothing
persists yet: no module touches a database, an S3 bucket, or any store.

The console consumes them. `components/scope/ScopedMapLanding.tsx` is the
map-first landing surface for the bounded demo scope, and
`components/audit/HistoricalInvestigation.tsx` is the register, investigation
map, evidence drawer and pack view. The map is the *first* thing on screen:
`App.tsx` renders `ScopedMapLanding` immediately, framed on Borneo as a
basemap with no events drawn, while a default demo scope is bootstrapped in
the background through the real endpoints (`lib/bootstrapScope.ts` — never a
hardcoded scope object; PR #118 removed one of those). `AuditStart.tsx` is now
only an overlay, for entering or changing a scope by hand.
`ConsoleContextPanel.tsx` exports both the panel and `ConsoleContextModal`,
the dialog over the map that states what the console does, what it refuses to
conclude, and which parts of this build are real — dismissed per browser,
reopened from the header. Events are typed
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
`GET /api/audits/{id}/events`, framed to the demo audit scope and context
buffer. The static FIRMS export remains behind its own clearly-labelled toggle.
The demo must never blur which data is real and which is a fixture.

## Skills

| Skill | Load when |
|---|---|
| `evidence-framing` | Writing any text describing a fire event or an agent prompt |
| `add-map-layer` | Adding or changing a console overlay layer |
| `add-data-source` | Adding or re-checking a source in `data_pipeline/` |
| `deploy-api` | Deploying or debugging the Lambda-hosted API |
| `branch-and-pr` | Before the first edit of any task, and again before merging |
| `audit-artifact` | Regenerating, inspecting or measuring `backend/app/data/audit_events.json.gz` |

## Working in this repo

**Start from an issue.** `gh issue list --state open` before writing anything
— the backlog is real and specific, and most work already has an issue with
deliverables and acceptance criteria written down. Work to it rather than
beside it. If nothing covers the work, open one first; if the work
*contradicts* an existing issue, say so in the issue before building the
opposite of what it specifies. The queue runs `#56 → #57 → #58 → #59 → #60 →
#61 → #62 → #64`; a new issue joins that order rather than jumping it.
Exceptions and the full rule are in the `branch-and-pr` skill.

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
| `CI` | every PR | frontend lint + build, backend ruff + pytest, data pipeline pytest |
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
