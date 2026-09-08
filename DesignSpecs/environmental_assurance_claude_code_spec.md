# Environmental Assurance Investigative Efficiency Tool
## Claude Code Build Specification

**Project type:** Hackathon MVP  
**Primary challenge:** ACCA Challenge Statement #1  
**Core positioning:** AI-driven investigative-efficiency tool for environmental assurance  
**Primary geography for MVP:** Indonesia  
**Primary workflow:** Thermal anomaly detection → cheap triage → evidence reconstruction → adversarial hypothesis assessment → human audit decision  
**Critical product boundary:** The system does **not** determine blame, guilt, legal responsibility, intent, or culpability.

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


# 1. Product Thesis

Existing satellite systems already detect thermal anomalies and possible fires.

The operational bottleneck is not detection.

The bottleneck is deciding:

> Which detected events deserve scarce human investigative effort?

The product sits between broad remote-sensing detection and expensive human verification.

Its job is to:

1. ingest imperfect fire / thermal-anomaly detections;
2. cheaply eliminate obvious dead ends;
3. reconstruct the environmental state around qualified events;
4. organise heterogeneous evidence into an auditable evidence package;
5. use adversarial AI agents to test competing hypotheses;
6. expose uncertainty and disagreement;
7. generate a structured investigation pack;
8. leave the final decision to a human auditor.

The system should be explainable even if all LLM output is removed.

The deterministic and environmental evidence layers must retain standalone value.

---

# 2. One-Sentence Product Pitch

> Satellites already find the fires. The bottleneck is deciding which ones are worth investigating. We automate the environmental desk investigation so scarce auditors spend their time where human verification matters.

---

# 3. Primary User

## MVP user

Environmental auditor / investigator reviewing possible fire events in Indonesia.

## Secondary future users

- RSPO-accredited certification bodies
- sustainability assurance firms
- Big Four ESG / sustainability assurance teams
- regulators
- insurers
- lenders
- commodity buyers
- ESG due-diligence teams
- environmental NGOs

---

# 4. Non-Goals

Do **not** build the MVP as:

- a fire attribution engine;
- an arson detector;
- a company guilt score;
- a legal conclusion engine;
- a public company-ranking system;
- an automated enforcement system;
- a generic chatbot;
- a replacement for human auditors;
- a replacement for NASA FIRMS;
- a replacement for remote-sensing platforms.

The product supports investigation prioritisation only.

---

# 5. Core Design Principle

The system must separate four layers:

## Layer A — Observed evidence

Directly retrieved facts from datasets.

Examples:

- FIRMS latitude / longitude
- timestamp
- FRP
- confidence
- rainfall
- humidity
- land-cover class
- nearby thermal events
- optical / SAR imagery metadata

## Layer B — Derived metrics

Deterministic or scientifically established calculations.

Examples:

- KBDI
- FWI
- VPD
- drought duration
- vegetation change score
- historical anomaly percentile
- distance to neighbouring fires
- distance to roads
- distance to concession boundary
- fire-cluster density

## Layer C — AI interpretation

LLM agents reason over structured evidence.

Examples:

- evidence supporting H1
- counter-evidence against H3
- unresolved contradictions
- evidence sufficiency
- recommended investigation priority

## Layer D — Human decision

A human auditor decides:

- ignore / deprioritise;
- request more evidence;
- escalate;
- perform field verification;
- open formal investigation.

Never collapse these layers.

---

# 6. High-Level Architecture

```text
NASA FIRMS
    |
    v
Candidate Thermal Anomaly
    |
    v
Cheap Triage Layer
    |
    |-- FIRMS metadata
    |-- location context
    |-- land-cover lookup
    |-- weather context
    |-- persistent heat-source heuristics
    |-- volcano / urban / industrial context
    |-- repeat-detection clustering
    |
    v
Fire Candidate Decision
    |
    |-- REJECT
    |-- ACCEPT
    |-- AMBIGUOUS
            |
            v
     Stage-1 Agent Review
            |
            v
Qualified Fire Event
    |
    v
Evidence Acquisition Layer
    |
    |-- weather history
    |-- rainfall history
    |-- soil moisture
    |-- FWI
    |-- KBDI
    |-- VPD
    |-- Sentinel-2
    |-- Sentinel-1
    |-- Landsat
    |-- historical FIRMS
    |-- land-cover change
    |-- vegetation change
    |-- peat / terrain
    |-- roads / infrastructure
    |-- concession context
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
           fixed rounds
                 |
                 v
        Hypothesis Support Matrix
                 |
                 +----------------------+
                 |                      |
                 v                      v
          Context / OSINT Agent    Limitations Engine
                 |                      |
                 +-----------+----------+
                             |
                             v
                    Report Generator
                             |
                             v
                  PDF Investigation Pack
                             |
                             v
                       Human Auditor
```

