import { useEffect, useMemo, useRef, useState } from 'react'
import { Layer, Map, Source, type MapLayerMouseEvent } from 'react-map-gl/maplibre'
import type { Feature, FeatureCollection, Geometry, LineString, Point } from 'geojson'
import type { AuditEventSummary, AuditScope, EventEvidenceResponse, InvestigationMap, InvestigationMapNode, StructuredAnalysis } from '../../api/types'
import { addToAuditPack, fetchAuditRegister, fetchInvestigationBundle, fetchInvestigationMap, generateInvestigationAnalysis } from '../../api/client'
import { AUDIT_EVENT_COLORS, AUDIT_SCOPE_BOUNDARY_COLOR, AUDIT_SCOPE_BUFFER_COLOR, SURFACE_FIRE_ENVELOPE_COLOR } from '../../lib/layerColors'
import { useAppStore } from '../../store/useAppStore'
import { Button } from '../ui/Button'
import { EvidenceDrawer } from '../audit/EvidenceDrawer'
import { envelopePolygons } from './propagationEnvelopes'
import { eventOverlapsDay, investigationDays, observationsForDay, type ScopedMapDay } from './temporalScrubber'
import 'maplibre-gl/dist/maplibre-gl.css'

const GRAPH_LINE_COLOR = '#f97316'
const OBSERVATION_COLOR = '#fbbf24'
const SCOPED_MAP_RELATIONSHIP_DISTANCE_KM = 10
const CLOCK_REFRESH_MS = 60 * 1000

function southeastAsiaLight(date: Date) {
  // UTC+8 is a useful regional midpoint. This is visual orientation only.
  const localHour = (date.getUTCHours() + date.getUTCMinutes() / 60 + 8) % 24
  const daylight = Math.max(0, Math.sin(((localHour - 6) / 12) * Math.PI))
  return { daylight, label: daylight > 0.15 ? 'DAYLIGHT' : 'NIGHT' }
}

// The correlation graph is one rolled-together view now, not two flows that
// silently replace each other: `origin` distinguishes an edge that touches
// the FireEvent currently open in the evidence drawer ("focus") from one that
// only belongs to the wider Fire Register selection ("selection"). Same hue,
// different weight -- "colour them slightly differently" rather than
// introducing a second unrelated color to an already-busy legend.
type GraphEdgeOrigin = 'focus' | 'selection'
type TaggedGraphEdge = InvestigationMap['edges'][number] & { origin: GraphEdgeOrigin }

function filteredObservationPoints(evidence: EventEvidenceResponse | undefined, day: ScopedMapDay): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: observationsForDay(evidence, day).map((obs) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [obs.lon, obs.lat] }, properties: { frp: obs.frp, acqDate: obs.acqDate } })),
  }
}

// Merges the always-visible in-scope+buffer register with whatever a graph
// fetch pulled in as neighbours -- a related event can sit outside the
// buffer bbox and still be worth drawing (spec §13: relevant graph
// neighbours, not the whole regional archive).
function mapPoints(events: AuditEventSummary[], graphNodes: InvestigationMapNode[]): FeatureCollection<Point> {
  // A plain object, not a Map instance -- `Map` in this file's scope is the
  // react-map-gl component import, and `new Map(...)` here would construct
  // that instead of the global collection type.
  const byId: Record<string, { lon: number; lat: number; state: string; focus: string }> = {}
  for (const event of events) {
    byId[event.eventId] = { lon: event.centroid.lon, lat: event.centroid.lat, state: event.triage.state, focus: '' }
  }
  for (const node of graphNodes) {
    byId[node.eventId] = { lon: node.centroid.lon, lat: node.centroid.lat, state: node.triage.state, focus: node.mapRole }
  }
  return {
    type: 'FeatureCollection',
    features: Object.entries(byId).map(([id, value]) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [value.lon, value.lat] },
      properties: { id, state: value.state, focus: value.focus },
    })),
  }
}

