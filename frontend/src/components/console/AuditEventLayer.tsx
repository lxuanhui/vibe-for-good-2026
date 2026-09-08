import { useMemo } from 'react'
import { Source, Layer } from 'react-map-gl/maplibre'
import type { FeatureCollection, Geometry, GeoJsonProperties } from 'geojson'
import type { DataDrivenPropertyValueSpecification, ExpressionSpecification } from 'maplibre-gl'
import type { AuditEvent, Stage1State } from '../../api/types'
import { STAGE1_STATE_COLORS } from '../../lib/layerColors'

export const AUDIT_EVENT_LAYER_ID = 'audit-events-circle'

// Every FireEvent is one circle, coloured by its Stage-1 state. Not a heatmap:
// the FIRMS layer uses one because raw detections stack into an undifferentiated
// mass at country zoom, but these are already clustered -- 3,610 of them, not
// 20,471 -- and each is individually clickable evidence. Blurring them back
// into a density field would throw away the derivation the pipeline just did.
const stateColor: DataDrivenPropertyValueSpecification<string> = [
  'match',
  ['get', 'state'],
  'LIKELY_FIRE',
  STAGE1_STATE_COLORS.LIKELY_FIRE,
  'LIKELY_NON_FIRE',
  STAGE1_STATE_COLORS.LIKELY_NON_FIRE,
  STAGE1_STATE_COLORS.AMBIGUOUS,
]

// Radius carries observation count, which is the honest size signal: an event
// is a cluster, and how many times it was seen is observed. FRP would look
// like intensity we did not measure per event.
//
// Built per layer with the scale folded into the stop values, because MapLibre
// only accepts `zoom` as the input of a *top-level* interpolate: wrapping one
// shared radius in a `*` expression is rejected at addLayer, the layer is
// silently absent, and the map looks like it works minus the clickable dots.
// The build does not catch this -- only the browser console does.
function radius(scale: number, pad = 0): ExpressionSpecification {
  const stop = (min: number, max: number): ExpressionSpecification => [
    'interpolate',
    ['linear'],
    ['get', 'observationCount'],
    1, min * scale + pad,
    40, max * scale + pad,
  ]
  return [
    'interpolate',
    ['linear'],
    ['zoom'],
    3, stop(1.6, 4),
    6, stop(3, 8),
    9, stop(6, 16),
    12, stop(10, 26),
  ]
}

function toFeatureCollection(events: AuditEvent[]): FeatureCollection<Geometry, GeoJsonProperties> {
  return {
    type: 'FeatureCollection',
    features: events.map((event) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [event.centroid.lon, event.centroid.lat] },
      properties: {
        eventId: event.eventId,
        state: event.triage.state,
        observationCount: event.observationCount,
      },
    })),
  }
}

interface Props {
  events: AuditEvent[]
  visibleStates: Set<Stage1State>
  selectedEventId: string | null
}

export function AuditEventLayer({ events, visibleStates, selectedEventId }: Props) {
  const data = useMemo(
    () => toFeatureCollection(events.filter((e) => visibleStates.has(e.triage.state))),
    [events, visibleStates],
  )

  const selected = useMemo(
    () => toFeatureCollection(events.filter((e) => e.eventId === selectedEventId)),
    [events, selectedEventId],
  )

  return (
    <>
      <Source id="audit-events" type="geojson" data={data}>
        {/* Soft halo under the crisp dot -- the same glow idiom the FIRMS and
            boundary layers use, so density still reads at country zoom without
            a heatmap. */}
        <Layer
          id="audit-events-glow"
          type="circle"
          paint={{
            'circle-radius': radius(1),
            'circle-color': stateColor,
            'circle-opacity': 0.22,
            'circle-blur': 1.1,
          }}
        />
        <Layer
          id={AUDIT_EVENT_LAYER_ID}
          type="circle"
          paint={{
            'circle-radius': radius(0.55),
            'circle-color': stateColor,
            'circle-opacity': 0.9,
            'circle-stroke-color': '#0a0d12',
            'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 3, 0, 8, 0.6],
          }}
        />
      </Source>

      <Source id="audit-event-selected" type="geojson" data={selected}>
        <Layer
          id="audit-event-selected-ring"
          type="circle"
          paint={{
            'circle-radius': radius(0.55, 6),
            'circle-color': 'transparent',
            'circle-stroke-color': '#e6e9ee',
            'circle-stroke-width': 1.5,
          }}
        />
      </Source>
    </>
  )
}
