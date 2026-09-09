# vibe-for-good-2026

Environmental-assurance console for auditors investigating satellite fire
detections in Indonesia. It reduces a regional archive to a user-authorised
audit scope, then presents traceable evidence for human review.

## Non-negotiable product boundary

The product does not determine blame, intent, legal responsibility, or
culpability. Keep these layers distinct:

```text
observed evidence → derived metrics → AI interpretation → human decision
```

Every AI factual claim must trace to an evidence ID. Do not present peatland,
satellite imagery, weather, proximity, or a propagation model as proof of
cause. Read `PRODUCT.md` and the canonical spec before changing user-facing
evidence language.

## Source of truth and project shape

- `Environmental_Assurance_Spec.md` is canonical. The three older specs are
  history; do not cite or implement a conflicting legacy instruction.
- The deployed stack is Flask on AWS Lambda behind API Gateway, with Terraform
  in `infra/`. Earlier Cloudflare references are obsolete.
- Read `docs/decision-log.md` before making architectural choices; add a short
  entry when making one worth preserving. `docs/environments.md` holds live
  environment facts.

```text
frontend/       React, TypeScript, MapLibre console
backend/        Flask API, Lambda entry point and committed artifacts
data_pipeline/  offline clustering, enrichment, graph and imagery processing
infra/          Terraform and Lambda build
docs/           decisions, deployment and demo facts
```

## Settled decisions

- Audits are scope-first: landing → GeoJSON scope → `POST /api/audits` →
  history build → scoped FireEvent register → investigation. Never restore a
  disconnected hardcoded demo scope or an unscoped FireEvent browser.
- Audit session state persists in DynamoDB when `AUDIT_STATE_TABLE` is set;
  local in-memory storage is only a development fallback. Persistent audit IDs
  must work across Lambda instances.
- FireEvent records and derived evidence are precomputed offline and served
  from immutable artifacts. Do not move scipy/pandas processing into Lambda.
- Map camera fitting is bounds-driven. The regional FIRMS layer on
  `AuditLanding.tsx` is context only, never an audit FireEvent source.
- Peatland is environmental context, not a suspicion or causal conclusion.
- Satellite display processing must be deterministic and provenance-preserving;
  no generative enhancement or content reconstruction.
- Persistence roles remain: DynamoDB for audit session state; durable bulky
  evidence and disposable cache technologies are deliberately undecided.

## Current state

- The scoped API serves 3,610 clustered FireEvents from 20,471 immutable 2019
  FIRMS observations. New API work must be audit-scoped; legacy flat
  `/api/events` routes remain interim fixture-case compatibility.
- `GET /api/audits/{id}/events`, graph, and evidence use the audit session
  state. Event IDs must remain stable across all endpoints.
- The investigation graph includes offline surface-spread compatibility and
  envelopes for the demo scope’s prepared events. Wider regional neighbours may
  still use conservative distance-only context.
- `AuditLanding.tsx` is the SEA orientation screen. It may show clearly-labelled
  live FIRMS context, but no unscoped FireEvents. `AuditStart.tsx` is the sole
  scope/history entry path; `ScopedMapLanding.tsx` is for an active audit.
- Some browser UI remains fixture-driven through `frontend/src/api/client.ts`.
  Preserve that seam and label fixture data honestly. Do not merge fixture
  `AuditEventSummary` values into the fuller `FireEvent` model.

## Routine commands

```bash
cd frontend && npm run lint && npm run build
cd backend && .venv/bin/ruff check . && .venv/bin/pytest -q
python -m pytest data_pipeline/tests -q
cd infra && ./scripts/build_lambda.sh && terraform plan
```

## Working rules

- Start from an existing issue where possible. Do not silently contradict a
  recorded decision or issue acceptance criterion.
- Never commit to `main`. Use a `<type>/<short-description>` branch, PR review,
  and `Closes #n` only when the merged change resolves the issue.
- CI validates frontend, backend, pipeline, security, and applicable Terraform
  plans. Read an infra plan before merging; CI applies infrastructure on merge.
- Do not commit `.env`, `*.tfvars`, Terraform state, `.terraform/`, or build
  output. Never run `terraform apply` for ordinary delivery.
- Keep this file’s **Current state** accurate in the same PR that changes it.
- Reuse shared status colors and tokens where they apply. Map paint colors may
  be local when a visual layer needs them; document the reason. Never render
  third-party concession boundaries as a public named directory.

## Before changing a subsystem

| Change | Read first |
|---|---|
| evidence wording or prompts | `PRODUCT.md`, canonical spec, decision log |
| map layer or source | decision log, existing map/data pipeline conventions |
| deployment or persistence | `docs/environments.md`, `infra/`, decision log |
| artifacts or benchmarks | `data_pipeline/README.md` and related tests |

Prefer concise comments that explain a decision or constraint, not the syntax.
