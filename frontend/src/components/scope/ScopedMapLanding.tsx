import { useEffect, useMemo, useRef, useState } from 'react'
import { Layer, Map, Source } from 'react-map-gl/maplibre'
import type { Feature, FeatureCollection, GeoJsonProperties, Geometry, Point } from 'geojson'
import type { AuditEventSummary, AuditScope } from '../../api/types'
import { fetchAuditRegister } from '../../api/client'
import { useFirms } from '../../api/hooks'
import { AUDIT_EVENT_COLORS, AUDIT_SCOPE_BOUNDARY_COLOR, AUDIT_SCOPE_BUFFER_COLOR, LAYER_COLORS } from '../../lib/layerColors'
import { useAppStore } from '../../store/useAppStore'
import { Button } from '../ui/Button'
import { LayerControlPanel } from '../map/LayerControlPanel'
import 'maplibre-gl/dist/maplibre-gl.css'

export const DEMO_SCOPE: AuditScope = {
  audit_id: 'demo-2019-haze',
  scope_id: 'demo-scope',
  review_start: '2019-09-01',
  review_end: '2019-09-05',
  context_buffer_km: 25,
  status: 'HISTORY_BUILD_READY',
  bbox: { minLon: 116.0, minLat: -4.05, maxLon: 116.5, maxLat: -3.55 },
  centroid: [116.25, -3.8],
  buffer_bbox: { minLon: 115.75, minLat: -4.28, maxLon: 116.75, maxLat: -3.32 },
  buffer_geometry: { type: 'Polygon', coordinates: [[[115.75, -4.28], [116.75, -4.28], [116.75, -3.32], [115.75, -3.32], [115.75, -4.28]]] },
  geometry: { type: 'Polygon', coordinates: [[[116.0, -4.05], [116.5, -4.05], [116.5, -3.55], [116.0, -3.55], [116.0, -4.05]]] },
  historyBuild: { duration_ms: 0, dataset_mode: 'cached-real-artifact' },
}

function eventPoints(events: AuditEventSummary[]): FeatureCollection<Point> {
  return { type: 'FeatureCollection', features: events.map((event) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [event.centroid.lon, event.centroid.lat] }, properties: { state: event.triage.state, id: event.eventId } })) }
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

  const points = useMemo(() => eventPoints(events), [events])
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

  return <div className="relative h-full w-full bg-bg">
    <Map
      mapStyle="/scoped-map-style.json"
      initialViewState={initialViewState}
      minZoom={5}
      maxZoom={15}
      maxBounds={scope.buffer_bbox ? [scope.buffer_bbox.minLon, scope.buffer_bbox.minLat, scope.buffer_bbox.maxLon, scope.buffer_bbox.maxLat] : undefined}
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
      <Source id="audit-events" type="geojson" data={points}><Layer id="audit-event-points" type="circle" paint={{ 'circle-radius': 5, 'circle-color': ['match', ['get', 'state'], 'LIKELY_FIRE', AUDIT_EVENT_COLORS.LIKELY_FIRE, 'LIKELY_NON_FIRE', AUDIT_EVENT_COLORS.LIKELY_NON_FIRE, AUDIT_EVENT_COLORS.AMBIGUOUS], 'circle-opacity': 0.9, 'circle-stroke-color': AUDIT_SCOPE_BOUNDARY_COLOR, 'circle-stroke-width': 0.75 }} /></Source>
    </Map>
    <div className="pointer-events-none absolute top-20 right-4"><LayerControlPanel scoped /></div>
    <header className="absolute top-0 right-0 left-0 flex items-center justify-between border-b border-border-strong bg-panel/90 px-5 py-3 backdrop-blur">
      <div><div className="text-sm font-semibold tracking-wide">Environmental Assurance Console</div><div className="text-[10px] uppercase tracking-[0.2em] text-text-faint">Scoped FireEvent review · {scope.review_start} → {scope.review_end}</div></div>
      <div className="flex items-center gap-2"><span className="rounded border border-status-good/50 px-2 py-1 text-[10px] uppercase tracking-wider text-status-good">Real derived events</span><Button onClick={onOpenScope}>EDIT SCOPE</Button></div>
    </header>
    <aside className="absolute top-20 left-4 w-72 rounded-lg border border-border-strong bg-panel/95 p-4 shadow-2xl backdrop-blur">
      <div className="text-xs uppercase tracking-[0.16em] text-accent">Audit scope map</div>
      <h1 className="mt-2 text-lg font-semibold">FireEvents in scope + context</h1>
      <p className="mt-2 text-xs leading-5 text-text-muted">Only the private audit boundary and its {scope.context_buffer_km} km context buffer are framed. Geographic intersection is context, not responsibility.</p>
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs"><div className="rounded border border-border bg-bg p-2"><div className="text-text-faint">EVENTS SHOWN</div><div className="mt-1 text-lg font-semibold text-accent">{loading ? '…' : events.length.toLocaleString()}</div></div><div className="rounded border border-border bg-bg p-2"><div className="text-text-faint">SOURCE</div><div className="mt-1 text-status-good">API artifact</div></div></div>
      <div className="mt-4 space-y-1 text-[11px] text-text-muted"><div><span className="mr-2 text-status-good">●</span>LIKELY_FIRE</div><div><span className="mr-2 text-status-moderate">●</span>AMBIGUOUS</div><div><span className="mr-2 text-text-muted">●</span>LIKELY_NON_FIRE</div><div className="mt-2"><span className="mr-2 text-accent">—</span>Audit boundary <span className="ml-2 text-status-moderate">- -</span> Context buffer</div></div>
      {error && <div role="alert" className="mt-3 rounded border border-status-urgent/40 bg-status-urgent/10 p-2 text-xs text-red-200">{error}</div>}
      {loading && <div role="status" className="mt-3 text-xs text-text-muted">Loading real audit FireEvents…</div>}
      {!loading && !error && events.length === 0 && <div className="mt-3 text-xs text-text-muted">No events intersect this audit scope and buffer.</div>}
      <Button variant="primary" className="mt-4 w-full" onClick={onOpenRegister}>OPEN FIRE REGISTER</Button>
    </aside>
  </div>
}
