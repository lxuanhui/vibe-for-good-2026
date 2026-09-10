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
| **Lambda** | `vibe-for-good-2026-dev-analysis-worker` — same zip, handler `lambda_handler.analysis_worker`, 512 MB, 300 s | Runs Investigator/Skeptic analysis, which measures ~51s and cannot fit API Gateway's 30s response cap. Invoked async by the API; async retries are off so a failure is not billed three times | **$0.00** (created 2026-09-10; ~$0.02 per 1,000 assessments) |
| **API Gateway** | HTTP API, `ANY /{proxy+}` | Fronts the Lambda. HTTP API, not REST — roughly a third the price | **$0.0001** |
| **DynamoDB** | `vibe-for-good-2026-dev-audit-state`, PAY_PER_REQUEST | Audit session state, plus analysis job rows under a `job#<audit>#<event>` key. Lambda serves later calls from a different warm container, so process memory lost the scope | **$0.00** (created 2026-09-09; est. **< $0.05**) |
| **Amplify Hosting** | `console` app + PR previews | The frontend, and a preview per pull request | **$0.02** |
| **CloudWatch Logs** | 3 groups, 14-day retention, ~11 KB stored | Both Lambdas and API Gateway. Retention is explicit so the groups die with the stack | **$0.00** |
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
3. **Claude analysis calls** — the only line where a single click costs real
   money. Investigator/Skeptic analysis makes two structured rounds of two
   roles, four provider calls, per auditor request. Measured against the real
   evidence pack (19,075 input + ~3,500 output tokens per call) at published
   `ap-southeast-1` Bedrock on-demand rates on 2026-09-10:

   | Model | $/1M in | $/1M out | Per assessment | Entitled? |
   |---|---|---|---|---|
   | **Claude Haiku 4.5** (deployed) | $1 | $5 | **$0.15** | yes |
   | Claude Sonnet 5 | $2 | $10 | $0.29 | **no** |
   | Claude Opus 5 | $5 | $25 | $0.73 | **no** |
   | Amazon Nova Lite | $0.081 | $0.324 | $0.011 | not probed |

   The entitlement column is not a footnote — it is the difference between a
   model you can choose and one you cannot. Verified by real Converse calls on
   account 424609180893 in `ap-southeast-1` on 2026-09-10: the Claude 5 family
   returns `AccessDeniedException: "... is not available for this account"`, so
   the two cheapest-looking upgrades in this table cannot be switched to by
   changing `var.bedrock_model_id`. **Claude Sonnet 4.5 is entitled**, is
   the only alternative that can actually be selected today, and passes
   schema validation since the prompt states the unresolved-question rule
   (decision log, 2026-09-10, Sonnet 4.5 validates); its rate is not
   listed here because it was not verified against published pricing at the
   same time as the rest of the table, and an unverified number in a cost
   document is worse than an absent one. Background, and how to tell a wrong
   model ID from a missing entitlement, is in the decision log (2026-09-10,
   Bedrock).

   So ~$15 per 100 assessments. Cheaper models are not a saving here: the
   one tried below Haiku 4.5 (Gemma 3 27B) was slower and failed schema
   validation, and cost per *successful* assessment is the only figure that
   matters. The
   real lever is Bedrock prompt caching on the ~19k-token evidence prefix
   every one of the four calls repeats — cache reads are $0.10/1M against
   $1.00/1M, taking an assessment to roughly $0.09 with no quality tradeoff.
   Not built yet (#147); the Lambda share of the same request is a rounding
   error beside it.

   The structural risk is not the model, it is a retry loop: an unbounded
   poll or auto-retry re-triggering analysis would multiply this line
   silently. `GET .../analyse` therefore only reads, and a job already
   RUNNING is returned rather than started again.

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
