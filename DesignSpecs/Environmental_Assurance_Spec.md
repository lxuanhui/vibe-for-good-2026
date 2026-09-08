# Environmental Assurance — Canonical Product & Build Specification

**Version:** 3.0 — Audit-Scope-First Architecture  
**Updated:** 2026-09-08  
**Project:** Vibe For Good 2026 hackathon MVP  
**Challenge:** ACCA Challenge Statement #1  
**Primary geography:** Indonesia  
**Stack:** Vite + React; Flask on AWS Lambda behind an API Gateway HTTP API; DynamoDB + S3  

> This file is the single source of truth. It consolidates the original Claude Code build specification, peat-aware v2 architecture, and Assurance Console UI specification. Where older documents conflict, this file wins.

---

# 1. Product thesis

Satellites and government/industry systems already detect and monitor fires. The assurance problem is different: an auditor begins with a defined management unit and review period and must decide what historical environmental evidence deserves scarce desk-review and field-verification effort.

**One sentence:**
> The auditor supplies the management-unit boundary and review period; the system reconstructs years of fire observations into coherent events, lets the auditor screen them temporally and investigate them spatially, then uses adversarial AI to identify unresolved explanations and targeted verification questions.

The product sits between remote-sensing data and human assurance judgment. It does not determine blame, guilt, intent, illegality, ownership liability, or legal responsibility.

# 2. Primary user and job

**Beachhead:** environmental/certification assurance teams assessing high-risk agricultural operations in Indonesia.

**Job:** before/during fieldwork, reconstruct the historical fire/environmental record for the sampled management unit, identify event relationships and evidence gaps, and focus limited human verification on the questions that matter.

Secondary users may include sustainability assurance firms, commodity buyers, lenders/insurers, regulators and NGOs, but the MVP is designed around the auditor workflow.

# 3. Assurance vs enforcement

Do not differentiate by claiming Indonesian authorities lack sophisticated geospatial intelligence. They do not. Differentiate by decision context.

| Enforcement intelligence | Assurance intelligence |
|---|---|
| territory-wide mandate | engagement-defined scope |
| current/recent monitoring | historical review period |
| detect/escalate incidents | reconstruct/screen event history |
| intervention/enforcement priority | verification/audit priority |
| authority can resolve concession context | auditor brings authorised management-unit scope |

Core question: **What happened within and around this audit scope during this review period, which relationships remain unresolved, and what should the auditor verify?**

# 4. Non-goals and safety boundary

Do not build:
- fire attribution/arson detector
- company guilt/responsibility score
- legal conclusion or automated enforcement engine
- public company ranking/accusation system
- public searchable Indonesian concession-polygon directory
- generic chatbot
- replacement for auditors/FIRMS/remote-sensing platforms

Rules:
- score FireEvents, not companies
- geographic association is not responsibility
- first detection inside a boundary does not establish origin
- external-context events may inform interpretation but are not automatically audit subjects
- client identity must not influence physical/environmental scoring
- evidence must cut both ways
- AI factual assertions require evidence IDs
- final decisions remain human

# 5. Canonical workflow

```text
1 CREATE AUDIT REVIEW
  boundary + dates + context buffer
          |
2 BUILD FIRE HISTORY
  source acquisition -> triage -> clustering -> cheap enrichment
          |
3 HISTORICAL FIRE REGISTER (TABLE)
  multi-year temporal screening / filtering / multi-select
          |
4 SPATIAL INVESTIGATION WORKSPACE (MAP)
  selected events + contextual neighbours + graph + layers
          |
5 EVIDENCE DRAWER
  deterministic metrics immediately; imagery progressively
          |
6 GENERATE INVESTIGATION ANALYSIS
  Investigator <-> Skeptic; fixed rounds; evidence IDs only
          |
7 HUMAN REVIEW
  verification questions / notes / disposition
          |
8 AUDIT EVIDENCE PACK
  engagement-level selected evidence + provenance + limitations
```

# 6. Audit Scope

