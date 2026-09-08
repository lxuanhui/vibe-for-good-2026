# Decision log

Newest first. Each entry records what was decided, why, and what was rejected
— including approaches that were tried and abandoned, which are usually the
more valuable half.

---

## 2026-09-08 — Events move behind the API; the FIRMS export deliberately does not

**Status:** done · PR #49

**Decision.** `GET /api/events` and `GET /api/events/{id}` are served by Flask
from `backend/app/data/events.json`. `client.ts` calls them with `fetch()`.
The 3.7 MB FIRMS export stays a static file served from `frontend/public/`.

**Why events first.** It is the smallest change that proves the whole path —
browser, Vite proxy, Flask, and the deployed Lambda — and everything else
(overlays, the report endpoint, a real agent loop) needs a working event
lookup to hang off. No new credentials, no new AWS resources.

**Why FIRMS stays static.** Routing 3.7 MB of GeoJSON through Lambda and API
Gateway would put it against the 6 MB response payload limit with no headroom,
add cold-start latency to a file that never changes, and bill egress per
request for bytes a CDN or static host serves for free. If it ever needs to
move, S3 is the destination, not the API. The layer stays behind its own
labelled toggle either way — which data is real and which is a fixture does
not change here.

**The events being served are still fixtures.** The endpoint is real; the data
is invented. Worth stating plainly because "served by the API" reads as "real"
and it is not.

**Spec discrepancy found.** UI spec §5 lists the status enum as
`AMBIGUOUS|REJECTED|STAGE2_RUNNING|CONVERGED`; `frontend/src/api/types.ts`
uses `AWAITING_REVIEW|STAGE1_REJECTED|STAGE2_RUNNING|CONVERGED`, and so does
the fixture data and the UI. The backend follows the frontend names, since
those are what actually exist on both sides. The spec is the stale one.

**Known duplication.** `frontend/src/api/fixtures/events.ts` still holds the
same three events, because `fixtures/overlays.ts` anchors its overlay geometry
to their coordinates. Move an event in one file and the other must follow or
overlays will sit away from the detection they describe. Both files say so.
This resolves itself when overlays move behind the API too.

---

## 2026-09-07 — Terraform state bucket stays on SSE-S3, not a customer managed key

**Status:** done · PR #48

**Decision.** Keep `sse_algorithm = "AES256"` on the state bucket and suppress
trivy's AWS-0132 inline, rather than moving to SSE-KMS with a CMK.

**Why.** The finding is real but it is a policy opinion, not a hole: the data
is encrypted at rest either way, and the rule is about who controls the key.
State does contain sensitive values (`flask_secret_key`), but the bucket is
private, versioned, has public access blocked, and lives in a single-tenant
account. A CMK would buy key rotation and an audit trail nobody here would
read, at the cost of a key policy that every principal touching state — the
CI role included — has to be granted against. That is a good trade for a
shared or multi-account setup and a bad one for this.

**How it is suppressed.** A `# trivy:ignore:AWS-0132` comment on the resource
with the reasoning above it, not a lowered severity threshold. The scan still
blocks on every other HIGH and CRITICAL; only this specific rule at this
specific resource is waived, and the waiver is visible in the file it applies
to.

**Revisit if** state is ever shared across accounts or teams.

---

## 2026-09-07 — Security scanning in CI: gitleaks over full history, audits that block only on runtime deps

**Status:** done · PR #34

**Decision.** A `Security` workflow with two independent jobs — gitleaks over
the entire commit history, and `npm audit` + `pip-audit` for known
vulnerabilities — on every PR, on `main`, and weekly.

**Why full history rather than the diff.** gitleaks scans commit patches, so
a credential that was committed and then deleted in a later commit is still a
finding. That is correct: it reached `origin`, so it is compromised regardless
of whether the file still exists at the tip. Diff-scoped scanning would call
that clean. The history is small — 14 commits reachable from `main`, ~9 MB of
patches, about 250 ms to scan — so there is no reason to narrow it.

