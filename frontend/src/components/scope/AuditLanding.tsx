import { useEffect, useMemo, useState } from 'react'
import { Layer, Map, Source } from 'react-map-gl/maplibre'
import type { FeatureCollection, Point } from 'geojson'
import { Button } from '../ui/Button'
import 'maplibre-gl/dist/maplibre-gl.css'

type FirmsProperties = { confidence: string; frp: number; ageHours: number }

const SEA_BOUNDS: [number, number, number, number] = [90, -12, 145, 25]
const FIRMS_REFRESH_MS = 15 * 60 * 1000
const CLOCK_REFRESH_MS = 60 * 1000

function emptyHotspots(): FeatureCollection<Point, FirmsProperties> {
  return { type: 'FeatureCollection', features: [] }
}

function readCsv(value: string): FeatureCollection<Point, FirmsProperties> {
  const [headerLine, ...rows] = value.trim().split(/\r?\n/)
  if (!headerLine) return emptyHotspots()
  const columns = headerLine.split(',').map((column) => column.trim())
  const index = (name: string) => columns.indexOf(name)
  const latitude = index('latitude')
  const longitude = index('longitude')
  const frp = index('frp')
  const confidence = index('confidence')
  const acquisitionDate = index('acq_date')
  const acquisitionTime = index('acq_time')
  if (latitude < 0 || longitude < 0) return emptyHotspots()

  const now = Date.now()
  return {
    type: 'FeatureCollection',
    features: rows.flatMap((row) => {
      const cells = row.split(',')
      const lat = Number(cells[latitude])
      const lon = Number(cells[longitude])
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || lon < SEA_BOUNDS[0] || lon > SEA_BOUNDS[2] || lat < SEA_BOUNDS[1] || lat > SEA_BOUNDS[3]) return []
      const date = cells[acquisitionDate]
      const time = cells[acquisitionTime]?.padStart(4, '0')
      const acquiredAt = date && time ? Date.parse(`${date}T${time.slice(0, 2)}:${time.slice(2, 4)}:00Z`) : Number.NaN
      const ageHours = Number.isFinite(acquiredAt) ? Math.max(0, (now - acquiredAt) / 3_600_000) : 24
      return [{ type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [lon, lat] }, properties: { confidence: cells[confidence] ?? 'unknown', frp: Number(cells[frp]) || 0, ageHours } }]
    }),
  }
}

function southeastAsiaLight(date: Date) {
  // UTC+8 is a useful regional midpoint. This is visual orientation only.
  const localHour = (date.getUTCHours() + date.getUTCMinutes() / 60 + 8) % 24
  const daylight = Math.max(0, Math.sin(((localHour - 6) / 12) * Math.PI))
  return { daylight, label: daylight > 0.15 ? 'DAYLIGHT' : 'NIGHT' }
}

