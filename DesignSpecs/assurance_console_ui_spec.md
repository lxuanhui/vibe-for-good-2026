# Environmental Assurance Console — Frontend/UI Specification

**Stack:** Vite + React frontend, Cloudflare Workers backend.
**Companion document:** `environmental_assurance_spec_v2.md` (data sources,
ingestion architecture, evidence model, agent design). This document
covers the UI layer only.

---

# 1. Two view modes, one shared state

The console has exactly two ways of looking at the same underlying event
data, switched with a persistent toggle in the top-right of the screen:
**Map** and **Table**.

- **Map** is for when spatial relationships carry the answer: is this fire
  inside a peat dome, does it sit near a concession boundary, does a SAR
  footprint overlap a projected fire-growth ellipse. Spatial resolution
  matters more than chronological ordering.
- **Table** is for when spatial position doesn't matter and time/priority
  does: an auditor triaging a backlog wants to sort by status, by support
  score, by which events are still awaiting review — not pan around a map
  clicking markers one at a time.

Both modes read from the same event/case state. Selecting a row in the
table pans to and highlights the corresponding marker if the user
switches to Map mode; selecting a marker in Map mode highlights the
matching row if they switch to Table. Neither mode is a separate page —
switching is instant and preserves the current selection.

---

# 2. Map mode

## 2.1 Base map

Render on an actual Indonesia basemap using a real, open-source GeoJSON
boundary source — do not hand-build a custom projection or bake
coordinates into static paths. Recommended approach: MapLibre GL JS
(free, open-source, renders GeoJSON and raster tiles natively, built-in
pan/zoom/bbox querying).

For the country/province outline, use a maintained open-source Indonesia
GeoJSON dataset rather than generating one, for example:
- `superpikar/indonesia-geojson` — lightweight province-level boundaries,
  good default for a fast-loading base layer.
- A GADM-derived dataset (e.g. `chmdznr/indonesia-geojson` or
  `wabiwabo/geojson-political-indonesia`) if kabupaten/kota-level
  granularity is needed for labeling which regency a given event falls in.

This boundary layer is static reference geography — bundle it as a
frontend asset. It is not fetched through the ingestion API, since it
doesn't change.

## 2.2 Overlay layers — one consistent pattern for every data source

Every data layer that varies by location and/or date — fire detections,
SAR backscatter, optical imagery, peat hydrological units, concessions,
fire-complex links — is added to the map the same way, as either a
GeoJSON source (points/polygons) or a raster tile source (imagery),
queried by bounding box and date:

```js
// point/polygon layers
map.addSource('firms', {
  type: 'geojson',
  data: '/api/overlays/firms?bbox={minLon,minLat,maxLon,maxLat}&date={date}'
});
map.addLayer({ id: 'firms-points', type: 'circle', source: 'firms', paint: {...} });

// raster layers (satellite imagery tiles)
map.addSource('s2-quicklook', {
  type: 'raster',
  tiles: ['/api/tiles/s2-quicklook/{z}/{x}/{y}?date={date}'],
  tileSize: 256
});
map.addLayer({ id: 's2-layer', type: 'raster', source: 's2-quicklook' });
```

Adding a new overlay to the map should always mean "add a source + layer
pointing at an endpoint," never a bespoke renderer per data type. Every
overlay layer has a toggle in a layer-control panel (top-left) so the
auditor can turn individual sensor layers on/off independently.

## 2.3 Timeline scrubber

A horizontal timeline control lets the user scrub backward from the most
recent pass. Because different sensors have different revisit cadence
(thermal detections are near-daily, SAR radar passes roughly every few
days, cloud-free optical imagery is intermittent), the scrubber should
visibly indicate which overlay layers actually have data available at the
selected date — greying out or badge-marking a layer with "no pass at
this date" rather than silently showing stale or missing data. Playback
(auto-advance through the timeline) should be supported with a play/pause
control.

## 2.4 Event markers and selection

Each qualified fire event renders as a marker. Two marker states:
monitored/no active detection, and active detection on the current pass —
visually distinct (e.g. a quiet outline reticle vs. a filled glow marker)
so the auditor can tell at a glance which monitored locations are
currently active. Clicking a marker opens a compact floating info card
anchored to it, showing current-day conditions (temperature, humidity,
wind, rainfall) and a button to open the full report (Section 4) if the
event has qualified for investigation.

---

# 3. Table mode

Opens as a full-height sidebar from the right edge; the map stays visible
and interactive at reduced width underneath rather than being replaced,
so switching between browsing spatially and scanning the queue doesn't
lose context.

**Columns, sortable and filterable:**

| Column | Description |
|---|---|
| Event / fire-complex ID | Unique identifier |
| Location | Kabupaten/province, resolved against the admin boundary layer |
| First detected | Timestamp of the earliest linked detection |
| Status | Awaiting review / Stage 1 rejected / Stage 2 running / Converged |
| Top hypothesis | Highest-support theory from the report (Section 4) |
| Support score | Numeric score for the top hypothesis |
| Peat classification | Protected dome / production zone / not applicable |
| Days since last surface detection | For events linked into a multi-detection fire complex |

