# Data source feasibility spike

Proof-of-concept scripts that check whether each environmental data source
in [`DesignSpecs/Environmental_Assurance_Spec.md`](../DesignSpecs/Environmental_Assurance_Spec.md)
(§7, Data sources) can actually be pulled, and — critically — whether it can
be pulled **historically**, not just for "today." Nothing here writes to a
database. It's a precursor to the real ingestion worker described in the
spec (§8, Persistence architecture): once a source is confirmed workable
here, its logic gets ported into that worker (or a scheduled job) with an
actual write to storage.

## Setup

```
pip install -r data_pipeline/requirements.txt
```

`data_pipeline/.env` already has the NASA FIRMS `MAP_KEY`. Copy
`.env.example` if you need to recreate it. Leave `CDSE_USERNAME`/
`CDSE_PASSWORD` blank until you have a Copernicus Data Space Ecosystem
account — catalogue search works without them.

Run everything:

```
python -m data_pipeline.run_all
```

Or one source at a time, e.g.:

```
python -m data_pipeline.sources.open_meteo
```

Sample pulls land in `data_pipeline/output/` (gitignored).

## FIRMS historical backfill

`sources/nasa_firms_backfill.py` sits on top of `nasa_firms.fetch_area()`
and turns the Area API's 5-day `day_range` cap into an implementation
detail: `fetch_historical_range(bbox, start_date, end_date)` pages an
arbitrary-length request into `<=5`-day calls, retries a window that fails
independently of the shared session's own retry logic, deduplicates
detections at window boundaries, and returns one result set split into
`observations` (inside the Indonesia analysis region) and
`external_context` (inside the queried bbox but outside it) rather than
silently dropping nearby cross-border detections. Run
`python -m data_pipeline.sources.nasa_firms_backfill` for a live demo
against the 2019-08-01..2019-10-31 haze window (268,543 deduplicated
observations, 0 failed windows, last verified run). `external_context` is
empty in that demo because it queries `SUMATRA_KALIMANTAN_BBOX`, which is a
strict subset of the default `INDONESIA_BBOX` analysis region — the
region-split logic itself is covered directly by
`data_pipeline/tests/test_nasa_firms_backfill.py` with synthetic
cross-border points, not left to depend on where real hotspots happened to
fall. `analysis_region` is a bounding box, not a political boundary, so it
cannot precisely separate Indonesian from Malaysian/Bruneian hotspots
inside the same rectangle near the Kalimantan border — see the module
docstring.

## FIRMS spatio-temporal clustering

`clustering/firms_clustering.py` groups raw FIRMS hotspots into coherent
`FireEvent`s -- a single VIIRS pixel flagged hot for one overpass is not an
independently significant fire. `cluster_events(observations)` connects two
detections when they're both within `spatial_threshold_km` (default 2km,
cKDTree-indexed, not O(n^2)) and `temporal_threshold_hours` (default 72h)
of each other; FireEvents are the connected components. Requiring both
constraints on every edge is what makes temporally disconnected reburns at
the same location split into separate events without a dedicated pass --
it falls out of the graph construction. Returns `(events, annotated)`:
`annotated` is the original observations DataFrame plus one `event_id`
column, so raw points are never discarded, only linked. Run
`python -m data_pipeline.clustering.firms_clustering` for a live demo
against the acceptance-criteria sample: 21,519 FIRMS observations -> 3,683
FireEvents (largest: 1,135 observations over 107 hours, 20.6km spatial
extent), last verified run. See the module docstring for the documented
single-linkage chaining limitation and how FireEvent fields here relate to
the canonical `FireEvent` type (`Environmental_Assurance_Spec.md` S9).

### Parameters, diagnostics and lobes (#86)

