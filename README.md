# vibe-for-good-2026

AI-driven investigative-efficiency tool for environmental assurance, built for the ACCA Challenge Statement #1 at Vibe For Good 2026. It helps auditors triage satellite fire detections in Indonesia and reconstruct evidence for human review — it does not determine blame, guilt, or legal responsibility.

## Design specs

Read the specs in `DesignSpecs/` in this order:

1. [`environmental_assurance_claude_code_spec.md`](DesignSpecs/environmental_assurance_claude_code_spec.md) — original project overview, goals, and architecture.
2. [`environmental_assurance_spec_v2.md`](DesignSpecs/environmental_assurance_spec_v2.md) — updated architecture accounting for peatland fires that are invisible to FIRMS; supersedes Stage 0/1 of the original spec.
3. [`assurance_console_ui_spec.md`](DesignSpecs/assurance_console_ui_spec.md) — frontend/UI specification for the console (Map/Table views, investigation report layout, API contract).
Vite + React + TypeScript frontend with a Flask API backend.

## Layout

```
frontend/   Vite + React + TypeScript (dev server on :5173)
backend/    Flask API (dev server on :5001, mounted at /api)
```

The Vite dev server proxies `/api/*` to the Flask backend, so the frontend can
call `fetch('/api/hello')` with no CORS setup in development.

## Getting started

**Backend**

```bash
cd backend
uv venv && uv pip install -e ".[dev]"   # or: python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/python wsgi.py                # http://127.0.0.1:5001
```

**Frontend** (in a second terminal)

```bash
cd frontend
npm install
npm run dev                             # http://localhost:5173
```

## Checks

```bash
cd backend  && .venv/bin/ruff check . && .venv/bin/pytest -q
cd frontend && npm run lint && npm run build
```

## Dependencies

Renovate opens grouped update PRs weekly (Monday mornings, Asia/Singapore).
Configuration lives in `renovate.json`; the Dependency Dashboard issue tracks
everything pending.
