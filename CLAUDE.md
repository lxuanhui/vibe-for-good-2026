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
frontend/       Vite + React + TS console (MapLibre, Tailwind 4, zustand, recharts)
backend/        Flask API — runs locally via wsgi.py, on Lambda via lambda_handler.py
infra/          Terraform: Lambda + API Gateway HTTP API
data_pipeline/  Python feasibility spike for the environmental data sources
DesignSpecs/    The specs. v2 supersedes v1's Stage 0/1; UI spec covers the console.
```

Read the specs in this order: `environmental_assurance_claude_code_spec.md`
(overview) → `environmental_assurance_spec_v2.md` (peatland-aware
architecture, supersedes v1 §0–1) → `assurance_console_ui_spec.md` (UI + API
contract).

## Commands

```bash
# frontend
cd frontend && npm install && npm run dev      # :5173, proxies /api -> :5001
cd frontend && npm run lint && npm run build

# backend
cd backend && uv venv && uv pip install -e ".[dev]"
cd backend && .venv/bin/python wsgi.py          # :5001
cd backend && .venv/bin/ruff check . && .venv/bin/pytest -q

# infra (apply creates billable AWS resources — confirm first)
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

## Conventions

- Comments explain *why*, not what. The existing code documents decisions and
  gotchas rather than restating the line below — match that.
- One colour scheme for confidence/status everywhere (`lib/layerColors.ts`,
  the Tailwind `--color-status-*` tokens). No inline hexes in components.
- Never render or store raw concession/peatland boundary geometry — attribute
  lookups only (spec v2 §2).
