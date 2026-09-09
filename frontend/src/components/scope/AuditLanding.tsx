import { useEffect, useMemo, useState } from 'react'
import { Layer, Map, Source } from 'react-map-gl/maplibre'
import type { FeatureCollection, Point } from 'geojson'
import indonesiaBoundary from '../../assets/indonesia-province-simple.json'
import { Button } from '../ui/Button'
import 'maplibre-gl/dist/maplibre-gl.css'

const SEA_BOUNDS = { west: 90, south: -12, east: 145, north: 25 }
const FIRMS_REFRESH_MS = 15 * 60 * 1000
const seaStyle = { version: 8 as const, sources: {}, layers: [{ id: 'ocean', type: 'background' as const, paint: { 'background-color': '#0a3157' } }] }
type LoadingState = 'loading' | 'ready' | 'unavailable'

function emptyHotspots(): FeatureCollection<Point> { return { type: 'FeatureCollection', features: [] } }

function parseFirmsCsv(csv: string): FeatureCollection<Point> {
  const [header, ...rows] = csv.trim().split(/\r?\n/)
  if (!header) return emptyHotspots()
  const fields = header.split(',')
  const lat = fields.indexOf('latitude'), lon = fields.indexOf('longitude'), frp = fields.indexOf('frp'), confidence = fields.indexOf('confidence')
  if (lat < 0 || lon < 0) return emptyHotspots()
  return { type: 'FeatureCollection', features: rows.flatMap((row) => {
    const values = row.split(','); const latitude = Number(values[lat]); const longitude = Number(values[lon])
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || longitude < SEA_BOUNDS.west || longitude > SEA_BOUNDS.east || latitude < SEA_BOUNDS.south || latitude > SEA_BOUNDS.north) return []
    return [{ type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [longitude, latitude] }, properties: { frp: Number(values[frp]) || 0, confidence: values[confidence] ?? 'unknown' } }]
  }) }
}

/** Regional orientation with near-real-time hotspots; never an audit register. */
export function AuditLanding({ onStartAudit, onOpenContext }: { onStartAudit: () => void; onOpenContext: () => void }) {
  const [hotspots, setHotspots] = useState<FeatureCollection<Point>>(emptyHotspots)
  const [state, setState] = useState<LoadingState>('loading')
  const firmsKey = import.meta.env.VITE_FIRMS_MAP_KEY as string | undefined

  useEffect(() => {
    if (!firmsKey) { setState('unavailable'); return }
    let active = true
    const load = async () => {
      try {
        // FIRMS requires a free MAP_KEY. The one-day NRT export is filtered
        // to SEA here, keeping this an orientation view rather than a register.
        const response = await fetch(`https://firms.modaps.eosdis.nasa.gov/api/area/csv/${encodeURIComponent(firmsKey)}/VIIRS_SNPP_NRT/world/1`)
        if (!response.ok) throw new Error(`FIRMS returned ${response.status}`)
        const next = parseFirmsCsv(await response.text())
        if (active) { setHotspots(next); setState('ready') }
      } catch { if (active) setState('unavailable') }
    }
    void load()
    const timer = window.setInterval(() => void load(), FIRMS_REFRESH_MS)
    return () => { active = false; window.clearInterval(timer) }
  }, [firmsKey])

  const status = useMemo(() => state === 'loading' ? 'Loading current FIRMS detections…' : state === 'ready' ? `${hotspots.features.length.toLocaleString()} SEA detections · last 24 hours` : firmsKey ? 'Current FIRMS feed unavailable' : 'Configure VITE_FIRMS_MAP_KEY for current FIRMS', [firmsKey, hotspots.features.length, state])

  return <main className="relative h-screen overflow-hidden bg-[#0a3157] text-text">
    <Map mapStyle={seaStyle} initialViewState={{ longitude: 117.5, latitude: 4, zoom: 3.2 }} minZoom={2.7} maxZoom={9} maxBounds={[SEA_BOUNDS.west, SEA_BOUNDS.south, SEA_BOUNDS.east, SEA_BOUNDS.north]} attributionControl={false}>
      <Source id="sea-land" type="geojson" data={indonesiaBoundary as unknown as FeatureCollection}>
        <Layer id="sea-land-fill" type="fill" paint={{ 'fill-color': '#2f6b48', 'fill-opacity': 1 }} />
        <Layer id="sea-land-line" type="line" paint={{ 'line-color': '#74b88a', 'line-width': 0.8, 'line-opacity': 0.65 }} />
      </Source>
      <Source id="latest-firms" type="geojson" data={hotspots}>
        <Layer id="firms-hotspot-glow" type="circle" paint={{ 'circle-radius': ['interpolate', ['linear'], ['get', 'frp'], 0, 8, 20, 16, 80, 28], 'circle-color': '#ff3b1f', 'circle-opacity': 0.12, 'circle-blur': 0.8 }} />
        <Layer id="firms-hotspot" type="circle" paint={{ 'circle-radius': ['interpolate', ['linear'], ['get', 'frp'], 0, 2.5, 20, 4.5, 80, 7], 'circle-color': '#ff5a36', 'circle-opacity': 0.84, 'circle-stroke-color': '#ffd166', 'circle-stroke-width': 0.7 }} />
        <Layer id="firms-hotspot-core" type="circle" paint={{ 'circle-radius': 1.2, 'circle-color': '#fff4ca', 'circle-opacity': 0.95 }} />
      </Source>
    </Map>
    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_62%_48%,transparent_0%,rgba(3,13,28,0.34)_78%)]" />
    <section className="absolute left-5 top-5 z-10 max-w-md rounded-xl border border-white/15 bg-[#071629]/92 p-5 shadow-2xl backdrop-blur">
      <p className="text-xs uppercase tracking-[0.2em] text-[#ffd166]">Southeast Asia · live satellite watch</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Heat signatures, before the audit begins.</h1>
      <p className="mt-3 text-sm leading-6 text-slate-300">Near-real-time NASA FIRMS detections make overlapping hotspots visible across the region. They are satellite observations, not FireEvents, causes, or allegations.</p>
      <div className="mt-4 border-l-2 border-[#ff5a36] pl-3 text-xs text-[#ffd9c9]">{status}</div>
      <Button variant="primary" className="mt-5 w-full py-3 uppercase tracking-[0.14em]" onClick={onStartAudit}>START AUDIT</Button>
      <button type="button" onClick={onOpenContext} className="mt-3 text-[11px] text-slate-400 underline underline-offset-2 hover:text-white">About this view</button>
    </section>
  </main>
}
