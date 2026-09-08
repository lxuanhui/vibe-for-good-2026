# Environmental Assurance Investigative Efficiency Tool
## Claude Code Build Specification — v2 (Peatland-Aware Architecture)

**Project type:** Hackathon MVP (Vibe For Good 2026)
**Primary challenge:** ACCA Challenge Statement #1
**Core positioning:** AI-driven investigative-efficiency tool for environmental assurance
**Primary geography for MVP:** Indonesia
**Tech stack:** Vite + React frontend, Cloudflare Workers for all backend (KV/D1 for storage)
**Critical product boundary:** The system does **not** determine blame, guilt, legal responsibility, intent, or culpability.

This version supersedes the original spec's Stage 0/1 detection model. The core change: **FIRMS cannot be the sole gate for imagery acquisition.** Peatland fires are the most damaging fire type in Indonesia and are frequently invisible to FIRMS — they smolder underground at low temperature, are obscured by canopy and smoke, and during the worst haze events satellites can detect *fewer* fires, not more. The architecture below is built to compensate for that documented sensor gap, not just to triage FIRMS output.

---

# 2026-09-08 Canonical Audit-Workflow Update

> **Status:** This section overrides conflicting workflow, concession-boundary, UI-entry-point, and hypothesis wording elsewhere in this legacy specification. The consolidated source of truth is `Environmental_Assurance_Spec.md`.

## Product workflow

The MVP is an **audit-scope-first historical environmental review tool**, not an Indonesia-wide enforcement monitor. The auditor begins with an engagement-defined spatial and temporal scope, reconstructs the historical fire register, screens events temporally in a table, then sends selected events and contextual neighbours into the spatial investigation map.

```text
Create Audit Review
  -> upload/draw management-unit boundary (or lat/lon + radius fallback)
  -> choose review start/end dates
  -> choose contextual buffer
  -> acquire/filter FIRMS + relevant S1/S2/weather/peat evidence
  -> cluster observations into FireEvents
  -> Historical Fire Register (Table-first)
  -> select events
  -> Investigate on Map
  -> Evidence Drawer + imagery + provenance
  -> Generate Investigation Analysis
  -> Investigator/Skeptic structured assessment
  -> Add selected events to Audit Evidence Pack
  -> Human auditor verifies/decides
```

## Audit-supplied boundary policy

The product does **not** provide a searchable public directory of named Indonesian concession polygons. For an audit engagement, an authorised user may upload a management-unit boundary as private workspace data (GeoJSON/KML/KMZ/SHP where implemented), draw an area, or use lat/lon + radius for quick analysis. The geometry is treated as client-supplied audit scope, not proof of ownership or responsibility.

Uploaded geometry may be retained privately for the audit according to tenant retention policy and may be deleted at audit completion. Environmental reasoning should use an anonymised `scope_id`; company identity must not alter physical/environmental scores.

Always query a configurable external context buffer around the audit boundary. Classify events as `INSIDE_SCOPE`, `BOUNDARY_INTERSECTING`, or `EXTERNAL_CONTEXT`. External events may explain events inside scope but are not automatically subjects of the engagement.

## Table-first, map-second UX

The **Historical Fire Register** is the primary screening workspace. It compresses raw observations into coherent FireEvents and supports sorting/filtering by date, scope relation, persistence, peat overlap, complexity, evidence sufficiency, investigation priority, and review state.

The Palantir-style map is the **Spatial Investigation Workspace**. It receives selected FireEvents plus relevant contextual neighbours and is optimized for event relationships, boundary context, peat, wind, satellite imagery, and surface-propagation compatibility. Do not dump the entire regional raw FIRMS archive into this view by default.

## Event interaction

Clicking a FireEvent opens an Evidence Drawer. Render cached/cheap deterministic metrics immediately; load Sentinel imagery asynchronously. Every important metric should be inspectable: selecting peat overlap highlights the intersection; selecting nearby events highlights graph edges; selecting surface-spread compatibility shows observed detections versus the first-order ellipse; selecting weather opens the supporting time series.

AI is an explicit downstream action: `Generate Investigation Analysis`. Agents receive only structured evidence IDs and must return competing explanations, unresolved disagreement, evidence sufficiency, and recommended verification questions. AI does not create the observations.

## Updated hypothesis space

Prefer event-history hypotheses over actor categories:

