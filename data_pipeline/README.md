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
against a real, timed run of this repo's own pipeline for one representative
FireEvent case -- the same largest event (`FE-20190901-ce19162367`) the
weather and peat modules above demo against, so all three sections describe
the same case. `manual_estimate.py` is a **reasoned estimate**, not a timed
human trial: each of the seven manual tasks (retrieve FIRMS history,
reconstruct event chronology, retrieve historical weather, inspect peat
context, identify neighbouring events, find imagery metadata, assemble an
evidence summary) is costed from what actually operating the real public tool
involves, with the reasoning recorded per task rather than left as a bare
number. `automated_run.py` chains the real modules above plus two pieces
built only for this benchmark: `find_neighbouring_events` (a lightweight
centroid-distance/time-window proximity check, explicitly **not** the
`FireEventGraph` relationship model of issue #10) and an imagery-metadata
search reusing `sources/copernicus_cds.search()` directly. `report.py`
combines both sides into the comparison and writes
`data_pipeline/output/workload_reduction_report.json`. Run
`python -m data_pipeline.benchmark.report` for the live comparison: last
verified run costed the manual estimate at 140.0 minutes, the automated run
completed the same evidence-reconstruction case in ~26-31s (dominated by the
FIRMS clustering step re-run on 21,519 observations and the Copernicus STAC
search; both are network/CPU calls, not fixed costs), a 99%+ reduction,
21,519 observations compressed to 3,683 FireEvents (5.84x), and full
(49/49 weather + 4/4 peat) evidence-field completeness for this case.

**Read the scope note before citing any of these numbers.** This benchmarks
one task -- reconstructing the evidence for one FireEvent -- not the audit
workflow as a whole, which also includes scope definition, screening
judgement across many events, field verification, and report sign-off. Do
not extrapolate "99% faster evidence reconstruction" into "the audit is 99%
faster."

**`events_to_human_review_queue_compression` is deliberately 1.0 (no
compression), not a fabricated number.** Stage-1 triage (issue #9) doesn't
exist yet, so every FireEvent clustering produces currently reaches a human
reviewer undiminished -- an honest measurement of the pipeline's current
state, to be re-measured once #9 lands, not a placeholder target invented to
fill the metric.

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