The thresholds are an explicit, validated `ClusteringParameters` value
rather than two loose keyword defaults. Construction rejects anything
pathological (zero, negative, NaN, infinite, or above the 50 km / 720 h
guardrails), so a bad value fails at the call site instead of silently
producing one event or ten thousand. `ClusteringParameters.from_env()` reads
`FIRMS_CLUSTER_SPATIAL_KM` / `FIRMS_CLUSTER_TEMPORAL_HOURS` for a developer
regenerating under a different radius; a blank variable is the default, a
malformed one is an error, never a fallback. `export_audit_events.py` records
the parameters it ran with in the artifact's `source.clustering` block, and
the committed artifact is always the defaults.

`cluster_run(observations, parameters)` is the same algorithm returning a
`ClusteringRun`, which also carries what the run *did*: how many pairs were
within the radius, how many of those the temporal rule accepted, and the
widest accepted gap and distance. Each `FireEvent` gains `link_count`,
`max_link_gap_hours` and `max_link_distance_km`, so a large event's widest
link can be read against the thresholds to see whether it is one fire or
two bridged by a single detection. `cluster_events` still returns
`(events, annotated)` and still accepts the old keyword thresholds.

`clustering/diagnostics.py` turns a run into numbers a reader can check
against expectations and prints them during export:

```bash
PYTHONPATH=. .venv/bin/python -m data_pipeline.clustering.diagnostics \
    --start 2019-09-01 --end 2019-09-05 --sweep
```

Reports the compression ratio, the size distribution, the singleton and
large-event (100+ observations) counts with their share of observations,
the link statistics, and the five largest events with their sub-clusters at
1 km. `--sweep` re-clusters the same window across a small threshold grid
(1/2/3/5 km by 24/48/72/120 h) so the effect of each threshold is measured
rather than guessed. Last verified run on the 2019 window, defaults:
20,471 observations, 3,610 events, 419,239 pairs within 2 km of which
378,619 were accepted (widest link 2.0 km / 71.1 h). The largest event stays
at roughly 1,100 observations across the whole sweep grid, so that structure
is in the data, not the radius. Output goes to
`data_pipeline/output/clustering_diagnostics.json`, which is not committed.

`event_lobes(event, observations, lobe_distance_km)` splits one event into
spatial-only components at a tighter radius (default 1 km). It never changes
membership; it is a description of an event that was already formed, for a
reader deciding whether a large event should be described as one fire
complex with several lobes. At or above the clustering radius it always
finds one lobe, since every clustered pair was already within it.

## Historical weather-window enrichment

`enrichment/weather_enrichment.py` reconstructs the weather context around a
`FireEvent` -- `fetch_weather_evidence_for_event(event, lat, lon)` returns a
`WeatherEvidenceBundle` covering seven windows relative to the event's own
timestamps (T-90d/T-30d/T-7d/T-72h/T-24h lookbacks ending at
`first_detection`, `event_duration`, and `T0_to_T+48h`), each with rainfall
accumulation, rainfall-free days, max temperature, mean relative humidity,
mean wind speed, circular-mean wind direction, topsoil moisture where
available, a rainfall anomaly against a multi-year seasonal baseline, and
disagreement against NASA POWER's independent daily estimate for the same
window. `to_evidence_objects()` converts the bundle into
`Environmental_Assurance_Spec.md` §16 `EvidenceObject`s, one per
window/metric so each is independently traceable. `compute_weather_windows()`
is pure (no network) and is what the tests exercise directly against
synthetic Open-Meteo-shaped DataFrames; only `fetch_weather_evidence_for_event`
and its `_demo()` touch the network. Run
`python -m data_pipeline.enrichment.weather_enrichment` for a live demo
against the largest FireEvent in the 2019 haze sample: last verified run
produced 49 evidence objects (7 windows x 7 metrics, all present) for
`FE-20190901-ce19162367`, correctly flagging T-72h/T-24h rainfall as ~100%
below the 5-year seasonal baseline (the dry-season conditions the 2019 haze
event is known for) and a NASA POWER rainfall disagreement of up to 74mm on
the T-90d window -- itself evidence of how much two independent reanalysis
products can differ over a 90-day accumulation. See the module docstring for
why NASA POWER is a disagreement check rather than a second primary source,
and why historical anomaly is computed for rainfall only.

