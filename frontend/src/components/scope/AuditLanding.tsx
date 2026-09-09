import { Layer, Map, Source } from 'react-map-gl/maplibre'
import type { GeoJSON } from 'geojson'
import indonesiaBoundary from '../../assets/indonesia-province-simple.json'
import { Button } from '../ui/Button'
import 'maplibre-gl/dist/maplibre-gl.css'

/** A deliberately event-free regional orientation screen. */
export function AuditLanding({ onStartAudit, onOpenContext }: { onStartAudit: () => void; onOpenContext: () => void }) {
  return (
    <main className="relative h-screen overflow-hidden bg-bg text-text">
      <Map
        mapStyle="/blank-style.json"
        initialViewState={{ longitude: 118, latitude: -2.5, zoom: 3.65 }}
        minZoom={3}
        maxZoom={10}
        attributionControl={false}
      >
        <Source id="indonesia-operating-region" type="geojson" data={indonesiaBoundary as GeoJSON}>
          <Layer id="indonesia-operating-region-fill" type="fill" paint={{ 'fill-color': '#364527', 'fill-opacity': 0.62 }} />
          <Layer id="indonesia-operating-region-line" type="line" paint={{ 'line-color': '#8fa870', 'line-width': 1.1, 'line-opacity': 0.75 }} />
        </Source>
      </Map>
      <section className="absolute left-4 top-4 z-10 max-w-md rounded-xl border border-border-strong bg-panel/95 p-5 shadow-2xl backdrop-blur">
        <p className="text-xs uppercase tracking-[0.18em] text-accent">Environmental Assurance Console</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Start with an audit scope.</h1>
        <p className="mt-3 text-sm leading-6 text-text-muted">This regional view is orientation only. FireEvents are not shown until you define an authorised management-unit boundary and review period.</p>
        <Button variant="primary" className="mt-5 w-full py-3 uppercase tracking-[0.14em]" onClick={onStartAudit}>START AUDIT</Button>
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
