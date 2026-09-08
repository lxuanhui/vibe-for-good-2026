import { useEffect, useMemo, useState } from 'react'
import { Map, Marker, Source, Layer } from 'react-map-gl/maplibre'
import type { FeatureCollection, Point, LineString, Geometry } from 'geojson'
import type { AuditEventSummary, AuditScope, InvestigationMap } from '../../api/types'
import { fetchAuditRegister, fetchInvestigationMap } from '../../api/client'
import { useAppStore } from '../../store/useAppStore'
import { Button } from '../ui/Button'
import 'maplibre-gl/dist/maplibre-gl.css'
import { EvidenceDrawer } from './EvidenceDrawer'

const RELATION_COLORS = { INSIDE_SCOPE: '#22d3ee', BOUNDARY_INTERSECTING: '#eab308', EXTERNAL_CONTEXT: '#a78bfa' } as const

function eventPoint(event: { centroid: { lat: number; lon: number } }, properties: Record<string, string | number | boolean>): GeoJSON.Feature<Point> {
  return { type: 'Feature', geometry: { type: 'Point', coordinates: [event.centroid.lon, event.centroid.lat] }, properties }
}

function eventRows(events: AuditEventSummary[], selected: string[], toggle: (id: string) => void) {
  return events.map((event) => (
    <tr key={event.eventId} className="border-b border-border/60 hover:bg-panel-raised">
      <td className="px-3 py-2"><input aria-label={`Select ${event.eventId}`} type="checkbox" checked={selected.includes(event.eventId)} onChange={() => toggle(event.eventId)} /></td>
      <td className="px-3 py-2 font-mono">{event.eventId}</td>
      <td className="px-3 py-2 text-text-muted">{event.firstDetection.slice(0, 10)}</td>
      <td className="px-3 py-2 text-right">{event.observationCount}</td>
      <td className="px-3 py-2 text-text-muted">{event.triage.state}</td>
      <td className="px-3 py-2 text-right">{event.maxFrp?.toFixed(1) ?? '—'}</td>
    </tr>
  ))
}

function InvestigationMapView({ investigation, scope, onBack }: { investigation: InvestigationMap; scope: AuditScope; onBack: () => void }) {
  const [drawerEventId, setDrawerEventId] = useState<string | null>(null)
  const nodes = investigation.nodes
  const points: FeatureCollection<Point> = { type: 'FeatureCollection', features: nodes.map((node) => eventPoint(node, { id: node.eventId, role: node.mapRole, relation: node.scopeRelation })) }
  const edges: FeatureCollection<LineString> = {
    type: 'FeatureCollection',
    features: investigation.edges.flatMap((edge) => {
      const from = nodes.find((node) => node.eventId === edge.sourceEventId)
      const to = nodes.find((node) => node.eventId === edge.targetEventId)
      return from && to ? [{ type: 'Feature', geometry: { type: 'LineString', coordinates: [[from.centroid.lon, from.centroid.lat], [to.centroid.lon, to.centroid.lat]] }, properties: {} }] : []
    }),
  }
  const boundary = scope.geometry as Geometry | undefined
  return <div className="relative h-full min-h-[520px]">
    <Map mapStyle="/blank-style.json" initialViewState={{ longitude: scope.centroid?.[0] ?? 113.9, latitude: scope.centroid?.[1] ?? -1.5, zoom: 7 }} minZoom={3} maxZoom={14}>
      {boundary && <Source id="audit-boundary" type="geojson" data={{ type: 'Feature', geometry: boundary, properties: {} }}><Layer id="audit-boundary-fill" type="fill" paint={{ 'fill-color': '#22d3ee', 'fill-opacity': 0.1 }} /><Layer id="audit-boundary-line" type="line" paint={{ 'line-color': '#22d3ee', 'line-width': 2 }} /></Source>}
      {scope.buffer_geometry && <Source id="audit-buffer" type="geojson" data={{ type: 'Feature', geometry: scope.buffer_geometry, properties: {} }}><Layer id="audit-buffer-line" type="line" paint={{ 'line-color': '#eab308', 'line-width': 1, 'line-dasharray': [2, 2] }} /></Source>}
      <Source id="graph" type="geojson" data={edges}><Layer id="graph-lines" type="line" paint={{ 'line-color': '#f97316', 'line-width': 2, 'line-dasharray': [1, 1] }} /></Source>
      <Source id="events" type="geojson" data={points}><Layer id="event-points" type="circle" paint={{ 'circle-radius': ['case', ['==', ['get', 'role'], 'SELECTED'], 9, 5], 'circle-color': ['match', ['get', 'relation'], 'INSIDE_SCOPE', RELATION_COLORS.INSIDE_SCOPE, 'BOUNDARY_INTERSECTING', RELATION_COLORS.BOUNDARY_INTERSECTING, RELATION_COLORS.EXTERNAL_CONTEXT], 'circle-stroke-color': '#10151d', 'circle-stroke-width': 2 }} /></Source>
      {nodes.map((node) => <Marker key={node.eventId} longitude={node.centroid.lon} latitude={node.centroid.lat} onClick={(event) => { event.originalEvent.stopPropagation(); setDrawerEventId(node.eventId) }}><button aria-label={`Open evidence for ${node.eventId}`} className="h-5 w-5 rounded-full border-2 border-bg bg-accent shadow-lg" /></Marker>)}
    </Map>
    <div className="absolute top-3 left-3 rounded-lg border border-border-strong bg-panel/95 p-3 text-xs shadow-lg">
      <div className="mb-2 font-semibold">Spatial investigation</div>
      <div className="space-y-1 text-text-muted"><div><span className="mr-2 text-accent">●</span>INSIDE_SCOPE</div><div><span className="mr-2 text-status-moderate">●</span>BOUNDARY_INTERSECTING</div><div><span className="mr-2 text-purple-400">●</span>EXTERNAL_CONTEXT</div></div>
      <p className="mt-2 max-w-[230px] text-[10px] leading-4 text-text-faint">External-context events inform interpretation; they are not audit subjects. Geographic intersection is context, not responsibility.</p>
      <Button className="mt-3 w-full" onClick={onBack}>RETURN TO REGISTER</Button>
    </div>
    {drawerEventId && <EvidenceDrawer auditId={investigation.auditId} eventId={drawerEventId} onClose={() => setDrawerEventId(null)} />}
  </div>
}

