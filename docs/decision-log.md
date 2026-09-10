# Decision log

Newest first. The complete historical record follows; do not delete an entry
to make this file shorter. Read the summary first, then the linked decision
when changing that subsystem.

## Current decisions at a glance

| Area | Current decision | Detail |
|---|---|---|
| Product boundary | Evidence supports human review; it never establishes blame, intent, or legal responsibility. | Standing constraints |
| Audit flow | Scope-first: create an audit from uploaded GeoJSON before rendering FireEvents. The regional landing may show labelled FIRMS context only. | 2026-09-09, audit session / landing |
| API state | Audit IDs and scope state persist in DynamoDB in deployed environments; in-memory state is local development only. Every write is revision-checked — there is no unconditional write path — and both backends implement the same compare-and-set. | 2026-09-09, audit session / landing; 2026-09-10, conditional writes |
| Derived data | Clustered events, weather, imagery selection, peat context, and prepared graph data are offline artifacts, not request-time Lambda work. | 2026-09-09, graph; weather and imagery; 2026-09-08, clustering |
| Investigation | Scores, review routing, graph edges, and propagation are separate deterministic evidence outputs; none establishes causation. | 2026-09-09, graph; review routing; 2026-09-08, triage / graph / surface growth |
| AI interpretation | Claude runs only after an explicit auditor request, receives bounded EvidenceObjects plus graph summaries, and returns schema-validated Investigator/Skeptic findings retained with the audit session. | 2026-09-09, structured analysis |
| Analysis delivery | Analysis is an async job on a second Lambda: POST starts one, GET polls it and never spends tokens. It does not fit API Gateway's 30s response cap. | 2026-09-10, async job |
| Live regional context | The landing map's live NASA FIRMS layer is proxied by the API. A FIRMS MAP_KEY cannot be domain-restricted, so it can never ship in the bundle. Two days are fetched and filtered to a rolling 24 h here; a non-CSV body is an error, not an absence of fires. | 2026-09-10, FIRMS proxy; rolling window |
| Map and imagery | Camera fitting is bounds-driven; map context is not an unscoped fire browser. Satellite display processing is deterministic and provenance-preserving. Investigation-sized Sentinel-1/2 context images are rendered once by the CDSE Process API, pinned to the scenes the evidence already names, and committed as static files under `frontend/public/imagery/`. | 2026-09-10, processed imagery; 2026-09-09, audit session / landing; 2026-09-08, Copernicus scenes |
| Infrastructure | Flask runs on Lambda behind API Gateway; Terraform owns the deployed configuration; CORS is Flask-owned. | 2026-09-09, Amplify; 2026-09-07, Lambda / CORS |
| Service selection | DynamoDB and S3 are authorised without a fresh argument each time; every service switched on gets a cost row in `docs/infra.md` in the same PR. | 2026-09-09, DynamoDB and S3 are authorised |
| Frontend tests | Vitest + jsdom + Testing Library, run in CI. They guard behaviours the product boundary depends on — explicit trigger, honest not-run state, no chain-of-thought — not the map, which jsdom cannot draw. | 2026-09-10, frontend test runner |
| Review period | The session's review period filters the register server-side, end-of-day inclusive, and every scope count is recomputed from the filtered set. The scope form's date pickers stay bounded to the coverage the artifact declares in `source.window`. | 2026-09-10, review period is a filter; review period bounds |
| Line endings | `.gitattributes` normalises all text to LF in the repository and on checkout; binary artifacts are declared explicitly rather than left to git's heuristic. | 2026-09-10, line endings |

**Use this log:** entries retain the original diagnosis, rejected alternatives,
and historical context. A later entry can supersede an earlier one; do not
apply an older decision without checking the entries above it.

---

## 2026-09-10 - Analysis findings get a register and a word cap in the prompt, not a second model to rewrite them

**Status:** done · PR #200 · Closes #199 · Refs #198, #194