- H1 Independent local ignition
- H2 Surface propagation from an earlier neighbouring event
- H3 Peat-mediated persistence/propagation
- H4 Multiple related land-management ignitions
- H5 Regional independent events under shared conducive conditions
- H6 Other mechanism
- Evidence sufficiency is a separate state: `SUFFICIENT | PARTIAL | INSUFFICIENT`

These hypotheses do not establish intent, illegality, ownership liability, or legal responsibility.

## Assurance differentiation

Government enforcement intelligence and assurance intelligence may use similar remote-sensing inputs but support different decisions. Government systems can monitor territory-wide current risk and prioritize intervention. This product begins with an auditor-defined management unit and historical review period and asks: **what happened within and around this audit scope, which event relationships remain unresolved, and what should be verified with scarce field time?**

## Smallholder/fairness principle

The product should lower the technical cost of assembling environmental evidence without privileging the party with the larger GIS, ESG, legal, or expert team. Evidence must cut both ways. A hotspot inside a supplied boundary is not evidence that the fire originated there. Exculpatory propagation evidence and uncertainty receive the same visibility as evidence supporting deeper scrutiny.


# 1. Product Thesis (unchanged)

Existing satellite systems already detect thermal anomalies and possible fires. The bottleneck is deciding which detected events deserve scarce human investigative effort — and, as of v2, also detecting fire activity that thermal-only systems miss entirely.

The system:
1. ingests imperfect fire/thermal-anomaly detections;
2. cheaply eliminates obvious dead ends;
3. reconstructs the environmental state around qualified events using multiple sensor modalities;
4. links related detections into fire complexes across time and combustion phase;
5. organises heterogeneous evidence into an auditable evidence package;
6. uses adversarial AI agents to test competing hypotheses;
7. exposes uncertainty and disagreement;
8. generates a structured investigation pack;
9. leaves the final decision to a human auditor.

The deterministic and environmental evidence layers must retain standalone value even with all LLM output removed.

---

# 2. Non-Goals (updated)

Do **not** build the MVP as:

- a fire attribution engine, arson detector, or company guilt score
- a legal conclusion engine or automated enforcement system
- a replacement for human auditors, NASA FIRMS, or remote-sensing platforms
- a canal/drainage-ditch detector — **dropped from scope.** Mapping newly dug drainage as evidence of deliberate arson preparation is a defamation-adjacent inference this product should not make, and it's a heavy computer-vision workload for marginal audit value. Peat hydrology stress is instead inferred from soil-moisture proxies, not intent-implying infrastructure detection.
- a public searchable concession-boundary directory or a system that republishes named Indonesian concession shapefiles. **The audit workflow may accept an auditor/client-supplied management-unit polygon as private workspace data.** Uploaded geometry is scope input only, is access-controlled, and is never treated as proof of ownership or responsibility.
- a consumer of RSPO Hotspot Hub. That platform re-filters raw FIRMS data down to a consent-gated subset of RSPO member concessions (~35% SEA consent rate) — narrower coverage than raw FIRMS + our own triage, not a cleaner upstream source.

---

# 3. Core Design Principle — Four Layers (unchanged)

**Layer A — Observed evidence** (raw retrieved facts, expanded in v2, see Section 5)
**Layer B — Derived metrics** (deterministic calculations, expanded in v2, see Section 6)
**Layer C — AI interpretation** (LLM agents reasoning over structured evidence, see Section 8)
**Layer D — Human decision** (ignore / request more evidence / escalate / field-verify / open investigation)

Never collapse these layers. Every AI factual claim traces to an evidence ID.

---

# 4. High-Level Architecture (v2)

