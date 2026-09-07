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

```bash
cd infra
./scripts/build_lambda.sh        # re-run whenever backend/ changes
terraform plan
terraform apply
curl "$(terraform output -raw api_health_url)"   # -> {"status":"ok"}
```

`terraform apply` creates real, billable AWS resources — confirm with the
user before running it. `plan`, `validate`, and `fmt` are safe.

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
| Apply wants to replace everything | Someone else applied against their own local state. Move state to the S3 backend in `versions.tf`. |
| 404 on a route that exists in Flask | The blueprint mounts at `/api`; the URL is `<api_base_url>/api/<route>`. |

## When changing infra

- Run `terraform fmt` and `terraform validate` before committing.
- Keep `.terraform.lock.hcl` tracked; keep `*.tfvars`, state, and
  `infra/build/` untracked.
- New runtime dependencies go in `backend/pyproject.toml`, not into the build
  script.
- New IAM permissions get their own scoped policy attached to
  `aws_iam_role.api` — don't widen the basic execution role.