---

# 7. Stage 0 — Data Ingestion

## Primary source

NASA FIRMS.

The system should ingest thermal anomaly / active-fire records.

Minimum fields:

```json
{
  "event_id": "generated-id",
  "latitude": -0.523,
  "longitude": 101.911,
  "acq_date": "2026-09-03",
  "acq_time": "1418",
  "satellite": "N",
  "instrument": "VIIRS",
  "confidence": "nominal",
  "frp": 18.4,
  "daynight": "D"
}
```

Preserve raw source fields.

Do not immediately label the event as "fire".

Internally call it:

`CandidateThermalEvent`

---

# 8. Stage 1 — Cheap Triage

## Objective

Avoid wasting expensive API calls, image acquisition, and auditor attention on obvious dead ends.

## Cheap evidence sources

Prefer:

- FIRMS metadata
- location
- land cover
- weather
- historical repeat detections
- urban / industrial masks
- volcano / geothermal proximity
- neighbouring FIRMS detections
- basic elevation
- cheap administrative / geographic lookup

## Cheap features

Suggested features:

```text
firms_confidence
frp
repeat_detections_24h
repeat_detections_7d
repeat_detections_90d
vegetated_land_boolean
urban_land_boolean
industrial_land_boolean
volcano_distance_km
road_distance_km
settlement_distance_km
recent_rainfall_mm
temperature_c
relative_humidity
wind_speed
persistent_heat_source_score
neighbouring_hotspot_count
```

## Output states

Exactly three:

```text
LIKELY_FIRE
LIKELY_NON_FIRE
AMBIGUOUS
```

## Triage logic

Use deterministic rules before LLMs.

Examples:

```text
IF land_cover = dense_urban
AND repeat_detections > threshold
AND vegetation_nearby = false
THEN likely_non_fire
```

```text
IF vegetation = true
AND multiple temporally related FIRMS detections nearby
AND no known persistent heat source
THEN likely_fire
```

Do not use LLMs for obvious cases.

Use Stage-1 agents only for ambiguous cases.

---

# 9. Stage-1 Adversarial Agents

## Investigator Agent

Goal:

> Argue that the candidate thermal anomaly is sufficiently consistent with a genuine vegetation / land fire to justify deeper analysis.

## Skeptic Agent

Goal:

> Search for benign, persistent, industrial, volcanic, reflective, or otherwise non-fire explanations.

## Important constraint

Do not allow unconstrained debate until agreement.

Use fixed rounds.

Recommended:

- Round 1: independent assessment
- Round 2: rebuttal after seeing opponent summary
- Round 3: final assessment

No more than 3 rounds in MVP.

## Structured output

Each agent returns:

```json
{
  "decision": "LIKELY_FIRE | LIKELY_NON_FIRE | AMBIGUOUS",
  "support_score": 0,
  "evidence_ids": ["E1", "E4"],
  "counter_evidence_ids": ["E9"],
  "summary": "Short structured explanation",
  "uncertainties": [
    "Land-cover source resolution is coarse"
  ]
}
```

`support_score` is not a probability.

It is an internal evidence-support score.

## Reconciliation

Use deterministic reconciliation rules.

Example:

```text
both likely_fire      -> LIKELY_FIRE
both likely_non_fire  -> LIKELY_NON_FIRE
high disagreement     -> AMBIGUOUS
weak evidence         -> AMBIGUOUS
```

Do not force consensus.

---

# 10. Stage 2 — Evidence Acquisition

Only run this for:

`LIKELY_FIRE`

and optionally selected `AMBIGUOUS` cases.

## Required baseline evidence pool

Every qualified event should receive the same minimum baseline evidence set where technically available.

This is important for impartiality.

### Weather history

Suggested windows:

- T-24h
- T-72h
- T-7d
- T-30d
- T-90d where practical

Variables:

- precipitation
- temperature
- relative humidity
- wind speed
- wind direction
- soil moisture
- evapotranspiration if available
- VPD if derivable

### Fire-weather indices

Prefer:

- Canadian Fire Weather Index
- Keetch-Byram Drought Index
- VPD

If full implementation is too costly, compute a limited subset and clearly mark unavailable metrics.