/** A separate regional live context layer; no unscoped FireEvents are rendered. */
export function AuditLanding({ onStartAudit, onOpenContext }: { onStartAudit: () => void; onOpenContext: () => void }) {
  const firmsMapKey = import.meta.env.VITE_FIRMS_MAP_KEY as string | undefined
  const cartoApiKey = import.meta.env.VITE_CARTO_API_KEY as string | undefined
  const [hotspots, setHotspots] = useState<FeatureCollection<Point, FirmsProperties>>(emptyHotspots)
  const [firmsStatus, setFirmsStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading')
  const [clock, setClock] = useState(() => new Date())
  const [fireSoundMuted, setFireSoundMuted] = useState(false)

  useEffect(() => {
    if (!firmsMapKey) { setFirmsStatus('unavailable'); return }
    let active = true
    const controller = new AbortController()
    const load = async () => {
      try {
        const response = await fetch(`https://firms.modaps.eosdis.nasa.gov/api/area/csv/${firmsMapKey}/VIIRS_SNPP_NRT/world/1`, { signal: controller.signal })
        if (!response.ok) throw new Error(`FIRMS ${response.status}`)
        const next = readCsv(await response.text())
        if (active) { setHotspots(next); setFirmsStatus('ready') }
      } catch {
        if (active && !controller.signal.aborted) setFirmsStatus('unavailable')
      }
    }
    void load()
    const refresh = window.setInterval(() => { void load() }, FIRMS_REFRESH_MS)
    return () => { active = false; controller.abort(); window.clearInterval(refresh) }
  }, [firmsMapKey])

  useEffect(() => {
    const refresh = window.setInterval(() => setClock(new Date()), CLOCK_REFRESH_MS)
    return () => window.clearInterval(refresh)
  }, [])

  useEffect(() => {
    if (fireSoundMuted) return
    const Context = window.AudioContext
    if (!Context) return
    const context = new Context()
    const buffer = context.createBuffer(1, context.sampleRate * 2, context.sampleRate)
    const samples = buffer.getChannelData(0)
    for (let index = 0; index < samples.length; index += 1) samples[index] = (Math.random() * 2 - 1) * (0.16 + Math.random() * 0.84)
    const source = context.createBufferSource()
    const filter = context.createBiquadFilter()
    const gain = context.createGain()
    source.buffer = buffer
    source.loop = true
    filter.type = 'lowpass'
    filter.frequency.value = 680
    gain.gain.value = 0.018
    source.connect(filter).connect(gain).connect(context.destination)
    source.start()
    void context.resume()
    // Browsers that block initial audio will resume this same ambience at the
    // first interaction, without requiring the visitor to find another control.
    const resume = () => { void context.resume() }
    window.addEventListener('pointerdown', resume, { once: true })
    return () => { window.removeEventListener('pointerdown', resume); source.stop(); void context.close() }
  }, [fireSoundMuted])

  const transformRequest = useMemo(() => {
    if (!cartoApiKey) return undefined
    return (url: string) => !url.includes('cartocdn.com') ? { url } : { url: `${url}${url.includes('?') ? '&' : '?'}key=${cartoApiKey}` }
  }, [cartoApiKey])
  const light = southeastAsiaLight(clock)
  const status = firmsStatus === 'ready'
    ? `${hotspots.features.length.toLocaleString()} thermal detections · past 24 h`
    : firmsStatus === 'loading' ? 'Loading latest FIRMS detections…' : 'Live FIRMS context unavailable'

  return (
    <main className="relative h-screen overflow-hidden bg-bg text-text">
      <Map
        mapStyle="/scoped-map-style.json"
        transformRequest={transformRequest}
        initialViewState={{ longitude: 117.5, latitude: 6.5, zoom: 3 }}
        maxBounds={SEA_BOUNDS}
        minZoom={3}
        maxZoom={10}
        attributionControl={false}
        onLoad={(event) => {
          // Recolour this map instance only: green land and blue water across SEA.
          const map = event.target
          if (map.getLayer('background')) map.setPaintProperty('background', 'background-color', '#183f37')
          if (map.getLayer('landcover')) map.setPaintProperty('landcover', 'fill-color', '#347657')
          if (map.getLayer('landuse')) map.setPaintProperty('landuse', 'fill-color', '#285f49')
          if (map.getLayer('park_national_park')) map.setPaintProperty('park_national_park', 'fill-color', '#54a34f')
          if (map.getLayer('park_nature_reserve')) map.setPaintProperty('park_nature_reserve', 'fill-color', '#438a4d')
          if (map.getLayer('water')) map.setPaintProperty('water', 'fill-color', '#010f2b')
          if (map.getLayer('waterway')) map.setPaintProperty('waterway', 'line-color', '#20b7d7')
        }}
      >
        <Source id="firms-live-sea" type="geojson" data={hotspots}>
          <Layer id="firms-live-glow" type="circle" paint={{ 'circle-color': '#ff351b', 'circle-radius': ['interpolate', ['linear'], ['get', 'frp'], 0, 7, 30, 15, 100, 25], 'circle-blur': 0.8, 'circle-opacity': ['interpolate', ['linear'], ['get', 'ageHours'], 0, 0.85, 6, 0.6, 24, 0.18] }} />
          <Layer id="firms-live-hotspots" type="circle" paint={{ 'circle-color': '#ff5c2e', 'circle-radius': ['interpolate', ['linear'], ['get', 'frp'], 0, 2.5, 30, 5, 100, 8], 'circle-stroke-color': '#ffe6a3', 'circle-stroke-width': 0.8, 'circle-opacity': ['interpolate', ['linear'], ['get', 'ageHours'], 0, 1, 6, 0.86, 24, 0.42] }} />
          <Layer id="firms-live-cores" type="circle" paint={{ 'circle-color': '#fff4ce', 'circle-radius': 1.5, 'circle-opacity': ['interpolate', ['linear'], ['get', 'ageHours'], 0, 1, 24, 0.5] }} />
        </Source>
      </Map>
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-[1] mix-blend-screen transition-opacity duration-[60000ms]" style={{ background: 'radial-gradient(ellipse at 14% 6%, rgba(42, 200, 255, 0.33), transparent 43%), radial-gradient(ellipse at 86% 84%, rgba(255, 166, 52, 0.18), transparent 45%), radial-gradient(ellipse at 45% 20%, transparent 18%, rgba(1, 13, 30, 0.72) 100%)', opacity: 0.82 - light.daylight * 0.6 }} />
      <section className="absolute right-5 top-5 z-10 max-w-md rounded-xl border border-border-strong bg-panel/95 p-5 shadow-2xl backdrop-blur">
        <p className="text-xs uppercase tracking-[0.18em] text-accent">Southeast Asia · live satellite watch</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Start with an audit scope.</h1>
        <p className="mt-3 text-sm leading-6 text-text-muted">Live FIRMS thermal detections provide regional context only. FireEvents appear after you define an authorised management-unit boundary and review period.</p>
        <div className="mt-4 flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-text-faint"><span className="h-2 w-2 rounded-full bg-[#ff5c2e] shadow-[0_0_10px_#ff351b]" />{status}<span className="ml-auto">{light.label}</span></div>
        <Button variant="primary" className="mt-5 w-full py-3 uppercase tracking-[0.14em]" onClick={onStartAudit}>START AUDIT</Button>
        <button type="button" onClick={() => setFireSoundMuted((muted) => !muted)} className="mt-3 text-[10px] uppercase tracking-[0.14em] text-text-faint transition-colors hover:text-text">{fireSoundMuted ? '▶  Play fire ambience' : '▮▮  Mute fire ambience'}</button>
        <p className="mt-3 text-[11px] leading-4 text-text-faint">Upload GeoJSON → validate scope → build the cached historical register → inspect selected FireEvents.</p>
        <button
          type="button"
          onClick={onOpenContext}
          className="mt-3 text-[11px] leading-4 text-text-muted underline underline-offset-2 transition-colors hover:text-text"
        >
          What this console does, and what it refuses to conclude
        </button>
      </section>
    </main>
  )
}
