import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Map, Source, Layer, type MapLayerMouseEvent, type MapRef } from 'react-map-gl/maplibre'
import type { FeatureCollection, Geometry, GeoJsonProperties } from 'geojson'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { AuditEvent, Stage1State } from '../../api/types'
import { DEMO_AUDIT_ID } from '../../api/client'
import { useAuditEvents } from '../../api/hooks'
import indonesiaBoundary from '../../assets/indonesia-province-simple.json'
import {
  AUDIT_SCOPE_BOUNDARY_COLOR,
  BOUNDARY_LINE_COLOR,
  INDONESIA_FILL_COLOR,
  INDONESIA_GLOW_COLOR,
  STAGE1_STATE_COLORS,
  STAGE1_STATE_LABELS,
} from '../../lib/layerColors'
import { AuditEventLayer, AUDIT_EVENT_LAYER_ID } from './AuditEventLayer'
import { EventEvidencePanel } from './EventEvidencePanel'
import { ScopeHeader } from './ScopeHeader'

const ALL_STATES: Stage1State[] = ['LIKELY_FIRE', 'AMBIGUOUS', 'LIKELY_NON_FIRE']

// Opening view while the first page is still in flight. Replaced by a fit to
// the scope's own extent as soon as events land -- the console must not settle
// on a national browse view (issue #58).
const INITIAL_VIEW = { longitude: 111.5, latitude: -1.0, zoom: 4.2 }

function scopeExtent(events: AuditEvent[]) {
  if (events.length === 0) return null
  let minLon = Infinity
  let minLat = Infinity
  let maxLon = -Infinity
  let maxLat = -Infinity
  for (const event of events) {
    minLon = Math.min(minLon, event.centroid.lon)
    maxLon = Math.max(maxLon, event.centroid.lon)
    minLat = Math.min(minLat, event.centroid.lat)
    maxLat = Math.max(maxLat, event.centroid.lat)
  }
  return { minLon, minLat, maxLon, maxLat }
}

function extentGeometry(extent: NonNullable<ReturnType<typeof scopeExtent>>) {
  const { minLon, minLat, maxLon, maxLat } = extent
  return {
    type: 'Polygon' as const,
    coordinates: [
      [
        [minLon, minLat],
        [maxLon, minLat],
        [maxLon, maxLat],
        [minLon, maxLat],
        [minLon, minLat],
      ],
    ],
  }
}

