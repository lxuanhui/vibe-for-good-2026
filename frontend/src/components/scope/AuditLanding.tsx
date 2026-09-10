import { useEffect, useMemo, useState } from 'react'
import { Layer, Map, Source } from 'react-map-gl/maplibre'
import type { FeatureCollection, Point } from 'geojson'
import { fetchLiveFirmsDetections } from '../../api/client'
import { FIRMS_HOTSPOT_COLORS } from '../../lib/layerColors'
import { Button } from '../ui/Button'
import { illuminationReference, nightCoverage } from '../../lib/illumination'
import { SOLAR_NIGHT_COLOR } from '../../lib/layerColors'
import { REGIONAL_MAP_BOUNDS } from '../../lib/regionalBounds'
import 'maplibre-gl/dist/maplibre-gl.css'

type FirmsProperties = { confidence: string; frp: number; ageHours: number }

const FIRMS_REFRESH_MS = 15 * 60 * 1000
const CLOCK_REFRESH_MS = 60 * 1000

function emptyHotspots(): FeatureCollection<Point, FirmsProperties> {
  return { type: 'FeatureCollection', features: [] }
}

/** The API relays raw UTC acquisition times, not ages.

  It caches a response for 15 minutes to stay inside the FIRMS transaction
  cap, so a server-computed "hours ago" would be up to 15 minutes wrong for
  everyone after the first visitor. The circle paint expressions below fade on
  `ageHours`, so it is derived here, against this browser's clock, at the
  moment the layer is built. */
function withAgeHours(
  detections: FeatureCollection<Point, { confidence: string; frp: number; acquiredAt: string | null }>,
): FeatureCollection<Point, FirmsProperties> {
  const now = Date.now()
  return {
    type: 'FeatureCollection',
    features: detections.features.map((feature) => {
      const acquiredAt = feature.properties.acquiredAt ? Date.parse(feature.properties.acquiredAt) : Number.NaN
      return {
        ...feature,
        properties: {
          confidence: feature.properties.confidence,
          frp: feature.properties.frp,
          // A detection whose timestamp did not parse is drawn at the faintest
          // end rather than dropped -- it was still observed.
          ageHours: Number.isFinite(acquiredAt) ? Math.max(0, (now - acquiredAt) / 3_600_000) : 24,
        },
      }
    }),
  }
}

