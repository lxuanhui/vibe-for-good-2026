# Infrastructure

Terraform for the AWS side of the Environmental Assurance Console. The Flask
API in [`../backend`](../backend) runs as a single Lambda behind an API
Gateway HTTP API; there is no server to keep warm and nothing to pay for
between demo runs.

```
Browser ──▶ API Gateway HTTP API (ANY /{proxy+})
                   │  payload format 2.0
                   ▼
             Lambda (python3.13, arm64)
                   │  apig-wsgi
                   ▼
             Flask app  (app.create_app, blueprint at /api)
```

## Layout

| File | Contents |
|---|---|
| `bootstrap/` | Applied once by hand: the S3 state bucket and the GitHub OIDC role CI assumes |
| `versions.tf` | Terraform/provider version pins; S3 remote-state backend |
| `providers.tf` | AWS provider, default tags applied to every resource |
| `variables.tf` | Region, environment, Lambda sizing, CORS origin, Flask secret |
| `api.tf` | IAM role, log groups, Lambda function, HTTP API, routes, permission |
| `outputs.tf` | API base URL, health URL, function name, log group |
| `scripts/build_lambda.sh` | Assembles the deployment payload at `build/lambda/` |

## Deploying

**Normally you don't.** Merging a change to `infra/**` or `backend/**` into
`main` applies it — see [Pipeline](#pipeline) below. A pull request touching
those paths gets a plan posted as a PR comment; nothing is applied until it
merges.

To apply by hand (same state, so this and CI cannot diverge):

```bash
./scripts/build_lambda.sh          # vendor deps + entrypoint into build/lambda
terraform init                     # first time only
terraform plan
terraform apply
curl "$(terraform output -raw api_health_url)"   # -> {"status":"ok"}
```

Re-run `build_lambda.sh` whenever anything under `backend/` changes.
Terraform hashes the built directory, so an apply with no source change is a
no-op.

### One-time bootstrap

`infra/bootstrap/` creates the two things the main stack and the pipeline
cannot create for themselves: the S3 bucket holding the main stack's state,
and the IAM role GitHub Actions assumes. It keeps **local** state, because it
owns the bucket the remote state lives in.

```bash
cd bootstrap
terraform init && terraform apply
gh variable set AWS_ROLE_ARN --body "$(terraform output -raw github_actions_role_arn)"
```

It is idempotent and already applied for this account. `create_oidc_provider`
defaults to `false` — AWS permits exactly one GitHub OIDC provider per
account and most accounts already have one; set it `true` only in a fresh
account.

## Pipeline

`.github/workflows/infra.yml`:

| Trigger | What happens |
|---|---|
| PR touching `infra/**`, `backend/**` | fmt check, init, validate, plan; plan posted as a PR comment and job summary |
| Push to `main` on those paths | the same, then `apply` of that exact plan, then a health-check curl |
| `workflow_dispatch` | manual run |

Auth is GitHub OIDC into `vibe-for-good-2026-github-actions` — no AWS keys
are stored in the repo. The role is scoped to this repository, and within it
to `refs/heads/main` and pull requests, so a random branch cannot assume it.
The role ARN lives in the `AWS_ROLE_ARN` repository variable.

`concurrency: terraform-infra` serialises runs so they queue for the state
lock instead of failing on it, and `cancel-in-progress` is false because
cancelling mid-apply leaves the lock held and the state half-written.

Optional repo config: `FLASK_SECRET_KEY` (secret) and `CORS_ORIGINS`
(variable). Both fall back to the defaults in `variables.tf` when unset, so
CI and a laptop apply produce identical config rather than fighting over the
Lambda environment on each run.

Tail logs with:

```bash
aws logs tail "$(terraform output -raw lambda_log_group)" --follow
```

Tear the stack down with `terraform destroy` — both log groups are managed
here specifically so they go with it.

## Decisions worth knowing before you change something

**One Lambda, not one per route.** Routing already exists inside Flask.
Splitting the blueprint across functions would buy nothing and multiply cold
starts.

**CORS is owned by Flask, not API Gateway.** `aws_apigatewayv2_api` has no
`cors_configuration` block on purpose. `flask-cors` already sets the headers;
configuring it in both places makes API Gateway append a second
`Access-Control-Allow-Origin`, and a browser rejects a response carrying two
of them — which presents as CORS being broken rather than double-configured.
Set the allowed origin through the `cors_origins` variable.

**arm64.** Graviton is cheaper per GB-second and every dependency is pure
Python. `build_lambda.sh` pins wheels to `manylinux2014_aarch64` rather than
whatever the developer's laptop is, so a compiled dependency added later
fails at build time instead of at the first invocation.

**The bundle must be byte-identical across machines.** Terraform hashes the
built directory, so if a laptop and a runner disagree, every plan reports a
Lambda update and no plan is ever clean — which destroys the value of the
plan posted on each PR. Three things in `build_lambda.sh` exist only to
protect that, and should not be "tidied away":

- `bin/` is deleted. pip generates console-script wrappers whose shebang
  names the interpreter that ran it (`/opt/homebrew/...` vs
  `/opt/hostedtoolcache/...`). Lambda never runs them.
- `../../bin/` lines are stripped from each `RECORD`, since they carry those
  scripts' hash and size.
- The backend is **copied in, not pip installed.** Installing it would build
  a wheel, pulling in whatever build-backend version pip resolved that day
  plus a `direct_url.json` recording the mktemp path it was built in.
  Dependencies still come from `pyproject.toml`, so there is one source of
  truth either way.

If you need to smoke-test the bundle by importing from it, copy it first —
running Python inside `build/lambda` writes `__pycache__` after the build
cleaned it, and silently changes the hash.

Dependency versions are unpinned (`flask>=3.1.0`), so a build resolving a
newer wheel legitimately changes the hash. That is a real change, and
Renovate is what proposes it.

**Timeout is 29s.** API Gateway HTTP API cuts the response off at 30s
regardless, so a longer Lambda timeout only bills for work no client is still
waiting on. Anything genuinely long-running (agent rounds, imagery
acquisition) needs a different shape — queue plus a worker — not a bigger
number here.

**State is remote, locked with `use_lockfile`.** That is S3-native locking
and needs Terraform >= 1.10; the old DynamoDB lock table was removed in 1.11,
so don't reintroduce one. A backend block cannot interpolate variables, so
the bucket name is a literal here and in `bootstrap/variables.tf` — change
both together.

**The CI role is service-scoped, not action-scoped.** It can manage Lambda,
API Gateway, logs, DynamoDB tables, and IAM roles whose names start with
`vibe-for-good-2026`, S3 buckets named `vibe-for-good-2026-*-cache-*`, plus
the state bucket. A main-stack change that needs a grant this role does not
have (a new service, a bucket outside that pattern) is a `bootstrap/` change
first, applied by hand, and only then a main-stack PR. That is deliberately looser than least privilege:
tightening it to individual actions is worth doing before this account holds
anything else, and splitting it into a read-only plan role and a write apply
role would be the next step after that.

## Not built yet

- **Frontend hosting.** The console is a static Vite build (`frontend/dist`).
  S3 + CloudFront is the natural fit and is a separate, additive module —
  deliberately left out rather than guessed at, since it drags in bucket
  policy, cache behaviour, and possibly a domain.
- **Secrets.** `flask_secret_key` is a Terraform variable, so its value lands
  in state in plain text — including when CI passes it from the
  `FLASK_SECRET_KEY` repository secret. Acceptable for a dev stack with a
  placeholder value; move to AWS Secrets Manager (read at runtime,
  IAM-scoped to this role) before it protects anything.
- **Ingestion.** The cron-triggered FIRMS poller from the spec is not here.
  It is an EventBridge schedule plus its own Lambda plus storage (DynamoDB or
  S3), and none of that has been decided yet — see `../data_pipeline`, which
  is still a feasibility spike.