## 6.1 Inputs
Preferred:
- private management-unit polygon uploaded by authorised auditor/client
- GeoJSON first for MVP; KML/KMZ/SHP follow-on

Alternatives:
- draw polygon
- lat/lon + radius quick analysis

Required temporal inputs:
- `review_start`
- `review_end`

Do not hard-code a five-year review. Provide presets if useful, but the engagement determines the period.

## 6.2 Boundary handling
The system does not need company identity to perform environmental reconstruction. Assign anonymised `scope_id`. Treat uploaded geometry as private client input, not public reference data and not proof of ownership.

Always derive a configurable external context buffer (MVP default may be 25 km). Classify FireEvents:
- `INSIDE_SCOPE`
- `BOUNDARY_INTERSECTING`
- `EXTERNAL_CONTEXT`

## 6.3 Geometry persistence
Store uploaded geometry privately, tenant-scoped, encrypted/access-controlled where infrastructure permits, with explicit retention/deletion policy. Never expose it through a public named-concession search.

# 7. Data sources

| Evidence | Source | Role | Persistence default |
|---|---|---|---|
| thermal observations | NASA FIRMS VIIRS/MODIS | historical observations/qualifier | S3 historical; cache recent |
| weather | Open-Meteo / NASA POWER | event context, wind/rain/RH/temp | cache table raw; DynamoDB finalized derived evidence |
| optical | Sentinel-2 / Landsat | pre/post visual/burn/vegetation evidence | metadata DynamoDB; selected derived imagery S3 |
| SAR | Sentinel-1 | cloud-independent change evidence | metadata DynamoDB; selected derived imagery S3 |
| peat | Greifswald/KHG where legally/technically suitable | peat context | versioned S3; derived facts DynamoDB |
| land cover | ESA WorldCover | contextual class only | versioned S3/static |
| roads/settlements | OSM | context | cache table |

WorldCover 2020/2021 must not be presented as contemporaneous 2019 land cover. Historical land change should come from contemporaneous imagery.

# 8. Persistence architecture

**DynamoDB stores what the product learned or humans decided. S3 stores bulky/historical evidence. A TTL-expiring cache table stores disposable/re-fetchable responses.**

The three roles matter more than the products. Revisions of this spec before
2026-09-08 named Cloudflare D1, R2 and KV; the running system is AWS, so the
same three roles map to DynamoDB, S3, and DynamoDB with a TTL attribute. One
store with TTL rather than a separate cache service keeps the number of moving
parts down. See `docs/decision-log.md`.

DynamoDB (durable, queryable — "what we learned or decided"):
- audit scopes metadata
- FireEvent summaries
- membership/index references
- FireEventGraph edges
- EvidenceObject metadata/finalized derived evidence
- analysis runs and agent assessments
- auditor review/disposition/notes
- report metadata
- source runs/checkpoints
- algorithm/model versions

S3 (bulky, immutable — "the evidence itself"):
- historical FIRMS Parquet/GeoParquet partitions
- uploaded private scope geometry
- reference rasters/datasets
- selected Sentinel derived products
- frozen report evidence snapshots
- PDFs/demo fixtures

Cache table, TTL-expiring (disposable — "we can always re-fetch this"):
- weather responses
- STAC searches
- OSM responses
- prepared GeoJSON/viewport responses
- temporary jobs/UI cache

Rule: **store every decision, enough evidence to reproduce that decision, and pointers to everything else.**

# 9. Observation -> FireEvent clustering

Raw FIRMS points are observations, not fires. The first major compression step clusters temporally/spatially related observations into coherent `FireEvent`s.

Required FireEvent fields:
```ts
type FireEvent = {
  id: string;
  scopeId: string;
  firstDetected: string;
  lastDetected: string;
  observationCount: number;
  centroid: [number, number];
  bbox: [number, number, number, number];
  scopeRelation: 'INSIDE_SCOPE'|'BOUNDARY_INTERSECTING'|'EXTERNAL_CONTEXT';
  distanceToBoundaryKm?: number;
  peakFrp?: number;
  peatFraction?: number;
  complexity?: number;
  evidenceSufficiency?: 'SUFFICIENT'|'PARTIAL'|'INSUFFICIENT';
  investigationPriority?: 'LOW'|'MEDIUM'|'HIGH'|'URGENT';
};
```

