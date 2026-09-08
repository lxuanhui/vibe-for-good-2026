# vibe-for-good-2026

AI-driven investigative-efficiency tool for environmental assurance, built for the ACCA Challenge Statement #1 at Vibe For Good 2026. It helps auditors triage satellite fire detections in Indonesia and reconstruct evidence for human review — it does not determine blame, guilt, or legal responsibility.

## Design specs

[`Environmental_Assurance_Spec.md`](DesignSpecs/Environmental_Assurance_Spec.md)
is the single source of truth: audit-scope-first workflow, data model, API
contract, and UI spec in one document. It consolidates and supersedes three
earlier documents, still kept in `DesignSpecs/` for history:

1. [`environmental_assurance_claude_code_spec.md`](DesignSpecs/environmental_assurance_claude_code_spec.md) — original project overview, goals, and architecture.
2. [`environmental_assurance_spec_v2.md`](DesignSpecs/environmental_assurance_spec_v2.md) — updated architecture accounting for peatland fires that are invisible to FIRMS.
3. [`assurance_console_ui_spec.md`](DesignSpecs/assurance_console_ui_spec.md) — frontend/UI specification for the console.

Where any of the three conflict with the canonical file, the canonical file wins.

## Layout

```
frontend/       Environmental Assurance Console — Vite + React + TypeScript
                (MapLibre, Tailwind, zustand, recharts). Dev server on :5173.
backend/        Flask API. Local dev server on :5001 mounted at /api;
                the same app runs on AWS Lambda via lambda_handler.py.
infra/          Terraform — Lambda + API Gateway HTTP API. See infra/README.md.
data_pipeline/  Python feasibility spike for the environmental data sources.
                See data_pipeline/README.md.
docs/           Decision log and environment facts. See docs/README.md.
DesignSpecs/    The specs the product is built against; Environmental_Assurance_Spec.md is canonical.
```

The Vite dev server proxies `/api/*` to the Flask backend, so the frontend can
call `fetch('/api/hello')` with no CORS setup in development.

`GET /api/events` and `GET /api/events/{id}` remain the legacy fixture-case
endpoints. The audit workflow now uses `POST /api/audits`,
`POST /api/audits/{audit_id}/history/build`, and
`GET /api/audits/{audit_id}/events`: those endpoints run the existing
deterministic `data_pipeline` and return scope-aware FireEvents. The default
demo source is the clearly labelled frozen real 2019 NASA FIRMS export; set
`HISTORY_SOURCE=live` to use the existing paged FIRMS backfill instead.

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

## Deploying

The Flask API runs on AWS Lambda behind an API Gateway HTTP API, deployed by
CI: a pull request touching `infra/**` or `backend/**` gets a Terraform plan
posted as a PR comment, and merging to `main` applies it and health-checks
the result. GitHub authenticates to AWS over OIDC — no keys in the repo.

To apply by hand against the same remote state:

```bash
cd infra
./scripts/build_lambda.sh
terraform init      # first time only
terraform apply
```

Requires Terraform >= 1.10. See [`infra/README.md`](infra/README.md) for the
architecture, the one-time bootstrap, the pipeline, and what is deliberately
not built yet.

## Credentials

[`.env.example`](.env.example) is the index of every credential the project
uses — which file each belongs in, where to obtain it, and which live in
GitHub rather than on disk. Copy the relevant block into `backend/.env` or
`data_pipeline/.env`; nothing loads a `.env` at the repo root.

For CI, one repository variable is required:

| Where | Name | Required | Purpose |
|---|---|---|---|
| Variable | `AWS_ROLE_ARN` | yes | IAM role GitHub assumes over OIDC. Already set. |
| Variable | `CORS_ORIGINS` | no | Origin the deployed console is served from; defaults to `*`. |
| Secret | `FLASK_SECRET_KEY` | no | Lambda's `SECRET_KEY`; defaults to `dev`. |

There are deliberately **no AWS access keys** in this repo — GitHub
authenticates to AWS over OIDC and assumes a role scoped to this repository.

## Checks

```bash
cd frontend && npm run lint && npm run build
cd backend  && .venv/bin/ruff check . && .venv/bin/pytest -q
cd infra    && terraform fmt -check -recursive && terraform validate
```

A `Security` workflow also runs on every PR and weekly: gitleaks over the
full commit history for committed credentials, plus `npm audit` and
`pip-audit` for known-vulnerable dependencies.

## Contributing

Branch, then PR — nothing lands on `main` directly. Name branches
`<type>/<short-description>` with one of `feat/`, `fix/`, `refactor/`,
`docs/`, `chore/`. See [`CLAUDE.md`](CLAUDE.md) for the full working
conventions, which apply to humans and to Claude sessions alike.

## Dependencies

Renovate opens grouped update PRs weekly (Monday mornings, Asia/Singapore).
Configuration lives in `renovate.json`; the Dependency Dashboard issue tracks
everything pending.

Renovate only runs once the [Renovate GitHub App](https://github.com/apps/renovate)
is installed on the repository — the config file on its own does nothing.
