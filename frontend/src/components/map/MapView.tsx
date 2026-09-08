import { useMemo } from 'react'
import { Map, Source, Layer, type MapLayerMouseEvent } from 'react-map-gl/maplibre'
import type { FeatureCollection, Geometry, GeoJsonProperties } from 'geojson'
import type { DataDrivenPropertyValueSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import indonesiaBoundary from '../../assets/indonesia-province-simple.json'
import {
  BOUNDARY_LINE_COLOR,
  INDONESIA_FILL_COLOR,
  INDONESIA_GLOW_COLOR,
  KHG_CLASSIFICATION_COLORS,
  KHG_FALLBACK_COLOR,
  LAYER_COLORS,
} from '../../lib/layerColors'
import { useAppStore } from '../../store/useAppStore'
import { useEvents, useOverlay, useFirms } from '../../api/hooks'
import { EventMarkers } from './EventMarkers'
import { LayerControlPanel } from './LayerControlPanel'
import { TimelineScrubber } from './TimelineScrubber'

const INDONESIA_CENTER = { longitude: 113.9, latitude: -1.5, zoom: 4.4 }

export function MapView() {
  const events = useEvents()
  const layerVisibility = useAppStore((s) => s.layerVisibility)
  const activeDate = useAppStore((s) => s.activeDate)
  const selectEvent = useAppStore((s) => s.selectEvent)

  const firms = useFirms(activeDate, layerVisibility.firms)
  const sarBackscatter = useOverlay('sar-backscatter', activeDate, layerVisibility['sar-backscatter'])
  const khg = useOverlay('khg', activeDate, layerVisibility.khg)
  const concessions = useOverlay('concessions', activeDate, layerVisibility.concessions)
  const fireComplexLinks = useOverlay('fire-complex-links', activeDate, layerVisibility['fire-complex-links'])

  const boundary = useMemo(() => indonesiaBoundary, [])

  // Per-point radius for the close-zoom dot layer below. 'zoom' must be the
  // top-level expression (MapLibre rejects it nested inside e.g. a '+'), so
  // the FRP-based size bump is nested inside each zoom stop instead.
  const firmsRadius: DataDrivenPropertyValueSpecification<number> = [
    'interpolate',
    ['linear'],
    ['zoom'],
    7, ['interpolate', ['linear'], ['get', 'frp'], 0, 2.5, 25, 4.5],
    9, ['interpolate', ['linear'], ['get', 'frp'], 0, 4, 25, 6.5],
    12, ['interpolate', ['linear'], ['get', 'frp'], 0, 7, 25, 11],
  ]

  return (
    <div className="relative h-full w-full">
      <Map
        mapStyle="/blank-style.json"
        initialViewState={INDONESIA_CENTER}
        minZoom={3}
        maxZoom={12}
        onClick={(e: MapLayerMouseEvent) => {
          if (!e.originalEvent.defaultPrevented) selectEvent(null)
        }}
      >
        <Source id="boundary" type="geojson" data={boundary as FeatureCollection<Geometry, GeoJsonProperties>}>
          {/* Soft blurred rim light along the coastline, drawn under the crisp
              fill/outline -- same glow-halo idea as the event marker's pulse,
              muted and static since this traces an entire landmass. */}
          <Layer
            id="boundary-glow"
            type="line"
            paint={{ 'line-color': INDONESIA_GLOW_COLOR, 'line-width': 10, 'line-blur': 6, 'line-opacity': 0.5 }}
          />
          <Layer id="boundary-fill" type="fill" paint={{ 'fill-color': INDONESIA_FILL_COLOR, 'fill-opacity': 0.85 }} />
          <Layer id="boundary-line" type="line" paint={{ 'line-color': BOUNDARY_LINE_COLOR, 'line-width': 0.75 }} />
        </Source>

        {khg && (
          <Source id="khg" type="geojson" data={khg as FeatureCollection<Geometry, GeoJsonProperties>}>
            <Layer
              id="khg-fill"
              type="fill"
              paint={{
                'fill-color': [
                  'match',
                  ['get', 'classification'],
                  'protected_dome',
                  KHG_CLASSIFICATION_COLORS.protected_dome,
                  'production_zone',
                  KHG_CLASSIFICATION_COLORS.production_zone,
                  KHG_FALLBACK_COLOR,
                ],
                'fill-opacity': 0.12,
              }}
            />
            <Layer
              id="khg-line"
              type="line"
              paint={{
                'line-color': [
                  'match',
                  ['get', 'classification'],
                  'protected_dome',
                  KHG_CLASSIFICATION_COLORS.protected_dome,
                  'production_zone',
                  KHG_CLASSIFICATION_COLORS.production_zone,
                  KHG_FALLBACK_COLOR,
                ],
                'line-width': 1.25,
                'line-dasharray': [2, 1.5],
              }}
            />
          </Source>
        )}

        {fireComplexLinks && (
          <Source id="fire-complex-links" type="geojson" data={fireComplexLinks as FeatureCollection<Geometry, GeoJsonProperties>}>
            <Layer
              id="fire-complex-links-line"
              type="line"
              paint={{ 'line-color': LAYER_COLORS['fire-complex-links'], 'line-width': 2, 'line-dasharray': [0.2, 1.6] }}
              layout={{ 'line-cap': 'round' }}
            />
          </Source>
        )}

        {sarBackscatter && (
          <Source id="sar-backscatter" type="geojson" data={sarBackscatter as FeatureCollection<Geometry, GeoJsonProperties>}>
            <Layer
              id="sar-backscatter-circle"
              type="circle"
              paint={{
                'circle-radius': 14,
                'circle-color': LAYER_COLORS['sar-backscatter'],
                'circle-opacity': 0.18,
                'circle-stroke-color': LAYER_COLORS['sar-backscatter'],
                'circle-stroke-width': 1.5,
              }}
            />
          </Source>
        )}

        {concessions && (
          <Source id="concessions" type="geojson" data={concessions as FeatureCollection<Geometry, GeoJsonProperties>}>
            <Layer
              id="concessions-circle"
              type="circle"
              paint={{
                'circle-radius': 5,
                'circle-color': LAYER_COLORS.concessions,
                'circle-stroke-color': '#0a0d12',
                'circle-stroke-width': 1.5,
              }}
            />
          </Source>
        )}

        {firms && (
          // Merges mock per-case detections with the real NASA FIRMS pipeline
          // pull into one source/layer, both scoped to activeDate -- see
          // hooks.ts useFirms(). The real pull's busiest single day is still
          // ~6.5k overlapping points, which would alpha-stack into a solid
          // red mass as plain circles at country-wide zoom, so this uses a
          // heatmap (a soft, muted glow field, brightest where detections
          // cluster) that fades out by zoom 9 as individually glowing dots
          // (echoing the event marker's halo) fade in -- the standard
          // MapLibre pattern for point clouds at this density.
          <Source id="firms" type="geojson" data={firms as FeatureCollection<Geometry, GeoJsonProperties>}>
            <Layer
              id="firms-heat"
              type="heatmap"
              maxzoom={9}
              paint={{
                'heatmap-weight': ['interpolate', ['linear'], ['get', 'frp'], 0, 0.15, 25, 0.6],
                'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 3, 0.3, 9, 1.8],
                'heatmap-color': [
                  'interpolate',
                  ['linear'],
                  ['heatmap-density'],
                  0, 'rgba(255,90,74,0)',
                  0.25, 'rgba(135,9,26,0.2)',
                  0.5, 'rgba(200,40,40,0.4)',
                  0.75, 'rgba(255,90,74,0.6)',
                  1, 'rgba(255,140,60,0.75)',
                ],
                'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 3, 7, 9, 28],
                'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 7, 1, 9, 0],
              }}
            />
            <Layer
              id="firms-circle"
              type="circle"
              minzoom={7}
              paint={{
                'circle-radius': firmsRadius,
                'circle-color': LAYER_COLORS.firms,
                'circle-opacity': ['interpolate', ['linear'], ['zoom'], 7, 0, 9, 0.75],
                'circle-blur': 0.25,
              }}
            />
          </Source>
        )}

        <EventMarkers events={events} />
      </Map>

      <div className="pointer-events-none absolute top-3 left-3">
        <LayerControlPanel />
      </div>
      <div className="pointer-events-none absolute right-3 bottom-3 left-3">
        <TimelineScrubber />
      </div>
    </div>
  )
}