Demo should show real progressive compression: `raw observations -> qualified observations -> FireEvents -> reviewed events`. Never imply an auditor manually inspected every raw point.

# 10. Cheap deterministic triage

Use deterministic rules before expensive imagery/LLMs. Features may include confidence, FRP, repeat detections, vegetated/urban/industrial masks, volcano proximity, recent weather and persistent heat-source patterns.

States:
- `LIKELY_FIRE`
- `LIKELY_NON_FIRE`
- `AMBIGUOUS`

Ambiguous cases may receive a bounded Stage-1 review. Do not use an LLM for obvious filtering.

# 11. Historical Fire Register (Table)

This is the primary screening workspace. Columns:
- FireEvent ID
- first/last detection and duration
- observation count
- scope relation / distance to boundary
- FRP summary
- peat overlap
- complexity
- evidence sufficiency
- graph relationship summary
- investigation priority
- review state

Filters:
- review dates
- inside/boundary/external
- peat
- persistence
- complexity
- evidence sufficiency
- priority
- review state
- optional land-management context when evidence exists

Support multi-select -> `INVESTIGATE ON MAP`.

# 12. FireEventGraph

Do not ask LLMs to reason over thousands of individual FIRMS points. Build graph nodes as FireEvents and deterministic candidate edges containing:
- distance
- elapsed time
- temporal ordering
- wind alignment
- surface-spread compatibility
- peat relationship/corridor evidence where defensible
- shared environmental episode
- supporting/contradicting evidence IDs
- model version

Candidate graph structures include neighbour propagation, independent events under shared regional conditions, multiple related ignitions, peat-mediated persistence, and insufficient observations.

# 13. Spatial Investigation Workspace (Map)

The Palantir-style map is for spatial reasoning after table screening. Render selected events plus relevant graph neighbours, not the entire regional archive.

Layers:
- audit boundary/context buffer
- FireEvents
- selected raw FIRMS observations
- graph edges
- peat
- wind
- Sentinel-1/2
- land cover
- first-order surface propagation envelope

Timeline controls temporal layers and exposes sensor availability/missing passes.

# 14. Surface fire-growth compatibility

A Richards-style growing/rotating ellipse may be used as a **first-order surface-fire compatibility model**, optionally refined with a simple Kalman state. It is not a forensic or operational fire forecast and does not model underground peat travel.

Use it to ask: are later observations broadly compatible with one straightforward wind-influenced surface-fire episode?

Assumptions/limitations must be visible: homogeneous fuel approximation, simplified terrain/fuel behavior, wind dependence, non-spotting, poor validity for peat/smouldering regimes.

# 15. Peat-aware reasoning

Peat can change persistence and observability. The MVP should represent `SURFACE`, `PEAT/SMOULDERING`, `MIXED`, `UNKNOWN` states rather than pretending a surface ellipse tracks subsurface propagation.

Sentinel-1 can provide cloud-independent change evidence; it must not be described as directly observing an underground fire path. Peat-mediated continuation remains a hypothesis supported by indirect evidence and uncertainty.

# 16. EvidenceObject

All observations/derived metrics passed to agents use a structured object:
```json
{
  "evidence_id":"ENV_017",
  "category":"weather",
  "type":"rainfall",
  "observation":"42.8 mm rainfall during T-72h to T-24h",
  "source":"Open-Meteo/ERA5",
  "time_window":"...",
  "value":42.8,
  "unit":"mm",
  "quality":0.82,
  "limitations":["gridded model estimate"],
  "retrieved_at":"...",
  "algorithm_version":null,
  "raw_reference":"..."
}
```

Observed evidence, derived metrics, AI interpretation and human decisions remain separate layers.

# 17. Evidence Drawer and inspectability

Click event -> render cached deterministic metrics immediately; hydrate imagery asynchronously.