```text
Cron Trigger Worker (single ingestion node)
    |
    |-- polls NASA FIRMS on schedule (VIIRS overpasses Indonesia ~2x/day)
    |-- applies cheap deterministic triage (Stage 1, unchanged from v1)
    |-- writes LIKELY_FIRE / AMBIGUOUS / rejected candidates to KV/D1
    |
    v
Qualifier / Raw Overlay Layer  <-- all consumers read from here, never hit FIRMS directly
    |
    |-- FIRMS thermal hotspots            (cadence: ~daily)
    |-- Sentinel-1 SAR VH backscatter      (cadence: ~6 days, nominal S1C/S1D constellation)
    |-- Sentinel-2 raw optical quicklook   (cadence: whenever cloud-free pass exists)
    |-- Peat hydrology overlay:
    |     - SMAP / ERA5-Land soil moisture (proxy for groundwater stress)
    |     - KHG peat hydrological unit classification (protected dome vs. production zone)
    |
    v
Fire Candidate Decision (REJECT / ACCEPT / AMBIGUOUS) --> Stage-1 Agent Review (ambiguous only)
    |
    v
Qualified Fire Event
    |
    v
FireComplex Linking (deterministic, Layer B)  <-- see Section 7
    |
    v
Evidence Acquisition Layer (expensive, gated — only for qualified events)
    |
    |-- Sentinel-2/Landsat dNBR (burn severity, needs pre/post cloud-free composite)
    |-- Sentinel-2/Landsat NDMI (desiccation index)
    |-- Richards elliptical fire-growth model + single Kalman filter  <-- see Section 8
    |-- FWI / KBDI / VPD (fire-weather indices)
    |-- [Phase 2] Concession attribute lookup (see Section 9)
    |
    v
Structured Evidence Store
    |
    +-----------------------------+
    |                             |
    v                             v
Investigator Agent          Skeptic Agent
    |                             |
    +------------+----------------+
                 |
           fixed rounds (max 3)
                 |
                 v
        Hypothesis Support Matrix
                 |
                 v
                Report Generator --> PDF Investigation Pack --> Human Auditor
```

---

# 5. Layer A — Observed Evidence (expanded)

| Category | Source | Cadence | Cost tier |
|---|---|---|---|
| Thermal hotspot | NASA FIRMS | ~daily | Raw / qualifier |
| SAR backscatter (VH drop) | Sentinel-1, Copernicus Data Space Ecosystem | ~6 days (S1C/S1D nominal, restored mid-2026) | Raw / qualifier |
| Optical quicklook (true/false color tile) | Sentinel-2, via Sentinel Hub OGC/WMS + Catalog API | whenever a low-cloud pass exists | Raw / qualifier |
| Soil moisture (GWL proxy) | SMAP (NASA Earthdata) or ERA5-Land (Copernicus CDS) | few days | Raw / qualifier |
| Peat hydrological unit (KHG) classification | KLHK Geoportal ArcGIS REST (`geoportal.menlhk.go.id/arcgis/rest/services`, `dbgis.menlhk.go.id/arcgis/rest/services/KLHK`) | static, updated periodically | Raw / qualifier |
| Weather (temp, humidity, wind, rainfall) | Open-Meteo, NASA POWER | hourly/daily | Raw / qualifier |
| Land cover class | ESA WorldCover | static | Raw / qualifier |
| Roads/settlements | OpenStreetMap Overpass | static | Raw / qualifier |
| Volcano/geothermal proximity | Smithsonian Global Volcanism Program | static | Raw / qualifier |
| Burn severity (dNBR), desiccation (NDMI) | Sentinel-2/Landsat composite | post-fire, weeks | **Gated — Evidence Acquisition only** |
| Concession attribution | GFW/KLHK ArcGIS REST spatial query (attribute only, no stored geometry) | on demand | **Gated — Phase 2** |

**Timeline UI implication:** the map's time-scrubber naturally reveals which layers have data at any given lookback — same-day typically shows FIRMS only; scrubbing back a few days usually surfaces SAR; scrubbing back about a week usually surfaces a cloud-free Sentinel-2 tile. This is a real function of each sensor's revisit cadence and cloud dependency, not a UI simplification.

---

# 6. Layer B — Derived Metrics (expanded)

Unchanged from v1: FWI, KBDI, VPD, drought duration, vegetation change score, historical anomaly percentile, distance to roads/neighbouring fires.

**New in v2:**

### 6.1 FireComplex linking (see Section 7)
### 6.2 Richards elliptical fire-growth model (see Section 8)

---

# 7. FireComplex Linking

**Problem it solves:** a surface fire ignites (FIRMS logs it), enters peat, smolders underground for days to weeks — untracked by FIRMS — then resurfaces as flame at a new location, producing a second, apparently unrelated FIRMS detection. This "resurfacing" pattern is documented in peat-fire literature (smouldering-to-flaming transition after underground survival, sometimes called "zombie fires"). Left alone, an LLM agent evaluating the second detection in isolation has no way to recognize it as a continuation of the first.