function graphEdges(graphNodes: InvestigationMapNode[], edges: TaggedGraphEdge[]): FeatureCollection<LineString> {
  // A plain object, not a Map instance -- see the note on `mapPoints` above.
  const nodeById: Record<string, InvestigationMapNode> = {}
  for (const node of graphNodes) nodeById[node.eventId] = node
  return {
    type: 'FeatureCollection',
    features: edges.flatMap((edge) => {
      const from = nodeById[edge.sourceEventId]
      const to = nodeById[edge.targetEventId]
      return from && to
        ? [{ type: 'Feature' as const, geometry: { type: 'LineString' as const, coordinates: [[from.centroid.lon, from.centroid.lat], [to.centroid.lon, to.centroid.lat]] }, properties: { origin: edge.origin, state: edge.state } }]
        : []
    }),
  }
}

function scopeFeature(geometry: unknown): Feature<Geometry> | null {
  return geometry ? { type: 'Feature', geometry: geometry as Geometry, properties: {} } : null
}

export function ScopedMapLanding({ scope, onOpenScope, onOpenRegister, onViewReport }: { scope: AuditScope; onOpenScope: () => void; onOpenRegister: () => void; onViewReport: () => void }) {
  const [events, setEvents] = useState<AuditEventSummary[]>([])
  const [packed, setPacked] = useState<string[]>([])
  // Package selection belongs to this sidebar. It is deliberately separate
  // from Fire Register selection, which drives the relationship graph and
  // should not force an auditor to put every compared event in the report.
  const [candidateIds, setCandidateIds] = useState<string[]>([])
  const [packError, setPackError] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const positionedForAudit = useRef('')
  const boundary = useMemo(() => scopeFeature(scope.geometry), [scope.geometry])
  const buffer = useMemo(() => scopeFeature(scope.buffer_geometry), [scope.buffer_geometry])

  // Table multi-select ("INVESTIGATE ON MAP") hands off through this store
  // field rather than a prop -- App.tsx just flips viewMode, it does not
  // know about event selection.
  const registerSelection = useAppStore((state) => state.registerSelection)

  // The wider correlation graph, seeded by every FireEvent checked in the
  // Fire Register. This used to live in the same state as "which event's
  // drawer is open" -- clicking one dot on the map replaced it outright, so
  // the richer multi-select correlations silently vanished the moment you
  // inspected one of them. It is now independent: checking rows in the
  // register is what grows or shrinks this graph, not clicking the map.
  const [selectionGraph, setSelectionGraph] = useState<InvestigationMap>()
  const [selectionGraphError, setSelectionGraphError] = useState('')
  useEffect(() => {
    if (registerSelection.length <= 1) { setSelectionGraph(undefined); setSelectionGraphError(''); return }
    let active = true
    setSelectionGraphError('')
    fetchInvestigationMap(scope.audit_id, registerSelection)
      .then((result) => { if (active) setSelectionGraph(result) })
      .catch((reason) => { if (active) setSelectionGraphError(reason instanceof Error ? reason.message : 'Related FireEvents could not be loaded.') })
    return () => { active = false }
  }, [scope.audit_id, registerSelection])

  // The ONE FireEvent whose evidence drawer is open -- from a map click, or
  // seeded once on arrival when the register selection was itself a single
  // row. Deliberately not the same state as the register selection above.
  const [focusedEventId, setFocusedEventId] = useState<string>()
  const seededFocusForAudit = useRef('')
  useEffect(() => {
    if (seededFocusForAudit.current === scope.audit_id) return
    seededFocusForAudit.current = scope.audit_id
    if (registerSelection.length === 1) setFocusedEventId(registerSelection[0])
  }, [scope.audit_id, registerSelection])

  // A single bundled request supplies the drawer, its own one-event graph,
  // and the raw observations layer. This avoids a click producing two
  // independent 404 opportunities against a just-created audit.
  const drawerEventId = focusedEventId
  const [evidence, setEvidence] = useState<EventEvidenceResponse>()
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [evidenceError, setEvidenceError] = useState('')
  const [analysis, setAnalysis] = useState<StructuredAnalysis>()
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [focusGraph, setFocusGraph] = useState<InvestigationMap>()
  const [focusGraphError, setFocusGraphError] = useState('')
  const [showObservations, setShowObservations] = useState(true)
  const [selectedDay, setSelectedDay] = useState<ScopedMapDay>(null)
  const days = useMemo(() => investigationDays(scope.review_start, scope.review_end), [scope.review_start, scope.review_end])
  const activeDay = selectedDay && days.includes(selectedDay) ? selectedDay : null
  const [showPeatland, setShowPeatland] = useState(false)
  const [evidenceReloadToken, setEvidenceReloadToken] = useState(0)
  const [clock, setClock] = useState(() => new Date())
  useEffect(() => {
    if (!drawerEventId) { setEvidence(undefined); setEvidenceError(''); setFocusGraph(undefined); setFocusGraphError(''); setAnalysis(undefined); setAnalysisError(''); return }
    setShowObservations(true)
    let active = true
    setEvidenceLoading(true)
    setEvidenceError('')
    setFocusGraphError('')
    fetchInvestigationBundle(scope.audit_id, drawerEventId)
      .then((result) => {
        if (!active) return
        setEvidence(result.event)
        setFocusGraph(result.graph ?? undefined)
        setAnalysis(result.analysis ?? undefined)
      })
      .catch((reason) => {
        if (!active) return
        const message = reason instanceof Error ? reason.message : 'Evidence could not be loaded.'
        setEvidenceError(message)
        setFocusGraphError(message)
      })
      .finally(() => { if (active) setEvidenceLoading(false) })
    return () => { active = false }
  }, [scope.audit_id, drawerEventId, evidenceReloadToken])
  const observations = useMemo(() => filteredObservationPoints(evidence, activeDay), [evidence, activeDay])

  async function generateAnalysis() {
    if (!drawerEventId) return
    setAnalysisLoading(true)
    setAnalysisError('')
    try { setAnalysis(await generateInvestigationAnalysis(scope.audit_id, drawerEventId)) }
    catch (reason) { setAnalysisError(reason instanceof Error ? reason.message : 'Investigation analysis could not be generated.') }
    finally { setAnalysisLoading(false) }
  }

  // One rolled-together graph for the map: every node either source contains,
  // and every edge tagged by which source it came from so the paint
  // expression below can colour the two "slightly differently" instead of
  // one flow's correlations silently overwriting the other's.
  const graphNodes = useMemo(() => {
    // A plain object, not a Map instance -- see the note on `mapPoints` above.
    const byId: Record<string, InvestigationMapNode> = {}
    for (const node of selectionGraph?.nodes ?? []) byId[node.eventId] = node
    for (const node of focusGraph?.nodes ?? []) byId[node.eventId] = node
    return Object.values(byId)
  }, [selectionGraph, focusGraph])
  const taggedEdges = useMemo<TaggedGraphEdge[]>(() => {
    const edgeKey = (edge: { sourceEventId: string; targetEventId: string }) => `${edge.sourceEventId} ${edge.targetEventId}`
    const focusKeys = new Set((focusGraph?.edges ?? []).map(edgeKey))
    const selected = new Set(registerSelection)
    return [
      ...(focusGraph?.edges ?? []).map((edge) => ({ ...edge, origin: 'focus' as const })),
      ...(selectionGraph?.edges ?? [])
        .filter((edge) => !focusKeys.has(edgeKey(edge)))
        .map((edge) => ({ ...edge, origin: 'selection' as const })),
    ].filter((edge) => {
      if (edge.distanceKm > SCOPED_MAP_RELATIONSHIP_DISTANCE_KM) return false
      const selectedPair = selected.has(edge.sourceEventId) && selected.has(edge.targetEventId)
      // A one-event drawer graph can rediscover another selected event as a
      // contextual neighbour. Do not let its distance-only fallback override
      // the multi-select rule: selected pairs need an existing deterministic
      // graph record before they can be drawn as a relationship.
      return !selectedPair || edge.evidence?.[0]?.type === 'candidate_edge_fire_event_graph'
    })
  }, [selectionGraph, focusGraph, registerSelection])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    fetchAuditRegister(scope.audit_id, { since: scope.review_start, until: scope.review_end, bbox: scope.buffer_bbox ?? undefined })
      .then((result) => { if (active) { setEvents(result.events); setPacked(result.progression.selectedEventIds); setCandidateIds([]) } })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : 'FireEvents could not be loaded.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [scope.audit_id, scope.review_start, scope.review_end, scope.buffer_bbox])

  function toggleCandidate(eventId: string) {
    setCandidateIds((ids) => ids.includes(eventId) ? ids.filter((id) => id !== eventId) : [...ids, eventId])
  }

  async function addCandidatesToPack() {
    const additions = candidateIds.filter((id) => !packed.includes(id))
    if (!additions.length) return
    setPackError('')
    // Keep the requests ordered so an error can remain attached to the exact
    // selection that failed. The audit store also merges each entry with a
    // conditional retry, protecting this pack from overlapping Lambda calls.
    const added: string[] = []
    const failed: string[] = []
    for (const id of additions) {
      try {
        await addToAuditPack(scope.audit_id, id)
        added.push(id)
      } catch {
        failed.push(id)
      }
    }
    if (added.length) setPacked((ids) => [...ids, ...added.filter((id) => !ids.includes(id))])
    setCandidateIds(failed)
    if (failed.length) setPackError(`Could not add ${failed.length} selected FireEvent${failed.length === 1 ? '' : 's'} to the audit report.`)
  }
  const visibleEvents = useMemo(() => events.filter((event) => eventOverlapsDay(event, activeDay)), [events, activeDay])
  const visibleGraphNodes = useMemo(() => graphNodes.filter((node) => eventOverlapsDay(node, activeDay)), [graphNodes, activeDay])
  const points = useMemo(() => mapPoints(visibleEvents, visibleGraphNodes), [visibleEvents, visibleGraphNodes])
  const edges = useMemo(() => graphEdges(visibleGraphNodes, taggedEdges), [visibleGraphNodes, taggedEdges])
  const envelopes = useMemo(() => envelopePolygons(taggedEdges, registerSelection), [taggedEdges, registerSelection])
  const [showSpreadEnvelopes, setShowSpreadEnvelopes] = useState(true)
  const center = useMemo<[number, number]>(() => scope.centroid ?? [116.25, -3.8], [scope.centroid])
  const light = southeastAsiaLight(clock)

  useEffect(() => {
    const refresh = window.setInterval(() => setClock(new Date()), CLOCK_REFRESH_MS)
    return () => window.clearInterval(refresh)
  }, [])

  // Carto's basemap tiles now require a key on every request. The style JSON
  // stays key-free and committed; the key is appended here so it never lands
  // in a tracked file, only in the built bundle (Carto keys are meant to be
  // client-side and domain-restricted on Carto's end, unlike a server secret).
  // The vector style pulls from several cartocdn.com subdomains -- tile,
  // sprite, and glyph requests all match this, not just the tile domain.
  const cartoApiKey = import.meta.env.VITE_CARTO_API_KEY as string | undefined
  const transformRequest = useMemo(() => {
    if (!cartoApiKey) return undefined
    return (url: string) => {
      if (!url.includes('cartocdn.com')) return { url }
      return { url: `${url}${url.includes('?') ? '&' : '?'}key=${cartoApiKey}` }
    }
  }, [cartoApiKey])

  const initialViewState = useMemo(() => {
    const span = scope.buffer_bbox
      ? Math.max(scope.buffer_bbox.maxLon - scope.buffer_bbox.minLon, scope.buffer_bbox.maxLat - scope.buffer_bbox.minLat, 0.01)
      : 1
    return {
      longitude: center[0],
      latitude: center[1],
      // Keep the first frame inside the audit footprint. The minimum zoom is
      // deliberate: without a supplied buffer there must still be no national
      // detection-browser state.
      zoom: Math.max(7, Math.min(13, 8 - Math.log2(span))),
    }
  }, [center, scope.buffer_bbox])

  function handleMapClick(event: MapLayerMouseEvent) {
    const feature = event.features?.[0]
    const id = feature?.properties?.id as string | undefined
    setFocusedEventId(id)
  }

  return <div className="scoped-map-print-root relative flex h-full w-full flex-col bg-bg text-text">
    <header className="scoped-map-print-hide flex h-14 shrink-0 items-center justify-between border-b border-border-strong bg-panel px-5">
      <div><div className="text-sm font-semibold tracking-wide">Environmental Assurance Console</div><div className="text-[10px] uppercase tracking-[0.2em] text-text-faint">Scoped FireEvent review · {scope.review_start} → {scope.review_end}</div></div>
      <div className="flex items-center gap-2"><Button onClick={onOpenScope}>EDIT SCOPE</Button></div>
    </header>
    <div className="scoped-map-print-shell relative flex min-h-0 flex-1">
      <div className="scoped-map-print-hide relative min-w-0 flex-1">
        <Map
          // Carto's vector dark-matter style with land/water recoloured to this
          // app's palette (land INDONESIA_FILL_COLOR #364527, water --color-bg
          // #0a0d12 -- see layerColors.ts / index.css). A static JSON asset can't
          // import those constants, so if either changes, update
          // scoped-map-style.json's "background"/"landcover"/"landuse"/"park_*"
          // and "water" paint colours to match by hand.
          mapStyle="/scoped-map-style.json"
          transformRequest={transformRequest}
          initialViewState={initialViewState}
          minZoom={5}
          maxZoom={15}
          maxBounds={scope.buffer_bbox ? [scope.buffer_bbox.minLon, scope.buffer_bbox.minLat, scope.buffer_bbox.maxLon, scope.buffer_bbox.maxLat] : undefined}
          interactiveLayerIds={['audit-event-points']}
          onClick={handleMapClick}
          cursor="default"
          onLoad={(event) => {
            // Keep scoped investigation maps in the same visual language as
            // Audit Landing: readable green land and clearly blue water.
            const map = event.target
            if (map.getLayer('background')) map.setPaintProperty('background', 'background-color', '#183f37')
            if (map.getLayer('landcover')) map.setPaintProperty('landcover', 'fill-color', '#347657')
            if (map.getLayer('landuse')) map.setPaintProperty('landuse', 'fill-color', '#285f49')
            if (map.getLayer('park_national_park')) map.setPaintProperty('park_national_park', 'fill-color', '#54a34f')
            if (map.getLayer('park_nature_reserve')) map.setPaintProperty('park_nature_reserve', 'fill-color', '#438a4d')
            if (map.getLayer('water')) map.setPaintProperty('water', 'fill-color', '#010f2b')
            if (map.getLayer('waterway')) map.setPaintProperty('waterway', 'line-color', '#20b7d7')
            event.target.jumpTo({ center, zoom: initialViewState.zoom })
          }}
          onIdle={(event) => {
            if (positionedForAudit.current === scope.audit_id) return
            positionedForAudit.current = scope.audit_id
            event.target.jumpTo({ center, zoom: initialViewState.zoom })
          }}
        >
          {buffer && <Source id="audit-context-buffer" type="geojson" data={buffer}><Layer id="audit-context-buffer-line" type="line" paint={{ 'line-color': AUDIT_SCOPE_BUFFER_COLOR, 'line-width': 1.5, 'line-dasharray': [2, 2], 'line-opacity': 0.9 }} /></Source>}
          {boundary && <Source id="audit-scope-boundary" type="geojson" data={boundary}><Layer id="audit-scope-fill" type="fill" paint={{ 'fill-color': AUDIT_SCOPE_BOUNDARY_COLOR, 'fill-opacity': 0.08 }} /><Layer id="audit-scope-line" type="line" paint={{ 'line-color': AUDIT_SCOPE_BOUNDARY_COLOR, 'line-width': 2 }} /></Source>}
          {showPeatland && <Source id="peatland-context" type="geojson" data="/peatland-indonesia.geojson"><Layer id="peatland-context-fill" type="fill" paint={{ 'fill-color': '#a855f7', 'fill-opacity': 0.22 }} /><Layer id="peatland-context-line" type="line" paint={{ 'line-color': '#c084fc', 'line-width': 0.7, 'line-opacity': 0.7 }} /></Source>}
          {edges.features.length > 0 && <Source id="fireevent-graph" type="geojson" data={edges}><Layer id="fireevent-graph-line" type="line" paint={{
            'line-color': GRAPH_LINE_COLOR,
            // Use the deterministic relationship state already supplied by
            // FireEventGraph. Compatibility is more legible; weaker or
            // unresolved candidates recede without inventing a UI score.
            'line-width': ['match', ['get', 'state'], 'PROPAGATION_COMPATIBLE', 2.2, 'PROPAGATION_WEAK', 1.5, ['match', ['get', 'origin'], 'focus', 1.5, 1]],
            'line-opacity': ['match', ['get', 'state'], 'PROPAGATION_COMPATIBLE', ['match', ['get', 'origin'], 'focus', 0.9, 0.65], 'PROPAGATION_WEAK', ['match', ['get', 'origin'], 'focus', 0.55, 0.35], 0.25],
            'line-dasharray': [1, 1],
          }} layout={{ 'line-cap': 'round' }} /></Source>}
          {/* A focused event's graph can carry a dozen-plus candidate edges at
              once (see MAX_ENVELOPE_REACH_KM in enrich_fire_spread_audit_events.py);
              translucent fills from that many overlapping polygons compound
              well past any single one's own opacity (N layers at opacity o
              approach solid coverage as 1-(1-o)^N), which is what actually
              turned the whole viewport red, not any one envelope's size.
              Kept faint enough that stacking a dozen still reads as texture,
              not a solid wash; the dashed outline (not subject to the same
              compounding) carries the actual boundary. */}
          {showSpreadEnvelopes && envelopes.features.length > 0 && <Source id="fireevent-spread-envelope" type="geojson" data={envelopes}><Layer id="fireevent-spread-envelope-fill" type="fill" paint={{ 'fill-color': SURFACE_FIRE_ENVELOPE_COLOR, 'fill-opacity': 0.05 }} /><Layer id="fireevent-spread-envelope-line" type="line" paint={{ 'line-color': SURFACE_FIRE_ENVELOPE_COLOR, 'line-width': 1.5, 'line-dasharray': [3, 3] }} /></Source>}
          {showObservations && observations.features.length > 0 && <Source id="fireevent-observations" type="geojson" data={observations}><Layer id="fireevent-observations-points" type="circle" paint={{ 'circle-radius': 3, 'circle-color': OBSERVATION_COLOR, 'circle-opacity': 0.85, 'circle-stroke-color': '#0a0d12', 'circle-stroke-width': 1 }} /></Source>}
          <Source id="audit-events" type="geojson" data={points}>
            <Layer
              id="audit-event-points"
              type="circle"
              paint={{
                'circle-radius': ['match', ['get', 'focus'], 'SELECTED', 8, 'EXTERNAL_CONTEXT', 6, 5],
                'circle-color': ['match', ['get', 'state'], 'LIKELY_FIRE', AUDIT_EVENT_COLORS.LIKELY_FIRE, 'LIKELY_NON_FIRE', AUDIT_EVENT_COLORS.LIKELY_NON_FIRE, AUDIT_EVENT_COLORS.AMBIGUOUS],
                'circle-opacity': 0.9,
                'circle-stroke-color': ['match', ['get', 'focus'], 'SELECTED', GRAPH_LINE_COLOR, AUDIT_SCOPE_BOUNDARY_COLOR],
                'circle-stroke-width': ['match', ['get', 'focus'], 'SELECTED', 2.5, 'EXTERNAL_CONTEXT', 1.5, 0.75],
              }}
            />
          </Source>
        </Map>
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-[1] mix-blend-screen transition-opacity duration-[60000ms]"
          style={{ background: 'radial-gradient(ellipse at 14% 6%, rgba(42, 200, 255, 0.33), transparent 43%), radial-gradient(ellipse at 86% 84%, rgba(255, 166, 52, 0.18), transparent 45%), radial-gradient(ellipse at 45% 20%, transparent 18%, rgba(1, 13, 30, 0.72) 100%)', opacity: 0.82 - light.daylight * 0.6 }}
        />
      </div>
      <aside className="scoped-map-print-hide flex w-80 shrink-0 flex-col overflow-y-auto border-l border-border-strong bg-panel">
        <div className="border-b border-border-strong p-4">
          <div className="text-sm uppercase tracking-[0.16em] text-accent">Audit scope map</div>
          <h1 className="mt-1 text-base font-semibold">FireEvents in scope + context</h1>
          <p className="mt-2 text-sm leading-5 text-text-muted">Review scoped FireEvents and optional peat context.</p>
          <div className="mt-3 rounded border border-border bg-bg p-2.5 text-sm"><div className="text-text-faint">EVENTS SHOWN</div><div className="mt-1 text-xl font-semibold text-accent">{loading ? '…' : visibleEvents.length.toLocaleString()}</div></div>
          <div className="mt-3 rounded border border-border bg-bg p-3" aria-label="Temporal observation scrubber">
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.12em] text-text-faint"><span>OBSERVATION DAY</span><span className="text-accent">{activeDay ?? 'ALL DAYS'}</span></div>
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              <button type="button" aria-pressed={activeDay === null} onClick={() => setSelectedDay(null)} className={`rounded border px-2 py-1.5 text-xs font-semibold ${activeDay === null ? 'border-accent bg-accent/15 text-accent' : 'border-border-strong text-text-muted'}`}>ALL DAYS</button>
              {days.map((day) => <button key={day} type="button" aria-label={`Show observations for ${day}`} aria-pressed={activeDay === day} onClick={() => setSelectedDay(day)} className={`rounded border px-2 py-1.5 text-xs font-semibold ${activeDay === day ? 'border-accent bg-accent/15 text-accent' : 'border-border-strong text-text-muted'}`}>{day.slice(8)}</button>)}
            </div>
            <p className="mt-2 text-xs leading-4 text-text-faint">FIRMS observations for the selected UTC day. Event points remain when their detection window overlaps.</p>
          </div>
          <p className="mt-3 text-xs leading-5 text-text-faint">Peat is environmental context, not cause; compare it with event evidence.</p>
          {taggedEdges.length > 0 && <p className="mt-2 text-xs leading-5 text-text-faint">Lines are limited to {SCOPED_MAP_RELATIONSHIP_DISTANCE_KM} km. <span className="text-accent">Bright</span> lines are stronger candidates for the open FireEvent; weaker or unresolved links recede. <span className="opacity-60">Faint</span> lines belong to other FireEvents selected in the Fire Register.</p>}
          {envelopes.features.length > 0 && <p className="mt-2 text-xs leading-5 text-text-faint">Dashed outline: first-order wind-oriented surface-spread compatibility estimate — not a validated forecast or claim about what happened.</p>}
          {error && <div role="alert" className="mt-3 rounded border border-status-urgent/40 bg-status-urgent/10 p-2 text-sm text-red-200">{error}</div>}
          {selectionGraphError && <div role="alert" className="mt-3 rounded border border-status-urgent/40 bg-status-urgent/10 p-2 text-sm text-red-200">{selectionGraphError}</div>}
          {loading && <div role="status" className="mt-3 text-sm text-text-muted">Loading real audit FireEvents…</div>}
          {!loading && !error && events.length === 0 && <div className="mt-3 text-sm text-text-muted">No events intersect this audit scope and buffer.</div>}
          <Button variant="primary" className="mt-4 w-full" onClick={onOpenRegister}>OPEN FIRE REGISTER</Button>
          <Button className="mt-2 w-full" onClick={() => setShowPeatland((shown) => !shown)}>{showPeatland ? 'HIDE PEATLAND' : 'SHOW PEATLAND'}</Button>
          {envelopes.features.length > 0 && <Button className="mt-2 w-full" onClick={() => setShowSpreadEnvelopes((shown) => !shown)}>{showSpreadEnvelopes ? 'HIDE SPREAD ENVELOPES' : 'SHOW SPREAD ENVELOPES'}</Button>}
        </div>
        <div className="p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm uppercase tracking-[0.16em] text-accent">Investigation candidates</div>
            <span className="rounded border border-border px-1.5 py-0.5 text-xs text-text-muted">{packed.length} IN REPORT</span>
          </div>
          <p className="mt-2 text-sm leading-5 text-text-muted">Select scoped FireEvents for the audit report.</p>
          {packError && <div role="alert" className="mt-2 rounded border border-status-urgent/40 bg-status-urgent/10 p-2 text-sm text-red-200">{packError}</div>}
          {!loading && events.length === 0 ? <p className="mt-3 text-sm text-text-faint">No scoped FireEvents are available to add.</p> : <ul className="mt-3 space-y-1.5">{events.map((event) => {
            const inReport = packed.includes(event.eventId)
            const selected = candidateIds.includes(event.eventId)
            return <li key={event.eventId}><button type="button" aria-label={`Select ${event.eventId} for audit report`} aria-pressed={selected} disabled={inReport} onClick={() => toggleCandidate(event.eventId)} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm transition-colors ${selected ? 'border-accent bg-accent/15 text-text' : 'border-border bg-bg text-text-muted hover:border-border-strong hover:bg-panel-raised'} ${inReport ? 'cursor-default opacity-70' : 'cursor-pointer'}`}><span className="min-w-0 flex-1 truncate font-mono">{event.eventId}</span><span className="shrink-0 text-xs text-text-faint">{inReport ? 'IN REPORT' : event.investigationPriority}</span></button></li>
          })}</ul>}
          <Button className="mt-3 w-full" disabled={!candidateIds.length} onClick={() => void addCandidatesToPack()}>{`ADD SELECTED TO REPORT (${candidateIds.length})`}</Button>
          <Button variant="primary" className="mt-3 w-full" onClick={onViewReport}>{`VIEW AUDIT REPORT (${packed.length})`}</Button>
        </div>
      </aside>
      {drawerEventId && (
        <EvidenceDrawer
          eventId={drawerEventId}
          loading={evidenceLoading}
          error={evidenceError || undefined}
          data={evidence}
          graph={focusGraph}
          graphError={focusGraphError || undefined}
          reviewStart={scope.review_start}
          reviewEnd={scope.review_end}
          showObservations={showObservations}
          onToggleObservations={() => setShowObservations((value) => !value)}
          observationCount={observations.features.length || undefined}
          onClose={() => setFocusedEventId(undefined)}
          onRetry={() => setEvidenceReloadToken((value) => value + 1)}
          analysis={analysis}
          analysisLoading={analysisLoading}
          analysisError={analysisError || undefined}
          onGenerateAnalysis={() => void generateAnalysis()}
        />
      )}
    </div>
  </div>
}