export function ConsoleMap() {
  const mapRef = useRef<MapRef | null>(null)
  const framed = useRef(false)
  const { events, scope, source, total, loading, error } = useAuditEvents(DEMO_AUDIT_ID)

  const [visibleStates, setVisibleStates] = useState<Set<Stage1State>>(new Set(ALL_STATES))
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [showExtent, setShowExtent] = useState(true)

  const extent = useMemo(() => scopeExtent(events), [events])
  const selectedEvent = useMemo(
    () => events.find((e) => e.eventId === selectedEventId) ?? null,
    [events, selectedEventId],
  )

  const counts = useMemo(() => {
    const byState: Record<Stage1State, number> = {
      LIKELY_FIRE: 0,
      AMBIGUOUS: 0,
      LIKELY_NON_FIRE: 0,
    }
    for (const event of events) byState[event.triage.state] += 1
    return byState
  }, [events])

  // Frame once, on the first page. Refitting as later pages arrive would yank
  // the camera out from under someone who has already started panning.
  useEffect(() => {
    if (framed.current || !extent || !mapRef.current) return
    framed.current = true
    mapRef.current.fitBounds(
      [
        [extent.minLon, extent.minLat],
        [extent.maxLon, extent.maxLat],
      ],
      { padding: { top: 96, bottom: 96, left: 96, right: 420 }, duration: 900 },
    )
  }, [extent])

  const handleClick = useCallback((event: MapLayerMouseEvent) => {
    const hit = event.features?.find((f) => f.layer.id === AUDIT_EVENT_LAYER_ID)
    setSelectedEventId(hit ? String(hit.properties?.eventId) : null)
  }, [])

  const toggleState = useCallback((state: Stage1State) => {
    setVisibleStates((prev) => {
      const next = new Set(prev)
      if (next.has(state)) next.delete(state)
      else next.add(state)
      return next
    })
  }, [])

  return (
    <div className="relative h-full w-full overflow-hidden bg-bg">
      <Map
        ref={mapRef}
        mapStyle="/blank-style.json"
        initialViewState={INITIAL_VIEW}
        minZoom={3}
        maxZoom={13}
        attributionControl={false}
        interactiveLayerIds={[AUDIT_EVENT_LAYER_ID]}
        onClick={handleClick}
        cursor="default"
      >
        <Source
          id="boundary"
          type="geojson"
          data={indonesiaBoundary as FeatureCollection<Geometry, GeoJsonProperties>}
        >
          <Layer
            id="boundary-glow"
            type="line"
            paint={{
              'line-color': INDONESIA_GLOW_COLOR,
              'line-width': 10,
              'line-blur': 6,
              'line-opacity': 0.45,
            }}
          />
          <Layer
            id="boundary-fill"
            type="fill"
            paint={{ 'fill-color': INDONESIA_FILL_COLOR, 'fill-opacity': 0.8 }}
          />
          <Layer
            id="boundary-line"
            type="line"
            paint={{ 'line-color': BOUNDARY_LINE_COLOR, 'line-width': 0.75 }}
          />
        </Source>

        {showExtent && extent && (
          <Source id="scope-extent" type="geojson" data={extentGeometry(extent)}>
            <Layer
              id="scope-extent-line"
              type="line"
              paint={{
                'line-color': AUDIT_SCOPE_BOUNDARY_COLOR,
                'line-width': 1,
                'line-dasharray': [4, 3],
                'line-opacity': 0.7,
              }}
            />
          </Source>
        )}

        <AuditEventLayer
          events={events}
          visibleStates={visibleStates}
          selectedEventId={selectedEventId}
        />
      </Map>

      <ScopeHeader scope={scope} source={source} total={total} loaded={events.length} loading={loading} />

      {/* Legend doubles as the state filter -- one control, so what is shown
          and what the colours mean cannot drift apart. */}
      <div className="pointer-events-auto absolute top-4 right-4 w-[248px] rounded-lg border border-border-strong bg-panel/95 p-3 backdrop-blur">
        <div className="text-[10px] uppercase tracking-[0.18em] text-text-faint">Stage-1 triage</div>
        <ul className="mt-2 space-y-1">
          {ALL_STATES.map((state) => {
            const active = visibleStates.has(state)
            return (
              <li key={state}>
                <button
                  type="button"
                  onClick={() => toggleState(state)}
                  aria-pressed={active}
                  className={`flex w-full items-center gap-2 rounded px-1.5 py-1 text-left transition-opacity hover:bg-panel-raised ${
                    active ? 'opacity-100' : 'opacity-40'
                  }`}
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: STAGE1_STATE_COLORS[state] }}
                  />
                  <span className="flex-1 text-xs text-text">{STAGE1_STATE_LABELS[state]}</span>
                  <span className="font-mono text-[10px] text-text-faint">
                    {counts[state].toLocaleString()}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
        <p className="mt-2 border-t border-border pt-2 text-[10px] leading-4 text-text-faint">
          Derived from observations. Says whether the evidence supports a fire — not how one
          started, and not who is answerable for it.
        </p>

        <label className="mt-3 flex cursor-pointer items-center gap-2 border-t border-border pt-2.5">
          <input
            type="checkbox"
            checked={showExtent}
            onChange={() => setShowExtent((v) => !v)}
            className="accent-accent"
          />
          <span className="flex-1 text-[11px] text-text-muted">Scope extent</span>
          <span className="text-[9px] text-text-faint">derived</span>
        </label>
      </div>

      {error && (
        <div
          role="alert"
          className="pointer-events-auto absolute bottom-4 left-4 max-w-md rounded-lg border border-status-urgent/40 bg-status-urgent/10 px-4 py-3 text-xs leading-5 text-red-200"
        >
          {error}
        </div>
      )}

      {!loading && !error && events.length === 0 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-24 text-center text-xs text-text-faint">
          This audit has no reconstructed history yet.
        </div>
      )}

      {selectedEvent && (
        <div className="pointer-events-none absolute inset-y-0 right-0">
          <EventEvidencePanel
            auditId={DEMO_AUDIT_ID}
            event={selectedEvent}
            onClose={() => setSelectedEventId(null)}
          />
        </div>
      )}
    </div>
  )
}
