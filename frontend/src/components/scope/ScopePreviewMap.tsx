import { useEffect, useMemo, useRef } from 'react'
import { Map, Source, Layer, type MapRef } from 'react-map-gl/maplibre'
import type { FeatureCollection, Geometry } from 'geojson'
import type { ScopePreview } from '../../lib/scope'
import indonesiaBoundary from '../../assets/indonesia-province-simple.json'
import { AUDIT_SCOPE_BOUNDARY_COLOR, AUDIT_SCOPE_BUFFER_COLOR, INDONESIA_FILL_COLOR } from '../../lib/layerColors'
import 'maplibre-gl/dist/maplibre-gl.css'

const indonesiaBoundaryGeoJson = indonesiaBoundary as unknown as FeatureCollection<Geometry>

export function ScopePreviewMap({ scope }: { scope: ScopePreview }) {
  const initialViewState = useMemo(() => {
    const span = Math.max(scope.bufferBbox.maxLon - scope.bufferBbox.minLon, scope.bufferBbox.maxLat - scope.bufferBbox.minLat, 0.01)
    return {
      longitude: scope.centroid[0],
      latitude: scope.centroid[1],
      zoom: Math.max(3, Math.min(12, 8 - Math.log2(span))),
    }
  }, [scope])

  const mapRef = useRef<MapRef>(null)
  useEffect(() => {
    mapRef.current?.jumpTo({
      center: [initialViewState.longitude, initialViewState.latitude],
      zoom: initialViewState.zoom,
    })
  }, [initialViewState])

  return (
    <Map
      ref={mapRef}
      mapStyle="/blank-style.json"
      initialViewState={initialViewState}
      minZoom={2}
      maxZoom={14}
      attributionControl={false}
    >
      <Source id="indonesia-geographic-context" type="geojson" data={indonesiaBoundaryGeoJson}>
        <Layer
          id="indonesia-geographic-context-fill"
          type="fill"
          paint={{ 'fill-color': INDONESIA_FILL_COLOR, 'fill-opacity': 0.5 }}
        />
        <Layer
          id="indonesia-geographic-context-line"
          type="line"
          paint={{ 'line-color': INDONESIA_FILL_COLOR, 'line-width': 0.8, 'line-opacity': 0.9 }}
        />
      </Source>
      <Source id="audit-context-buffer" type="geojson" data={scope.bufferGeometry}>
        <Layer
          id="audit-context-buffer-fill"
          type="fill"
          paint={{ 'fill-color': AUDIT_SCOPE_BUFFER_COLOR, 'fill-opacity': 0.1 }}
        />
        <Layer
          id="audit-context-buffer-line"
          type="line"
          paint={{ 'line-color': AUDIT_SCOPE_BUFFER_COLOR, 'line-width': 2, 'line-dasharray': [3, 2] }}
        />
      </Source>
      <Source id="audit-boundary" type="geojson" data={scope.displayGeometry}>
        <Layer
          id="audit-boundary-fill"
          type="fill"
          paint={{ 'fill-color': AUDIT_SCOPE_BOUNDARY_COLOR, 'fill-opacity': 0.18 }}
        />
        <Layer
          id="audit-boundary-line"
          type="line"
          paint={{ 'line-color': AUDIT_SCOPE_BOUNDARY_COLOR, 'line-width': 2.5 }}
        />
      </Source>
    </Map>
  )
}
