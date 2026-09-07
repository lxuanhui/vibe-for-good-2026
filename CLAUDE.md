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
DesignSpecs/    The specs. v2 supersedes v1's Stage 0/1; UI spec covers the console.
```

Read the specs in this order: `environmental_assurance_claude_code_spec.md`
(overview) → `environmental_assurance_spec_v2.md` (peatland-aware
architecture, supersedes v1 §0–1) → `assurance_console_ui_spec.md` (UI + API
contract).

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

The console is **fixture-driven**. `frontend/src/api/client.ts` mocks the
endpoint contract from UI spec §5 exactly, so swapping it for real `fetch()`
calls should not change any caller. Keep that seam intact.

The Flask API is currently two stub routes (`/api/health`, `/api/hello`). The
real endpoints from UI spec §5 are not built yet.

`data_pipeline/` writes to no database by design — it answers "can this
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
`CI` (frontend lint+build, backend ruff+pytest) runs on every PR; `Infra`
runs only on `infra/**`, `backend/**`, or its own file, posts the Terraform
plan as a PR comment, and applies on merge to `main`. **Read the plan comment
before merging an infra PR** — merging is what deploys.

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
- Never render or store raw concession/peatland boundary geometry — attribute
  lookups only (spec v2 §2).
- Comments and commit messages are written for the other person on this team,
  who does not have your context. Say what was rejected and why, not only what
  was chosen.