`enrich_audit_events.py` is the batch job that runs this module (plus
`imagery/scene_selection.py`) against the demo audit geoshape's FireEvents
(the actual boundary the console shows, not the full committed artifact --
that artifact's 3,610 events are the whole unscoped regional export) and
folds the results into `backend/app/data/audit_triage_detail.json.gz` --
weather and imagery-scene evidence for the console's evidence drawer, not
just the module demos above. Weather is fetched once per point on a spatial
grid over the geoshape (batched, at Open-Meteo/ERA5's own native
resolution) rather than once per event; imagery is two scope-wide STAC
searches, not one pair per event. It is a human-run, resumable script
(SQLite checkpoint, safe to Ctrl+C and rerun), not something to run inside
an agent session -- see its own docstring for usage and
`docs/decision-log.md` (2026-09-09) for why this stays a local checkpoint
rather than a new database.

## Peat intersection and context service

`enrichment/peat_context.py` makes peat a first-class environmental attribute
of every `FireEvent` -- `get_peat_context_for_event(event)` returns a
`PeatContext` covering direct footprint intersection, peat fraction within
the event's footprint and a configurable buffer, distance to the nearest
mapped peat if none intersects, and (via `peat_fraction_along_corridor`) the
peat fraction of a straight-line corridor between two linked events'
centroids. It reads the Greifswald Mire Centre's Global Peatland Map 2.0 (a
single static 3.6MB zip containing one ~550MP unprojected-WGS84 GeoTIFF) with
Pillow plus hand-rolled affine math rather than pulling in a GDAL/rasterio
stack, downloads and crops it to `INDONESIA_BBOX` exactly once, and caches
the crop as a `.npy` array (~9MB on disk) in `data_pipeline/output/` so every
later call in the same or a later process skips the network entirely.
`compute_peat_context()` is pure (no network) and is what the tests exercise
directly against a small synthetic raster; only `load_peat_raster()` and its
`_demo()` touch the network. `to_evidence_objects()` converts a `PeatContext`
into `Environmental_Assurance_Spec.md` §16 `EvidenceObject`s, and always
attaches a non-inference limitation stating that peat overlap is geometric
context only -- never a claim of underground combustion, smouldering, or
fire persistence, which stays an interpretation layer's hypothesis to weigh
against SAR persistence and elapsed time (§15). Run
`python -m data_pipeline.enrichment.peat_context` for a live demo against the
same largest FireEvent used in the weather-enrichment demo above: last
verified run found the event's footprint and 5km buffer 100% mapped peat
(`FE-20190901-ce19162367`, direct on-peat centroid) and flagged that the
event's 20.6km spatial extent exceeds the default 5km buffer radius, so the
footprint check -- not the buffer -- is the representative intersection
result for a fire complex this large.

## Auditor workload-reduction benchmark

