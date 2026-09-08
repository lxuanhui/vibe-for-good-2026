# Decision log

Newest first. Each entry records what was decided, why, and what was rejected
— including approaches that were tried and abandoned, which are usually the
more valuable half.

---

## 2026-09-09 — Terraform creates the Amplify app; a human connects the repo

**Status:** done · issue #96

**Decision.** `aws_amplify_app.console` is declared without `repository`, and
there is no `aws_amplify_branch` resource at all. Terraform owns the app's
name, build spec, SPA rewrite and environment variables. The GitHub
connection, the `main` branch, auto-build and pull-request previews are set
once by hand in the Amplify console.

**Why.** The first apply of the Amplify config failed twice on `main`. The
first failure was IAM: `infra/bootstrap` is applied by hand and had not been
re-applied after the `AmplifyConsoleHosting` statement was added, so the CI
role could not call Amplify at all. The second failure is the one that
mattered:

```
CreateApp, StatusCode: 400, BadRequestException:
You should at least provide one valid token
```

Amplify's API reference requires `accessToken` or `oauthToken` when a new app
names a repository. There is no token-free way to declare a connected
repository. So the choice was: put a GitHub personal access token in Terraform
state, or stop the configuration one step short of the connection.

**What was rejected.** Passing a PAT, sourced from a variable or from Secrets
Manager. Either way the value lands in the state file in S3. This stack has no
long-lived credential anywhere by design — GitHub authenticates to AWS over
OIDC precisely so that none is needed — and a hosting convenience is not worth
being the exception.

**What this costs.** Auto-build and pull-request previews are now console
checkboxes rather than declared HCL, so they are not reproducible from the
repository and a rebuild in a fresh account needs the walkthrough in
`docs/environments.md`. Previews were the reason Amplify beat S3 + CloudFront
and they still work; they are just configured by a person once. Terraform also
cannot manage the branch afterwards, because the connection wizard creates it
and an `aws_amplify_branch` would collide with what already exists.

---

## 2026-09-09 — The console is hosted on Amplify, not S3 + CloudFront

**Status:** done · issue #91

**Decision.** The React console deploys to AWS Amplify Hosting, app
`<project>-<env>-console`, branch `main`, with pull-request previews on. The
API stays where it is: Lambda behind API Gateway.

**Why not S3 + CloudFront**, which `docs/environments.md` had named as the
natural fit. Both serve from CloudFront, so what reaches a browser is the same.
The difference is what has to be written and operated: Amplify carries the SPA
rewrite, the managed certificate and the build in about 40 lines, against ~100
for a bucket, an origin access control, a distribution, custom error responses
and an invalidation step in CI. For a custom domain, CloudFront also needs its
ACM certificate in `us-east-1` while the rest of this stack is
`ap-southeast-1`, which is a well-known way to lose an evening.