**Design principle: this is a deterministic Layer B linking step, not an LLM-memory feature.** LLM "recall" across sessions is non-reproducible and violates the provenance requirement (every claim needs a traceable evidence ID). FireComplex instead computes a structured link before any agent sees the event.

**Logic (runs on every new qualified FIRMS event):**

```text
FOR the new event, check within a search radius AND within the same KHG peat hydrological unit:
  - is there a persistent VH-backscatter-drop or subsidence trend in the SAR evidence
    store since the last FIRMS detection in that area, with no intervening
    re-vegetation signal?
  IF yes:
    -> attach new event to existing FireComplex ID (not a new independent event)
    -> compute: days_since_last_surface_detection, same_KHG_dome (bool),
       underground_persistence_indicator
  IF no:
    -> create new FireComplex ID
```

The resulting `FireComplex` object — prior detections, SAR persistence trend, KHG classification, elapsed time — is passed to the Investigator/Skeptic agents as structured evidence, same as any other evidence object. The agents reason over the assembled evidence pack; they do not "remember" prior conversations.

**Required framing for the report generator:** underground travel is inferred from indirect signals (subsidence + timing + no revegetation), not directly observed. Surface accordingly as a hypothesis with a support score, with "resurfaced fire complex" vs. "independent new ignition nearby" as competing hypotheses for the Investigator/Skeptic to test — never as a confirmed tracked path.

**Known limitation to log:** Sentinel-1's ~6-day revisit lets you credibly claim a burn signature persisted across a KHG dome between two dates; it cannot resolve precise underground travel speed or path at that cadence. Keep report language to "resurfaced within the same peat hydrological unit," not "tracked underground movement."

---

# 8. Fire Growth Modeling — Richards Elliptical Model + Single Kalman Filter

**Why not full physics-based assimilation (FARSITE + ensemble Kalman filter):** that class of method assimilates against a continuous fire *perimeter* (from airborne infrared), requires a Rothermel rate-of-spread physics model with fuel/terrain/wind inputs, and runs 10–20+ parallel simulations per update. None of that is feasible on Cloudflare Workers (hard CPU-time caps per invocation, no long-running stateful compute, no native compiled-simulator support) or realistic to build in the time available. That tier of method is cited in the deck as prior art, not something claimed as shipped.

**What's actually built:** the Richards (1990) elliptical fire-growth model — a closed-form geometric approximation where the fire front is modeled as a growing, rotating ellipse parameterized by head/back/flank rate-of-spread, driven by wind direction and speed. Paired with a single (non-ensemble) Kalman filter:

- **State:** centroid, ellipse major/minor axes, orientation, rate-of-spread
- **Measurements:** gated hotspot clusters from the qualifier layer
- **Inputs:** wind speed/direction (already pulled for FWI/KBDI, no new data source), a default rate-of-spread per ESA WorldCover land-cover class (grass/scrub/plantation) — not a calibrated Rothermel fuel model

Computational cost: a handful of matrix operations per update — genuinely Workers-feasible, unlike the ensemble approach.

**What this model is for, and what it is not for**
- It is wind-driven and models **above-ground, flaming-phase spread only.** Valid for the initial surface ignition and for a resurfacing flare-up.
- It does **not** model underground peat smoldering, which propagates on oxygen/moisture/peat-density, not wind — that phase stays owned by the SAR persistence evidence (Section 7), never by the ellipse.

**New use in v2 — geometric plausibility check for FireComplex resurfacing:** given the first event's estimated rate-of-spread, wind data, and elapsed time, does the ellipse's projected reach extend toward the KHG peat dome and, further out in time, toward the second detection's location? If the model's projected extent plausibly reaches the peat boundary around the time FIRMS lost track, that's a concrete, citable piece of geometric evidence for "this event drove into peatland and lost FIRMS visibility while still burning" — a stronger basis for the resurfacing hypothesis than spatial proximity and timing alone. Feed this as another evidence ID into the Investigator/Skeptic evidence pack.

**Required framing:** label explicitly in UI and report as a first-order/naive estimate ("estimated surface extent, not a validated fire-behavior forecast"), not a calibrated operational fire model. Useful for triage, search-radius sizing, and hypothesis support — not for forensic precision claims.

---

# 9. Phase 2 (post-MVP roadmap, not this week)

