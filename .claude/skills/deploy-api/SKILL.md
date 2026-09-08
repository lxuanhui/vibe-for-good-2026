---
name: deploy-api
description: Build and deploy the Flask API to AWS Lambda, or diagnose a deployed API that is failing. Use for deploys, terraform plan/apply on infra/, checking Lambda logs, or when the console gets CORS errors, 502s, or import errors from the deployed backend.
---

# Deploying the API

The backend is one Flask app that runs two ways from the same
`app.create_app()` factory: `backend/wsgi.py` locally on :5001, and
`backend/lambda_handler.py` on Lambda via `apig-wsgi`. Full rationale in
`infra/README.md`.

## Deploy

**The pipeline deploys.** `.github/workflows/infra.yml` plans on any PR
touching `infra/**` or `backend/**` (posting the plan as a PR comment) and
applies on merge to `main`, then health-checks. Prefer landing a PR over
applying by hand — a manual apply from a laptop is invisible to reviewers.

Manual apply, same remote state:

```bash
cd infra
./scripts/build_lambda.sh        # re-run whenever backend/ changes
terraform plan
terraform apply
curl "$(terraform output -raw api_health_url)"   # -> {"status":"ok"}
```

`terraform apply` creates real, billable AWS resources — confirm with the
user before running it. `plan`, `validate`, and `fmt` are safe.

`infra/bootstrap/` (state bucket + GitHub OIDC role) is already applied and
is not part of the pipeline. Touch it only when the state bucket or CI role
needs changing, and apply it by hand.

## Diagnosing

```bash
aws logs tail "$(terraform output -raw lambda_log_group)" --follow
```

| Symptom | Most likely cause |
|---|---|
| `Runtime.ImportModuleError` | `build_lambda.sh` wasn't re-run, or a dependency was added to `pyproject.toml` without rebuilding. |
| Duplicate `Access-Control-Allow-Origin`, browser reports CORS failure | CORS got configured on `aws_apigatewayv2_api` as well as in flask-cors. Only Flask sets it — remove the `cors_configuration` block. |
| Works locally, `.so` / arch error on Lambda | A dependency with a compiled component was installed for the build machine. `build_lambda.sh` pins `manylinux2014_aarch64`; check the wheel actually exists for arm64. |
| 503/504 after ~30s | API Gateway HTTP API caps responses at 30s. Long work needs a queue plus a worker, not a bigger `lambda_timeout_seconds`. |
| Apply wants to replace everything | State is not being read — check the backend block resolves and the S3 bucket exists. |
| CI fails at `configure-aws-credentials` | The `AWS_ROLE_ARN` repo variable is unset, or the run is on a branch other than `main`/a PR, which the role's trust policy excludes. |
| CI fails holding a state lock | A previous run was cancelled mid-apply. Inspect, then `terraform force-unlock <id>` — never as a reflex. |
| 404 on a route that exists in Flask | The blueprint mounts at `/api`; the URL is `<api_base_url>/api/<route>`. |

## When changing infra

- Run `terraform fmt -recursive` and `terraform validate` before committing;
  CI checks both.
- Keep `.terraform.lock.hcl` tracked; keep `*.tfvars`, state, and
  `infra/build/` untracked.
- Terraform >= 1.10 is required (S3 native state locking).
- New runtime dependencies go in `backend/pyproject.toml`, not into the build
  script.
- New IAM permissions get their own scoped policy attached to
  `aws_iam_role.api` — don't widen the basic execution role.