export function HistoricalInvestigation({ scope }: { scope: AuditScope }) {
  const viewMode = useAppStore((s) => s.viewMode)
  const setViewMode = useAppStore((s) => s.setViewMode)
  const selection = useAppStore((s) => s.registerSelection)
  const toggleSelection = useAppStore((s) => s.toggleRegisterSelection)
  const [events, setEvents] = useState<AuditEventSummary[]>([])
  const [investigation, setInvestigation] = useState<InvestigationMap | null>(null)
  const [error, setError] = useState('')

  useEffect(() => { fetchAuditRegister(scope.audit_id, { since: scope.review_start, until: scope.review_end }).then(setEvents).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Register could not be loaded.')) }, [scope.audit_id, scope.review_start, scope.review_end])
  const selectedEvents = useMemo(() => events.filter((event) => selection.includes(event.eventId)), [events, selection])

  async function investigate() {
    setError('')
    try { setInvestigation(await fetchInvestigationMap(scope.audit_id, selection)); setViewMode('map') } catch (reason) { setError(reason instanceof Error ? reason.message : 'Map handoff failed.') }
  }

  if (viewMode === 'map' && investigation) return <InvestigationMapView investigation={investigation} scope={scope} onBack={() => setViewMode('table')} />
  return <div className="flex h-full flex-col bg-bg text-text">
    <div className="flex shrink-0 items-center justify-between border-b border-border-strong bg-panel px-5 py-3"><div><div className="text-sm font-semibold">Historical Fire Register</div><div className="text-xs text-text-muted">{events.length.toLocaleString()} FireEvents · {scope.review_start} → {scope.review_end} · {scope.context_buffer_km} km context buffer</div></div><Button variant="primary" disabled={!selection.length} onClick={() => void investigate()}>INVESTIGATE ON MAP ({selection.length})</Button></div>
    {error && <div role="alert" className="border-b border-status-urgent/40 bg-status-urgent/10 px-5 py-2 text-xs text-red-200">{error}</div>}
    <div className="flex-1 overflow-auto"><table className="w-full border-collapse text-xs"><thead className="sticky top-0 bg-panel"><tr className="border-b border-border"><th className="px-3 py-2 text-left">Select</th><th className="px-3 py-2 text-left">FireEvent ID</th><th className="px-3 py-2 text-left">First detected</th><th className="px-3 py-2 text-right">Observations</th><th className="px-3 py-2 text-left">Stage-1 state</th><th className="px-3 py-2 text-right">Max FRP</th></tr></thead><tbody>{eventRows(events, selection, toggleSelection)}</tbody></table></div>
    {selectedEvents.length > 0 && <div className="shrink-0 border-t border-border bg-panel px-5 py-2 text-xs text-text-muted">Selected FireEvents remain selected when you return from the map.</div>}
  </div>
}