Important metrics are clickable:
- peat overlap -> map intersection
- nearby events -> graph edges
- surface compatibility -> ellipse vs detections
- weather -> time series
- imagery -> source acquisition metadata
- complexity -> component features

Every metric exposes provenance, time window, quality, limitations and algorithm version.

# 18. Investigation hypotheses

Use event-history/mechanistic hypotheses:
- H1 Independent local ignition
- H2 Surface propagation from earlier neighbouring event
- H3 Peat-mediated persistence/propagation
- H4 Multiple related land-management ignitions
- H5 Regional independent events under shared conducive conditions
- H6 Other mechanism

Maintain evidence sufficiency separately: `SUFFICIENT | PARTIAL | INSUFFICIENT`.

Do not infer intent/legal responsibility.

# 19. Adversarial AI

AI is explicit action: `GENERATE INVESTIGATION ANALYSIS`. It runs after evidence assembly, not on every click.

Fixed rounds:
1. independent Investigator/Skeptic assessment
2. rebuttal against opponent summary/evidence IDs
3. final structured assessment

Investigator asks what evidence justifies further verification. Skeptic searches for alternative explanations, sensor limitations and missing evidence. Neither represents a party.

Output:
- hypothesis support (High/Moderate/Low or evidence-support score)
- supporting/contradicting evidence IDs
- unresolved disagreements
- evidence sufficiency
- limitations
- recommended field/document verification questions

No raw private chain-of-thought in UI.

# 20. Investigation Priority and Fire Complexity

Priority is a review-routing score, not culpability. Inputs may include event validity, complexity, evidence richness, unresolved disagreement, peat/persistence, environmental mismatch, graph ambiguity and evidence quality.

Fire Complexity measures how poorly an event can be explained as one straightforward surface-fire episode. Candidate features: duration, observation count, spatial extent, centroid movement, directional consistency, wind alignment, FRP variability, subclusters, peat fraction, nearby events and recurrence.

# 21. Human verification / information gain

The highest-value output is often not a causal label but a question that resolves disagreement. Examples:
- inspect intervening peat corridor
- verify earliest apparent origin area
- obtain incident/fire-response records for date window
- compare management records to observed chronology
- seek higher-resolution/local evidence for an observation gap

# 22. Audit Evidence Pack

The final product is engagement-level: **Environmental Fire Review / Environmental Fire Investigation Pack**.

Include:
1. audit scope and review period
2. source/method summary
3. screening/compression summary
4. selected FireEvents
5. maps and timelines
6. deterministic environmental metrics
7. imagery evidence
8. event relationships
9. adversarial analysis
10. unresolved questions
11. recommended verification
12. evidence limitations
13. provenance/model versions
14. human auditor notes/disposition
15. disclaimer

Mandatory disclaimer:
> This report is an investigative-support product. It does not establish legal responsibility, intent, culpability, ownership liability, or criminal wrongdoing. Findings require human verification.

# 23. Smallholder and fairness design principle

The product hypothesis is that lowering the technical cost of reconstructing environmental evidence can reduce dependence on large GIS/compliance/expert teams. Do not claim the product proves systematic bias or that certified companies frame smallholders.

Design consequence: exculpatory evidence must be first-class. If an earlier neighbouring event is compatible with later observations inside the audit scope, surface that relationship as prominently as evidence supporting independent local ignition.

# 24. API

```text
POST /api/audits
POST /api/audits/{audit_id}/scope/upload
POST /api/audits/{audit_id}/history/build
GET  /api/audits/{audit_id}/events
GET  /api/audits/{audit_id}/events/{event_id}
GET  /api/audits/{audit_id}/events/{event_id}/history
GET  /api/audits/{audit_id}/events/{event_id}/evidence
GET  /api/audits/{audit_id}/graph?event_ids=...
GET  /api/audits/{audit_id}/overlays/{layer}?bbox=&date=
GET  /api/audits/{audit_id}/tiles/{layer}/{z}/{x}/{y}?date=
POST /api/audits/{audit_id}/events/{event_id}/triage
POST /api/audits/{audit_id}/events/{event_id}/evidence/collect
POST /api/audits/{audit_id}/events/{event_id}/analyse
POST /api/audits/{audit_id}/events/{event_id}/add-to-pack
POST /api/audits/{audit_id}/report
GET  /api/audits/{audit_id}/report
```