**The deciding factor was pull-request previews.** `branch-and-pr` records that
every check in CI is static -- `npm run build` proves the console compiles,
nothing proves it runs -- and that this already cost the team once, when a
maplibre-gl major passed every check and then rendered nothing because Vite's
pre-bundler emitted a broken worker chunk. Two people driving separate agents
at the same frontend files (#75/#79 and #78 collided on four of them) need to
open each other's branch, not trust a green tick. Amplify gives a URL per PR;
S3 + CloudFront does not.

**Accepted cost: a second build system.** `npm run build` now runs in Amplify's
build container as well as in GitHub Actions. That is duplicated work and a
second place a build can fail differently. Taken deliberately -- the preview
URLs are the point, and the GitHub Actions build stays the one that gates a
merge.

**Rejected: putting a GitHub token in Terraform.** `aws_amplify_app` accepts
`oauth_token` or `access_token`, which would let Terraform connect the
repository unattended. It would also put a real credential in Terraform state,
in a repo whose whole authentication story is OIDC precisely so no long-lived
secret exists. The repository is connected once by hand through the Amplify
GitHub App instead, and `lifecycle.ignore_changes` keeps later plans from
stripping what the console sets.

**Deferred: narrowing CORS.** `cors_origins` stays `*`. The deliverable in #91
said narrow it, and the reason not to is that the final origin is not settled
-- a custom domain is still open -- and a wrong value fails silently in the
browser at exactly the wrong moment. The `console_url` output makes it a
one-line change once the domain is fixed.

**Note for whoever applies this.** The CI role had no Amplify permissions, so
`infra/bootstrap/` gains an `amplify:*` statement scoped to this account. That
config has its own state and is **not** applied by the pipeline: it must be
applied by hand, before the console PR merges, or the apply fails with
AccessDenied.

---

## 2026-09-09 - Review compression is scope-based, not Stage-1-based

**Status:** done · issue #80

Implements the measurement recorded in the 2026-09-08 entry below.

The console now treats Stage-1 as a classifier of fire support, not a promise
to remove FIRMS-only events from the review queue. The API derives the useful
progression from the committed artifact: FIRMS observations -> FireEvents,
then, only when a private audit boundary exists, FireEvents in scope plus the
context buffer -> review queue. Without a boundary the scope count and ratio
are `null`, rather than a misleading 1.0×.

**Rejected: adding context to Stage-1 to manufacture compression.** The 2019
haze artifact has 396 `LIKELY_FIRE`, 3,214 `AMBIGUOUS`, and zero
`LIKELY_NON_FIRE`; this is structural for FIRMS-only input. Context would
classify more events as fire-support and would not shrink the queue. Scope is
the actual product compression boundary, and priority ranking remains a
separate concern.
## 2026-09-08 — Stage-1 is a classifier, not the compressor; workload reduction comes from scope and ranking

**Status:** measured · issues #80 #83 #89 (#81 and #82 closed as duplicates)

**Decision.** The product's efficiency claim is observations → FireEvents →
in-scope (+ buffer) → ranked. Stage-1 triage is a *label* on that chain, not
a step in it. Do not try to make Stage-1 narrow the queue by adding context
fields, and do not present its 1.0× as a gap that more data would close.

**What was measured, on the committed 2019 artifact.** 20,471 detections
cluster to 3,610 events (5.7×). Stage-1 leaves 396 LIKELY_FIRE, 3,214
AMBIGUOUS and 0 LIKELY_NON_FIRE. The zero is structural: on FIRMS-only input
the highest non-fire score any event reaches is 2 (singleton +1, FRP ≤2 MW
+1) against a threshold of 4. Only a persistent-heat-source match or a
volcano within 3 km (+5 each) flips an event alone.

Supplying the context most likely to apply in dry-season Sumatra/Kalimantan
(vegetated ≥0.5 → +1, rainfall ≤2 mm → +1) would move ~979 events *into*
LIKELY_FIRE (396 → ~1,375) and leave the queue at 3,610, because LIKELY_FIRE
and AMBIGUOUS both stay in review. Stage-1 is a false-positive filter and
haze-season Indonesia has few false positives. That is the rules working.

A synthetic 30×30 km management unit at the densest cell plus a 10 km
buffer holds 80 events — 2.2% of the history, ~45×. Scope is the compressor
the product already designed (#56); the demo scope has no boundary, which is
why the console shows 1.0×.

**Rejected: tuning Stage-1 thresholds or adding rules to reach non-fire.**
Lowering `NON_FIRE_DECISION_THRESHOLD` so singleton + low-FRP qualifies would
label 337 real dry-season detections non-fire on no evidence. The rules are
right; the framing around them was wrong (#80).

**Rejected: tightening clustering to shrink the mega-events.** 22 events
with ≥100 observations hold 32% of all detections (largest: 1,103
observations, 107 h, 20.5 km, near Jambi) — transitive closure across the
peak week. A tighter radius would fragment genuine fire complexes and change
every downstream count. The review-unit problem is #82, solved by exposing
the complexity module's subclusters, not by re-clustering.

**Follow-through.** Ranking already runs inside PR #78's history adapter
(`compute_fire_complexity`, `compute_investigation_priority`), which degrades
honestly on FIRMS-only input — 40 of 100 weight evaluable, reported as
`evidence_coverage`. What is unsettled is *where* that runs: #89 measures the
Lambda bundle and chooses zip, container image, or EC2, and supersedes the
offline-artifact decision below if the adapter wins. #85 calibrates the
routing layer, #86 the clustering diagnostics, #83 points the benchmark at
the artifact instead of live FIRMS. Method for re-running the measurement is
in the `audit-artifact` skill.
## 2026-09-08 — Issue-first is part of `branch-and-pr`, not a second skill

**Status:** done · PR #77 · issue #76

**Decision.** "Open an issue before starting" is enforced in the existing
`branch-and-pr` skill, whose description now triggers loading before work
starts rather than only before merging.

**Why not a separate `issue-first` skill.** Issue → branch → PR → merge is one
workflow, and splitting it across two skills means one of them gets loaded and
the other does not — reliably the one that runs first, because a session
usually reaches for the skill when it is about to commit. A second skill would
also duplicate the branch-prefix table and the "two agents, one trunk"
rationale, which is how two documents start disagreeing.

**Why the rule exists.** Three failures in one session that it would have
caught: PR #74 implemented the backend half of #57 without referencing it,
leaving a stale checklist; issue #75 (map-first landing) contradicts the
register-before-map ordering in #57 and #58, which surfaced only by luck of
reading order; and `backend/app/audits.py` was clobbered because two
workstreams reached for the same filename with nothing signalling it was
taken.

**The rule names its own exceptions** — typos, fixing your own open PR,
Renovate bumps, and work the user asked for directly. A rule with no
exceptions gets ignored wholesale, and an issue-per-typo policy would be
ignored within a day. The exception for direct user requests is deliberately
narrow: the ask is the mandate, but an issue is still expected when the work
touches a surface the other person is building on.

**Rejected: GitHub issue templates.** They enforce shape, not the reading step
that actually matters, and the house format is already legible from the
existing issues. Rejected again: required-status or branch-protection rules to
enforce the link — unavailable on this plan for a private repo, returning 403
on every ruleset call.

---

## 2026-09-08 - Clustering runs offline; the API serves a committed artifact

**Status:** done · PR #74

`GET /api/audits/{id}/events` returns FireEvents derived from real FIRMS
observations: 20,471 detections in the 2019 haze window, clustered into 3,610
events and run through Stage-1 triage.

None of that runs in the request. `cluster_events` needs pandas, numpy and
scipy — about 200 MB unzipped, against Lambda's 250 MB ceiling — and the
derivation is identical for every caller, so paying for it per request buys
nothing. `data_pipeline/export_audit_events.py` runs it once and writes two
gzipped artifacts into `backend/app/data/`.

**Rejected: generating the artifacts in CI.** `triage_events` stamps every
evidence object with its retrieval time, so a re-export rewrites both files
byte-for-byte whether or not any derived value changed. Building them in CI
would churn the Lambda bundle's `source_code_hash` on every run and deploy a
"new" function that computes the same answers. They are committed instead;
re-exporting is a deliberate act, and its diff is expected to be total.

**Rejected: a container or an EC2 worker for the clustering.** Neither is
needed while the scope is fixed. When scopes become user-defined this has to
be reopened — clustering an arbitrary uploaded boundary cannot be precomputed
— and that is the point at which a container is worth its cost.

Both artifacts are gzipped: 23 MB of repetitive JSON becomes 853 KB. The 19
MB half is the rule-by-rule triage detail, loaded lazily so a list request
never pays for it.

**Stage-1 does not reduce the review queue on FIRMS alone.** All 3,610 events
are queued: 396 LIKELY_FIRE, 3,214 AMBIGUOUS, 0 LIKELY_NON_FIRE — compression
1.0. Most rules return NOT_EVALUATED because FIRMS carries no peat, land-use
or weather context. This is a property of the input, not a bug in the rules,
and it is the argument for enrichment: without it there is no triage benefit
to demonstrate.

**No frontend consumes these endpoints yet, deliberately.** `FireEvent` in
`frontend/src/api/types.ts` requires `location`, `peatClassification` and
`currentConditions`. FIRMS-only data supplies none of them, and inventing
them would blur real and fixture data in exactly the way the product boundary
forbids. The register needs its own view instead of a coerced legacy shape.

---

## 2026-09-08 — The spec drops Cloudflare, and names storage roles not products

**Status:** done · PR #72

**Decision.** `Environmental_Assurance_Spec.md` no longer says "Cloudflare
Workers; D1 + R2 + KV". The stack line names what is deployed — Flask on AWS
Lambda behind an API Gateway HTTP API, Terraform-managed — and §8 describes
the three persistence roles by role: a durable queryable metadata store, a
bulky immutable evidence store, and a disposable cache. `storage_policy` in
§26 and `geometryObjectKey` in §25 use the same neutral names.

**Why change the spec rather than record a deviation.** The spec declares
itself the source of truth where documents conflict, so a deviation recorded
only in this log loses to it by the spec's own rule. An agent reading the spec
cold would have been told to provision D1 and R2 against an AWS account. The
infrastructure has been AWS since 2026-09-07, it is deployed and working, and
rebuilding on Cloudflare would spend the remaining budget to arrive at the
same behaviour. The document was the thing that was wrong.

**Rejected: naming DynamoDB and S3 in the spec.** This PR originally did
exactly that, mapping D1→DynamoDB, R2→S3 and KV→a TTL-expiring DynamoDB
table. Issue #56 landed the neutral wording first and it is the better answer:
nothing implements persistence yet, so the service choice is not made, and
writing it into the canonical spec would have made an unmade decision look
settled to every agent that reads it. Removing the *wrong* stack does not
require inventing the right one. When persistence is actually built, that is a
separate decision and belongs in its own entry here.

**Constraint that will shape that decision.** Serverless only, per the project
owner: Lambda, S3, DynamoDB are fine; anything always-on, EC2 in particular,
needs justification first. A container pushed to ECR is acceptable where one is
genuinely needed — the trigger to watch for is the Lambda bundle outgrowing
the 250 MB unzipped limit.

**Left alone.** The three legacy specs still say Cloudflare. They are kept for
history and are superseded by the canonical file; editing them would rewrite a
record of what was true when they were written.

---

## 2026-09-08 - Audit-scope sessions use a small adapter until persistence is chosen

**Status:** implemented on issue #56

**Decision.** The audit-first entry flow creates an anonymised `audit_id` and
`scope_id`, validates the uploaded private GeoJSON boundary, and carries dates,
bbox, centroid, context buffer, and buffer preview through a minimal Flask
contract. The current adapter keeps sessions process-local and exposes the
history-build handoff without reconstructing history.

**Why.** The repository's real deployment path is Flask on AWS Lambda behind
API Gateway HTTP API, while application persistence is explicitly not yet
provisioned. A small interface gives #57 a stable scope contract without
silently inventing a DynamoDB/S3 design or moving the product to the stale
Cloudflare Workers/D1/R2/KV wording in the earlier spec.

**Rejected.** Company identity, public concession lookup, and KML/KMZ/SHP
parsers are outside the audit-scope boundary. A process-local session is not a
production retention model and must be replaced by the later persistence
decision before multi-instance or multi-tenant use.

---

## 2026-09-08 - Investigator/Skeptic analysis is a bounded structured boundary

**Status:** implemented on issue #15 branch

**Decision.** `data_pipeline/analysis/investigator_skeptic.py` owns the
provider-neutral Investigator/Skeptic contract after deterministic
reconstruction. It supplies structured EvidenceObjects and evidence IDs,
executes independent, rebuttal, and final rounds, validates every finding and
question against the evidence pack, and persists only concise summaries,
support/counter references, and unresolved questions.

**Why.** A fixed three-round boundary makes the adversarial workflow bounded
and testable without coupling reconstruction to an LLM vendor. Keeping the
opponent input as a prior structured assessment preserves rebuttal while
avoiding a conversation transcript or private chain-of-thought. Disagreement
is retained as a human verification question rather than forced into a single
explanation.

**Rejected.** Free-form agent conversation and unreferenced factual summaries
were rejected because they cannot be audited against EvidenceObjects. The
runner does not infer responsibility, intent, or cause; it validates the
interpretation layer only.

---

## 2026-09-08 - Investigation Priority is an evidence-backed routing score

**Status:** implemented on issue #14 branch

**Decision.** `priority/investigation_priority.py` computes a bounded 0--100
score and `LOW|MEDIUM|HIGH|URGENT` label from nine environmental/event factors.
Each result returns all nine components, fixed visible weights, evidence IDs,
quality, limitations, coverage, and the source EvidenceObjects. Existing
Stage-1, Fire Complexity, FireEventGraph, peat, and surface-compatibility
outputs can feed the relevant factors without flattening their provenance.

**Why.** Investigative attention needs a reproducible queueing aid while the
canonical product boundary forbids a guilt or responsibility score. Fixed
weights make the current policy inspectable until a labelled calibration set
exists; missing context remains `NOT_EVALUATED` and is reported in coverage.
Evidence sufficiency increases routing attention when it is partial or
insufficient, but does not imply a cause or adverse finding.

**Rejected.** Company identity, reputation, previous misconduct, intent,
culpability, responsibility, and legal fields are rejected as inputs rather
than merely ignored. A learned model and an opaque aggregate complexity
number were rejected because the repository has no calibration set and issue
#12 deliberately preserves complexity as named evidence.

## 2026-09-08 - Copernicus scenes are selected deterministically from STAC metadata

**Status:** implemented on issue #13 branch

**Decision.** `imagery/scene_selection.py` selects one closest usable
Sentinel-2 and Sentinel-1 scene on each side of a FireEvent. Optical scenes
must have catalogue cloud cover at or below a caller-visible threshold;
missing optical cloud metadata is not treated as cloud-free. SAR scenes are
not cloud-filtered. Every selected scene keeps its product ID, acquisition
time, sensor, orbit fields, temporal distance, STAC item reference and
product/download reference, plus the selector version.

**Why.** The STAC adapter already proved catalogue search and the golden
fixtures already preserve raw responses, but the pipeline previously only
listed the first returned features. A pure selection step makes the choice
reproducible before any large product download and keeps catalogue retrieval,
scene choice and evidence processing inspectable as separate stages.

**Rejected.** Sorting by cloud percentage alone was rejected: the closest
usable pass is the temporal priority, with cloud cover acting as an S2
eligibility gate and deterministic tie-breaker. Pixel-level cloud masking,
footprint coverage scoring and imagery download remain later evidence-
processing concerns; scene metadata alone does not establish environmental
change, cause, or responsibility.

## 2026-09-08 - Fire Complexity stays a named evidence bundle, not a score

**Status:** implemented on issue #12 branch

**Decision.** `complexity/fire_complexity.py` derives the 13 candidate Fire
Complexity features from a reconstructed `FireEvent` and preserves each one
as a separate, versioned EvidenceObject. It computes observation-derived
movement, direction, FRP, and thermal-lobe metrics from the event's linked raw
observations; nearby-event and recurrence metrics from the supplied event
collection; and uses peat/surface results only when those already-derived
contexts are supplied. Missing optional context is `NOT_EVALUATED`.

**Why.** The canonical spec defines complexity as how poorly one event is
explained by one straightforward surface episode, but the issue's acceptance
criterion requires the evidence fields themselves to be exposed. An
aggregate score would hide which input drove routing and would make missing
sources look like low complexity.

**Rejected.** A learned or hand-weighted magic score was rejected: the repo
has no labelled calibration set, and complexity evidence must remain
separate from AI interpretation and human disposition. Outside-envelope
observations remain a first-order compatibility mismatch, not a cause or
responsibility finding.

## 2026-09-08 - Surface growth remains a first-order compatibility screen

**Status:** implemented on issue #11 branch

**Decision.** `propagation/surface_fire.py` projects a wind-oriented ellipse
from a source FireEvent using explicit head/back/flank spread rates. It
compares later FireEvent centroids individually and records clusters outside
the expected envelope. Historical wind is used for orientation; missing wind
produces `NOT_EVALUATED`, never negative evidence. FireEventGraph edges use
the envelope result when wind is available and retain the existing speed-bound
fallback otherwise.

**Why.** The issue needs a transparent plausibility comparison for observed
progression, not a fire-behaviour forecast. Keeping the model pure and
parameterized makes its assumptions, limitations, and version inspectable in
the data layer before any AI interpretation.

**Rejected.** Peat-mediated or underground travel was deliberately excluded
from the envelope. Persistent peat evidence remains a separate contextual
hypothesis and cannot be represented as a surface ellipse path.

---

## 2026-09-08 — FireEventGraph stays a deterministic pipeline boundary

**Status:** implemented on issue #10 branch

**Decision.** Build `FireEventGraph` from clustered `FireEvent` summaries, not
raw FIRMS rows. Candidate edges are spatially indexed and time-gated, carry
the requested deterministic relationship features, preserve optional missing
context as `None`, and record supporting/contradicting evidence IDs plus
`fire-event-graph-v1`. Earlier non-overlapping events are the source of a
directed edge; overlapping windows are explicitly non-directional.

**Why.** Relationship screening must remain inspectable and bounded before any
AI interpretation. The first-order surface-speed check is a compatibility
screen, not a fire forecast or a conclusion about cause, intent, responsibility,
or legality. Weather, peat-corridor, shared-episode, and recurrence values are
accepted only as already-derived context; acquisition remains outside this
pure model.

**Rejected.** An all-pairs graph was rejected because historical FireEvent
collections can be large; a cKDTree candidate gate is used instead. Inferring
missing environmental context as negative evidence was also rejected because
it would turn source gaps into unsupported independence claims.

---

## 2026-09-08 — Stage-1 triage stays deterministic, provenance-bound, and conservative

**Status:** implemented on issue #9 branch

**Decision.** Stage 1 is a versioned additive rule engine (`stage1-rules-v1`).
It derives FIRMS confidence, FRP, repeat-observation evidence, and nearby
detections from the supplied event collection. It accepts other context only
when the caller supplies an EvidenceObject-compatible value with an evidence
ID and source. Missing context is `NOT_EVALUATED`, never silently treated as
absence. A score of four is required for `LIKELY_FIRE` or `LIKELY_NON_FIRE`;
if both sides reach the threshold, the outcome is `AMBIGUOUS` rather than
allowing one explanation to cancel the other.

**Why.** The pipeline has no labelled validation set from which to fit or
calibrate a probabilistic classifier. Explicit rules make every screening
decision inspectable today and allow the thresholds to be replaced later
without pretending the current numbers are learned probabilities. Strong
documented persistent-heat-source or volcano/geothermal context can meet the
non-fire threshold alone. Weak urban/settlement context cannot: it needs
corroborating low-confidence, low-FRP, or singleton evidence before deeper
investigation spend is withheld.

**Routing.** Only `AMBIGUOUS` requests bounded AI review. `LIKELY_FIRE` remains
eligible for deterministic evidence acquisition. `LIKELY_NON_FIRE` records why
deeper investigation budget was not used. These are screening states about
the available observations and context, not findings about ignition cause,
intent, legality, or responsibility.

**Revisit when** a representative labelled set is available. Calibrate the
thresholds against false-negative cost before production use and increment
the algorithm version whenever a threshold or rule weight changes.

---

## 2026-09-08 — `EventStatus` renamed to match the canonical spec's Stage-1 vocabulary

**Status:** done

**Decision.** `AWAITING_REVIEW` → `AMBIGUOUS`, `STAGE1_REJECTED` →
`LIKELY_NON_FIRE`. `STAGE2_RUNNING` and `CONVERGED` are unchanged. Same shape
— one flat `EventStatus` field on `FireEvent` — just renamed. Touched every
call site: `frontend/src/api/types.ts`, `lib/color.ts`,
`components/table/EventTable.tsx`, `api/fixtures/events.ts`,
`backend/app/events.py` (`VALID_STATUSES`), `backend/app/data/events.json`,
`backend/tests/test_events.py`.

**Why these two, and not a bigger change.** `AMBIGUOUS` and `LIKELY_NON_FIRE`
are exact matches for the Stage-1 triage outcomes in
`Environmental_Assurance_Spec.md` §10, so renaming them removes a real
naming collision, not just a cosmetic one. `STAGE2_RUNNING`/`CONVERGED` stay
as this repo's own vocabulary for Stage-2 adversarial-analysis progress —
the canonical spec doesn't enumerate an AnalysisRun status, and `CONVERGED`
already matches `InvestigationReport.status` (`'running' | 'converged'`)
exactly.

**What this is not.** The canonical spec's actual `FireEvent` model (§9)
replaces a single status field with `evidenceSufficiency`
(SUFFICIENT/PARTIAL/INSUFFICIENT) and `investigationPriority`
(LOW/MEDIUM/HIGH/URGENT) — two separate fields driven by real scoring logic,
not four string literals. That is the Stage-1-triage and
investigation-priority-scoring work already tracked as its own issues, not a
naming fix. Do not read this entry as having done that migration.

---

## 2026-09-08 — `Environmental_Assurance_Spec.md` is now the canonical spec

**Status:** done

**Decision.** `DesignSpecs/Environmental_Assurance_Spec.md` consolidates the
three prior documents (`environmental_assurance_claude_code_spec.md`,
`environmental_assurance_spec_v2.md`, `assurance_console_ui_spec.md`) into one
audit-scope-first spec. Where they conflict, the canonical file wins. Each
legacy file got a short banner section pointing back to it; the legacy files
themselves are kept for history, not deleted.

**Why.** The product moved to an audit-scope-first workflow (auditor supplies
a management-unit boundary and review period; table-first screening; map for
selected-event investigation) rather than the prior Indonesia-wide monitoring
console with a demo timeline over fixed mock cases. That is too large a shift
to express as edits scattered across three documents with drifting section
numbers.

**Repo-wide reference sweep.** Every citation of the three legacy filenames
or their section numbers, outside `DesignSpecs/` itself, was repointed at the
canonical file's sections: `.claude/skills/{add-map-layer,evidence-framing}`,
`CLAUDE.md`, `README.md`, `backend/app/{events,routes}.py`,
`frontend/src/{api/client.ts,api/fixtures/events.ts,lib/color.ts,lib/layerColors.ts}`,
`data_pipeline/{README.md,run_all.py,sources/future/global_forest_watch.py}`,
`docs/environments.md`, and the "Standing constraints" section below. Dated
entries above this one keep their original citations untouched — they are a
record of what was true when written, not live documentation.

**One citation carried a stale rule, not just a stale pointer.** The legacy
"never render or store raw concession/peatland boundary geometry" rule is
narrower in the canonical spec: a public named-concession directory or
third-party concession polygon geometry is still forbidden (§4), but an
auditor's own uploaded management-unit boundary is now legitimate private
audit-scope data and may be stored tenant-scoped/encrypted (§6.2–6.3). Fixed
the rule's wording everywhere it appeared, not only the citation.

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

**Spec discrepancy found — ~~the spec is the stale one~~. SUPERSEDED, see
"`EventStatus` renamed to match the canonical spec's Stage-1 vocabulary"
above.** At the time: UI spec §5 listed `AMBIGUOUS|REJECTED|...` while
`types.ts`, the fixture data and the UI used
`AWAITING_REVIEW|STAGE1_REJECTED|...`, so the backend followed the frontend
names. That reasoning did not survive contact with
`Environmental_Assurance_Spec.md`, which arrived hours later and made
`AMBIGUOUS`/`LIKELY_NON_FIRE` canonical. The conclusion was wrong, not just
the citation — flagged here because a reader who stops at this entry would
act on it.

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
- **Never build a public named-concession directory or render third-party
  concession polygon geometry beyond an attribute-only lookup.**
  `Environmental_Assurance_Spec.md` §4. This does not ban geometry storage
  outright: an auditor's own uploaded management-unit boundary is legitimate
  private audit-scope data and may be stored tenant-scoped/encrypted (§6.2–6.3)
  — that policy changed from the original spec's blanket "never store."
- **The console is fixture-driven.** `frontend/src/api/client.ts` mocks the
  `Environmental_Assurance_Spec.md` §24 (API) contract exactly so it can be
  swapped for real calls without touching callers. Keep that seam.
- **The demo must never blur real data and fixtures.** The one real dataset
  (2019 FIRMS haze export) sits behind its own labelled toggle.