### Historical FIRMS

Calculate:

- detections in 1 km / 5 km / 10 km
- past 7d
- past 30d
- past 1y
- historical recurrence if archive data available

### Optical remote sensing

Prefer:

- Sentinel-2
- Landsat

Use for:

- visible vegetation changes
- burn scars
- land clearing
- NDVI or vegetation-index changes
- before/after comparison

### SAR

Prefer:

- Sentinel-1

Purpose:

- obtain cloud-independent radar observations;
- support evidence of surface / vegetation structural change when optical imagery is unavailable.

Do not claim SAR independently proves clearing.

### Geography / context

Potential:

- peat map
- elevation
- slope
- roads
- rivers
- settlements
- concessions
- plantations
- protected areas
- administrative boundaries

---

# 11. Evidence Object

Every observation or derived metric should be represented as a structured `EvidenceObject`.

## Schema

```json
{
  "evidence_id": "ENV_017",
  "category": "weather",
  "type": "rainfall",
  "observation": "42.8 mm rainfall in prior 72 hours",
  "value": 42.8,
  "unit": "mm",
  "source": "Open-Meteo / ERA5",
  "source_url": null,
  "latitude": -0.523,
  "longitude": 101.911,
  "time_start": "2026-08-21T00:00:00Z",
  "time_end": "2026-08-24T00:00:00Z",
  "quality": "MEDIUM",
  "quality_score": 0.82,
  "supports_hypotheses": ["H4"],
  "contradicts_hypotheses": ["H1"],
  "limitations": [
    "Gridded model estimate rather than local weather station"
  ],
  "retrieved_at": "2026-09-06T12:00:00Z"
}
```

## Rule

Agents may only make factual assertions if backed by evidence IDs.

No uncited evidence assertions.

---

# 12. Phase-2 Hypothesis Space

Use the following seven causal / mechanistic hypotheses.

## H1 — Environmental / regional fire-weather conditions

Question:

> Were regional and local environmental conditions strongly conducive to fire ignition and spread?

## H2 — Small-scale agricultural land-management burning

Question:

> Is the event consistent with small-scale agricultural burning or land-clearing practices?

## H3 — Plantation / large-scale land-management activity

Question:

> Is the event consistent with recent large-scale land-management or plantation-related activity?

Important:

This does **not** imply company responsibility.

## H4 — Propagation from neighbouring area

Question:

> Could the fire plausibly have spread from a nearby existing fire?

## H5 — Infrastructure-associated ignition

Examples:

- roads
- industrial infrastructure
- power infrastructure
- other human-made ignition-adjacent context

## H6 — Documented / authorised burning

Only evaluate if authoritative records exist.

Otherwise mark:

`NOT_ASSESSABLE`

## H7 — Other / unknown mechanism

Used when evidence supports a mechanism outside H1-H6.

---

# 13. Evidence Sufficiency

Do not make "insufficient evidence" a causal hypothesis.

Instead maintain a separate field:

```text
HIGH
MEDIUM
LOW
INSUFFICIENT
```

for each hypothesis and for the event overall.

---

# 14. Phase-2 Investigator Agent

## Role

The Investigator Agent asks:

> What evidence justifies further human investigation?

It should look for:

- recent land-cover change
- anomalous fire-weather mismatch
- unusual timing
- unexplained vegetation change
- boundary adjacency
- historical non-recurrence
- neighbouring propagation patterns
- infrastructure context
- temporal sequences

## Restrictions

It must not:

- accuse a company;
- infer intent;
- infer illegality;
- use prior prosecutions as causal evidence;
- convert concession overlap into responsibility.

---

# 15. Phase-2 Skeptic Agent

## Role

The Skeptic Agent asks:

> What benign, environmental, data-quality, or alternative explanation could account for the same observations?

It should actively search for:

- drought
- low soil moisture
- recurring regional fire patterns
- neighbouring fire propagation
- cloud / sensor limitations
- stale concession data
- coarse weather products
- alternative land-use explanations
- inconsistent timing
- weak image evidence

The Skeptic is not there to "defend companies".

It is there to resist confirmation bias.

---

# 16. Phase-2 Agent Rounds

Recommended:

## Round 1 — Independent assessment

Both agents independently score all hypotheses.

## Round 2 — Adversarial rebuttal

Each agent receives:

- the opponent's hypothesis summary;
- evidence IDs cited;
- points of disagreement.

Each writes a rebuttal.

## Round 3 — Final structured assessment

Each agent outputs:

