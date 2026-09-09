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
| Console | Amplify app `vibe-for-good-2026-dev-console`, id `dz8w2n4hd2d22`. Terraform creates the app; the repository, the `main` branch and previews are connected by hand (see below). |
| Console URL | `https://main.dz8w2n4hd2d22.amplifyapp.com` (live) |

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

## Signing in to the AWS console

Access keys and a console password are different credentials, and this account
started with only the first. As of 2026-09-09 neither IAM user had a login
profile:

| Principal | Console password | Notes |
|---|---|---|
| `kino` | none | `AdministratorAccess`, no MFA — access keys only, which is what the laptop and every `terraform apply` here uses |
| `lxuanhui` | none | created 2023, unused |
| Root | yes | MFA enabled |

The trap is that this reads as a permissions problem and is not one. `kino` is
already an administrator; it simply has no password to sign in with. Adding
Amplify permissions, or any other policy, does nothing for it.

Root is therefore the only way into the console until that is fixed, and
fixing it is a one-time job:

1. Sign in as root.
2. IAM → Users → `kino` → Security credentials → **Enable console access**,
   set a password.
3. Assign an MFA device to `kino` while you are on that page.
4. Sign out. From then on, sign in as an IAM user against account
   `424609180893` and leave root alone.

Root is worth avoiding for routine work: it cannot be scoped, restricted or
handed to CI, and every action it takes is indistinguishable from every other.
The only tasks that genuinely need it are account-level ones — billing,
closing the account, and exactly this bootstrap.

## Connecting the console to GitHub

Amplify builds nothing until the repository is connected, and that connection
is deliberately not in Terraform. `CreateApp` rejects a repository with no
credential — "You should at least provide one valid token" — and the only way
to satisfy it is a personal access token, which would then sit in the state
file in S3. This stack has no long-lived credential anywhere; CI assumes a role
over OIDC so that none is needed. The connection is a manual step instead.

Once per account, after the first apply. This is a console task, so it needs a
principal that can sign in — see the section above if that is currently only
root:

1. [The app in the Amplify console](https://ap-southeast-1.console.aws.amazon.com/amplify/apps/dz8w2n4hd2d22)
   (also the `console_app_id` Terraform output, if the id ever changes).
2. **Connect a repository** → GitHub → authorize the AWS Amplify GitHub App.
   The authorization is between GitHub and Amplify; no token reaches this repo
   or Terraform.
3. Pick `lxuanhui/vibe-for-good-2026`, branch `main`.
4. Leave the build settings alone — the build spec comes from Terraform, and
   editing it in the console makes the two disagree.
5. Enable **auto-build** on `main` and **pull-request previews**. These are not
   in Terraform: the wizard creates the branch, so a branch resource in HCL
   would collide with it.

Terraform ignores later changes to `repository` and the token attributes, so
the next plan does not strip any of this.

## After any Amplify console change: re-apply, then rebuild

The connect-repository wizard replaced the app's entire environment-variable
map with its own defaults. `VITE_API_BASE_URL` disappeared, the Node pin was
overwritten with Amplify CLI `latest`, and the build that followed shipped a
console that loaded correctly and could not reach the API at all —
`client.ts` falls back to `API_BASE = ''`, so every request went to the Amplify
origin and 404'd. A green build serving an inert app is the worst shape this
failure could take, because nothing looks wrong.

So, after touching anything in the Amplify console:

```bash
gh workflow run Infra --ref main        # restores the Terraform-managed settings
aws amplify start-job --region ap-southeast-1 \
  --app-id dz8w2n4hd2d22 --branch-name main --job-type RELEASE
```

The second command is not optional. Vite bakes `VITE_*` in at build time, so
restoring the variable does nothing until something rebuilds. The repository
connection survives the apply — `ignore_changes` covers `repository` and the
token attributes.

To check it actually worked, look for the API host in the shipped bundle
rather than trusting the build status:

```bash
curl -s https://main.dz8w2n4hd2d22.amplifyapp.com/ \
  | grep -oE '/assets/[A-Za-z0-9._-]+\.js'         # find the bundle
curl -s https://main.dz8w2n4hd2d22.amplifyapp.com/assets/<that>.js \
  | grep -o 'execute-api[^"]*'                      # must not be empty
```

## GitHub configuration

Settings → Secrets and variables → Actions:

| Kind | Name | Required | Purpose |
|---|---|---|---|
| Variable | `AWS_ROLE_ARN` | yes | Role assumed over OIDC. Set. |
| Variable | `CORS_ORIGINS` | no | Origin the console is served from; defaults to `*` |
| Secret | `FLASK_SECRET_KEY` | no | Lambda's `SECRET_KEY`; defaults to `dev` |
| Secret | `NASA_FIRMS_MAP_KEY` | no | Server-side key for `GET /api/firms/live`. Unset leaves the landing map's live regional layer reporting itself unavailable |

**`NASA_FIRMS_MAP_KEY` is a GitHub *secret*, never an Amplify variable.** A
FIRMS MAP_KEY cannot be restricted to a domain, and Amplify variables named
`VITE_*` are inlined into the public bundle by Vite — so setting it there
publishes it. It reaches the Lambda through `TF_VAR_nasa_firms_map_key` in the
Infra workflow, the same route `FLASK_SECRET_KEY` takes.

**No AWS access keys, by design** — the whole point of the OIDC role. If
`AWS_ACCESS_KEY_ID` ever appears in this repo's settings, something has gone
wrong. See the root `.env.example` for the full credential index.

## Not deployed

- **Ingestion.** The cron FIRMS poller implied by `Environmental_Assurance_Spec.md`
  §7–8 (data sources, persistence architecture) is unbuilt — EventBridge plus
  its own Lambda plus storage, none of it decided. `data_pipeline/` is still a
  feasibility spike that writes to no database.
- **Most API endpoints.** Live: `/api/health`, `/api/hello`, the flat
  `/api/events` pair, and `GET /api/audits/{id}/events`, which serves a
  committed artifact. The rest of `Environmental_Assurance_Spec.md` §24 (API)
  — overlays, reports, the agent loop — is still mocked in the frontend.
