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
docs/           Decision log and environment facts — read before re-deciding anything
frontend/       Vite + React + TS console (MapLibre, Tailwind 4, zustand, recharts)
backend/        Flask API — runs locally via wsgi.py, on Lambda via lambda_handler.py
infra/          Terraform: Lambda + API Gateway HTTP API, applied by CI
data_pipeline/  Python feasibility spike for the environmental data sources
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
`backend/app/data/events.json`. Still fixtures in the browser:
`fetchOverlay`, `fetchReport`, and `generateReport` — the last of which fakes
the Investigator/Skeptic loop with `setTimeout`, and is where a real agent
goes.

The events `GET /api/events` serves are still *fixture cases*; that endpoint
is real, its data is invented.

Events derived from real observations live behind
`GET /api/audits/{id}/events` instead — 3,610 FireEvents clustered from
20,471 FIRMS detections in the 2019 haze window and run through Stage-1
triage. Clustering happens offline in
`data_pipeline/export_audit_events.py`; the API only serves the committed
artifact, because scipy/pandas would take the Lambda bundle to the edge of
its 250 MB limit and the derivation is identical for every caller. **No
frontend calls these endpoints yet** — `FireEvent` in
`frontend/src/api/types.ts` requires `location`, `peatClassification` and
`currentConditions`, none of which FIRMS-only data can honestly supply.
Filling them with placeholders is exactly the blurring the product boundary
forbids, so the register needs its own view.

`data_pipeline/` otherwise writes to no database by design — it answers "can this
source be pulled, and pulled *historically*". Its negative results (FIRMS
`day_range` caps at 5 not 10; Overpass attic queries silently return empty;
NASA FIRMS needs `truststore` for TLS) are the valuable part.

The only real data reaching the UI is a static FIRMS export from the 2019
haze window, behind its own clearly-labelled toggle. The demo must never blur
which data is real and which is a fixture.

## Skills

| Skill | Load when |
|---|---|
| `evidence-framing` | Writing any text describing a fire event or an agent prompt |
| `add-map-layer` | Adding or changing a console overlay layer |
| `add-data-source` | Adding or re-checking a source in `data_pipeline/` |
| `deploy-api` | Deploying or debugging the Lambda-hosted API |

## Working in this repo

**Never commit to `main`.** Every change goes on a branch and lands through a
pull request, so the two of us can see what the other's Claude did before it
is in the trunk. Name the branch `<type>/<short-kebab-description>`, using the
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