```json
{
  "hypotheses": {
    "H1": {
      "support_score": 76,
      "evidence_sufficiency": "HIGH",
      "supporting_evidence": ["ENV_001", "ENV_004"],
      "contradicting_evidence": ["ENV_019"],
      "reasoning_summary": "..."
    }
  },
  "unresolved_disagreements": [
    "Whether recent SAR change is attributable to vegetation loss"
  ]
}
```

No free-running debate.

---

# 17. Support Score

Never label LLM-generated numbers as probability.

Use:

`Evidence Support Score`

Range:

`0-100`

Meaning:

- 0-20: very weak support
- 21-40: weak support
- 41-60: mixed / moderate
- 61-80: strong
- 81-100: very strong

These are structured reasoning scores.

They are not calibrated causal probabilities.

---

# 18. Hypothesis Matrix

The report must show both agents side by side.

Example:

| Hypothesis | Investigator | Skeptic | Sufficiency | Disagreement |
|---|---:|---:|---|---|
| H1 Environmental conditions | 82 | 77 | High | Low |
| H2 Small-scale agricultural | 54 | 31 | Medium | Medium |
| H3 Plantation activity | 74 | 42 | Medium | High |
| H4 Neighbour propagation | 28 | 63 | High | High |
| H5 Infrastructure | 12 | 18 | Low | Low |
| H6 Authorised burning | N/A | N/A | Insufficient | N/A |
| H7 Other | 16 | 29 | Low | Low |

This matrix should be one of the most visible outputs.

---

# 19. Context / OSINT Agent

## Purpose

A third agent may retrieve external context.

This agent is separate from physical-causation reasoning.

## Allowed sources

Prefer authoritative sources:

- government ministries
- environmental agencies
- courts
- RSPO
- certification-body notices
- company statements
- regulators
- reputable news only where primary sources are unavailable

## Search targets

- recent prosecutions
- active investigations
- regulatory notices
- RSPO complaints
- certification suspensions
- court findings
- company responses
- documented controlled burns
- enforcement action

## Critical firewall

OSINT context must **not** alter:

- weather-derived scores;
- physical environmental metrics;
- land-change observations;
- base hypothesis support scores.

Keep it in a separate report section:

`External Regulatory / Enforcement Context`

Example:

```text
Environmental hypothesis assessment:
H3 = moderate support

External context:
A regulator announced an investigation involving the mapped concession operator on 31 Aug 2026.

These are separate observations.
```

---

# 20. Defamation / Wrongful Attribution Safety Rules

These are mandatory product rules.

## Never generate:

- "Company X caused the fire"
- "Company X illegally burned land"
- "Company X is guilty"
- "Company X committed arson"
- "Company X is responsible"
- "fraudulent ESG company"
- "greenwasher"
- "culprit"

unless an authoritative source has already made that finding and it is clearly cited as an external finding.

## Allowed formulations

- "mapped concession intersects event area"
- "event is located within / adjacent to a mapped concession"
- "recent vegetation change was observed"
- "environmental explanation is weak / moderate / strong"
- "event warrants human investigation"
- "evidence is insufficient"
- "external authority has opened an investigation"
- "source X reported / found Y"

## Entity handling

Score events, not companies.

Primary key should be:

`event_id`

not:

`company_id`

---

# 21. Investigation Priority

Final output should be:

```text
LOW
MEDIUM
HIGH
URGENT
```

or a 0-100 `Investigation Priority Score`.

This score should combine:

- event validity
- evidence anomaly
- evidence richness
- unresolved disagreement
- environmental mismatch
- recent land-change indicators
- possible propagation explanation
- evidence quality

Do not make prior company misconduct a direct scoring factor.

---

# 22. Report Structure

Name:

**Environmental Fire Investigation Pack**

Suggested sections:

1. Case metadata
2. Executive summary
3. Candidate thermal event
4. Stage-1 triage result
5. Event map
6. Fire-weather timeline
7. Historical weather comparison
8. KBDI / FWI / VPD
9. Historical FIRMS activity
10. Optical imagery
11. SAR observations
12. Land-cover change
13. Spatial context
14. Hypothesis matrix
15. Investigator findings
16. Skeptic counter-findings
17. Unresolved disagreements
18. Evidence limitations
19. External regulatory context
20. Data provenance
21. Human auditor notes
22. Disclaimer

Mandatory disclaimer:

> This report is an investigative-support product. It does not establish legal responsibility, intent, culpability, ownership liability, or criminal wrongdoing. Findings require human verification.

