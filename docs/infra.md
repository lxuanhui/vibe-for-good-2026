# Infrastructure and what it costs

Every AWS service this project runs, why it is there, and what it actually
costs. `infra/README.md` says how the stack works and how to change it; this
file says what is switched on and what the bill looks like.

Kept honest by measurement, not estimation: the "observed" column is real
Cost Explorer data for the account, not a model. Where a figure is a forward
estimate — a service too new or too idle to have billed yet — it says so.

**Region:** `ap-southeast-1` (Singapore). **Account:** `424609180893`.
**Last measured:** 2026-09-09, against 2026-09-01 → 2026-09-10 usage,
extrapolated to 30 days.

## What this project runs

All of it is declared in Terraform. Two stacks: `infra/` (applied by CI on
merge to `main`) and `infra/bootstrap/` (applied by hand, holds the state
bucket and the CI role).

| Service | Resource | Why | Observed / month |
|---|---|---|---|
| **Lambda** | `vibe-for-good-2026-dev-api` — python3.13, arm64, 512 MB, 29 s | The Flask API. Nothing to keep warm between demo runs | **$0.00** |
| **API Gateway** | HTTP API, `ANY /{proxy+}` | Fronts the Lambda. HTTP API, not REST — roughly a third the price | **$0.0001** |
| **DynamoDB** | `vibe-for-good-2026-dev-audit-state`, PAY_PER_REQUEST | Audit session state. Lambda serves later calls from a different warm container, so process memory lost the scope | **$0.00** (created 2026-09-09; est. **< $0.05**) |
| **Amplify Hosting** | `console` app + PR previews | The frontend, and a preview per pull request | **$0.02** |
| **CloudWatch Logs** | 2 groups, 14-day retention, ~11 KB stored | Lambda and API Gateway logs. Retention is explicit so the groups die with the stack | **$0.00** |
| **S3** | `vibe-for-good-2026-tfstate-apse1` — versioned, encrypted, lifecycle-expired | Terraform state. Not application storage | **$0.01** |
| **IAM** | 3 roles + inline policies, 1 OIDC provider | CI authenticates over OIDC; there are no access keys in this repo by design | free |

**Total for this project: about $0.03/month**, and most of that is Amplify
build minutes. At demo traffic every metered service sits inside its free
tier or rounds to zero. Lambda's 1M requests / 400k GB-s per month is
perpetual, not a 12-month trial, so this does not become expensive when the
account's first year ends.

### What would actually change the bill

Only three things, in order of likelihood:

1. **Amplify build minutes** — every pull request builds a preview. Dozens of
   PRs in a day is still cents, but it is the only line that scales with how
   hard we are working rather than with traffic.
2. **DynamoDB on-demand** at real audit volume. On-demand is right while usage
   is spiky and near zero; it is the *wrong* mode under sustained load, where
   provisioned capacity is severalfold cheaper. Approximate published
   `ap-southeast-1` rates: ~$1.42 per million writes, ~$0.28 per million
   reads, ~$0.285/GB-month. Verify against the AWS calculator before relying
   on them.
3. **Lambda duration** if the Investigator/Skeptic loop starts calling an LLM
   per event. That is a model-provider bill first and a Lambda bill second,
   and neither is in this table yet.

Nothing here is always-on. There is no NAT gateway, no load balancer, no RDS,
no provisioned concurrency — the four usual ways a serverless project starts
costing real money.

## Also in this account, and not ours

The account is shared, and the majority of the bill is not this project:

| Service | What | Est. / month |
|---|---|---|
| VPC — public IPv4 address | One in-use address, charged hourly since AWS began billing them | **$3.18** |
| EC2 — EBS `gp3` | One 16 GB volume, attached | **$1.34** |
| Secrets Manager | Stored secrets | **$0.35** |
| ECR | A container image | **$0.01** |

These belong to **`i-03d53840a3553a537` (`anvil-api`, `t4g.small`, running
since 2026-07-23)** — an instance that predates this project and is not in
either Terraform stack. August's full-month total for the account was
**$6.18**, of which this project accounted for roughly a cent.

Recorded here only so the next person reading a bill does not conclude the
console is expensive, or start deleting things to find out. It is somebody's
running workload; leave it alone unless its owner says otherwise.

## Keeping this current

Re-measure when a service is added or removed, not on a schedule — a cost
doc nobody trusts is worse than none:

```bash
aws ce get-cost-and-usage --region us-east-1 \
  --time-period Start=<month-start>,End=<today> \
  --granularity MONTHLY --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --query 'ResultsByTime[0].Groups[?Metrics.UnblendedCost.Amount!=`0`].[Keys[0],Metrics.UnblendedCost.Amount]' \
  --output text | sort -k2 -rn
```

Add `--group-by Type=DIMENSION,Key=USAGE_TYPE` with a `--filter` on one
service to find out what a surprising line item actually is; that is how the
$3.18 above was identified as a public IPv4 address rather than "some VPC
thing".

The standing constraint is in `CLAUDE.md`: serverless by default, and
anything always-on needs justification before it is switched on. Adding a
service means adding a row here in the same pull request.
