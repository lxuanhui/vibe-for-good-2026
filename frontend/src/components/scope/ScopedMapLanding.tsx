import { useEffect, useMemo, useRef, useState } from 'react'
import { Layer, Map, Source, type MapLayerMouseEvent } from 'react-map-gl/maplibre'
import type { Feature, FeatureCollection, GeoJsonProperties, Geometry, LineString, Point } from 'geojson'
import type { AuditEventSummary, AuditScope, EventEvidenceResponse, InvestigationMap } from '../../api/types'
import { fetchAuditEventEvidence, fetchAuditRegister, fetchInvestigationMap } from '../../api/client'
import { useFirms } from '../../api/hooks'
import { AUDIT_EVENT_COLORS, AUDIT_SCOPE_BOUNDARY_COLOR, AUDIT_SCOPE_BUFFER_COLOR, LAYER_COLORS } from '../../lib/layerColors'
import { useAppStore } from '../../store/useAppStore'
import { Button } from '../ui/Button'
import { LayerControlPanel } from '../map/LayerControlPanel'
import { EvidenceDrawer } from '../audit/EvidenceDrawer'
import 'maplibre-gl/dist/maplibre-gl.css'

const GRAPH_LINE_COLOR = '#f97316'
const OBSERVATION_COLOR = '#fbbf24'

function observationPoints(evidence: EventEvidenceResponse | undefined): FeatureCollection<Point> {
  const observations = evidence?.event.triageDetail?.observations ?? []
  return {
    type: 'FeatureCollection',
    features: observations.map((obs) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [obs.lon, obs.lat] }, properties: { frp: obs.frp } })),
  }
}