---

# 23. UI / Demo

## Core UX

Build a dark, operational, "Palantir-style" geospatial interface.

Priority is visual storytelling.

## Main view

Indonesia map.

Overlay:

- FIRMS thermal anomalies
- event clusters
- administrative boundaries
- optional concession boundaries
- optional peat / land-cover layer

## Hotspot visualisation

Clicking a marker opens a side panel.

Example:

```text
Event IND-02671

Sensor: VIIRS
Detected: 03 Sep 2026 14:18
FRP: 18.4 MW
Confidence: nominal

Cheap triage
Vegetated land: YES
Urban heat source: NO
Persistent anomaly: NO
Nearby detections: 4
Recent rainfall: 11.8 mm

Status:
LIKELY FIRE
```

## Timeline replay

Add a 7-day replay slider.

As time changes:

- FIRMS points appear / disappear
- rainfall changes
- temperature changes
- optionally wind direction / vectors change
- cluster propagation becomes visible

## Generate Report button

Button:

`Generate Investigation Pack`

On click:

1. fetch Stage-2 evidence;
2. compute metrics;
3. run agents;
4. stream structured agent findings;
5. generate final report;
6. show PDF download.

---

# 24. Agent Reasoning UI

Do not show raw chain-of-thought.

Show structured evidence-backed statements.

Example:

```text
INVESTIGATOR
H3 + SUPPORT
Vegetation-loss signal detected approximately 19 days before the event.
Evidence: IMG_004, SAR_002
```

```text
SKEPTIC
H3 - COUNTERPOINT
SAR change may be influenced by moisture variation; optical confirmation is incomplete.
Evidence: SAR_002, LIMIT_003
```

```text
INVESTIGATOR
H4 + SUPPORT
Neighbouring thermal activity occurred 6.1 km east approximately 9 hours earlier.
Evidence: FIRMS_HIST_014
```

```text
SKEPTIC
H4 - COUNTERPOINT
Observed wind direction weakens the east-to-west propagation explanation.
Evidence: WX_033
```

---

# 25. Frontend Suggested Stack

Preferred for hackathon speed:

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- MapLibre GL JS or Leaflet
- Recharts for charts
- React Query / TanStack Query
- Zustand or simple React state

Optional:

- deck.gl for large geospatial overlays

Avoid overengineering.

---

# 26. Backend Suggested Stack

Recommended:

- Python
- FastAPI
- Pydantic
- Pandas / Polars
- GeoPandas
- Rasterio where required
- Shapely
- NumPy
- httpx / requests
- SQLModel or SQLAlchemy
- SQLite for MVP
- Postgres + PostGIS only if time permits

LLM integration:

- provider abstraction
- strict JSON schemas
- deterministic temperature where possible
- structured output validation
- retry invalid JSON once only

---

# 27. Suggested Monorepo

```text
environmental-assurance/
|
|-- apps/
|   |-- web/
|   |   |-- app/
|   |   |-- components/
|   |   |-- lib/
|   |   |-- public/
|   |   `-- types/
|   |
|   `-- api/
|       |-- main.py
|       |-- routes/
|       |-- services/
|       |-- models/
|       |-- agents/
|       |-- data/
|       |-- reports/
|       `-- tests/
|
|-- packages/
|   |-- schemas/
|   `-- fixtures/
|
|-- data/
|   |-- geojson/
|   |-- demo/
|   `-- cache/
|
|-- docs/
|   |-- architecture.md
|   |-- data-sources.md
|   |-- safety.md
|   `-- demo-script.md
|
|-- .env.example
|-- docker-compose.yml
|-- README.md
`-- CLAUDE.md
```

---

# 28. Backend API

Suggested endpoints.

## FIRMS

```text
GET /api/events
GET /api/events/{event_id}
GET /api/events/{event_id}/history
```

## Triage

```text
POST /api/events/{event_id}/triage
GET  /api/events/{event_id}/triage
```

## Evidence

```text
POST /api/events/{event_id}/evidence/collect
GET  /api/events/{event_id}/evidence
```

## Analysis

```text
POST /api/events/{event_id}/analyse
GET  /api/events/{event_id}/analysis
```

## OSINT

```text
POST /api/events/{event_id}/context
GET  /api/events/{event_id}/context
```

## Reports

```text
POST /api/events/{event_id}/report
GET  /api/events/{event_id}/report
```

## SSE / streaming

Optional:

```text
GET /api/events/{event_id}/analysis/stream
```

Use SSE for live agent UI if time permits.

---

# 29. Data Models

## CandidateThermalEvent

```python
class CandidateThermalEvent(BaseModel):
    event_id: str
    latitude: float
    longitude: float
    detected_at: datetime
    satellite: str | None
    instrument: str | None
    confidence: str | float | None
    frp: float | None
    daynight: str | None
    raw_source: dict
