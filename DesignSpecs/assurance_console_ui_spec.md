# Environmental Assurance Console — Frontend/UI Specification

**Status:** Updated 2026-09-08  
**Stack:** Vite + React frontend, Cloudflare Workers backend  
**Canonical companion:** `Environmental_Assurance_Spec.md`

---

# 1. UX thesis

The console follows an assurance workflow rather than a territory-wide fire-monitoring workflow. The auditor first defines **where** and **when** the engagement applies, reconstructs the historical event register, screens it temporally, then investigates selected events spatially.

**Table first = screening. Map second = investigation.** Both operate on the same `AuditScope`, `FireEvent`, `FireEventGraph`, and evidence state.

```text
Audit Scope -> Build Fire History -> Historical Fire Register
           -> select events -> Spatial Investigation Workspace
           -> Evidence Drawer -> Generate Investigation Analysis
           -> Add to Audit Evidence Pack -> Human decision
```

# 2. Create Audit Review

The landing workflow is a scope form, not an Indonesia-wide map.

Required fields:
- review start date
- review end date
- area under review
- contextual buffer distance

Preferred area input:
1. upload management-unit boundary: GeoJSON first for MVP; KML/KMZ/SHP as follow-on
2. draw polygon on map
3. lat/lon + radius fallback

Do not provide a public concession-name search that resolves named Indonesian concession polygons. Uploaded geometry is private client/auditor scope data. Company name is optional and must not enter environmental scoring.

After upload, validate geometry, display a preview, calculate bbox/centroid, assign `scope_id`, and clearly show the external context buffer.

# 3. Build Fire History

On `BUILD FIRE HISTORY`:
1. query FIRMS for scope bbox + context buffer + date range;
2. apply confidence/non-fire triage;
3. cluster observations into FireEvents;
4. classify each event `INSIDE_SCOPE`, `BOUNDARY_INTERSECTING`, or `EXTERNAL_CONTEXT`;
5. enrich event summaries with cached/cheap weather, peat and recurrence metrics;
6. index relevant Sentinel-1/Sentinel-2 scenes without blocking the table;
7. construct candidate FireEventGraph edges.

Show progressive compression prominently, using real computed numbers:
`raw observations -> qualified observations -> FireEvents -> events requiring review`.

# 4. Historical Fire Register — primary table workspace

The first analysis screen is a dense, full-width table optimized for multi-year temporal review.

Sortable/filterable columns:
| Column | Purpose |
|---|---|
| FireEvent ID | stable event identifier |
| First detected | temporal ordering |
| Last detected / duration | persistence |
| Observation count | cluster support |
| Scope relation | inside / boundary / external |
| Distance to boundary | spatial context |
| Peak FRP | thermal intensity descriptor |
| Peat overlap | environmental context |
| Complexity | deterministic investigation feature |
| Evidence sufficiency | sufficient / partial / insufficient |
| Relationship | isolated / linked? / graph neighbours |
| Investigation priority | low / medium / high / urgent |
| Review state | unreviewed / screened / investigating / added to pack |

Filters should include date range, scope relation, peat, persistence, complexity, evidence sufficiency, priority, and review state. Where data exists, allow land-management context such as replanting/expansion, but never infer intent from it.

Support multi-select. Primary CTA: `INVESTIGATE ON MAP`.

# 5. Spatial Investigation Workspace — Palantir-style map

The map receives selected FireEvents plus graph-relevant contextual neighbours. Do not render the entire historical regional FIRMS archive by default.

Layers:
- uploaded audit boundary
- context buffer
- FireEvents
- optional raw FIRMS observations for selected event(s)
- FireEventGraph edges
- peat
- wind
- Sentinel-2
- Sentinel-1
- land cover
- first-order surface propagation envelope

Timeline controls all temporal layers and shows sensor availability. Missing imagery must be shown as missing/no-pass, never silently replaced with stale imagery.

External-context events are visually distinct and cannot be added to the audit subject list unless the user deliberately expands scope.

# 6. Evidence Drawer

Clicking a FireEvent opens a persistent side drawer. Cheap/cached evidence renders immediately; expensive imagery and derived products load progressively.

Immediate summary:
- event time range and duration
- observation count / FRP
- scope relation / distance to boundary
- peat overlap
- rainfall / wind / humidity windows
- historical recurrence
- surface-spread compatibility
- nearby prior/subsequent events
- complexity
- evidence sufficiency

Satellite section:
- Sentinel-2 pre/post quicklooks/composites
- Sentinel-1 pre/post/change evidence
- acquisition dates, cloud/cadence limitations and provenance

# 7. Inspectable metrics