This is a plain dense sortable table — the goal is scannability for
triage, not additional charting. Row click selects that event across both
view modes as described in Section 1.

---

# 4. Investigation report

The report for a qualified, investigated event is a synthesized document,
not a raw transcript of agent-to-agent dialogue. Structure, top to bottom:

## 4.1 Executive summary
Two to three plain-language sentences summarizing what was found and the
overall confidence level.

## 4.2 Top 3 theories
The three highest-support hypotheses, each rendered as a ranked card:

- Hypothesis label
- Support score, with consistent color coding across the app (e.g. green
  for high-confidence/benign, red for high-confidence/concerning, grey for
  inconclusive — pick one scheme and use it everywhere scores appear)
- Supporting evidence IDs and contradicting evidence IDs, shown as small
  clickable chips
- Clicking an evidence chip scrolls to and highlights that evidence's
  entry in the full reasoning log (Section 4.4)

## 4.3 Data visualization panel
Inline charts drawn from the event's evidence, for example:
- Fire-weather index (FWI/KBDI/VPD) trend over the lead-up period
- SAR backscatter trend showing the drop/persistence signature
- The fire-growth ellipse projection, rendered as a small map inset
  showing the modeled extent against the peat boundary

This panel is a first-class part of the report, not an appendix — a
reader should be able to see the evidence shape without opening the full
transcript.

## 4.4 Full reasoning log — collapsed by default
The round-by-round exchange between the investigating agents, available
behind a "Show full reasoning" disclosure. This preserves complete
transparency (nothing is hidden, every claim is traceable to an evidence
ID) without making the raw dialogue the first thing the reader has to
parse. When expanded, each round shows both agents' position, their
support/contradiction scores, and whether that round reached agreement.

## 4.5 Limitations
A short, always-visible list of caveats attached to this specific report
(e.g. sensor cadence limits, proxy-data caveats) — sourced directly from
the evidence layer's own limitation flags, not generated fresh by the
report view.

## 4.6 Stage 1 gate (pre-investigation)
Before Section 4.1–4.5 render at all, show the Stage 1 validation
checklist as a distinct step-by-step sequence with a clear pass/reject
outcome. If the event fails Stage 1, show that outcome plainly and do not
render Sections 4.1–4.5 — make it visually obvious that no investigation
budget was spent on a rejected event.

---

# 5. Ingestion endpoint contract

All dynamic data — events, overlays, tiles, reports — is served from
these endpoints. Every listing/overlay endpoint accepts bounding-box and
date filters so the map viewport and timeline scrubber only ever request
what's currently visible.

```text
GET /api/events
    ?bbox=minLon,minLat,maxLon,maxLat
    &since=ISO8601
    &status=AMBIGUOUS|REJECTED|STAGE2_RUNNING|CONVERGED
    -> { events: [ { id, lat, lon, firstDetected, status, ... } ] }

GET /api/events/{event_id}
    -> full event / fire-complex object

GET /api/overlays/{layer}
    ?bbox=...&date=...
    layer in: firms | sar-backscatter | khg | concessions | fire-complex-links
    -> GeoJSON FeatureCollection

GET /api/tiles/{layer}/{z}/{x}/{y}
    ?date=...
    layer in: s2-quicklook | sar-visualization
    -> raster tile

GET /api/events/{event_id}/report
    -> report object per Section 4; while an investigation is in progress,
       returns the same shape with status: "running" and partial fields,
       so the UI can render an in-progress state without a separate endpoint
```

Report object shape:

```json
{
  "event_id": "IND-02671",
  "status": "converged",
  "executive_summary": "string",
  "top_theories": [
    { "rank": 1, "hypothesis": "string", "support_score": 78,
      "evidence_ids": ["E4","E9","E14"], "counter_evidence_ids": ["E2"] }
  ],
  "data_visualizations": {
    "fwi_kbdi_timeseries": [],
    "sar_backscatter_trend": [],
    "fire_growth_projection": {}
  },
  "limitations": ["string"],
  "reasoning_log": [
    { "round": 1, "converged": false,
      "investigator": { "hypothesis": "string", "support": 0, "contra": 0, "text": "string" },
      "skeptic":      { "hypothesis": "string", "support": 0, "contra": 0, "text": "string" } }
  ]
}
```

---

# 6. Visual language guidelines

- Keep a single, consistent color scheme for confidence/status across the
  entire app (map markers, table status column, report support scores) —
  the same three or four colors should mean the same thing everywhere.
- Distinguish "monitored, quiet" from "active detection" states clearly
  in both map markers and table rows.
- The Stage 1 gate (Section 4.6) should feel procedural and visibly
  real — a step-by-step checklist with individual pass/fail states, not
  a single spinner — since demonstrating that the gate does real
  filtering work is part of the product's value proposition.