```

## TriageResult

```python
class TriageResult(BaseModel):
    event_id: str
    deterministic_status: str
    final_status: str
    fire_candidate_score: float
    evidence_ids: list[str]
    limitations: list[str]
    agent_review_required: bool
```

## HypothesisAssessment

```python
class HypothesisAssessment(BaseModel):
    hypothesis_id: str
    support_score: float
    evidence_sufficiency: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    reasoning_summary: str
```

## AgentAssessment

```python
class AgentAssessment(BaseModel):
    agent_name: str
    round_number: int
    hypotheses: list[HypothesisAssessment]
    unresolved_disagreements: list[str]
```

---

# 30. Data Provider Interfaces

Create provider abstractions.

Example:

```python
class WeatherProvider(Protocol):
    async def get_weather(
        self,
        lat: float,
        lon: float,
        start: datetime,
        end: datetime
    ) -> WeatherSeries:
        ...
```

Suggested interfaces:

```text
FirmsProvider
WeatherProvider
LandCoverProvider
OpticalImageryProvider
SarProvider
HistoricalFireProvider
ConcessionProvider
OsintProvider
```

This allows mocked data during the demo.

---

# 31. MVP Data Strategy

Do not attempt perfect live integration with every source.

Use three classes:

## Live

Use where easy and stable:

- FIRMS
- cheap weather
- base map / GeoJSON

## Preprocessed / cached

Use where acquisition is slow:

- Sentinel imagery
- historical imagery
- land-cover rasters
- demo concessions
- peat data

## Mocked-but-realistic

Only where necessary.

Clearly label in internal docs.

Never misrepresent synthetic values as live data during judging.

---

# 32. One-Week MVP Scope

## Must Have

- Indonesia map
- FIRMS events
- click event
- cheap telemetry
- event history replay
- deterministic triage
- at least one weather provider
- at least one historical environmental metric
- structured evidence store
- Investigator Agent
- Skeptic Agent
- fixed adversarial rounds
- hypothesis matrix
- limitations
- report generator
- PDF export

## Strongly Desired

- Sentinel-2 before / after image
- historical FIRMS analysis
- KBDI or FWI
- third Context / OSINT agent
- live streamed structured agent debate
- land-cover layer

## Nice to Have

- Sentinel-1 SAR
- concession maps
- peat layer
- VPD
- automated vegetation-change metric
- event clustering
- PostGIS
- role-based access

## Do Not Waste Time On

- perfect company ownership mapping
- perfect concession ownership
- full Indonesia historical archive
- computer-vision model training
- calibrated causal classifier
- authentication
- billing
- production deployment architecture
- multi-country rollout
- actual legal attribution

---

# 33. Recommended Development Order

## Day 1

- scaffold repo
- build map
- ingest FIRMS
- plot events
- click event
- side panel
- demo event fixture

## Day 2

- cheap weather
- event history
- deterministic triage
- basic timeline replay

## Day 3

- evidence schema
- historical environmental context
- KBDI or FWI
- charting

## Day 4

- Investigator Agent
- Skeptic Agent
- structured outputs
- 2-3 fixed rounds
- hypothesis matrix

## Day 5

- remote-sensing evidence
- cached Sentinel-2
- land-cover / before-after view
- limitations engine

## Day 6

- OSINT context agent
- PDF report
- streaming UI
- polish

## Day 7

- test
- freeze demo cases
- record fallback data
- pitch integration
- performance
- edge cases

---

# 34. Demo Case Strategy

Do not demo a random fire.

Prepare 2-3 prevalidated cases.

Recommended:

## Case A — obvious false / non-fire candidate

Purpose:

Demonstrate cheap triage saving work.

## Case B — environmentally plausible fire

Purpose:

Show that the system can deprioritise rather than accuse.

## Case C — ambiguous / anomalous event

Purpose:

Show value of adversarial reasoning.

Case C should have:

- recent vegetation change
- non-trivial rainfall history
- competing propagation explanation
- incomplete optical data
- meaningful Investigator/Skeptic disagreement

This will make the demo much stronger than a simplistic guilty/not-guilty case.

---

# 35. Measurable Impact Metrics

MVP should report operational impact.

Primary:

```text
time_to_first_assessment
events_screened_per_analyst_hour
evidence_items_auto_collected
manual_data_sources_replaced
percentage_events_rejected_at_triage
percentage_events_marked_insufficient
report_generation_time
```

Demo metric idea:

Compare:

```text
Manual workflow:
open FIRMS
open weather
inspect imagery
search history
calculate context
write summary