# 25. Core data models

```text
AuditScope
SourceRun
ObservationIndex
CandidateThermalEvent
FireEvent
FireEventMembership
FireEventEdge
EvidenceObject
AnalysisRun
HypothesisAssessment
AuditReview
Report
```

Suggested `AuditScope`:
```ts
type AuditScope = {
  id: string;
  label?: string;
  reviewStart: string;
  reviewEnd: string;
  geometryR2Key?: string;
  bbox: [number, number, number, number];
  centroid: [number, number];
  contextBufferKm: number;
  createdAt: string;
};
```

# 26. Source provider storage policy

Every provider declares storage semantics:
```python
storage_policy = {
  "raw": "S3|NONE",
  "metadata": "DYNAMODB",
  "cache": "CACHE|NONE",
  "cache_ttl": 86400,
}
```

Do not duplicate overlapping weather windows per event when a shared cached query can serve them.

# 27. Reproducibility

When a report is finalized, freeze enough evidence to reproduce it later: structured evidence, source query parameters, selected raw snapshots/partitions, algorithm/model versions, input hashes and report PDF. Never silently overwrite historical conclusions after model upgrades.

# 28. UI acceptance criteria

- create audit scope from dates + GeoJSON boundary or coordinate fallback
- visible context buffer
- build historical event register
- table first, map second
- multi-select table -> map
- map shows selected events + relevant neighbours
- Evidence Drawer renders cheap evidence immediately
- imagery loads asynchronously with missing-data states
- metrics are inspectable/provenanced
- AI only runs explicitly
- human can add events to audit evidence pack
- engagement-level report generated

# 29. Technical acceptance criteria

- raw FIRMS preserved and clustered reproducibly
- GeoJSON coordinate order `[longitude, latitude]`
- geometry validation and tenant scoping
- deterministic triage before expensive sources
- EvidenceObjects carry provenance/limitations
- FireEventGraph is deterministic/versioned
- agent outputs validate against strict schema
- no unsupported causal/legal language
- finalized reports are reproducible

# 30. Hackathon cut line

**Must ship:**
- audit scope form + GeoJSON upload / coordinate fallback
- date range + context buffer
- FIRMS -> FireEvent clustering
- Historical Fire Register table
- table filters + multi-select
- selected-event map handoff
- FireEventGraph basics
- peat/weather enrichment
- Evidence Drawer
- inspectable metrics
- Investigator/Skeptic structured output
- evidence pack/report view

**If possible:**
- Sentinel-2 processing
- Sentinel-1 change evidence
- simple surface ellipse
- PDF export

**Do not delay demo for:**
- Kalman refinement
- public concession lookup
- BMKG integration
- historical OSM
- perfect SAR processing
- full KML/KMZ/SHP parser if GeoJSON works

# 31. Demo narrative

1. Auditor creates review: uploads management-unit boundary and chooses historical period.
2. `Build Fire History`: show real compression from raw observations to FireEvents.
3. Historical Fire Register appears; sort/filter and select a complex event plus related neighbour.
4. `Investigate on Map`: map opens selected events, context buffer and graph relationship.
5. Click event: deterministic metrics appear immediately; S1/S2 evidence hydrates.
6. Click metrics to reveal peat/weather/propagation evidence.
7. `Generate Investigation Analysis`: Investigator and Skeptic disagree over local ignition vs neighbour/peat explanation.
8. System outputs unresolved question and recommended field verification.
9. Add event to evidence pack; show engagement-level review.

Core demo line:
> Raw satellite observations are abundant. Auditor attention is not. We reconstruct the historical event record so fieldwork starts with targeted questions instead of a blank map.

# 32. Final architectural principle

> **Deterministic systems establish observations. Physical/environmental models derive evidence. AI challenges competing interpretations. Humans investigate and decide.**