Note that gitleaks covers what is *reachable in the clone*. CI's fresh clone
has only the PR ref and `main`, where a local checkout also has stale
remote-tracking branches; a local run therefore reports a higher commit count
(24 here) than CI does. Nothing is missed by this: branches are squash-merged
and deleted, so their original commits do not survive on `origin`.

**Why the binary and not `gitleaks/gitleaks-action`.** The action is free for
personal accounts but requires a `GITLEAKS_LICENSE` secret under an
organization. This repo is user-owned today; if it ever moves to an org, a
pinned binary keeps working and the action would start failing for a reason
that has nothing to do with the code. The download is checksum-verified
against the release's own `checksums.txt` — that catches a corrupted or
substituted download, not a compromised release, which is the honest limit of
what it buys.

**Why the npm audit is split in two.** The blocking step is
`--omit=dev`: an advisory in a runtime dependency ships to a user. The full
audit including dev dependencies runs `continue-on-error` for visibility —
Vite and oxlint are build-time only, and an advisory in a bundler should not
block a docs PR at a hackathon. Both were clean when this landed.

**Rejected: GitHub's native secret scanning and push protection.** Both are
disabled on this repo and cannot be enabled — for a private repository they
are a GitHub Advanced Security feature, not available on a free personal
account. Same class of limitation as the auto-merge finding above.

**Note.** GitGuardian already posts a "GitGuardian Security Checks" status on
pull requests, so there is deliberate overlap on the secrets question. That
scanner belongs to an installed app and can be removed by whoever installed
it; the gitleaks job is in this repository, runs on a schedule, and covers
history rather than the PR diff. The overlap is cheap and the failure modes
differ.

---

## 2026-09-07 — Renovate: bump open Python ranges, and track the Terraform CLI pin

**Status:** done · PR #33

**Decision.** Set `rangeStrategy: "bump"` for the `pep621` and
`pip_requirements` managers, and add a `customManagers` regex entry for
`TF_VERSION` in `.github/workflows/infra.yml`.

**Why.** Both were silent failures rather than visible ones, which is the
worst kind of dependency config. Renovate's default range strategy leaves a
constraint alone as long as the installed version still satisfies it, so
`flask>=3.1.0` in `backend/pyproject.toml` and `pandas>=2.0` in
`data_pipeline/requirements.txt` would never have produced a single PR —
Flask 3.2 satisfies `>=3.1.0`. Neither Python project has a lockfile, so the
range is the only place a version is written down; if Renovate does not move
it, nothing does. Separately, the `github-actions` manager updates `uses:`
refs but not workflow inputs, so `TF_VERSION: '1.16.0'` — the Terraform that
actually runs the apply, and the version we deliberately chose for native S3
state locking — was tracked by nothing.

**Rejected.** Pinning the Python deps to exact versions instead. It would
make Renovate work by default, but `backend/pyproject.toml` is a library-style
`[project].dependencies` list installed into Lambda by
`scripts/build_lambda.sh`, and exact pins there would fight the reproducible
build rather than help it. The bundle's determinism comes from
`--platform manylinux2014_aarch64` and the post-install cleanup, not from
pinning.

**Consequence.** The Terraform CLI update is explicitly `automerge: false`.
A PR that bumps it changes the binary that applies infrastructure on merge to
`main`; a human reads that plan.

**Not done: repository auto-merge.** The existing `automerge: true` rule for
dev-only patch updates would ideally use GitHub's native auto-merge, but
`PATCH /repos/.../` with `allow_auto_merge=true` returns 200 and the field
stays `false` — native auto-merge is not available for a private repo on a
free personal account, and the API declines silently rather than erroring.
Renovate falls back to merging through the API itself, which works, so the
rule is functional. If the repo goes public or the account is upgraded, flip
the setting; nothing in the config needs to change.

**Note.** Renovate had never actually run — there was config but no installed
app. The Renovate GitHub App must be installed on the repository for any of
this to take effect.

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
