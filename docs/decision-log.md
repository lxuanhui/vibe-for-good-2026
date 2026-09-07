# Decision log

Newest first. Each entry records what was decided, why, and what was rejected
— including approaches that were tried and abandoned, which are usually the
more valuable half.

---

## 2026-09-07 — Lambda bundle must be byte-identical across machines

**Status:** done · PR #31

Terraform hashes the built payload directory. A laptop build and a CI build
disagreed, so every plan reported a Lambda update and **no plan was ever
clean** — which destroys the value of posting a plan for review on each PR.

Three separate causes, none of them the application code. Found by generating
a file-level manifest (path, mode, size, sha256) on the runner and diffing it
against one generated locally — guessing had already burned three CI round
trips:

1. `bin/flask` and `bin/dotenv` — pip console-script wrappers whose shebang
   names the interpreter that ran pip (`/opt/homebrew/...` locally,
   `/opt/hostedtoolcache/...` on the runner). Lambda never executes them.
2. Those same scripts are listed in each package's `.dist-info/RECORD` with
   their hash and size, so removing the files left machine-dependent lines.
3. The backend was `pip install`ed from source, which builds a wheel — pulling
   in whatever build-backend version pip resolved that day, plus a
   `direct_url.json` recording the mktemp path it was built in.

**Fixes:** delete `bin/`, strip `../../bin/` lines from `RECORD`, and stop
building the backend wheel entirely — dependencies are read from
`pyproject.toml` (still one source of truth) and `app/` is copied in.

Verified: identical manifests, 228 files, matching mode/size/sha256 for every
one. The first apply on `main` reported `0 added, 0 changed, 0 destroyed`.

**Trap worth remembering:** running Python inside `infra/build/lambda` to
smoke-test imports writes `__pycache__` *after* the build cleaned it, silently
changing the hash. Copy the bundle elsewhere to test it. This cost a debugging
cycle — the "difference" being chased was self-inflicted.

**Left open:** dependency versions stay unpinned (`flask>=3.1.0`), so a build
resolving a newer wheel legitimately changes the hash. That is a real change;
Renovate proposes it.

---

## 2026-09-07 — GitHub OIDC uses the immutable subject format here

**Status:** done · PR #31

The CI role could not be assumed: `Not authorized to perform
sts:AssumeRoleWithWebIdentity`. Provider, audience and policy were all
correct; the `sub` pattern was not.

This repository receives tokens in GitHub's **hardened immutable** subject
format, which appends numeric owner and repo ids:

```
repo:lxuanhui@73178128/vibe-for-good-2026@1358849204:pull_request
```

not the widely documented `repo:owner/repo:pull_request` that every tutorial
shows. The trust policy now allows both forms, each still pinned to this
repository. Deliberately **not** `repo:...:*` — that would let any branch
assume a role with write access to the account.

Diagnosed with a temporary workflow step printing only `sub`/`aud`/
`repository`/`ref`, never the token. If OIDC auth ever breaks again, that is
the first thing to re-check.

The immutable form is the stronger of the two: it does not follow a rename, so
a repo deleted and recreated under the same name cannot inherit the role.

---

## 2026-09-07 — Terraform state in S3 with native locking; Terraform >= 1.10

**Status:** done · PR #31

CI needs remote state — a runner is ephemeral, so local state means every run
plans against nothing and tries to recreate the whole stack.

Locking uses S3-native `use_lockfile`, which requires **Terraform >= 1.10**.
The alternative, a DynamoDB lock table, works on older Terraform but was
**removed in Terraform 1.11** — a dead end, so it was rejected despite being
the zero-friction option at the time. Local Terraform was upgraded 1.9.8 →
1.16.0 rather than accept that.

`infra/bootstrap/` is a separate root module for the state bucket and the CI
role — the two things the main stack cannot create for itself. It keeps local
state because it owns the bucket the remote state lives in. Applied by hand,
idempotent, and outside the pipeline.

`create_oidc_provider` defaults to **false**: AWS permits exactly one GitHub
OIDC provider per account and this account already had one (first apply failed
with `EntityAlreadyExists`). Set it true only in a fresh account.

---

## 2026-09-07 — CORS is owned by Flask, never by API Gateway

**Status:** done · PR #30, #31

`flask-cors` sets the CORS headers inside the app. `aws_apigatewayv2_api` has
**no** `cors_configuration` block on purpose.

Configuring both makes API Gateway append a second
`Access-Control-Allow-Origin`, and a browser rejects a response carrying two —
presenting as CORS being *unconfigured* rather than double-configured, which
is a genuinely confusing hour to lose. Set the allowed origin through the
`cors_origins` Terraform variable.

Verified live: exactly one such header on the deployed endpoint.

---

## 2026-09-07 — Backend runs on AWS Lambda, not Cloudflare Workers

**Status:** done · PR #30 · **deviates from the specs**

Both design specs say Cloudflare Workers for all backend. The project is on
**AWS Lambda + API Gateway HTTP API** instead, per the team's infrastructure
choice.

Consequences the specs have not been updated for:

- Spec v2 §8 rejects ensemble Kalman filtering partly on Workers' CPU-time
  caps. Lambda's limits differ, so that reasoning needs revisiting on its own
  merits rather than being inherited.
- The spec's KV/D1 storage has no chosen equivalent yet — the ingestion worker
  is unbuilt, and DynamoDB vs S3 is undecided.
- API Gateway HTTP API caps a response at 30s, so Lambda timeout is 29s.
  Anything genuinely long-running (agent rounds, imagery acquisition) needs a
  queue plus a worker, not a bigger timeout.

One Lambda serves every route rather than one per route: Flask already owns
routing, and splitting would multiply cold starts for nothing. `apig-wsgi`
adapts the existing `create_app()` factory, so `wsgi.py` (local :5001) and
Lambda share one app definition.

---

## 2026-09-07 — One frontend, at `frontend/`, containing the console

**Status:** done · PR #30

The repo carried two: `apps/web` held the real Environmental Assurance Console
(~1.4k lines, MapLibre/Tailwind/zustand/recharts), and `frontend/` held a Vite
starter that a later scaffold commit landed on top of it.

README and CI both pointed at the starter — so the only frontend that mattered
was **never built in CI**, and anyone following the README got a hello-world.

`frontend/` survives as the path, the console as the code. The starter's one
real contribution, the Vite `/api` → `:5001` proxy, was merged into the
console's Tailwind-enabled config.

Kept `apps/web`'s `package.json` (Vite 6, plugin-react 4) rather than the
starter's newer Vite 8, because that combination was verified building. Let
Renovate propose the bump.

---

## Standing constraints (not decisions — do not relitigate)

- **The product does not determine blame, guilt, legal responsibility, intent,
  or culpability.** This shapes the architecture, not just the wording. See
  `.claude/skills/evidence-framing`.
- **Never render or store raw concession/peatland boundary geometry.**
  Indonesian law restricts publishing plantation boundaries; attribute-only
  lookups. Spec v2 §2.
- **The console is fixture-driven.** `frontend/src/api/client.ts` mocks the
  UI spec §5 contract exactly so it can be swapped for real calls without
  touching callers. Keep that seam.
- **The demo must never blur real data and fixtures.** The one real dataset
  (2019 FIRMS haze export) sits behind its own labelled toggle.