vs

System:
select event
generate pack
review
```

Do not invent real-world time savings.

If measured on team members, label as:

`Hackathon workflow benchmark`

---

# 36. Product / Commercial Positioning

Initial wedge:

**Environmental fire-investigation efficiency**

Buyer value:

> Reduce analyst desk-research time and increase the number of events that can be screened with the same specialist workforce.

Future expansion:

- deforestation investigations
- peat degradation
- land-clearing compliance
- supply-chain ESG due diligence
- protected-area encroachment
- mining / land-use change
- environmental incident assurance

Business model possibilities:

- B2B SaaS
- per-seat analyst product
- per-region subscription
- per-investigation pricing
- API / evidence-pack generation
- enterprise data integration
- assurance-firm licensing

---

# 37. Commercial Boundary

Do not claim:

> KPMG/EY/PwC/Deloitte findings automatically trigger RSPO enforcement.

Instead claim:

> Multiple assurance organisations perform overlapping environmental evidence work. The same evidence engine can support different assurance workflows.

---

# 38. Error Handling

Every provider must return:

```json
{
  "status": "SUCCESS | PARTIAL | FAILED",
  "data": {},
  "limitations": [],
  "error": null
}
```

The pipeline must tolerate missing sources.

Example:

Sentinel-2 fails due to cloud cover.

Do not fail report generation.

Instead add:

```text
LIMITATION:
Optical imagery unavailable due to cloud cover.
SAR evidence used where available.
```

---

# 39. Provenance

Every evidence item must track:

- source
- timestamp
- spatial resolution if known
- temporal range
- retrieval timestamp
- transformation
- quality
- limitations

Report claims should refer back to evidence IDs.

---

# 40. Reproducibility

Store:

- event data
- provider responses
- derived metrics
- agent prompts
- model name
- agent outputs
- timestamp
- report version

This allows rerunning a case.

---

# 41. Logging

Use structured logs.

Example:

```json
{
  "event_id": "IND-02671",
  "stage": "evidence_collection",
  "provider": "weather",
  "status": "success",
  "duration_ms": 814
}
```

---

# 42. LLM Prompting Rules

System prompt should explicitly state:

1. You are not a legal decision maker.
2. You must reason only over supplied evidence.
3. Every factual statement requires evidence IDs.
4. Prior enforcement history cannot establish current causation.
5. Concession overlap cannot establish responsibility.
6. Missing evidence must be acknowledged.
7. You may recommend investigation, not guilt.
8. You may return insufficient evidence.

---

# 43. Example Investigator System Prompt

```text
You are the Investigator Agent in an environmental assurance workflow.

Your job is to identify evidence that may justify deeper human investigation of a qualified fire event.

You are NOT determining legal responsibility, intent, culpability, or company guilt.

Use only the supplied structured evidence.

Every factual assertion must reference evidence IDs.

Evaluate H1-H7.

For each hypothesis:
- assign an evidence support score from 0-100;
- assign evidence sufficiency;
- list supporting evidence;
- list contradicting evidence;
- provide a concise reasoning summary.

Concession overlap does not establish responsibility.

Prior company misconduct does not establish causation.

If evidence is weak, say so.
```

---

# 44. Example Skeptic System Prompt

```text
You are the Skeptic Agent in an environmental assurance workflow.

Your job is to challenge premature escalation and search for environmental, benign, propagation-based, measurement-related, or data-quality explanations.

You are NOT defending a company.

You are testing whether the evidence supports the proposed interpretation.

Use only supplied structured evidence.

Every factual assertion must cite evidence IDs.

Actively identify:
- alternative explanations;
- sensor uncertainty;
- missing data;
- historical environmental plausibility;
- propagation possibilities;
- stale or coarse datasets.

Evaluate H1-H7 independently.

Do not force agreement with the Investigator.
```

---

# 45. Example Context Agent Prompt

```text
You are the Context Agent.

Search authoritative public sources for external regulatory, enforcement, certification, and legal context related to the event location, concession, or associated entity.

Prefer:
- government agencies;
- regulators;
- courts;
- RSPO;
- certification notices;
- company statements.