`benchmark/` compares a documented manual-evidence-reconstruction estimate
against a timed run of this repo's own pipeline for one representative
FireEvent case -- the same largest event (`FE-20190901-ce19162367`) the
weather and peat modules above demo against, so all three sections describe
the same case. `manual_estimate.py` is a **reasoned estimate**, not a timed
human trial: each of the seven manual tasks (retrieve FIRMS history,
reconstruct event chronology, retrieve historical weather, inspect peat
context, identify neighbouring events, find imagery metadata, assemble an
evidence summary) is costed from what actually operating the real public tool
involves, with the reasoning recorded per task rather than left as a bare
number. By default `automated_run.py` reads observations from the committed
`SOURCE_JSON` export and FireEvents/triage from the committed gzipped audit
artifacts, so the benchmark does not require a FIRMS key. Pass
`--live-firms` to `python -m data_pipeline.benchmark.report` only when an
explicit live rebuild is wanted. It chains the real modules above plus two pieces
built only for this benchmark: `find_neighbouring_events` (a lightweight
centroid-distance/time-window proximity check, explicitly **not** the
`FireEventGraph` relationship model of issue #10) and a Copernicus STAC
search followed by the deterministic scene selector. `report.py`
combines both sides into the comparison and writes
`data_pipeline/output/workload_reduction_report.json`. Run
`python -m data_pipeline.benchmark.report` for the artifact-backed comparison.
The report also measures FireEvents inside a supplied private boundary plus
buffer versus the full history; without a boundary this stage is explicitly
reported as not measurable.

**Read the scope note before citing any of these numbers.** This benchmarks
one task -- reconstructing the evidence for one FireEvent -- not the audit
workflow as a whole, which also includes scope definition, screening
judgement across many events, field verification, and report sign-off. Do
not extrapolate "99% faster evidence reconstruction" into "the audit is 99%
faster."

## Deterministic Stage-1 triage

`triage/stage1.py` screens reconstructed FireEvents before imagery acquisition
or AI analysis. It always evaluates FIRMS confidence, FRP, and repeat
observations. Batch triage derives spatially and temporally nearby FIRMS
detections with one spatial index. Callers may add provenance-linked
land-cover, urban, settlement, persistent heat-source, volcano/geothermal, and
recent-rainfall context through `Stage1Context`. Missing context stays explicit
as `NOT_EVALUATED`; it is never treated as evidence that a feature is absent.
`MetricEvidence.from_evidence_object()` adapts existing weather or contextual
EvidenceObjects while preserving their source, quality, limitations, time
window, retrieval time, algorithm version, and raw reference.

Every result includes all rule evaluations, the evidence IDs behind each
measured claim, separate fire/non-fire support scores, the decisive rule IDs,
and a budget explanation. Only `AMBIGUOUS` requests bounded AI review.
`LIKELY_NON_FIRE` prevents deeper investigation spend but remains a screening
state, not a conclusion about ignition cause or responsibility. Thresholds are
versioned as `stage1-rules-v1` and should be calibrated against labelled cases
before production use.

The workload benchmark now measures FireEvents-to-review-queue compression
using FIRMS-only Stage-1 evidence for the full collection. Its result records
the state counts and exactly which optional rules were unavailable, rather
than presenting missing context as benign. Run the benchmark again before
citing a numeric queue-compression result; it depends on the current cached
FIRMS sample.

## Deterministic Copernicus scene selection

`imagery/scene_selection.py` turns the Copernicus STAC response into four
inspectable selection slots: closest usable Sentinel-2 pre/post scenes and
closest Sentinel-1 pre/post scenes. Sentinel-2 uses the configured scene-level
cloud-cover threshold (default 50%); Sentinel-1 is not cloud-filtered. The
selection stores product ID, acquisition time, sensor, orbit metadata, cloud
cover where available, temporal distance from the event boundary, catalogue
reference, and product/download reference. Missing optical cloud metadata is
excluded conservatively when the cloud threshold is active.

The selector is pure and versioned (`copernicus-scene-selector-v1`), so the
same frozen STAC response and event timestamps reproduce the same result.
`sources/copernicus_cds.py` keeps the network search separate and exposes the
selector for callers that already fetched the features. Scene metadata is
provenance for later evidence processing, not a finding about cause or
responsibility.

## Processed Sentinel context images (CDSE Process API)

`generate_processed_imagery.py` turns each selected scene into a picture an
auditor can read. For every demo FireEvent whose evidence names selected
scenes, it asks the Copernicus Data Space Ecosystem **Process API** to
render a 10 km square around the event centroid at 1024 px, server-side, and
commits the result under `frontend/public/imagery/<eventId>/` next to a JSON
sidecar and a `manifest.json` covering all events. Nothing is downloaded
beyond the finished image: no SAFE products, no local SAR toolchain.

Two recipes, in `imagery/process_api.py`:

| Recipe | Sensor | UI label | What CDSE does | What the evalscript does |
|---|---|---|---|---|
| `s2-swir-false-colour-v1` | Sentinel-2 L2A | Optical context | bilinear resampling | R=B12, G=B08, B=B04 with a fixed 2.5× gain; no-data black |
| `s1-vvvh-db-composite-v1` | Sentinel-1 GRD IW DV | Radar context | orthorectify, Gamma0 terrain (Copernicus DEM 30 m), Lee 3×3 speckle | R=VV dB (−20..0), G=VH dB (−25..−5), B=VV−VH dB (0..15); no-data black |

Three choices matter more than the recipes:

- **The request is pinned to the selected scene.** The time range is the UTC
  day of the product the `ENV_IMAGERY_*` EvidenceObject already names, and
  Sentinel-1 also pins the orbit direction, so the picture is *of* the scene
  the drawer describes rather than whatever date the API's `leastCC`
  mosaicking would prefer over a wider window. Each sidecar records
  `source_evidence_id`, the product ID, the exact data filter, and the SHA-256
  of both the evalscript and the request.
- **The stretches are fixed, not per-scene.** `sentinel1_visualization.py`'s
  2–98 % percentile stretch is right for one image alone and wrong for a
  pre/post pair, which would each be normalised to their own contents.
- **No data is recorded, not papered over.** An API error, or an image where
  under 5 % of pixels carried data (an orbit clipping the corner of the
  square), writes a `.missing.json` with the reason and no image. The
  manifest lists it under `missing`; nothing from another date is substituted.

It needs a CDSE **OAuth client** (`CDSE_CLIENT_ID` / `CDSE_CLIENT_SECRET` in
`.env`), registered under *User settings → OAuth clients* in the CDSE
dashboard. The `CDSE_USERNAME`/`CDSE_PASSWORD` pair is for product download
and is not accepted by Sentinel Hub APIs. Without the client it exits 2 and
says so. Runs are idempotent: an image already on disk is skipped unless
`--force`, and `--manifest-only` rebuilds the manifest from whatever the
directory holds without a network call.

```bash
python -m data_pipeline.generate_processed_imagery              # everything not yet rendered
python -m data_pipeline.generate_processed_imagery --limit 2    # smoke test
python -m data_pipeline.generate_processed_imagery --event FE-20190901-1ecb99d2e4 --force
```

The images are display products for human orientation. The sidecar and
manifest carry per-recipe limitations, and the Sentinel-1 ones say the
important thing outright: backscatter is surface and structural context; it
does not observe sub-surface peat combustion, and a change in it is not a
burn map.

## FireEventGraph relationship model

`graph/fire_event_graph.py` builds a deterministic, versioned candidate graph
over the coherent `FireEvent` nodes produced by clustering. It does not accept
raw FIRMS rows and does not ask an LLM to infer relationships. Candidate edges
carry geographic distance, elapsed time and temporal ordering, event-buffer
overlap, first-order surface-spread compatibility, and optional wind alignment,
directional compatibility, peat-corridor fraction, shared environmental
episode, and historical recurrence. Optional context is supplied as already
derived weather/peat/history values; unavailable context remains `None`.

Edges are routed to `RELATED_POSSIBLE`, `PROPAGATION_COMPATIBLE`,
`PROPAGATION_WEAK`, `INDEPENDENT_PLAUSIBLE`, or `UNRESOLVED`. Each edge keeps
supporting/contradicting derived-evidence IDs and `fire-event-graph-v1`, so a
map or later analysis can inspect why a relationship was proposed. A directed
edge points from the earlier non-overlapping event to the later one; an
overlapping pair is explicitly non-directional. These are investigative
relationships only: geographic or environmental association is not a finding
about cause, intent, responsibility, or legality.

## Surface-fire compatibility model

`propagation/surface_fire.py` provides `surface-fire-ellipse-v1`, a pure
first-order compatibility screen for later FireEvent clusters. It uses a
caller-supplied head/back/flank spread rate, orients the ellipse downwind from
historical meteorological wind, and records every later cluster as inside,
outside, or not evaluated when wind is missing. `compare_event_progression()`
returns the overall compatibility plus `observations_outside_expected_envelope`
for inspection in a report or map. The model is explicitly labelled as an
estimate, assumes homogeneous fuel and simplified terrain, does not include
spotting, and does not model underground peat propagation. An outside cluster
is a compatibility observation, not a conclusion about ignition cause or
responsibility.

## Explainable Fire Complexity evidence

`complexity/fire_complexity.py` derives the canonical Fire Complexity
features for one reconstructed `FireEvent` as 13 individually named,
versioned EvidenceObjects: duration, observation count, spatial extent,
centroid movement, directional consistency, wind alignment, FRP variability,
distinct thermal lobes, peat overlap, nearby event count, historical
recurrence, unexplained detections, and surface-propagation mismatch. The
result has no aggregate magic score. Each field carries its value, status,
time window, source, quality, limitations, algorithm version, and raw event
reference so a reviewer can inspect why it was or was not evaluated.

The function is pure and accepts already-derived peat, recurrence, and
surface-propagation context. Missing optional context stays `NOT_EVALUATED`,
and outside-envelope observations are compatibility mismatches only; they do
not establish a separate fire, underground propagation, cause, intent, or
responsibility.

## Explainable Investigation Priority routing

`priority/investigation_priority.py` turns environmental evidence into a
bounded 0--100 Investigation Priority Score and one of `LOW`, `MEDIUM`,
`HIGH`, or `URGENT`. It combines nine explicit, weighted routing factors:
event validity, environmental significance, event complexity, evidence
inconsistency, unresolved event relationships, evidence sufficiency, peat
involvement, land-change indicators, and propagation uncertainty. Every
factor is returned as a component with its normalized value, weight,
contribution, evidence IDs, source, quality, and limitations.
The score is the sum of `weight * normalized_signal * evidence_quality` for
evaluated factors; the weights sum to 100. This makes lower-quality evidence
visible in the contribution instead of turning it into a false certainty.

The scorer can consume existing Stage-1, Fire Complexity, FireEventGraph,
peat, and surface-compatibility results. Missing context is
`NOT_EVALUATED`, never silently treated as reassuring evidence. The weights
are a transparent routing policy rather than calibrated probabilities. The v2
score bands are LOW below 12, MEDIUM at 12, HIGH at 20, and URGENT at 60;
they are routing bands, not quotas. The separate review-routing layer
escalates only HIGH/URGENT results, while preserving ambiguous events as
review-recommended. The scorer rejects company identity/reputation, previous misconduct, guilt,
intent, culpability, responsibility, and legal fields entirely. A priority
result is therefore a queueing aid for human investigation, not a finding
about who caused an event or who is responsible for it.

## Golden historical regression cases

`golden/` freezes real 2019 haze-window data end to end so the pipeline's
output for known input never silently drifts as the code around it changes.
`golden/cases.py` defines three cases, each a real FIRMS-detected FireEvent
picked from the cached Sumatra/Kalimantan sample: `simple`
(`FE-20190904-4904392c16`, 3 detections, 0.16km extent -- the smallest
non-degenerate shape), `complex_multilobe` (`FE-20190901-ce19162367`, the
1,135-detection/107h/20.6km event already used as the worked example
elsewhere in this README), and `peat_related` (`FE-20190901-15f6721402`, East
Kalimantan, 71.4% footprint peat fraction -- picked because it is *partial*,
exercising the peat-fraction metric's actual range rather than the complex
case's saturated 100%). All three happen to sit on mapped peat, since the
sampled bbox is peat-dominated lowland; `peat_related` is the one chosen to
make that metric interesting, not the only one that has it.

Each case directory holds real, frozen inputs -- FIRMS observations, an
Open-Meteo/NASA POWER weather window, a small crop of the actual Global
Peatland Map 2.0 raster (padded so the default buffer/search radii never run
off its edge), and a Copernicus STAC search response -- plus `expected/`,
the output of `cluster_events`, `compute_weather_windows`,
`compute_peat_context`, and this module's own imagery-candidate mapping
against those frozen inputs. `tests/test_golden_regression.py` recomputes
each from the frozen inputs and asserts it still matches `expected/` --
**no network access**, so it runs in CI like any other test. Run
`python -m data_pipeline.golden.build_golden_cases` only when a case's
frozen inputs genuinely need to change (a new case, or a source's response
shape changing); it overwrites every fixture from live sources, so review
the diff it produces rather than trusting it blindly.

Weather observation text rounds to two decimal places for readability;
the structured `value` retains the computed precision. Formatting-only
changes should update only expected observation strings, leaving frozen
source inputs and numeric expectations intact.

One dtype trap worth knowing before touching this: Open-Meteo's response
decodes to `float32` (`sources/open_meteo.py`'s `_hourly_to_df`), but
`pd.read_csv` on the frozen CSV infers `float64` from the written decimal
text -- summing the extra precision gives a value that differs from the
frozen one in the last couple of decimal places. The test casts the relevant
columns back to `float32` after loading for exactly this reason; don't
remove that cast to "simplify" the loader.

## Provider interface

`nasa_firms.py`, `open_meteo.py`, `nasa_power.py`, `copernicus_cds.py`, and
`global_peatland_database.py` all return a `SourceResult`
(`common/result.py`) from `fetch_historical_sample()` instead of a bespoke
dict or a bare `None` — one status enum (`PASS`/`FAIL`/`SKIPPED`), one
provenance shape (endpoint, retrieved-at, auth method), and a
`limitations` list carrying each source's known caveats (e.g. FIRMS's
5-day `day_range` cap). `run_all.py` reads that shape to print a per-source
PASS/FAIL/SKIPPED summary without knowing anything module-specific.
`esa_worldcover.py` and `overpass_api.py` are still plain print-and-return
spike scripts; `run_all.py` treats "ran without raising" as PASS for those.

## Sources covered

| Module | Source | Auth needed | Historical? |
|---|---|---|---|
| `sources/nasa_firms.py` | NASA FIRMS (MODIS/VIIRS hotspots) | Free MAP_KEY (provisioned) | **Confirmed** — VIIRS_SNPP_SP availability reports 2012-01-20 through present; a real pull for the 2019 haze window over Sumatra/Kalimantan returned 21,519 individual hotspots. Area API day_range is capped at 5 days per call (not 10). |
| `sources/open_meteo.py` | Open-Meteo Historical Weather Archive | None | Yes — ERA5 reanalysis; tested back to 2005 and against the 2019 haze window. **Confirmed point-specific**: queries 3 distinct Indonesian peat coordinates and shows values differ, plus a single batched multi-point request. |
| `sources/nasa_power.py` | NASA POWER | None | Yes — daily point archive tested from 1990; hourly tested for 2019. Point-based by construction. |
| `sources/copernicus_cds.py` | Copernicus Data Space Ecosystem (Sentinel-1/2 STAC catalogue) | None for search; free account + OAuth2 token for product download | Yes — STAC search over Sumatra/Kalimantan for the 2019 window; no auth required for search itself. |
| `sources/esa_worldcover.py` | ESA WorldCover (10m land cover) | None | **No** — static product, only two epochs exist (2020 v100, 2021 v200). Script resolves the S3 tile name per point and confirms it exists via HTTP HEAD. |
| `sources/global_peatland_database.py` | Global Peatland Database (Greifswald Mire Centre) | None | **No** — single static global raster, no time series, no query API. Script just confirms the download link is live. |
| `sources/overpass_api.py` | Overpass API (OpenStreetMap roads/settlements) | None | **No** — confirmed via a Jakarta control point (12,274 ways with no date filter) that `[date:...]` attic queries return 0 for every historical date tried (2010/2015/2020). This public instance's attic database is empty/unsupported, not actually time-travelling. Current-snapshot only. |

## Not yet wired — pending accounts

These need signups being handled separately. Placeholder modules exist so
the interface is already there when the accounts land — just fill in the
request logic and set the key in `.env`.

| Module | Source | Notes |
|---|---|---|
| `sources/future/global_forest_watch.py` | Global Forest Watch Data API | Deprioritized post-MVP (`Environmental_Assurance_Spec.md` §30); if built, concession attribute lookup by point stays attribute-only per §4 — never store or render third-party concession polygon geometry. |
| `sources/future/bmkg.py` | BMKG (Indonesian met/climate/geophysics agency) | Some feeds are public without a key at `data.bmkg.go.id`; confirm what an account unlocks once you have one. |

`run_all.py` runs both groups and prints a combined pass/fail summary; the
pending-account ones just report "skipped" until their key is set.

## Planned cron cadence (once ported to the real ingestion worker)

Matches the cadence column of `Environmental_Assurance_Spec.md` §7 (Data sources):

| Source | Cadence |
|---|---|
| NASA FIRMS | ~daily (VIIRS overpasses Indonesia ~2x/day) |
| Open-Meteo / NASA POWER | hourly/daily |
| Copernicus Sentinel-1 | ~6 days (nominal constellation revisit) |
| Copernicus Sentinel-2 | whenever a low-cloud pass exists |
| ESA WorldCover | static — re-check only when ESA ships a new epoch |
| Global Peatland Database | static — one-off download, not polled |
| Overpass API | static-ish — periodic refresh, not time-critical |
| GFW / BMKG | TBD once accounts exist |

## Notes / gotchas found while building this

- **Open-Meteo answers the "specific lat/lon" question**: yes, it's a
  per-point API. There is no such thing as "one value for all Indonesia"
  — every request needs a lat/lon (or a comma-separated list for a batch
  call), so this was never actually a limitation, just something to
  confirm empirically.
- **FIRMS area API day_range maxes out at 5** (not 10 as older
  documentation/folklore suggests) — a multi-day historical backfill
  needs paging by shifting the start date.
- **ESA WorldCover and the Global Peatland Database are not
  cron-pollable** in the usual sense — they're static products. Treat
  them as one-off downloads refreshed only when the upstream publishes a
  new epoch, not as recurring ingestion jobs.
- **Copernicus catalogue search needs no account** — only bulk product
  *download* does. Worth exploiting: the STAC search can run in the
  ingestion path immediately, and the OAuth2 step can be deferred until
  actual imagery download is needed.
- **Overpass silently "fails closed" on `[date:...]`** rather than
  erroring — it returns HTTP 200 with an empty result set instead of
  raising, which would have looked like a successful historical query if
  we hadn't cross-checked against a point with known dense road coverage.
  Anything depending on OSM history should re-verify against a different
  Overpass mirror (or the dedicated attic endpoint) before being trusted.
- **Two infra gotchas hit while building this, both fixed in
  `common/http.py`:** (1) `firms.modaps.eosdis.nasa.gov` fails plain
  `requests`/certifi TLS verification on Windows with
  `CERTIFICATE_VERIFY_FAILED` — the server doesn't send its full
  intermediate chain and relies on the client fetching it via AIA, which
  Windows does natively but OpenSSL doesn't. Fixed by injecting
  `truststore` so Python verifies against the OS trust store instead.
  (2) Overpass returns `406 Not Acceptable` for the default
  `python-requests/x.y` User-Agent — fixed by setting an explicit one on
  the shared session.