// Merges the always-visible in-scope+buffer register with whatever a graph
// fetch pulled in as neighbours -- a related event can sit outside the
// buffer bbox and still be worth drawing (spec §13: relevant graph
// neighbours, not the whole regional archive).
function mapPoints(events: AuditEventSummary[], graph: InvestigationMap | undefined): FeatureCollection<Point> {
  // A plain object, not a Map instance -- `Map` in this file's scope is the
  // react-map-gl component import, and `new Map(...)` here would construct
  // that instead of the global collection type.
  const byId: Record<string, { lon: number; lat: number; state: string; focus: string }> = {}
  for (const event of events) {
    byId[event.eventId] = { lon: event.centroid.lon, lat: event.centroid.lat, state: event.triage.state, focus: '' }
  }
  for (const node of graph?.nodes ?? []) {
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

function graphEdges(graph: InvestigationMap | undefined): FeatureCollection<LineString> {
  if (!graph) return { type: 'FeatureCollection', features: [] }
  return {
    type: 'FeatureCollection',
    features: graph.edges.flatMap((edge) => {
      const from = graph.nodes.find((node) => node.eventId === edge.sourceEventId)
      const to = graph.nodes.find((node) => node.eventId === edge.targetEventId)
      return from && to
        ? [{ type: 'Feature' as const, geometry: { type: 'LineString' as const, coordinates: [[from.centroid.lon, from.centroid.lat], [to.centroid.lon, to.centroid.lat]] }, properties: {} }]
        : []
    }),
  }
}

function scopeFeature(geometry: unknown): Feature<Geometry> | null {
  return geometry ? { type: 'Feature', geometry: geometry as Geometry, properties: {} } : null
}

export function ScopedMapLanding({ scope, onOpenScope, onOpenRegister }: { scope: AuditScope; onOpenScope: () => void; onOpenRegister: () => void }) {
  const [events, setEvents] = useState<AuditEventSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const positionedForAudit = useRef('')
  const firmsVisible = useAppStore((state) => state.layerVisibility.firms)
  const staticFirms = useFirms(scope.review_start, firmsVisible)
  const boundary = useMemo(() => scopeFeature(scope.geometry), [scope.geometry])
  const buffer = useMemo(() => scopeFeature(scope.buffer_geometry), [scope.buffer_geometry])

  // Table multi-select ("INVESTIGATE ON MAP") hands off through this store
  // field rather than a prop -- App.tsx just flips viewMode, it does not
  // know about event selection. Seeded once per audit on arrival; further
  // focus changes come from clicking the map itself, not from the table
  // selection continuing to change underneath.
  const registerSelection = useAppStore((state) => state.registerSelection)
  const [focusEventIds, setFocusEventIds] = useState<string[]>([])
  const seededFocusForAudit = useRef('')
  useEffect(() => {
    if (seededFocusForAudit.current === scope.audit_id) return
    seededFocusForAudit.current = scope.audit_id
    if (registerSelection.length) setFocusEventIds(registerSelection)
  }, [scope.audit_id, registerSelection])

  const [graph, setGraph] = useState<InvestigationMap>()
  const [graphError, setGraphError] = useState('')
  useEffect(() => {
    if (!focusEventIds.length) { setGraph(undefined); setGraphError(''); return }
    let active = true
    setGraphError('')
    fetchInvestigationMap(scope.audit_id, focusEventIds)
      .then((result) => { if (active) setGraph(result) })
      .catch((reason) => { if (active) setGraphError(reason instanceof Error ? reason.message : 'Related FireEvents could not be loaded.') })
    return () => { active = false }
  }, [scope.audit_id, focusEventIds])

  // Owned here, not by EvidenceDrawer -- the same fetch also supplies the
  // "connecting FIRMS observations" map layer below, so one request serves
  // both the drawer and the map instead of each fetching it separately.
  const drawerEventId = focusEventIds.length === 1 ? focusEventIds[0] : undefined
  const [evidence, setEvidence] = useState<EventEvidenceResponse>()
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [evidenceError, setEvidenceError] = useState('')
  const [showObservations, setShowObservations] = useState(true)
  const [evidenceReloadToken, setEvidenceReloadToken] = useState(0)
  useEffect(() => {
    if (!drawerEventId) { setEvidence(undefined); setEvidenceError(''); return }
    setShowObservations(true)
    let active = true
    setEvidenceLoading(true)
    setEvidenceError('')
    fetchAuditEventEvidence(scope.audit_id, drawerEventId)
      .then((result) => { if (active) setEvidence(result) })
      .catch((reason) => { if (active) setEvidenceError(reason instanceof Error ? reason.message : 'Evidence could not be loaded.') })
      .finally(() => { if (active) setEvidenceLoading(false) })
    return () => { active = false }
  }, [scope.audit_id, drawerEventId, evidenceReloadToken])
  const observations = useMemo(() => observationPoints(evidence), [evidence])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    fetchAuditRegister(scope.audit_id, { since: scope.review_start, until: scope.review_end, bbox: scope.buffer_bbox ?? undefined })
      .then((result) => { if (active) setEvents(result.events) })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : 'FireEvents could not be loaded.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [scope.audit_id, scope.review_start, scope.review_end, scope.buffer_bbox])

  const points = useMemo(() => mapPoints(events, graph), [events, graph])
  const edges = useMemo(() => graphEdges(graph), [graph])
  const scopedFirms = useMemo(() => {
    if (!staticFirms || !scope.buffer_bbox) return null
    const { minLon, minLat, maxLon, maxLat } = scope.buffer_bbox
    const features = staticFirms.features.filter((feature) => {
      const geometry = feature.geometry as { type?: string; coordinates?: unknown }
      if (geometry.type !== 'Point' || !Array.isArray(geometry.coordinates)) return false
      const [lon, lat] = geometry.coordinates
      return typeof lon === 'number' && typeof lat === 'number' && lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat
    })
    return {
      ...staticFirms,
      features,
    } as unknown as FeatureCollection<Geometry, GeoJsonProperties>
  }, [scope.buffer_bbox, staticFirms])
  const center = useMemo<[number, number]>(() => scope.centroid ?? [116.25, -3.8], [scope.centroid])

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
    setFocusEventIds(id ? [id] : [])
  }

  return <div className="relative flex h-full w-full flex-col bg-bg text-text">
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-strong bg-panel px-5">
      <div><div className="text-sm font-semibold tracking-wide">Environmental Assurance Console</div><div className="text-[10px] uppercase tracking-[0.2em] text-text-faint">Scoped FireEvent review · {scope.review_start} → {scope.review_end}</div></div>
      <div className="flex items-center gap-2"><span className="rounded border border-status-good/50 px-2 py-1 text-[10px] uppercase tracking-wider text-status-good">Real derived events</span><Button onClick={onOpenScope}>EDIT SCOPE</Button></div>
    </header>
    <div className="relative flex min-h-0 flex-1">
      <div className="relative min-w-0 flex-1">
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
          {scopedFirms && <Source id="static-firms-archive" type="geojson" data={scopedFirms}><Layer id="static-firms-archive-points" type="circle" paint={{ 'circle-radius': 3, 'circle-color': LAYER_COLORS.firms, 'circle-opacity': 0.55 }} /></Source>}
          {edges.features.length > 0 && <Source id="fireevent-graph" type="geojson" data={edges}><Layer id="fireevent-graph-line" type="line" paint={{ 'line-color': GRAPH_LINE_COLOR, 'line-width': 2, 'line-dasharray': [1, 1] }} layout={{ 'line-cap': 'round' }} /></Source>}
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
      </div>
      <aside className="flex w-80 shrink-0 flex-col overflow-y-auto border-l border-border-strong bg-panel">
        <div className="border-b border-border-strong p-4">
          <div className="text-xs uppercase tracking-[0.16em] text-accent">Audit scope map</div>
          <h1 className="mt-1 text-sm font-semibold">FireEvents in scope + context</h1>
          <p className="mt-2 text-xs leading-5 text-text-muted">Only the private audit boundary and its {scope.context_buffer_km} km context buffer are framed. Geographic intersection is context, not responsibility.</p>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs"><div className="rounded border border-border bg-bg p-2"><div className="text-text-faint">EVENTS SHOWN</div><div className="mt-1 text-lg font-semibold text-accent">{loading ? '…' : events.length.toLocaleString()}</div></div><div className="rounded border border-border bg-bg p-2"><div className="text-text-faint">SOURCE</div><div className="mt-1 text-status-good">API artifact</div></div></div>
          <div className="mt-3 space-y-1 text-[11px] text-text-muted"><div><span className="mr-2 text-status-good">●</span>LIKELY_FIRE</div><div><span className="mr-2 text-status-moderate">●</span>AMBIGUOUS</div><div><span className="mr-2 text-text-muted">●</span>LIKELY_NON_FIRE</div><div className="mt-2"><span className="mr-2 text-accent">—</span>Audit boundary <span className="ml-2 text-status-moderate">- -</span> Context buffer</div>{edges.features.length > 0 && <div><span className="mr-2 text-[#f97316]">┄</span>Candidate relationship</div>}{showObservations && observations.features.length > 0 && <div><span className="mr-2 text-[#fbbf24]">●</span>Connecting FIRMS observations</div>}</div>
          <p className="mt-3 text-[10px] leading-4 text-text-faint">Click a FireEvent to open its evidence and draw any candidate relationships to nearby events. A candidate edge is a relationship for review, not a shared cause.</p>
          {error && <div role="alert" className="mt-3 rounded border border-status-urgent/40 bg-status-urgent/10 p-2 text-xs text-red-200">{error}</div>}
          {graphError && <div role="alert" className="mt-3 rounded border border-status-urgent/40 bg-status-urgent/10 p-2 text-xs text-red-200">{graphError}</div>}
          {loading && <div role="status" className="mt-3 text-xs text-text-muted">Loading real audit FireEvents…</div>}
          {!loading && !error && events.length === 0 && <div className="mt-3 text-xs text-text-muted">No events intersect this audit scope and buffer.</div>}
          <Button variant="primary" className="mt-4 w-full" onClick={onOpenRegister}>OPEN FIRE REGISTER</Button>
        </div>
        <div className="p-3"><LayerControlPanel scoped /></div>
      </aside>
      {drawerEventId && (
        <EvidenceDrawer
          eventId={drawerEventId}
          loading={evidenceLoading}
          error={evidenceError || undefined}
          data={evidence}
          graph={graph}
          graphError={graphError || undefined}
          reviewStart={scope.review_start}
          reviewEnd={scope.review_end}
          showObservations={showObservations}
          onToggleObservations={() => setShowObservations((value) => !value)}
          observationCount={observations.features.length || undefined}
          onClose={() => setFocusEventIds([])}
          onRetry={() => setEvidenceReloadToken((value) => value + 1)}
        />
      )}
    </div>
  </div>
}