**Decision.** The Investigator/Skeptic prompt in `backend/app/analysis_provider.py`
now states who reads the output and how it is written: summaries of at most
25 words, questions of at most 20 and reasons of at most 15, measured then
"consistent with", one figure per clause, no em-dashes, a short banned-phrase
list, and "estimated" or "inferred" rather than "confirmed" or "caused". The
caps live in `data_pipeline/analysis/investigator_skeptic.py` so the number
the model is told is the number the validator measures. The validator
normalises any dash that arrives anyway (`plain_text`: a spaced dash becomes a
full stop or comma, a bare one between digits an en-dash, any other a colon)
and logs, without rejecting, text over its cap. The job record carries a
`stage` ("Starting", "Round 1 of 2: independent assessment", "Round 2 of 2:
rebuttal") written between rounds, which is what lets the console show real
progress (#198).

**Why.** The owner's report was that the findings were "extremely verbose and
claudish". The schema-only prompt gave the model no register at all: its one
style instruction was "one concise evidence-grounded sentence". The proposed
fix was a second call to an OpenAI model to rewrite the prose into clearer
English. Rejected, for reasons worth keeping:

- It adds a provider outside AWS the night before the demo: a credential in
  the Lambda environment, a dependency in a bundle near its 250 MB edge, new
  egress, a new cost line.
- It adds latency to a job already near a minute, in the direction #198 is
  trying to make bearable.
- It bypasses the product boundary. The validator checks evidence IDs on the
  first model's output; a rewriting model that hedges, drops "consistent
  with" or promotes "estimated" to "confirmed" is never re-checked. That is
  AI interpretation rewritten by a second AI with no evidence trace.
- The 2026-09-10 Bedrock entry rejected "terser findings" as a *latency*
  trade. A register and a cap on the sentence trade no substance: the
  finding count, the sufficiency field and the ID lists are untouched.

**Measured.** Same event (`FE-20190901-f300bcd6f8`, 70 evidence items, six
hypotheses), same model, temperature 0, two rounds, from a laptop in
`ap-southeast-1`. "Before" is the prompt on `main` at 0bc49c1.

| | Before | After (run 1) | After (run 2) |
|---|---|---|---|
| Wall time, two rounds | 51.7 s | 37.7 s | 36.4 s |
| Output tokens, four calls | 17,557 | 13,419 | 13,237 |
| Summary words, mean / max | 30.0 / 42 | 23.3 / 35 | 22.5 / 35 |
| Summaries over 25 words | 18 of 24 | 6 of 24 | 3 of 24 |
| Question words, mean / max | 23.1 / 38 | 15.9 / 22 | 15.5 / 22 |
| Reason words, mean / max | 21.8 / 39 | 13.0 / 23 | 13.0 / 19 |
| Em-dashes | 0 | 0 | 0 |

The latency gain was not the aim and is real: the model writes a third fewer
output tokens, and output tokens are what the wall clock is made of.

**Two findings about validation that the measurement surfaced, both now
covered by the prompt.** The "before" prompt was rejected by the pipeline on
one of two runs: the Skeptic returned a finding with neither a supporting nor
a contradicting ID, which `Finding` refuses. Temperature 0 does not make
Bedrock deterministic. The first draft of the new prompt was rejected on two
of two runs for the mirror fault, an `unresolved_question` with empty
`evidence_ids`, because a rule written for summaries ("keep IDs out of the
sentence") was read as a rule for questions. The prompt now says, for
findings and for questions separately, that at least one supplied ID is
required and that an empty list fails the whole assessment. Both final runs
passed. The lesson worth keeping: every validator rule the pipeline enforces
must be stated in the prompt in the same terms, because a rule the model
cannot see is a FAILED job the auditor pays for twice.

**Rejected: rejecting over-length text.** A 26-word summary on screen is a
style fault; a FAILED job for it is a paid retry. Over-cap text is logged
with its length so drift is visible in CloudWatch.

**Rejected: a progress bar.** A bar implies a rate nobody has; the stage
names the round that is actually running.

**Open.** #198 renders the stage. If the owner still wants a rewrite pass
after reading the new output, the AWS-native shape is a second Haiku call
with the evidence-ID validator run again on its result, and it needs its own
entry here.

---

## 2026-09-10 - Sentinel context images are rendered once by the CDSE Process API and served as static files

**Status:** done · PR #192 · Closes #191 · Refs #171

**Decision.** The evidence drawer's satellite pictures come from
`data_pipeline/generate_processed_imagery.py`, run once by hand. For each of
the 16 demo FireEvents with selected scenes it asks the Copernicus Data Space
Ecosystem Process API to render a 10 km square around the centroid at
1024 px: Sentinel-2 L2A as SWIR/NIR/Red false colour, Sentinel-1 GRD as a
VV/VH decibel composite that CDSE has already orthorectified, terrain-corrected
to Gamma0 on the Copernicus 30 m DEM and Lee-filtered. The JPEGs, a JSON
sidecar each, and `manifest.json` are committed under
`frontend/public/imagery/` and served by Amplify from the console's own
origin, the same path `public/pipeline/firms-2019-09.json` already takes.
Each request is pinned to the UTC day (and, for Sentinel-1, the orbit
direction) of the product the `ENV_IMAGERY_*` EvidenceObject names, and the
sidecar records that evidence ID, the product, the data filter and the
SHA-256 of the evalscript and request. Both recipes use fixed stretches. A
scene that cannot be rendered gets a `.missing.json` with the reason.

**Why.** The catalogue quicklook is a few hundred pixels of a 100 km tile; it
does not show the event. Sentinel-1 in particular is unreadable without
calibration, terrain correction and speckle filtering, and the Process API
does all of that server-side per request, so no SAR toolchain, SNAP install
or SAFE download enters this repo. Pinning to the already-selected scene
keeps provenance intact: the drawer's scene metadata and the picture describe
the same acquisition, so the image is a display attribute of an existing
EvidenceObject rather than a new, untraceable claim. Fixed stretches are what
make a before/after pair comparable; a per-scene percentile stretch
normalises each image to its own contents. Committing the output means the
demo cannot fail on a live Copernicus call, and a ~20 MB static folder is
free on Amplify where it would be a real cost on Lambda's bundle limit.

**Rejected: downloading SAFE products and processing locally.** Gigabytes per
scene, a SNAP/GPT or snappy toolchain to install and version, and hours of
work the night before the demo, for output no better than the API's.

**Rejected: letting `leastCC` choose the date over the event window.** It
would often return a clearer picture, of a different acquisition from the one
the evidence names. The drawer would then describe one scene and show
another. The Sentinel-2 request keeps `leastCC` only as a tiebreak within the
single pinned day.

**Rejected: a per-scene percentile stretch, as `sentinel1_visualization.py`
does.** Right for one image, wrong for a pair; see above.

**Rejected: an S3 bucket for the images.** S3 is authorised, and bulky
immutable evidence is the role §8 reserves for it, but the images are a few
tens of megabytes of demo output with no writer. A new bucket, its Terraform,
a cost row and a CORS/CDN decision the evening before the demo bought nothing
the `public/` folder does not already give. It remains the eventual home when
imagery is generated per audit rather than once.

**Rejected: NBR / ΔNBR as a third product.** A burn-severity index looks like
an analytical result and would be read as one. The evidence layer stops at
display products for human orientation; anything that could be mistaken for a
measured burn extent needs the limitations and evidence framing of a derived
metric, which this PR does not attempt.

**Rejected: fetching the manifest through the API.** It would put the imagery
contract behind a Lambda route for no reason; the console fetches static
pipeline output from its own origin already, and #171 consumes the manifest
the same way.

**Measured.** The first run on 2026-09-10 rendered 58 of 64 requested images
(17.5 MB of JPEG at quality 90, median coverage 100 %, minimum 24 %) and
recorded 6 as missing, all with 0-4 % data on the pinned day. Those six are
not an API problem: the scene selector ran once against the scope bbox and
attached the same four products to every event, so events at the western edge
of the scope are told their scene is a tile that does not reach them. That is
#193; the manifest records the gaps honestly rather than filling them from
another date.

**Open.** #171 builds the drawer surface that reads `manifest.json`. Folding
each image into the evidence response as a display attribute of its source
EvidenceObject (rather than a parallel manifest) is the right eventual shape
and is not done here.

---

## 2026-09-10 - Every write to the audit store is revision-checked, in both backends

**Status:** done · PR #190 · Closes #146

**Decision.** `audit_store` has no unconditional write left. A caller picks an
intent: `create`, which fails if the item already exists, or `update`, which
re-reads, re-applies the mutation and compare-and-sets on the revision it
read, retrying up to 8 times before raising. Items are held in the DynamoDB
shape (`{audit_id, state, revision}`) in memory too, so both backends run the
same code and differ only in the read and the compare-and-set. `audits`
scope-setup writes and `analysis_jobs` job rows both go through it.

**Why.** #183 gave pack and analysis mutations a conditional path but left
`put()` — an unconditional whole-blob write — as the way scope setup and job
rows persisted. That is only half a fix, and the asymmetry was the dangerous
direction: a conditional write losing to a blob put *retries*, but a blob put
landing between another writer's read and its write *wins silently*, dropping
a pack entry or a completed assessment with no error and nothing in the log.
Reaching it needed an auditor to re-upload a boundary or rebuild history while
an assessment was running — narrow, but it is the whole bug class the issue
exists to remove, and "safe because of the order the routes happen to run in"
is not a property anything enforces.

**The in-memory store implements the same compare-and-set, not a lock.**
Wrapping the local read-modify-write in a `threading.Lock` would also prevent
a lost write and was rejected: it serialises writers, so the retry path never
runs locally and the two stores agree only by never being compared. The lock
that is there covers the compare-and-set alone — exactly the span DynamoDB's
conditional put makes atomic — so the same test bodies run against both and
the local store fails the same way the deployed one would.

**Rejected: `update_item` with attribute-level expressions** (the issue's
option 2). It removes the collision rather than detecting it, but the session
is one JSON blob by design — that is what keeps the auditor's private GeoJSON
intact without a second scope representation — and attribute-level updates
would mean decomposing it into DynamoDB attributes. A storage-model change to
fix a write-path bug.

**Rejected: splitting the analysis result out of the session** (option 3).
Removes this collision and leaves the next one, which is the criticism the
issue already makes of it.

**`create` refuses to overwrite.** Audit ids are 96 bits of `token_urlsafe`,
so a collision means a bug somewhere else — a retried create, an id reused
deliberately — and overwriting would discard a live audit's scope. Failing is
the better answer than silently continuing.

**Verified.** The concurrency tests were each checked against the *old*
behaviour, not just observed to pass: reverting the memory store to a plain
read-modify-write fails four of them, and simulating the old `_save` (writing
the blob it loaded, after another writer's read) drops the pack entry outright
with a `KeyError`. 88 backend tests pass.

**Open.** `analysis_jobs.dispatch` still guards duplicate work with a
read-then-act: two requests arriving together for the same event can both read
`NOT_RUN` and both start a job, billing the same assessment twice. The store
now has the primitive to claim a job atomically; using it is #189.

---

## 2026-09-10 - The review period filters the register, and every count beside it is recomputed from the filtered set

**Status:** done · PR #188 · Closes #161

**Decision.** `get_audit` filters the committed artifact's events to the
session's own review period before serving them. The closing date is read as
the *end* of that day, so a period that names 2019-09-03 includes the
detections made at 10:00 on it. `eventCount`, `reviewQueueCount`,
`compression` and `qualifiedObservations` in the served scope are computed
from the filtered set. `rawObservations` is served as `null` for a narrowed
window, and the register component no longer re-sends the period as a
`?since=/?until=` query filter — the backend is the single authority on what
the period means.

**Why.** A review created for `2019-09-02 → 2019-09-03` returned all 3,610
FireEvents, every one of them detected across the full 09-01..09-05 window,
and printed the auditor's dates over them: on the engagement report as "Audit
scope", and in the evidence drawer as the span each detection bar is drawn
inside. That is the console blurring which data is real, which `CLAUDE.md`
says the demo must never do. The bound added for #95 stopped the label naming
a period the dataset does not hold at all; it did nothing about a sub-range.

**Rejected: filtering the events but leaving the scope counts as the
artifact's totals.** This is what the code already did with the dates, one
layer down — a register of 812 events sitting under `eventCount: 3610` is the
same mislabel, and the number an auditor quotes is the one in the summary,
not the row count they scrolled past.

**Rejected: computing `rawObservations` for the window.** 21,519 is the
pre-clustering detection count, and the 1,048 it exceeds `qualifiedObservations`
by are detections dropped at the confidence gate *before* any event existed to
attribute them to. There is no per-day breakdown to filter, so any figure for a
sub-window would be manufactured. It is served as `null`, and
`AuditProgression.rawObservations` is `number | null` in the frontend to match.

**Rejected: `compression = eventCount / reviewQueueCount`.** Tried first, and
wrong in a way worth recording because it looked right: it produced 9.1× at
full coverage against the artifact's own 1.0×. `compression` in the artifact
is Stage-1's ratio, whose denominator is events not classified
`LIKELY_NON_FIRE`; the served `reviewQueueCount` (396) is the *later*
calibrated HIGH/URGENT routing count. The two are different measurements with
similar names, and dividing by the wrong one would have put a fabricated ~9×
efficiency figure on the demo screen — exactly the number the decision log's
Stage-1 entry says not to manufacture. The Stage-1 denominator is now derived
separately. The naming collision itself is #187.

**Rejected: a blank table for an in-range empty period.** A blank table reads
as something that failed to load. The register now states "No FireEvents were
detected in this period", names the period and buffer, and says explicitly
that it returned nothing rather than failing — a measurement, which an empty
table is not.

**Verified.** At full coverage the served scope reproduces the artifact's own
figures on every field, so the demo's default path is unchanged: 3,610 events,
`compression` 1.0, `rawObservations` 21519. A sub-window narrows all of them
together; a period inside the coverage with no detections returns 200 with an
empty register and `history_status` AVAILABLE, not a 404.

`cached_reconstruction_ready` changed with it: it compared the triage detail
file's entry count to the event count, which a filtered register legitimately
breaks. It now checks that every *served* event has a detail entry — coverage
rather than equality — which is what the evidence drawer actually needs.

**Open.** The window is a filter over one committed artifact, not a build
parameter: the pipeline is not re-run for it. If #89 makes the pipeline the
real path, the period becomes a genuine input and this becomes the shim.

---

## 2026-09-10 - Line endings are normalised by `.gitattributes`, so a Windows commit cannot manufacture a merge conflict

**Status:** done · PR #184 · Closes #132

**Decision.** A root `.gitattributes` sets `* text=auto eol=lf`: text is stored
LF in the repository and checked out LF on every platform, whatever a
contributor's `core.autocrlf` says. Binary artifacts — `*.gz`, `*.npy`, `*.pdf`
and the pre-emptive image and font extensions — are declared `binary`
explicitly.

**Why.** A Windows checkout committed four files as CRLF through PR #129. When
one side of a merge is CRLF and the other LF, *every line* of the file differs,
so git finds no hunks and reports the whole file as a single conflict. Merging
#131 hit 15 conflicted files; 4 were pure line-ending noise and 2 of those had
no real content difference at all once `\r` was stripped. They had to be
resolved by hand-running three-way merges on `tr -d '\r'`-normalised blobs.
That is a whole class of merge pain, and it lands on whoever merges next rather
than on whoever caused it.

The four CRLF files were already normalised back to LF by the #131 merge, so
`git add --renormalize .` in this PR changed nothing — the commit is purely
preventative. That is the intended outcome, not a sign the fix did nothing:
without the file, the *next* Windows commit reintroduces the problem.

**Rejected: `git -c merge.renormalize=true` at merge time.** The obvious escape
hatch, and it does not work. `merge.renormalize` reads its normalisation rules
from `.gitattributes`; with no such file there is nothing for it to act on, so
it silently does nothing. It becomes useful *because* of this change, not
instead of it.

**Rejected: relying on git's binary auto-detection for the artifacts.**
`text=auto` classifies by NUL-byte sniffing and would very likely get these
right on its own. But `backend/app/data/audit_events.json.gz` and
`audit_triage_detail.json.gz` genuinely contain CR bytes (916 and 4,805
respectively), and the three `data_pipeline/golden/**/raster_crop.npy` files are
the regression baselines. A misclassification would corrupt the dataset the API
serves, or the baseline the tests compare against, *silently* — the failure mode
is a wrong number on the console, not a crash. Too cheap to leave to a
heuristic.

**Verified.** All six binary blob hashes are identical before and after
`git add --renormalize .`. `eol=lf` is still reported as inherited on the binary
paths by `git check-attr`, which looks alarming and is not: `binary` unsets
`text`, and end-of-line conversion requires `text`. Confirmed empirically rather
than from the docs, whose wording on this differs between git versions — a
scratch repo using the same rule ordering, cloned with `core.autocrlf=true` to
simulate a Windows checkout, returned a CR-bearing binary byte-identical while
still checking a CRLF source file out as LF.

**Open.** `.npy` was added beyond what #132 asked for. The same
Windows-checkout root cause is still live in #128, where `source_provenance()`
leaks a backslash path separator into the artifact; `.gitattributes` does not
fix that one.

---

## 2026-09-10 - The review period is bounded by the dataset, because it is printed as fact

**Status:** done · PR #162 · Closes #95

> **Partly superseded 2026-09-10 by PR #188.** The window is a real filter
> now; the paragraphs below describing it as a label copied onto the scope
> describe the behaviour this entry was written against, not current
> behaviour. The bound itself stands and is still the reason an auditor
> cannot name a period the evidence does not cover — see the entry of that
> date for why an in-range empty window still needs it.

#95 asked for a datepicker on the date inputs. Both inputs were already
`type="date"`, so a native picker and a date-typed value were there; the
premise was stale. What was missing is the part the issue was reaching for
when it said the input should be "date time instead of random strings": the
pickers accepted *any* date, and this build cannot answer for any date.

The register is served from one committed artifact covering
`2019-09-01..2019-09-05`, and `get_audit` copies the session's review window
onto the scope without filtering the events by it (#161). So an out-of-range
period does not come back empty — it comes back as the same 3,610 September
2019 FireEvents under someone else's dates. That window is then printed as
fact in two places: the engagement report's `Audit scope · start → end`
header, which is what the exported PDF carries, and the evidence drawer's
detection bar, which positions each event's detection *inside* the chosen
span. A 2024 review therefore renders 2019 evidence against a 2024 axis and
prints a 2024 period on the report. That is the demo blurring real data with
a fixture, which `CLAUDE.md` forbids.

**The bound is read from the artifact, not hardcoded.** The obvious
implementation is two more constants beside `DEFAULT_REVIEW_START` /
`DEFAULT_REVIEW_END` in `AuditStart.tsx`. Rejected: a second copy of the
dates in the component would keep passing lint, build and every test while
the committed dataset moved underneath it, and the bound would then be a
confident claim about a window nothing holds — the same class of failure as
a stale "State of things" line. The window is already served, as
`source.window`, through the `fetchDemoDatasetSummary` call the first-load
context panel makes; the form parses it from there.

**A failed fetch leaves the pickers unbounded.** Not knowing the coverage is
not the same as knowing it is unlimited, and no fallback range is invented:
stating one from a failed request would be the fabrication this avoids. The
defaults are inside the real window, so the form stays usable.

**The submit-time check is kept even though the browser refuses the click.**
`min`/`max` make an out-of-range value fail interactive validation in Chrome
and in jsdom, so the guard is unreachable through the button — the test
submits the form directly to cover it. It stays because a caller that reaches
the form without interactive validation (`form.submit()`, an automation
driver, a later `noValidate`) must not be able to create an audit whose
printed period the evidence cannot support.

`[color-scheme:dark]` on both inputs is what makes Chrome draw the calendar
indicator and the picker panel for the dark surface they sit on; without it
the control is a black glyph on a near-black field.

This does not make the window a filter. A sub-range inside the coverage still
returns all 3,610 events. That is #161, and it touches the backend, so it
deploys on merge — deliberately not done the day before the demo.

---

## 2026-09-10 - The frontend gets a test runner, for the behaviours the product boundary rests on

**Status:** done · PR #158 · Closes #61

`frontend/package.json` had `dev`, `build`, `lint` and `preview` and no test
runner at all, so every frontend check was static: `tsc -b` proves the console
compiles and `oxlint` proves it is tidy. Neither can observe that opening the
engagement report does *not* start an AI analysis.

That distinction is not a nicety. #61's rules — analysis runs only on an
explicit `GENERATE INVESTIGATION ANALYSIS` press, an unanalysed event says so
rather than showing a fabricated assessment, and only the bounded final
assessment reaches the page while the intermediate rounds stay off it — are
all *absences*. A regression in any of them adds nothing to the screen that a
reviewer would notice; it removes a restraint. The backend has had schema and
route tests for this since #142/#148. The console had nothing.

**Vitest**, not Jest. Vite 8 is already the build tool, so Vitest reuses its
resolver, its TS handling and the same `import.meta.env` semantics; Jest would
need a second transform pipeline (babel or ts-jest) and its own module
mapping, and would then be resolving imports differently from the thing that
actually ships. `@testing-library/react` over shallow rendering or enzyme-style
introspection: these tests assert on what an auditor sees and presses, which is
the level the rules are written at.

**A separate `vitest.config.ts` rather than a `test` block in
`vite.config.ts`.** The app config carries the Tailwind plugin and both
maplibre worker workarounds; a jsdom component test needs none of them, and
loading Tailwind on every run costs seconds for nothing. JSX comes from
`tsconfig.app.json`'s `"jsx": "react-jsx"`, so the React plugin is not needed
either.

**The API seam is mocked, not `fetch`.** `client.ts` decides how an analysis
job is polled (2026-09-10, async job); a component test that stubbed `fetch`
would fail whenever that polling changed, while proving nothing extra about
the component. Mocking the seam keeps the two independently changeable — which
is the same reason the seam exists.

**What this deliberately does not do.** jsdom draws no canvas and loads no
tiles, so nothing here covers the map, and the standing rule survives intact:
for any change touching rendering, the map or a frontend dependency, open the
app and look at it before merging. A green Vitest run is not that check.

Adding a devDependency is normally Renovate's job. This one is a deliverable of
the issue rather than a bump: there was no runner to update.

## 2026-09-10 - The live FIRMS window is fetched wide and narrowed here, and a non-CSV answer is an error

**Status:** done · PR #155 · Closes #154

The proxy in the entry below shipped, deployed, answered `200`, reported
`status: ready`, `sensor: VIIRS_SNPP_NRT`, `windowHours: 24` — and carried
**zero features**. Every field was true except the one that mattered: the
layer drew an empty Southeast Asia, which reads as *no fires are burning*.
That is the exact fabricated observation the 503-not-empty-collection
decision below exists to prevent, arriving through a path that decision did
not cover.

Two separate causes, either of which alone produces it.

**The area API's day range is anchored on the UTC calendar day, not on a
rolling window.** `.../VIIRS_SNPP_NRT/{bbox}/1` means "since 00:00 UTC
today", so at 01:44 UTC it is a 104-minute window. VIIRS/Suomi-NPP crosses
this region near 18:30 UTC the previous day and 06:30 UTC, so an early-UTC
request contains no Southeast Asian overpass at all. Measured directly
against the real API at 01:51 UTC on 2026-09-10: `day_range=2` returned
**5,389 detections, every one of them stamped 2026-09-09** (03:30Z to
19:38Z) and every one inside a rolling 24 hours. Not one row bore today's
date. `day_range=1` had nothing to return.

So the route fetches `FETCH_DAYS = 2` and filters to `WINDOW_HOURS = 24`
server-side. Fetching wide and narrowing here is correct under *either*
reading of the parameter — calendar-anchored or rolling — so the fix does not
rest on which one is right, and `windowHours: 24` becomes true by
construction rather than by assertion. The filter is a lower bound only: a
detection cannot be observed in the future, so an upper bound would police
nothing but clock skew between the Lambda and FIRMS, and would do it by
dropping real detections.

**Rejected: `day_range=1` plus an explicit `[DATE]` of yesterday.** It fixes
the empty early-UTC case and breaks the late-UTC one, where the freshest
overpass is today's. Rejected too: widening to the `5` the day range caps at
— more upstream bytes and more parsing for detections the layer then throws
away.

**FIRMS serves its errors as plain text with HTTP 200.** "Invalid MAP_KEY.",
transaction-limit notices. `csv.DictReader` reads a one-line error body as a
*header* and yields no rows, so an unusable key and a quiet fire season were
indistinguishable — both rendered as an empty region. The parser now checks
the header for `latitude`/`longitude` and raises `FirmsUnavailable` carrying
upstream's own first line, because "invalid key" and "you have exhausted your
transactions" need different responses from us and neither is a statement
about fires. The key is redacted out of that message: it reaches the browser
in the 503 body, and a FIRMS error page can echo the URL it was given.

**A detection whose timestamp will not parse is dropped rather than kept.**
The client draws an unparseable one at the faintest end of the age ramp,
which is a fair way to *render* something already known to be in range;
counting it here would place it inside a 24-hour claim nothing measured. The
two are not in conflict — they answer different questions.

**And a count of zero now says so in words.** The console said `0 thermal
detections · past 24 h`, which reads as a measurement of the region rather
than of what FIRMS returned. An empty layer and an unanswered one draw the
same blank map, so the label is the only thing that separates them.

Verified end to end against the live API before merging: 5,389 features
served locally through the route, and the key absent from the response body.

---

## 2026-09-10 - The live FIRMS layer is proxied by the API, not fetched by the browser

**Status:** done · PR #150 · Closes #149

The console's landing screen draws current regional thermal detections as
orientation context. It fetched them from the browser:

```ts
await fetch(`https://firms.modaps.eosdis.nasa.gov/api/area/csv/${firmsMapKey}/VIIRS_SNPP_NRT/world/1`)
```

with `firmsMapKey` read from `import.meta.env.VITE_FIRMS_MAP_KEY`. That shape
has no correct configuration, which is why it had to move rather than be
fixed in place:

- **Unset** — which is how the Amplify app was actually configured — Vite
  folds the key to `undefined`, the minifier proves the guard always returns,
  and the whole fetch is eliminated as dead code. The deployed landing page
  had reported "Live FIRMS context unavailable" since it shipped. (That
  elimination is also why grepping an older bundle for `modaps` finds
  nothing: absence of the host there is not evidence the key was safe.)
- **Set** — the key is inlined into the public bundle. Unlike
  `VITE_CARTO_API_KEY` beside it, which is designed to be published and
  restricted to an origin, **a NASA FIRMS MAP_KEY cannot be restricted to a
  domain at all.** Publishing it hands the account's transaction quota to
  anyone who opens the JS.

**So the key stays on the server.** `GET /api/firms/live`
(`backend/app/firms_live.py`) holds `NASA_FIRMS_MAP_KEY`, fetches, parses the
CSV and returns GeoJSON; `client.ts` gains `fetchLiveFirmsDetections` and
`AuditLanding` loses its CSV parser and its `import.meta.env` read. The built
bundle now contains `/api/firms/live` and no FIRMS host — checked in the
`dist/` output, not assumed.

**The route is deliberately flat, not audit-scoped.** `CLAUDE.md` says to
build new endpoints audit-scoped; this is the exception that proves it. The
layer is what the console shows *before* a scope exists, so there is no audit
to scope it to. It is regional context, never evidence — nothing it returns is
persisted, and the audit path still reads the committed, immutable 2019
artifact so a review reproduces.

**Rejected: setting `VITE_FIRMS_MAP_KEY` in Amplify.** It is one click and it
makes the layer work. It also publishes a credential that cannot be
restricted, which is a worse state than the dead layer it fixes.

**Rejected: returning an empty FeatureCollection when the key is missing or
FIRMS is down.** The route answers 503 and the console renders an explicit
unavailable state. An empty regional layer is indistinguishable from "no
fires are burning" — an observation nothing measured, which is exactly the
class of claim the product boundary exists to prevent.

Two things came free from moving server-side. The browser was requesting
`world/1` — every VIIRS detection on Earth for 24 hours, several MB of CSV —
and discarding everything outside Southeast Asia after downloading it; the
area API takes a bounding box, so the fetch is now regional. And a 15-minute
server-side cache means N visitors are one FIRMS transaction rather than N,
against a per-key cap the landing page is the most exposed screen to.

The response carries raw UTC `acquiredAt` rather than a precomputed age,
because a response cached for 15 minutes would otherwise hand every later
visitor a stale "now"; the client derives `ageHours` at render time, which is
what the circle-fade paint expressions read.

The key reaches the Lambda as `TF_VAR_nasa_firms_map_key` from a
`NASA_FIRMS_MAP_KEY` GitHub secret, the same route `FLASK_SECRET_KEY` takes,
and lands in Terraform state in plain text like that one — acceptable for a
free, re-issuable key on a dev stack, and recorded in `infra/variables.tf`
rather than left to be discovered.

**The plan for this PR turned up a second, unrelated finding worth keeping.**
`environment_variables` on `aws_amplify_app.console` is a Terraform-owned map
and is replaced wholesale on every apply, so both variables that had been
typed into the Amplify console by hand — `VITE_FIRMS_MAP_KEY` and
`VITE_CARTO_API_KEY` — showed as deletions. For the FIRMS key that is the
correct outcome and does the cleanup for us. For the Carto key it is a silent
regression: the basemap would drop to unauthenticated, rate-limited tiles with
nothing in the repository explaining why. `VITE_CARTO_API_KEY` is therefore
declared in `console.tf` and fed by a `CARTO_API_KEY` GitHub *variable* — a
variable, not a secret, because it is public by design and masking it would
only hide it from us. The general rule: an Amplify environment variable that
is not in `console.tf` does not exist past the next infra merge.

**The published key is reused through the 2026-09-11 demo and rotated after
it** (owner's call, 2026-09-10; tracked in #152). Recorded because a leaked
credential left in place looks like an oversight six commits later. The
reasoning: a FIRMS MAP_KEY carries a transaction quota and nothing else, so
the whole downside is the landing layer answering 503 if someone else spends
it, and this change is what stops the key being re-published on every
subsequent build. Rotation is a secret swap with no code change.

---

## 2026-09-10 - Analysis runs as an async job on a second Lambda

**Status:** done · PR #148 · Closes #143

The measurement in the entry below left one conclusion: a two-round
Investigator/Skeptic assessment (51.1s) cannot be delivered inside API
Gateway's 30s response cap, and neither can a single round (29.9s). This is
how the work now gets delivered anyway.

**`POST .../analyse` records a job and returns; `GET` polls it.** The rules
the shape rests on are worth stating because they are easy to erode later:
an HTTP status describes the *request* and `jobStatus` describes the *work*,
so a provider failure is a truthful `FAILED` job rather than a 5xx (the
deployed path has no other option -- the response is long gone by the time
the worker fails); and `GET` only ever reads, so polling never re-triggers
work or spends tokens. A job already `RUNNING` is returned rather than
started again, which makes a double press free.

**Two Lambda functions from one artifact, rather than one longer timeout.**
`api` stays at 29s and a new `analysis-worker` gets 300s, both built from the
same zip with different handlers. Raising the single function's timeout was
the smaller diff and was rejected: it would let a stuck *synchronous* request
bill the full worker budget for a response API Gateway abandoned at 30s.
Both functions share one IAM role -- same table, same model -- plus a
`lambda:InvokeFunction` grant scoped to the worker alone. Async retries are
set to zero: Lambda's default of two would bill the same assessment three
times, and the job row already records a failure for the auditor to retry
deliberately.

**Job rows live in the existing audit-state table** under a namespaced
`job#<audit_id>#<event_id>` hash key. Same key attribute, same item shape, so
`audit_store` needed no change and no new service was switched on. They are
deliberately *not* nested inside the audit session: `audit_store` reads a
whole session, mutates it and writes it back, so a worker persisting an
analysis while the console saves a pack review would silently drop one of the
two writes. That read-modify-write is now the store's weak point rather than
a theoretical one -- filed as #146 rather than fixed here.

**Annotated 2026-09-10, issue #164.** Pack and analysis mutations now use a
revision-checked retry in `audit_store`, so overlapping Lambda requests merge
against the latest session rather than silently replacing another selection.
The job rows remain separate because their lifecycle and polling cadence are
still independent of the engagement record.

**Annotated 2026-09-10, PR #190 (#146).** The read-modify-write named above is
no longer the store's weak point: there is no unconditional write left in
`audit_store` at all, job rows included. The paragraph stands as the reason
job rows were separated; it no longer describes a live hazard.

**A stale `RUNNING` job does not wedge the endpoint.** A worker killed before
it records an outcome would otherwise leave a job running forever, which the
console cannot tell from slow work and which blocks every retry. A job whose
`startedAt` is older than Lambda's 900s ceiling is treated as startable.

**Local development runs the job inline.** With `ANALYSIS_WORKER_FUNCTION`
unset there is no second function to invoke and no 30s cap to fit under, so
`dispatch` does the work and returns a `COMPLETE` job. Reporting `RUNNING`
for work nothing would ever perform was the alternative, and it would have
made the dev server lie.

**Rejected: SQS, Step Functions, or a status endpoint of its own.** Each adds
a service or a URL for a queue that is one item deep and a state machine with
two states. Async self-invocation needs no new compute and no new service;
the existing `analyse` URL already had a natural GET.

---

## 2026-09-10 - Bedrock runs Haiku 4.5, and analysis cannot be delivered synchronously

**Status:** done · PR #142 · Refs #61 — the open part below (synchronous
delivery is impossible) is answered by the entry above it: analysis is now an
async job. Everything else here still holds.

**The 503 was a model entitlement, not a bug.** The deployed
`POST /api/audits/{id}/events/{id}/analyse` returned 503 for every request. The
cause was invisible because the adapter discarded the underlying `ClientError`,
so a missing entitlement, an IAM denial and a throttle all logged identically.
It now logs the cause; the caller still gets the same generic message.

Probing Converse in `ap-southeast-1` on account 424609180893 established that
**the Claude 5 family is not entitled for this account** -- `AccessDeniedException:
"anthropic.claude-sonnet-5 is not available for this account"` -- which is
exactly what `BEDROCK_MODEL_ID` defaulted to. Note that an inference profile
listing as ACTIVE does *not* imply entitlement: all 16 Claude profiles list
ACTIVE and most are not invokable. Several 4.x profiles additionally return
`ResourceNotFoundException: "Model use case details have not been submitted"`
intermittently, so availability was confirmed by repeated probing rather than
by a single success.

**Default is now `global.anthropic.claude-haiku-4-5-20251001-v1:0`**, on two
measured grounds: it is entitled, and it is roughly twice as fast as Sonnet 4.5
(~8.8s vs ~17s on a synthetic pack). Speed decides here, for the reason below.

**Two output-handling faults were masking as one.** The model wraps its JSON in
a ```json fence despite the prompt forbidding markdown, and `maxTokens` of 2200
truncated a real six-hypothesis pack mid-array. Both surfaced only as
`JSONDecodeError`. Fences are now stripped, the budget is 6000, and a
`max_tokens` stop reason is reported as itself rather than as invalid JSON.

**The two roles in a round now run concurrently.** Both agents read only the
*previous* round, never each other, so this changes wall time and nothing else
-- same inputs, same outputs, same validation.

**Synchronous delivery is nonetheless impossible, and that is the open part.**
Measured against the real evidence pack (19k input tokens, six hypotheses,
~3.5k output tokens): a full two-round assessment takes **51.1s**, and even a
single round takes **29.9s**. API Gateway HTTP API hard-caps a response at 30s,
which is why `lambda_timeout_seconds` is 29. So no arrangement of rounds fits:
parallelism halves the cost of a round but the slowest single provider call
already exceeds the cap on its own.

**A different model does not fix this, and it was measured, not assumed.** One
round against the real pack, each output run through the pipeline's own
validation:

| Model | Region | One round | Outcome |
|---|---|---|---|
| `google.gemma-3-27b-it` | us-east-1 | 92.6s | Failed: output was not a structured mapping |
| `us.google.gemma-3-27b-it` | us-east-1 | - | Failed: no such model identifier |
| `global.anthropic.claude-sonnet-4-5-20250929-v1:0` | ap-southeast-1 | 44.3s | Failed: unresolved question carried no evidence ID |
| `global.anthropic.claude-haiku-4-5-20251001-v1:0` | ap-southeast-1 | 29.6s | Passed, six findings |

Haiku 4.5 is not a downgrade accepted for speed; it is both the fastest and
the only candidate that produced schema-valid output. Two results are worth
keeping: a small open model is cheap per token but *slower* per request and
markedly worse at emitting strict JSON with exact evidence IDs (Gemma 3 27B is
the largest Gemma on Bedrock -- there is no Gemma 4 -- and it is us-east-1
only); and Sonnet 4.5 was rejected by the evidence-ID guard, so a larger model
is not automatically a safer one here.

**Rejected:** cutting to one round (29.9s leaves no margin for cold start and
evidence assembly, and discards the rebuttal round that makes the loop
adversarial); trimming the hypothesis set or asking for terser findings
(competing hypotheses and explicit evidence sufficiency are the product's
safety substance, not padding, and must not be traded for latency); a larger
or smaller model (see the table above -- every alternative was slower, and
both failed validation).

**EC2 was also rejected**, though it would genuinely remove the cap: the 30s
limit belongs to API Gateway, not to Lambda, whose own budget is 900s. Moving
to an always-on instance to escape a limit that an asynchronous job escapes
for free would take the project from ~$0.03/month to ~$15/month permanently,
and require a VPC, TLS, a deploy path and a second CI target. Serverless by
default stands; the delivery model is what needs to change, not the compute.

**Consequence:** analysis has to become an asynchronous job -- accept, work
past the API Gateway cap in the Lambda's own 900s budget, persist to the
`audit-state` DynamoDB table that already exists, and let the console poll.
That changes the API contract and the frontend, so it is tracked separately
rather than folded in here.

**Re-probed 2026-09-10, because "surely Claude 5 is available now" is a
question this project keeps asking.** It is not, and the reason it looks like
it should be is a naming trap worth writing down.

The Claude 5 models carry **no date stamp and no version suffix**. Bedrock
lists them as bare `anthropic.claude-sonnet-5` and `anthropic.claude-opus-5`,
next to the dated `anthropic.claude-haiku-4-5-20251001-v1:0` form. An ID that
short looks truncated, so the natural conclusion on an `AccessDeniedException`
is "I typed the ID wrong" -- and that conclusion is wrong.

**Tell a wrong ID from a missing entitlement by the exception type.** They are
different failures and Bedrock distinguishes them precisely:

| Model ID sent | Result |
|---|---|
| `apac.anthropic.claude-sonnet-5` | `ValidationException: The provided model identifier is invalid` |
| `global.anthropic.claude-sonnet-5` | `AccessDeniedException: ... is not available for this account` |
| `anthropic.claude-sonnet-5` | `AccessDeniedException: ... is not available for this account` |
| `global.anthropic.claude-opus-5` | `AccessDeniedException: ... is not available for this account` |
| `global.anthropic.claude-sonnet-4-5-20250929-v1:0` | Invoked, replied |
| `global.anthropic.claude-haiku-4-5-20251001-v1:0` | Invoked, replied |

`ValidationException` means Bedrock could not resolve the identifier -- that is
a typo. `AccessDeniedException` means it resolved it fine and the account may
not call it. Every Claude 5 attempt above is the second kind. Same account
(424609180893), same region (`ap-southeast-1`), same credentials, same call
shape as the two that succeeded, so nothing but entitlement separates them.

**`GetFoundationModelAvailability` answers this without spending a token, but
only one of its four fields is load-bearing.** `agreementAvailability.status`
is the gate. `authorizationStatus`, `entitlementAvailability` and
`regionAvailability` read AUTHORIZED/AVAILABLE for *every* Claude model
including the ones that cannot be invoked, so reading them is worse than
reading nothing -- they positively suggest access that does not exist.
Measured in `ap-southeast-1`: `agreementAvailability` is AVAILABLE for Haiku
4.5 and Sonnet 4.5, NOT_AVAILABLE for Sonnet 5, Opus 5, Sonnet 4.6 and Opus
4.8. `ListInferenceProfiles` showing ACTIVE remains meaningless, as above.

**What would change it:** the model-use-case form in the Bedrock console,
which is an account-level agreement. It is free, but it is the account owner's
to submit and it does not return instantly. **A Bedrock API key would not
help** -- an API key changes *authentication*, and this is an *authorization*
failure against the account, so the same key on this account still cannot call
Sonnet 5. It would also replace the Lambda's IAM role with a static long-lived
credential stored in Terraform state, against the no-static-AWS-credentials
rule in `CLAUDE.md`. Using the Anthropic API directly instead of Bedrock would
genuinely reach Sonnet 5, but it is a new provider integration plus a real
credential in GitHub secrets and Lambda env.

**One argument above has weakened and should not be quoted as-is.** Haiku 4.5
was chosen on two grounds -- entitled, and roughly twice as fast as Sonnet 4.5
-- and speed mattered because delivery was synchronous under a hard 30s API
Gateway cap. That cap is gone: analysis is an async job with the Lambda's 900s
budget. Sonnet 4.5's 44.3s is no longer disqualifying, so **the live objection
to Sonnet 4.5 is now only that it failed the evidence-ID guard**, on a single
run. That is thin evidence to settle a model choice on permanently. Re-running
the comparison against the real pack is worth doing after the demo; changing
the model the day before it is not.

---

## 2026-09-09 - Investigator/Skeptic analysis is explicit, evidence-bound, and durable

**Status:** done Â· issue #64

**Annotated 2026-09-10:** this entry originally named Claude Sonnet 5 as the
model invoked. It never ran on Sonnet 5 -- that account is not entitled to the
Claude 5 family (see the 2026-09-10 Bedrock entry, which has the probe and the
exception-type test). The deployed model is
`global.anthropic.claude-haiku-4-5-20251001-v1:0`, set by `var.bedrock_model_id`.
Everything else in this entry -- the evidence-bound contract, the interpretation
boundary, the report behaviour -- is model-independent and still holds.

**Decision.** The real audit path uses `POST /api/audits/{audit_id}/events/{event_id}/analyse` to invoke a Bedrock-hosted Claude model only after the auditor presses **GENERATE INVESTIGATION ANALYSIS**. The provider receives structured, provenance-bearing EvidenceObjects and deterministic FireEventGraph relationship summaries, not raw point dumps. The existing pipeline validates every returned hypothesis and evidence reference before the result is stored with the audit session in DynamoDB (or local memory in development).

**Interpretation boundary.** The fixed H1-H6 mechanism set covers local ignition, surface propagation, peat-mediated persistence/propagation, related land-management ignitions, shared-condition regional events, and other mechanisms. Evidence sufficiency is separate from support. The provider prompt and the pipeline prohibit company identity, intent, blame, legal, and responsibility inference; output is compact findings, evidence IDs, limitations, disagreement, and targeted human verification questions, never a transcript or chain-of-thought.

**Report behaviour.** The engagement package reads persisted output for analysed selected events and labels every other selected event as **not run**. It does not infer or fabricate an empty event’s assessment. Weather, peat, imagery, and surface-propagation evidence remain deterministic inputs shown separately from the AI interpretation.

**Cost / failure behaviour.** The provider is Amazon Bedrock, authenticated by the Lambda role's narrowly scoped `bedrock:InvokeModel` permission; `BEDROCK_MODEL_ID` is a Terraform-controlled model/profile setting, not a browser value or API key. Provider failure returns a truthful 503 and preserves the existing evidence view; it does not retry automatically. Calls are explicit and bounded (two structured rounds), so model cost scales with deliberate auditor actions rather than map clicks.

---

## 2026-09-09 - The scoped map's correlation graph gets real edges, offline

**Status:** done · issue #135

**Decision.** `GET /api/audits/{id}/graph` (`investigation_map`) now prefers
a precomputed real `FireEventGraph` edge over its own synthesized
distance-only one, for any candidate pair inside a new offline artifact.
`data_pipeline/enrich_fire_spread_audit_events.py` (mirrors
`enrich_peat_audit_events.py`) reuses `build_fire_event_graph`/
`compare_event_progression` exactly as they already existed — no new fire
math was written — over the demo scope's 16 in-scope+buffer FireEvents, and
writes each edge onto its *source* event's `fireSpreadEdges` field in
`audit_triage_detail.json.gz`. `SurfaceFireEnvelope.to_polygon()` is the one
new method: it samples the ellipse boundary into a closed `[lon, lat]` ring
for map rendering, an exact inverse of the module's own projection (the
along/across → east/north rotation is its own inverse), not an
approximation. `FireEventEdgeFeatures` gained three fields
(`surface_envelope_semi_major_km`/`_semi_minor_km`/`_center_offset_km`) so
the envelope doesn't need recomputing downstream — `_build_edge` already
built it via `compare_event_progression` and previously discarded it after
reading two summary fields off it.

**Why offline, and why this scope.** The dataset is permanently fixed to the
2019 demo window for this project, so there is no live/arbitrary-audit case
to support — the same reasoning that already sent clustering and peat
context offline. The real blocker turned out not to be `fire_event_graph.py`'s
scipy dependency (offline, that's a non-issue) but that per-event historical
wind had a checkpoint fully fetched (`enrich_audit_events.py`'s SQLite cache
had all 16 events at `weather_status='ok'`) that had simply never been
`--finalize`d into the committed artifact. Finalizing it was this change's
first step; 82 candidate edges resulted, 59 with a real wind-oriented
envelope (state distribution: 39 UNRESOLVED, 22 INDEPENDENT_PLAUSIBLE, 19
PROPAGATION_COMPATIBLE, 2 RELATED_POSSIBLE — not a flat "everything is
possible", unlike the fallback it now only covers residually).

**The unit gotcha.** Open-Meteo's committed wind-speed evidence is already
km/h (no `wind_speed_unit` override in `sources/open_meteo.py`), but
`fire_event_graph._wind_values` multiplies a `mean_wind_speed_ms` key by 3.6
assuming m/s input. The adapter in the new script deliberately uses the
`speed_kmh` key instead — the wrong key would have silently inflated every
wind speed 3.6×.

**Rejected: computing this live in the API.** Not for the reason stated in
an earlier version of this diagnosis (Lambda bundle size) — `surface_fire.py`
itself is pure Python, no numpy/scipy. Offline still wins here because the
dataset is fixed and the derivation is identical for every caller, the same
argument already accepted for clustering.

**Left alone.** Peatland-corridor uncertainty
(`peat_fraction_along_corridor`, numpy + Pillow + a raster) is a separable,
heavier piece not needed for spread *direction* and not attempted here.

---

## 2026-09-09 - DynamoDB and S3 are authorised; every service switched on gets a cost row

**Status:** done - PR #137

**Decision.** DynamoDB and S3 are approved for use without a fresh
service-selection argument each time (owner's call). In exchange, every AWS
service this project switches on is recorded in
[`docs/infra.md`](infra.md) with what it is for and what it costs, updated in
the pull request that adds it.

**Why the trade.** The reason the persistence roles were left unchosen was
never that DynamoDB was suspect - it was that nobody wanted a service quietly
appearing in the stack because one agent found it convenient. A cost table
that has to be updated in the same PR solves that directly and cheaply,
without making each new table an architecture debate.

**What the numbers actually are.** The whole project costs about **$0.03 a
month** at demo traffic - Lambda, API Gateway, DynamoDB and CloudWatch all sit
inside free tiers or round to zero, and most of the three cents is Amplify
build minutes for PR previews. Lambda's monthly free allowance is perpetual
rather than a 12-month trial, so this does not change when the account's first
year ends.

**The account bill is dominated by something else.** August's account total
was **$6.18**, of which this project was roughly a cent. The rest is
`i-03d53840a3553a537` (`anvil-api`, a `t4g.small` running since 2026-07-23)
and its attached public IPv4 address and 16 GB gp3 volume - about $4.90/month
between them. It predates this project, is in neither Terraform stack, and is
somebody else's workload. Recorded so that nobody reads a bill, concludes the
console is expensive, and starts deleting things to find out which part.

**Enforced by a skill, not by memory.** `.claude/skills/decision-log/` is
loaded when opening a PR or creating an issue. It makes the *check* mandatory
and the *entry* conditional -- a log with an entry for every typo fix stops
being read, which defeats the point -- and it carries the test for what earns
an entry, the format, the rule for annotating a reversal rather than deleting
it, and the requirement that a new AWS service also gets a cost row here.
`branch-and-pr` now points at it for the recording step instead of restating
a shorter version.

**Still true, and not weakened by this:** serverless by default, and anything
always-on needs justification before it is switched on. The escalation order
for compute is unchanged: zip, then container image, then EC2.

---

## 2026-09-09 - Audit session state goes in DynamoDB; the scope-first landing wins over the map-first one

**Status:** done - PR #131

**Decision (persistence).** Audit session state - the audit record, its
uploaded scope GeoJSON, and evidence-pack selections - persists in a
PAY_PER_REQUEST DynamoDB table (`aws_dynamodb_table.audit_state`).
`backend/app/audit_store.py` keeps using process memory locally and switches
to the table only when `AUDIT_STATE_TABLE` is set, so local development gains
no AWS dependency.

**Why.** `POST /api/audits` returned an audit id that later register, graph,
evidence and pack calls then used. On Lambda those later calls are routinely
served by a *different* warm container, whose process-local dict has never
heard of that id - so an audit created successfully would 404 moments later.
This is not a caching nicety; the flow was broken in the deployed
configuration and worked only locally, which is exactly the class of bug the
single-process dev server hides.

**What this does and does not settle.** `CLAUDE.md` reserved §8's persistence
roles, saying not to quietly settle them by writing DynamoDB or S3 into the
spec. This settles exactly one of the three: *durable/queryable metadata*, and
only for session state. Bulky immutable evidence and the disposable cache
remain unchosen - the FIRMS artifact is still packaged and immutable, and
nothing writes to it. CLAUDE.md has been updated to say so rather than to keep
claiming nothing persists.

**Rejected: sticky sessions or a single-container Lambda.** Pinning a caller
to one container (reserved concurrency of 1) would have "fixed" it without new
infrastructure, at the cost of serialising every request in the demo and still
losing state on any cold start. It trades a correctness bug for a throughput
bug.

**Rejected: putting the scope in the client and re-posting it.** Would remove
the server-side store entirely, but the uploaded management-unit boundary is
private audit-scope data (spec 6.2-6.3); round-tripping it through the browser
on every call enlarges its exposure for no benefit.

**Not done: a TTL.** The table has no expiry policy. Rows are few and small,
and choosing a TTL means deciding how long an audit session may be resumed -
a product question nobody has answered. The Terraform comment says so instead
of implying an expiry that does not exist. Encryption at rest is DynamoDB's
default (AWS-owned key); no explicit KMS key was declared.

**Decision (landing surface).** The console lands on
`components/scope/AuditLanding.tsx` - an event-free regional Indonesia map
with a START AUDIT button - not on the Borneo map with an auto-created default
scope that PR #126 shipped two days earlier.

**Why, and what was reversed.** #126 and this PR made opposite choices about
the same screen, and both were on `main`-bound branches at once. The
scope-first flow won on the product boundary: the console must not draw
FireEvents before an authorised scope exists, and #126's auto-bootstrapped
"default demo scope" put real events on screen for a user who had defined no
audit at all. The map-first landing's own rationale - that a form is a poor
first impression - is answered by making the landing a map that simply draws
no events.

**Consequences.** `lib/bootstrapScope.ts` was deleted: it existed only to
share a scope-creation path between the auto-bootstrap and the form, and with
no auto-bootstrap nothing imported it. `AuditStart.tsx` calls the endpoints
directly again. The first-load explainer from #124 was *kept* and rewired -
`ConsoleContextModal` now opens over the landing, reached from a link under
the START AUDIT button - because what it explains (what the console refuses to
conclude) is what a first-time user needs before defining a scope, not after.
Leaving it unmounted would have made it the orphan CLAUDE.md forbids.

**Open.** How much regional context the pre-scope screen should carry is
issue #127, deliberately not settled here.

**Also fixed in passing: CRLF on `main`.** Merging this branch produced 15
conflicts, of which four were whole-file line-ending conflicts -
`backend/app/audit_events.py`, `data_pipeline/README.md`,
`data_pipeline/imagery/scene_selection.py` and
`data_pipeline/sources/open_meteo.py` had landed on `main` as CRLF via the
earlier PR #129 merge from a Windows checkout. Two of those four had *zero*
real content difference. The merge normalises all four back to LF. The repo
has no `.gitattributes` to stop this recurring - see issue for that.

---

## 2026-09-09 - Weather and imagery-scene evidence: spatial grid, local checkpoint, not a new database

**Status:** implemented, `data_pipeline/enrich_audit_events.py`

**Decision.** Weather (Open-Meteo/ERA5, every hourly variable) and
Copernicus scene-selection evidence (Sentinel-1 + Sentinel-2, pre/post
event) for the demo audit geoshape's FireEvents is fetched by a standalone,
human-run script that checkpoints to a local SQLite file
(`data_pipeline/output/enrichment_checkpoint.sqlite`, gitignored) and folds
completed results into the already-committed `audit_triage_detail.json.gz`
via a separate, idempotent `--finalize` step. No new AWS resource was added.

**Superseded its own first version within the same day.** The first cut
fetched weather per event (7 windows + a 5-year rainfall-anomaly baseline,
~7 Open-Meteo calls/event) and imagery per event (2 STAC searches/event) —
for all 3,610 events in the *committed artifact*, which turned out to be the
entire unscoped Sumatra/Kalimantan regional export, not one audit geoshape
(its `scope` metadata carries no geometry at all). A live run hit Open-Meteo
rate limits repeatedly and the bare `except: skip` meant hits degraded data
quality instead of waiting them out. Reworked to: (1) one small geoshape —
the actual demo audit boundary the console shows
(`frontend/src/lib/scope.ts`'s `DEFAULT_MANAGEMENT_UNIT_GEOMETRY`, 25 km
buffer), not the artifact's full event set, cutting 3,610 events to 16; (2) a
weather grid at Open-Meteo/ERA5's own native resolution (~0.15°), fetched
once via multi-location batching, with each event reading its nearest grid
point instead of its own query; (3) two windows (event duration, T-7d) with
every hourly variable, not seven windows plus a 5-year baseline — the
baseline was the single biggest driver of request volume and is dropped
entirely, per direct instruction, not silently; (4) two scope-wide STAC
searches total (one per collection) instead of one pair per event, with
`scene_selection.select_scenes()` (already pure, no-network) reused per
event against the shared results; (5) a rate-limit handler that parses
Open-Meteo's own "try again in a minute/hour" and sleeps-then-retries the
same request, rather than skipping. Net effect verified live: 16/16 events,
both sources, zero errors, well under a minute — down from a projected
several hours.

**Why not a new database.** This enriches one committed *historical*
geoshape, which never changes once computed — exactly the condition under
which a precomputed static artifact beats a live store. A real "any
geoshape, any time" audit needs a live FIRMS backfill plus on-demand
clustering pipeline that does not exist yet (issue #27, P2, not started);
standing up DynamoDB/S3 now would not unlock that by itself, and would be
real Terraform, real IAM, and a real infra PR in exchange for data that fits
in a committed gzip. The checkpoint tables are a reasonable sketch of what a
future live store's schema would need, but building that store is a
separate, larger issue.

**Why offline, not a live Lambda call.** `weather_enrichment.py`'s
underlying metric functions and pandas/numpy are the same dependency weight
the Lambda architecture was built to avoid (see "Clustering runs offline"
below). `scene_selection.py` itself is dependency-light and pure, but the
STAC search feeding it is still a live network call; running either from
Lambda per request adds latency and failure modes a precomputed artifact
does not have, for data that is historical either way.

**Why a script, not run in an agent session.** Even after the grid rework,
a wider geoshape or finer spacing scales request count back up. A
human-supervised batch job run in a terminal that can be left open or
resumed is the right shape for that, not something to launch and wait on
inside a conversation — confirmed by the first version's real rate-limit
hits during exactly such a run.

**What was rejected.** A smaller demo subset instead of full coverage of
the one geoshape — full coverage was every event, nothing held back, once
the geoshape itself was scoped correctly. Storing raw HTTP responses in the
checkpoint instead of computed EvidenceObjects — the shared HTTP session
(`data_pipeline/common/http.py`) already caches raw responses for an hour;
the checkpoint's job is tracking *which grid points and events are done*,
not re-implementing that cache. The 5-year rainfall-anomaly baseline —
real evidentiary value (raw vs. normal-for-the-season), but the largest
single cost driver; dropped per direct instruction rather than assumed.

**Revisit when** issue #27's live ingestion pipeline exists — at that point
the "any geoshape" architecture question is worth relitigating on its own,
with a real target: what a live audit scope's storage needs, not what one
fixed demo geoshape's do. Also revisit if the rainfall-anomaly baseline
turns out to be wanted after all — reintroduce it as a second, explicit
pass over the grid (same batching benefits apply), not a per-event refetch.

---

## 2026-09-09 - The console opens on the map, framed on Borneo, with the explanation as a modal

**Superseded.** The later 2026-09-09 scope-first landing decision above
replaced its automatic default scope and Borneo-first frame. This entry is
retained as the historical diagnosis and rejected-options record.

**Status:** done · issue #125

**Decision.** The first surface on a cold load is the MapLibre canvas itself,
fitted to Borneo's own bounding box, with no FireEvents drawn. The #124
first-load explanation moved from a band above the map into a closable dialog
over it, reopenable from the header. A default demo scope is bootstrapped in
the background through the real `POST /api/audits` → scope upload → history
build sequence, and the camera eases from the Borneo frame to the audit
footprint when it lands.

**Why.** #75 made the scoped map the landing *route* but not the first thing
on screen: a form still rendered above it, and #124 then added an explanation
band above that. The only surface in this build showing real derived data was
below the fold on the frame that decides whether anyone keeps looking.

**What this does not reverse.** The register stays the primary screening
surface, the regional FIRMS archive stays behind its own toggle, and the
unscoped Borneo frame is a *basemap only* — the anti-goal in #57/#58 is an
Indonesia-wide detection browser, and no detection is drawn until a real
scope bounds them. Same boundary #75 argued, one frame earlier.

**Rejected: a hardcoded centre and zoom.** `{longitude: 114, latitude: 1.4,
zoom: 6.2}` framed Borneo on the viewport it was tuned against and cropped
South Kalimantan off the bottom on another — how many degrees a zoom spans
depends on the container. `initialViewState={{bounds, fitBoundsOptions}}`
makes MapLibre solve for the zoom from the container it actually has.

**Rejected: reinstating a hardcoded `DEMO_SCOPE` object.** PR #118 removed one
because a hand-built scope diverged from what the API returns and hid a bbox
shape bug. `lib/bootstrapScope.ts` gives the automatic bootstrap and the scope
form one shared path through the real endpoints instead.

**maxBounds has to stay much wider than the viewport.** MapLibre clamps the
camera to fit `maxBounds` and will silently override the frame you asked for,
with no error — so the unscoped bounds are wide regional guard rails rather
than a tight box around the island.

**A hidden Chrome tab cannot verify a MapLibre change.** Most of the debugging
time here went to a basemap that rendered as a flat olive rectangle in the
automation browser: no tiles requested, no console error, `onLoad` never
firing. The cause was `document.visibilityState === "hidden"` in the
extension's tab — `requestAnimationFrame` never fires there, and MapLibre v6
resolves a vector source declared with an inline `tiles` array by awaiting a
frame (`browser.frameAsync` inside `loadTileJson`), so the source never
loads. Nothing was wrong with the app, the style, or the Carto key. A forced
screenshot yields one frame, so a *second* screenshot shows the real render.
If a map ever looks blank through browser automation, check
`document.visibilityState` before suspecting the code.

## 2026-09-09 - Review routing is calibrated separately from priority and sufficiency

**Status:** implemented · issue #85

**Decision.** FireEvents now expose three independent deterministic outputs:
evidence sufficiency, investigation priority, and human workflow state. The
priority score uses calibrated bands (LOW < 12, MEDIUM >= 12, HIGH >= 20,
URGENT >= 60). Only HIGH/URGENT routes enter `HUMAN_REVIEW`; ambiguous events
remain visible as `REVIEW_RECOMMENDED` rather than being sent to the human
queue by a conservative Stage-1 default.

**Why.** The 2019 FIRMS-only artifact has 396 `LIKELY_FIRE` and 3,214
`AMBIGUOUS` events. Treating both Stage-1 states as human review erased the
meaning of prioritisation. Under this routing policy, 396 events enter human
review and the other 3,214 remain inspectable with explicit priority and
sufficiency states.

**What was rejected.** Fixed quotas, event-ID exceptions, geography-based
responsibility signals, and changes to clustering or scientific feature
calculations. Every escalation carries component evidence IDs and a reason
code; diagnostics report counts and percentages for priority, workflow, and
escalation reasons.

---

## 2026-09-09 — An Amplify console field is Terraform-owned until proven otherwise

**Status:** done · issues #108, #110, #113, #116

**Decision.** Every setting the Amplify console exposes is assumed to be an
attribute Terraform manages, and is declared in `infra/console.tf`, until
someone checks and finds otherwise. After any console wizard run, re-apply and
rebuild.

**Why.** Connecting the repository surfaced four settings in one wizard that
look like console state and are not:

| Console field | Actually | Fixed in |
|---|---|---|
| Live package updates | `_LIVE_UPDATES` env var | #108 |
| Monorepo root directory | `AMPLIFY_MONOREPO_APP_ROOT` env var | #110 |
| Service role | `iam_service_role_arn` on the app | #113 |
| — | the wizard replaces the whole env-var map | #116 |

The first three would have been stripped by the next apply. The fourth went the
other way and bit immediately: the wizard replaced Terraform's environment
variables wholesale, `VITE_API_BASE_URL` vanished, and the build that followed
was green while serving a console that could not reach the API — `client.ts`
falls back to an empty base URL, so every call hit the Amplify origin. A
successful build serving a dead app is the failure worth designing against.

**What was rejected.** Putting `environment_variables` under `ignore_changes`,
which would stop the fight in both directions. It also stops Terraform wiring
`VITE_API_BASE_URL` from the API Gateway stage, which is the one value that
must not be hand-copied. Declaring everything and re-applying after console
work is the lesser cost, because console work happens roughly once per account.

**Recovery, which is now in `docs/environments.md`:** `gh workflow run Infra
--ref main` to restore the settings, then `aws amplify start-job --job-type
RELEASE`, because Vite bakes `VITE_*` in at build time and restoring a variable
changes nothing until a rebuild. Verify by grepping the shipped bundle for the
API host rather than trusting the build status.

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