### 9.1 Concession legal attribution
Query GFW/KLHK ArcGIS REST spatial endpoint with a hotspot's lat/lon (`spatialRel=esriSpatialRelIntersects`) to resolve which concession, if any, contains the point. Store only the returned attributes (concession name/ID, holder, type) in the `EvidenceObject` — never the polygon geometry, which keeps this compliant with the boundary-publication restriction noted in Section 2. This is a Context Agent input (per original spec Section 45): concession overlap is logged as a fact, never used to imply responsibility, and never changes hypothesis scores per the agent's system prompt constraints.

### 9.2 Peat legal/illegal boundary classification
The KHG classification already pulled into the raw qualifier layer (Section 5) carries a legal dimension worth surfacing explicitly in Phase 2: KHG units are classified by KLHK as either a **protected peat dome** or a **production zone** (Ministerial Decree No. 129/2017, No. 130/2017). Burning — or maintaining groundwater below the 0.4m threshold under PP No. 71/2014 jo. PP No. 57/2016 — carries different regulatory weight depending on which zone a fire complex falls in. Phase 1 already surfaces the KHG overlay itself (useful on its own for the map); Phase 2 adds the legal classification and threshold-reference layer on top, applied to the SMAP/ERA5 soil-moisture proxy per the caveat in Section 5 — framed as "proxy-based hydrological stress indicator referencing the regulatory threshold," not as confirmed borehole readings (no public API exists yet for Indonesia's actual BRGM/BRIN groundwater network — BRIN's own GWL early-warning system was still described as in development as of early September 2026).

---

# 10. Stage-1 Adversarial Agents (unchanged core, expanded evidence inputs)

Investigator and Skeptic agents, fixed rounds (max 3), structured JSON output — unchanged from original spec Sections 9–11. **New in v2:** both agents now receive FireComplex evidence (Section 7) and Richards-ellipse geometric evidence (Section 8) as additional evidence IDs in their input pack, alongside FWI/KBDI/VPD, land-cover, and concession context (Phase 2). System prompt constraints (not a legal decision maker, evidence-ID-only reasoning, concession/prior-history cannot establish causation, missing evidence must be acknowledged) carry over unchanged from original spec Sections 42–45.

---

# 11. Data Source / API Appendix

| Purpose | Source | Auth | Notes |
|---|---|---|---|
| Fire hotspots | NASA FIRMS | Free MAP_KEY (email signup) | 5,000 req/10min limit |
| SAR + optical | Copernicus Data Space Ecosystem | Free account, access token | Covers Sentinel-1 and Sentinel-2 under one login |
| Sentinel-2 quicklook + cloud-cover query | Sentinel Hub Catalog/OGC API (same Copernicus account) | Same token | Used for raw qualifier tile, not dNBR |
| Weather | Open-Meteo, NASA POWER | None | No signup needed |
| Soil moisture proxy | NASA SMAP (Earthdata) or ERA5-Land (Copernicus CDS) | Free account | Proxy for GWL, not ground-truth |
| Peat hydrology (KHG), peat ecology function, burned area | KLHK Geoportal ArcGIS REST | None (public REST) | `geoportal.menlhk.go.id`, `dbgis.menlhk.go.id` |
| Land cover | ESA WorldCover | None | Static tiles |
| Roads/settlements | OpenStreetMap Overpass | None | |
| Volcano/geothermal | Smithsonian GVP | None | Static dataset |
| Concession attribution (Phase 2) | GFW Data API / ArcGIS Open Data (Indonesia oil palm concessions, MoF-sourced) | Free account + token | Attribute-only query, never store geometry |
| ~~RSPO Hotspot Hub~~ | — | — | **Explicitly not used** — consent-gated, ~35% coverage, no public API |
| ~~BRGM/BRIN groundwater network~~ | — | — | **Not currently public** — system still in development as of Sept 2026 |

---

# 12. Demo Narrative Adjustment

Add to the original 90-second walkthrough (Section 48 of v1): after showing the Investigator/Skeptic disagreement, add a beat showing a FireComplex resurfacing case — "FIRMS lost this event on day 3; SAR shows the burn signature persisting underground through day 9; a new FIRMS detection 2km away on day 10 sits inside the same peat dome and inside the ellipse's projected reach — the system flags this as a probable resurfacing, not two separate fires, for the auditor to confirm." This is the single clearest demonstration of why multi-sensor fusion beats FIRMS-only monitoring, and it's grounded in fire behavior that's actively in the news this week.