/** A separate regional live context layer; no unscoped FireEvents are rendered. */
export function AuditLanding({ onStartAudit, onOpenContext }: { onStartAudit: () => void; onOpenContext: () => void }) {
  const cartoApiKey = import.meta.env.VITE_CARTO_API_KEY as string | undefined
  const [hotspots, setHotspots] = useState<FeatureCollection<Point, FirmsProperties>>(emptyHotspots)
  const [firmsStatus, setFirmsStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading')
  const [clock, setClock] = useState(() => new Date())

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const load = async () => {
      try {
        const live = await fetchLiveFirmsDetections(controller.signal)
        if (active) { setHotspots(withAgeHours(live.detections)); setFirmsStatus('ready') }
      } catch {
        // The API answers 503 when it holds no MAP_KEY or FIRMS did not
        // respond. Either way the honest render is "unavailable" -- an empty
        // map would say no fires are burning, which nothing measured.
        if (active && !controller.signal.aborted) setFirmsStatus('unavailable')
      }
    }
    void load()
    const refresh = window.setInterval(() => { void load() }, FIRMS_REFRESH_MS)
    return () => { active = false; controller.abort(); window.clearInterval(refresh) }
  }, [])

  useEffect(() => {
    const refresh = window.setInterval(() => setClock(new Date()), CLOCK_REFRESH_MS)
    return () => window.clearInterval(refresh)
  }, [])

  const transformRequest = useMemo(() => {
    if (!cartoApiKey) return undefined
    return (url: string) => !url.includes('cartocdn.com') ? { url } : { url: `${url}${url.includes('?') ? '&' : '?'}key=${cartoApiKey}` }
  }, [cartoApiKey])
  const night = useMemo(() => nightCoverage(illuminationReference(null, clock)), [clock])
  // Three states, not two. An empty layer and an unanswered one draw the same
  // blank region, so both the panel and the map must identify the response
  // state without adding detections that FIRMS did not return.

  const statusLabel = firmsStatus === 'loading'
    ? 'FIRMS DATA PENDING'
    : firmsStatus === 'unavailable'
      ? 'FIRMS UNAVAILABLE'
      : hotspots.features.length === 0
        ? 'NO DETECTIONS RETURNED'
        : 'FIRMS DATA RETURNED'
  const statusDetail = firmsStatus === 'loading'
    ? 'Regional detections are still being retrieved.'
    : firmsStatus === 'unavailable'
      ? 'The regional live context could not be retrieved.'
      : hotspots.features.length === 0
        ? 'No thermal detections were returned for the past 24 hours.'
        : `${hotspots.features.length.toLocaleString()} thermal detections in the past 24 hours.`
  const statusTone = firmsStatus === 'loading'
    ? 'border-status-info/50 bg-status-info/10 text-status-info'
    : firmsStatus === 'unavailable'
      ? 'border-status-quiet/70 bg-status-quiet/20 text-text-muted'
      : 'border-status-good/50 bg-status-good/10 text-status-good'
  const statusDot = firmsStatus === 'loading'
    ? 'bg-status-info text-status-info animate-pulse shadow-[0_0_10px_currentColor]'
    : firmsStatus === 'unavailable'
      ? 'bg-status-quiet text-status-quiet'
      : 'bg-status-good text-status-good shadow-[0_0_10px_currentColor]'
  const mapStatusTone = firmsStatus === 'loading'
    ? 'border-status-info/60 bg-bg/85 text-status-info'
    : firmsStatus === 'unavailable'
      ? 'border-status-quiet/70 bg-bg/85 text-text-muted'
      : 'border-status-good/60 bg-bg/80 text-status-good'

  return (
    <main className="relative h-screen overflow-hidden bg-bg text-text">
      <div className="absolute inset-0">
        <Map
          mapStyle="/scoped-map-style.json"
          transformRequest={transformRequest}
          initialViewState={{ longitude: 117.5, latitude: 6.5, zoom: 3 }}
          maxBounds={REGIONAL_MAP_BOUNDS}
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
          <Source id="solar-night-coverage" type="geojson" data={night}><Layer id="solar-night-coverage-fill" type="fill" paint={{ 'fill-color': SOLAR_NIGHT_COLOR, 'fill-opacity': 0.3 }} /></Source>
          <Source id="firms-live-sea" type="geojson" data={hotspots}>
            <Layer id="firms-live-glow" type="circle" paint={{ 'circle-color': FIRMS_HOTSPOT_COLORS.glow, 'circle-radius': ['interpolate', ['linear'], ['get', 'frp'], 0, 7, 30, 15, 100, 25], 'circle-blur': 0.8, 'circle-opacity': ['interpolate', ['linear'], ['get', 'ageHours'], 0, 0.85, 6, 0.6, 24, 0.18] }} />
            <Layer id="firms-live-hotspots" type="circle" paint={{ 'circle-color': FIRMS_HOTSPOT_COLORS.point, 'circle-radius': ['interpolate', ['linear'], ['get', 'frp'], 0, 2.5, 30, 5, 100, 8], 'circle-stroke-color': FIRMS_HOTSPOT_COLORS.stroke, 'circle-stroke-width': 0.8, 'circle-opacity': ['interpolate', ['linear'], ['get', 'ageHours'], 0, 1, 6, 0.86, 24, 0.42] }} />
            <Layer id="firms-live-cores" type="circle" paint={{ 'circle-color': FIRMS_HOTSPOT_COLORS.core, 'circle-radius': 1.5, 'circle-opacity': ['interpolate', ['linear'], ['get', 'ageHours'], 0, 1, 24, 0.5] }} />
          </Source>
        </Map>
        {(firmsStatus !== 'ready' || hotspots.features.length === 0) && <div className={`pointer-events-none absolute inset-0 z-[5] flex items-center justify-center ${firmsStatus === 'loading' ? 'bg-status-info/[0.04]' : ''}`} aria-hidden="true">
          <div className={`max-w-[min(90vw,28rem)] rounded-lg border-2 px-5 py-4 text-center shadow-xl backdrop-blur-sm ${mapStatusTone}`}>
            <p className="text-sm font-semibold tracking-[0.16em]">{statusLabel}</p>
            <p className="mt-1 text-xs opacity-80">{firmsStatus === 'loading' ? 'Waiting for the regional thermal layer' : firmsStatus === 'unavailable' ? 'No live regional layer is available' : 'The returned layer contains zero detections'}</p>
          </div>
        </div>}
      </div>
      <section className="absolute right-5 top-5 z-10 max-w-md rounded-xl border border-border-strong bg-panel/95 p-5 shadow-2xl backdrop-blur">
        <p className="text-xs uppercase tracking-[0.18em] text-accent">Southeast Asia · live satellite watch</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Start with an audit scope.</h1>
        <p className="mt-3 text-sm leading-6 text-text-muted">Live FIRMS thermal detections provide regional context only. FireEvents appear after you define an authorised management-unit boundary and review period.</p>
        <div className={`mt-4 rounded-lg border p-3 ${statusTone}`} role="status" aria-live="polite">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${statusDot}`} />
            <span className="text-sm font-semibold tracking-[0.12em]">{statusLabel}</span>
          </div>
          <p className="mt-1 pl-[18px] text-xs leading-5 opacity-80">{statusDetail}</p>
        </div>
        <div className="mt-3 text-right text-[10px] uppercase tracking-[0.14em] text-text-faint">NIGHT SHADE: CURRENT SUN</div>
        <Button variant="primary" className="mt-5 w-full py-3 uppercase tracking-[0.14em]" onClick={onStartAudit}>START AUDIT</Button>
        <p className="mt-3 text-[11px] leading-4 text-text-faint">Choose a boundary (demo area, point and radius, or GeoJSON) → validate scope → build the cached historical register → inspect selected FireEvents.</p>
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
