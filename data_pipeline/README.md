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
