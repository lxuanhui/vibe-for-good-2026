# Environments

This repository is private; operational identifiers are recorded here so
nobody has to go digging. Nothing on this page is a credential.

## dev (the only environment)

| | |
|---|---|
| AWS account | `424609180893` (no account alias set) |
| Region | `ap-southeast-1` (Singapore — closest to the Indonesian data and users) |
| Deployed by | `.github/workflows/infra.yml` on merge to `main` |
| API base | `https://g1g4hhe8m7.execute-api.ap-southeast-1.amazonaws.com/` |
| Health | `https://g1g4hhe8m7.execute-api.ap-southeast-1.amazonaws.com/api/health` |
| Lambda | `vibe-for-good-2026-dev-api` (python3.13, arm64, 512 MB, 29s) |
| Logs | `/aws/lambda/vibe-for-good-2026-dev-api`, `/aws/apigateway/vibe-for-good-2026-dev-api` (14-day retention) |
| Terraform state | `s3://vibe-for-good-2026-tfstate-apse1/infra/terraform.tfstate`, native `use_lockfile` |
| CI role | `vibe-for-good-2026-github-actions` (assumed over OIDC) |

The `environment` Terraform variable defaults to `dev` and feeds every
resource name, so a second environment is `-var environment=staging` plus a
separate state key — not a fork of the config.

## Local AWS credentials

The stack was first applied from a laptop using whatever profile the shell had
active — `AWS_PROFILE=kino`, a long-lived IAM user access key in
`~/.aws/credentials`, resolving to `arn:aws:iam::424609180893:user/kino`.

Two things follow:

- **CI does not depend on that.** GitHub assumes the OIDC role in the account
  directly, so deploys keep working regardless of anyone's local profile.
- Before applying by hand, check which account you are actually pointed at:
  `aws sts get-caller-identity`. There are several profiles on that machine
  and the active one is set by an environment variable, which is easy to miss.

Moving the project to a different AWS account means: `terraform destroy` on
`infra/` then `infra/bootstrap/`, re-apply under the new profile, and update
the `AWS_ROLE_ARN` repository variable. Cheap early, expensive later.

## GitHub configuration

Settings → Secrets and variables → Actions:

| Kind | Name | Required | Purpose |
|---|---|---|---|
| Variable | `AWS_ROLE_ARN` | yes | Role assumed over OIDC. Set. |
| Variable | `CORS_ORIGINS` | no | Origin the console is served from; defaults to `*` |
| Secret | `FLASK_SECRET_KEY` | no | Lambda's `SECRET_KEY`; defaults to `dev` |

**No AWS access keys, by design** — the whole point of the OIDC role. If
`AWS_ACCESS_KEY_ID` ever appears in this repo's settings, something has gone
wrong. See the root `.env.example` for the full credential index.

## Not deployed

- **The frontend.** No hosting exists yet; the console runs locally on `:5173`.
  S3 + CloudFront is the natural fit and is additive.
- **Ingestion.** The cron FIRMS poller implied by `Environmental_Assurance_Spec.md`
  §7–8 (data sources, persistence architecture) is unbuilt — EventBridge plus
  its own Lambda plus storage, none of it decided. `data_pipeline/` is still a
  feasibility spike that writes to no database.
- **Real API endpoints.** The Flask app serves `/api/health` and `/api/hello`
  only. Everything in `Environmental_Assurance_Spec.md` §24 (API) is still
  mocked in the frontend.
