# Infrastructure and what it costs

Every AWS service this project runs, why it is there, and what it actually
costs. `infra/README.md` says how the stack works and how to change it; this
file says what is switched on and what the bill looks like.

Kept honest by measurement, not estimation: the "observed" column is real
Cost Explorer data for the account, not a model. Where a figure is a forward
estimate — a service too new or too idle to have billed yet — it says so.

**Region:** `ap-southeast-1` (Singapore). **Account:** `424609180893`.
**Last measured:** 2026-09-15, against 2026-09-01 → 2026-09-15 usage.
The hackathon ended on 2026-09-14; see "After the hackathon" at the end for
what was switched off that day and why.

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
| **Amplify Hosting** | `console` app, `main` branch only | The frontend. Pull-request previews were switched off on 2026-09-15 (see below); hosting itself is cents, build minutes were $2.97 for the hackathon fortnight | **$0.02** hosting |
| **CloudWatch Logs** | 3 groups, 14-day retention, ~11 KB stored | Both Lambdas and API Gateway. Retention is explicit so the groups die with the stack | **$0.00** |
| **S3** | `vibe-for-good-2026-tfstate-apse1` — versioned, encrypted, lifecycle-expired | Terraform state. Not application storage | **$0.01** |
| **S3** | `vibe-for-good-2026-dev-cache-<account>` — encrypted, public access blocked, objects expire after a day | The shared copy of `GET /api/firms/live`'s 15-minute cache, so a cold Lambda container reads ~100 KB from S3 instead of refetching from NASA. One object, overwritten every refresh; the spec's disposable-cache role | not yet billed (created 2026-09-10); est. **< $0.01**: one PUT per refresh and one GET per cold start at $0.005 and $0.0004 per thousand, ~0.1 MB stored |
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
   matters. The Lambda share of the same request is a rounding error beside
   it.

   The prefix every one of the four calls repeats (system framing, evidence
   pack, hypotheses) is sent behind a Bedrock cache point (#147). Cache
   reads bill at $0.10/1M against $1.00/1M fresh, cache writes at $1.25/1M.
   The two roles of a round run in parallel and a cache entry is readable
   only once the response that wrote it has begun, so per assessment that
   is **two writes and two reads, not one write and three reads**. Measured
   on 2026-09-10 through the production adapter (`bedrock_runner` with the
   real 128-object pack for the demo event, Haiku 4.5, `max_rounds=2`, four
   calls per assessment), which corrects the per-call figure above: the
   real prefix is ~36k tokens, not ~19k, so the uncached baseline is nearer
   $0.20 than $0.15.

   | Assessment | Fresh input | Cache write | Cache read | Output | Wall | Cost |
   |---|---|---|---|---|---|---|
   | Uncached (`BEDROCK_PROMPT_CACHE=0`) | 152,422 | 0 | 0 | 8,900 | 41.8s | ~$0.20 |
   | Cached, first in 5 min | 7,526 | 72,488 | 72,488 | 9,094 | 33.3s | ~$0.15 |
   | Cached, second within 5 min | 7,446 | 0 | 144,976 | 8,904 | 36.5s | ~$0.07 |

   Per call: round 1 sends 34 fresh tokens and writes 36,244; round 2 sends
   ~3.7k fresh (the round-1 output it reasons over) and reads 36,244. The
   input side of the bill falls from ~$0.152 to ~$0.105 on a cold cache and
   to ~$0.022 when a second assessment lands inside the 5-minute TTL, which
   is the demo pattern; output tokens are now the larger share of the bill.
   The issue's ~$0.09 assumed the one-write case; reaching it means running
   round 1 sequentially, ~9s more on the job, which was not taken (decision
   log, 2026-09-10, prompt caching). These are local runs through the
   deployed code path, not worker-log figures: no deployed assessment had
   run when they were taken. Each deployed call logs its `usage` including
   `cacheReadInputTokens` and `cacheWriteInputTokens` at INFO in the
   worker's log group, so the first real assessments can be checked against
   this table.

   The structural risk is not the model, it is a retry loop: an unbounded
   poll or auto-retry re-triggering analysis would multiply this line
   silently. `GET .../analyse` therefore only reads, and a job already
   RUNNING is returned rather than started again.

Nothing here is always-on. There is no NAT gateway, no load balancer, no RDS,
no provisioned concurrency — the four usual ways a serverless project starts
costing real money.

## Also in this account, and not ours

The account is shared. Until 2026-09-15 the majority of the bill was not this
project: **`i-03d53840a3553a537` (`anvil-api`, `t4g.small`)**, an instance
that predated this project and was in neither Terraform stack, cost about
$5/month, and none of it was compute. The `t4g.small` was free-tier; the bill
was its public IPv4 address (~$3.18) and 16 GB `gp3` root volume (~$1.34),
both charged whether the instance ran or not, so stopping it would have
saved nothing. August's full-month total for the account was **$6.18**, of
which this project accounted for roughly a cent.

The owner had it torn down on 2026-09-15 (instance, Elastic IP, security
group, key pair, ECR repository, instance profile and role). A snapshot of
its root volume, `snap-04c770acc524da7bb`, is kept as the only backup, at
about $0.08/month; delete it when nobody wants the app back.

Still here and not ours: one Secrets Manager secret in `us-east-1`
(`kino/github-token`, ~$0.40/month), which belongs to the account owner.

## After the hackathon

The hackathon ended on 2026-09-14. Everything this project runs is metered,
so at idle it costs about $0.03/month and nothing was worth destroying, but
one thing was worth trimming and one alert is worth understanding.

**Trimmed on 2026-09-15:** Amplify pull-request previews on `main` are off
and the stale `pr-255` and `pr-262` preview branches are deleted. Build
minutes were the only line that scaled with how hard we worked (294 minutes,
$2.97, in the hackathon fortnight) and previews were most of them. This is
set in the Amplify console, not Terraform (`infra/console.tf` explains why
there is no branch resource), so an apply will not turn it back on; re-enable
it from the app's branch settings if PR previews are wanted again.

**Not destroyed, on purpose:** the Lambdas, API Gateway, DynamoDB table, S3
cache and Amplify app. They bill nothing at idle and the console URL is the
thing people will follow from the submission. Bedrock is the one line a
visitor can spend: ~$0.07 to $0.20 per assessment, only when someone clicks
Analyse, and `GET .../analyse` never re-triggers a running job. If that ever
matters, `terraform destroy` on `infra/` removes the API and worker, and the
`Infra` workflow has to be disabled in the same breath or the next merge
recreates them.

**The budget alert.** Both account budgets (`anvil-monthly` at $15,
`kino-monthly` at $10) fired on 2026-09-14 with a *forecast* of $82.81 for
September. Daily spend tells the real story: a flat $0.19/day baseline
(anvil-api) all month, then $3.07, $9.57 and $0.92 on 2026-09-09, 10 and 11
from Bedrock assessments and Amplify builds during the final push, then back
to $0.19/day. The forecaster extrapolated the spike. Actual month-to-date on
2026-09-15 was $16.14; AWS's own forecast had already fallen to $22.85, and
with anvil-api gone the baseline is nearer $0.01/day. A forecast alert the
day after a burst of work is expected, and is not a sign that something is
still running.

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