Clearly separate:
- confirmed findings;
- open investigations;
- allegations;
- company responses.

Do not change environmental hypothesis scores.

Do not infer present causation from historical enforcement actions.
```

---

# 46. Demo Visual Language

Use terms:

- Candidate Thermal Event
- Qualified Fire Event
- Environmental Context
- Evidence Pack
- Investigation Priority
- Evidence Support
- Evidence Sufficiency
- Competing Hypotheses
- Unresolved Disagreement
- Human Review Required

Avoid:

- Guilty
- Culprit
- Illegal burn
- Arson likelihood
- Company guilt
- Blame score

---

# 47. UI Status Labels

Suggested:

```text
TRIAGE
LIKELY FIRE
LIKELY NON-FIRE
AMBIGUOUS

ANALYSIS
EVIDENCE COLLECTION
MODELLING
AGENT REVIEW
COMPLETE

PRIORITY
LOW
MEDIUM
HIGH
URGENT

SUFFICIENCY
HIGH
MEDIUM
LOW
INSUFFICIENT
```

---

# 48. Demo Narrative

Recommended 90-second product walkthrough.

## Opening

> Satellites already detect thousands of possible fires. The problem is deciding which ones deserve expensive human investigation.

## Map

Show Indonesia with FIRMS events.

## Select candidate

Show cheap telemetry.

## Stage 1

> We first eliminate obvious dead ends using cheap deterministic evidence.

## Timeline

Replay seven days.

## Generate pack

> Only qualified events trigger expensive evidence acquisition.

## Environmental reconstruction

Show:

- rainfall
- FWI / KBDI
- historical events
- before / after imagery

## Agents

> The Investigator argues for escalation. The Skeptic actively searches for alternative explanations.

Show structured disagreement.

## Final report

> The system does not assign blame. It packages evidence so the human auditor can decide whether this event deserves field investigation.

---

# 49. Acceptance Criteria

The MVP is successful if:

1. User opens Indonesia map.
2. FIRMS events are visible.
3. User selects an event.
4. Cheap triage data appears.
5. User sees prior 7-day context.
6. User starts analysis.
7. Evidence objects are generated.
8. At least one deterministic fire-weather metric is shown.
9. Investigator and Skeptic produce structured assessments.
10. Hypothesis matrix is rendered.
11. Evidence gaps are visible.
12. Context agent data is clearly separate.
13. Report is generated.
14. PDF is downloadable.
15. No output assigns guilt or legal responsibility.
16. Every AI factual claim can trace to evidence IDs.

---

# 50. First Claude Code Tasks

Start by implementing these in order.

## Task 1

Create monorepo scaffold:

- Next.js frontend
- FastAPI backend
- shared schema documentation
- `.env.example`

## Task 2

Implement `CandidateThermalEvent`.

Create a demo fixture with 20-100 FIRMS-style records if live API setup is not yet available.

## Task 3

Render Indonesia GeoJSON using MapLibre / Leaflet.

Plot events.

Add clickable markers and event side panel.

## Task 4

Implement:

`GET /api/events`

`GET /api/events/{event_id}`

## Task 5

Implement a weather provider abstraction and one working provider.

## Task 6

Implement deterministic cheap triage.

## Task 7

Implement `EvidenceObject` and structured evidence store.

## Task 8

Implement agent schemas before agent prompts.

Validate every LLM output against Pydantic.

## Task 9

Implement Investigator and Skeptic agents with fixed rounds.

## Task 10

Render hypothesis matrix.

## Task 11

Implement report generation.

## Task 12

Polish timeline replay and live analysis UI.

---

# 51. Instructions to Claude Code

When implementing:

- prioritise a complete demo flow over production completeness;
- write small modular services;
- prefer provider abstractions;
- preserve provenance;
- use strict schemas;
- do not bury business logic in frontend components;
- make every major stage independently testable;
- use cached/demo fixtures for unreliable external APIs;
- fail gracefully;
- never fabricate unavailable evidence;
- never expose hidden LLM chain-of-thought;
- only display structured summaries;
- preserve all uncertainty;
- keep legal / attribution safety language central;
- build for a polished demonstration first.

When a feature is expensive, implement the interface and fixture before the full integration.

The critical demo path must always remain runnable.

---

# 52. Final Architectural Principle

> Deterministic systems establish observations. Established models derive environmental metrics. AI agents challenge competing interpretations. Humans decide whether those interpretations justify investigation.

That principle should guide every technical decision in this repository.