Metrics are not dead labels. Clicking a metric reveals the evidence behind it:
- peat overlap -> highlight intersecting area
- nearby events -> highlight nodes/edges
- surface-spread compatibility -> observed detections vs first-order ellipse
- rainfall/wind -> supporting time-series chart
- Sentinel evidence -> imagery and acquisition metadata
- complexity -> contributing deterministic features

Every derived metric exposes evidence IDs, source, time window, quality, limitations, algorithm version, and inputs hash where available.

# 8. Explicit AI action

Do not auto-run adversarial AI when an event is clicked. CTA: `GENERATE INVESTIGATION ANALYSIS`.

Before execution, show the evidence package being supplied. Investigator and Skeptic reason only over structured evidence IDs.

Output sections:
- competing event-history hypotheses
- supporting and contradicting evidence
- unresolved disagreement
- evidence sufficiency
- limitations
- recommended field/document verification questions

Do not show private chain-of-thought. Show concise structured arguments and evidence references.

# 9. Hypothesis UI

Default hypotheses:
- H1 Independent local ignition
- H2 Surface propagation from earlier neighbouring event
- H3 Peat-mediated persistence/propagation
- H4 Multiple related land-management ignitions
- H5 Regional independent events under shared conducive conditions
- H6 Other mechanism

Evidence sufficiency is separate: `SUFFICIENT | PARTIAL | INSUFFICIENT`. Support scores are evidence-support scores, not probabilities.

# 10. Audit Evidence Pack workflow

After review, CTA: `ADD TO AUDIT EVIDENCE PACK`. The audit workspace summarizes:
- FireEvents identified
- events screened/deprioritized
- events reviewed
- events recommended for verification
- insufficient-evidence events
- selected evidence-pack events

Final CTA: `GENERATE AUDIT FIRE REVIEW`. The output is engagement-level, not merely one-fire-at-a-time.

Required sections: scope metadata; boundary/date definition; screening summary; selected events; maps/timelines; evidence; adversarial analyses; unresolved questions; fieldwork priorities; provenance; human notes; disclaimer.

# 11. Safety and scope semantics

- Score events, not companies.
- Boundary membership is context, not responsibility.
- First detection inside a boundary does not establish origin there.
- External events may inform interpretation but are not automatically audit subjects.
- Client identity must not alter physical/environmental scores.
- No public worst-company leaderboard or searchable accusation interface.
- Use neutral language: `requires verification`, `compatible with`, `not established`, `insufficient evidence`.

# 12. Shared state

Core client state:
```ts
type AuditScope = {
  id: string;
  label?: string;
  reviewStart: string;
  reviewEnd: string;
  geometryRef: string;
  bbox: [number, number, number, number];
  contextBufferKm: number;
};

type ScopeRelation = 'INSIDE_SCOPE' | 'BOUNDARY_INTERSECTING' | 'EXTERNAL_CONTEXT';
```

Persist selection across table/map. Switching from table to map preserves selected events, filters, date window and audit scope.

# 13. API contract additions

```text
POST /api/audits
POST /api/audits/{audit_id}/scope/upload
POST /api/audits/{audit_id}/history/build
GET  /api/audits/{audit_id}/events
     ?since=&until=&scope_relation=&priority=&complexity=&review_state=
GET  /api/audits/{audit_id}/events/{event_id}
GET  /api/audits/{audit_id}/events/{event_id}/evidence
GET  /api/audits/{audit_id}/graph?event_ids=...
POST /api/audits/{audit_id}/events/{event_id}/analyse
POST /api/audits/{audit_id}/events/{event_id}/add-to-pack
POST /api/audits/{audit_id}/report
GET  /api/audits/{audit_id}/report
```

Overlay/tile endpoints must accept audit scope, bbox and time constraints.

# 14. Progressive loading

`Build Fire History` must not wait for every satellite product. Table rows appear once clustering and cheap enrichment complete. Sentinel scene metadata and imagery hydrate asynchronously. Evidence Drawer shows explicit loading/availability states per source.

# 15. Visual language

Maintain the dark operational visual language, but optimize for assurance rather than command-and-control. The table should feel like a review register; the map like an evidence investigation workspace. Distinguish observed evidence, derived metrics, AI interpretation and human decisions visually and structurally.

# 16. MVP acceptance criteria

- user can create an audit review with date range + GeoJSON boundary or lat/lon fallback
- system applies configurable context buffer
- historical FIRMS observations are clustered into FireEvents
- table is the first populated analysis view
- table supports scope/date/risk/review filtering and multi-select
- selected events open on map with contextual neighbours
- clicking event opens Evidence Drawer immediately
- S1/S2 imagery loads asynchronously with provenance/limitations
- important metrics are inspectable
- AI runs only on explicit request and uses evidence IDs
- user can add reviewed events to engagement-level evidence pack
- final report preserves uncertainty and does not establish blame/intent/legal responsibility
