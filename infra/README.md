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
| `versions.tf` | Terraform/provider version pins; commented S3 remote-state block |
| `providers.tf` | AWS provider, default tags applied to every resource |
| `variables.tf` | Region, environment, Lambda sizing, CORS origin, Flask secret |
| `api.tf` | IAM role, log groups, Lambda function, HTTP API, routes, permission |
| `outputs.tf` | API base URL, health URL, function name, log group |
| `scripts/build_lambda.sh` | Assembles the deployment payload at `build/lambda/` |

## Deploying

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

**Timeout is 29s.** API Gateway HTTP API cuts the response off at 30s
regardless, so a longer Lambda timeout only bills for work no client is still
waiting on. Anything genuinely long-running (agent rounds, imagery
acquisition) needs a different shape — queue plus a worker — not a bigger
number here.

**State is local.** Fine for one person on a hackathon clone; uncomment the
S3 backend in `versions.tf` before a second person runs `apply`, or you will
have two state files racing over the same resources.

## Not built yet

- **Frontend hosting.** The console is a static Vite build (`frontend/dist`).
  S3 + CloudFront is the natural fit and is a separate, additive module —
  deliberately left out rather than guessed at, since it drags in bucket
  policy, cache behaviour, and possibly a domain.
- **Secrets.** `flask_secret_key` is a Terraform variable, so its value lands
  in state in plain text. Acceptable for a dev stack with a placeholder
  value; move to AWS Secrets Manager (read at runtime, IAM-scoped to this
  role) before it protects anything.
- **Ingestion.** The cron-triggered FIRMS poller from the spec is not here.
  It is an EventBridge schedule plus its own Lambda plus storage (DynamoDB or
  S3), and none of that has been decided yet — see `../data_pipeline`, which
  is still a feasibility spike.
