import { useMemo } from 'react'
import { Map, Source, Layer } from 'react-map-gl/maplibre'
import type { GeoJSON } from 'geojson'
import type { ScopePreview } from '../../lib/scope'
import { AUDIT_SCOPE_BOUNDARY_COLOR, AUDIT_SCOPE_BUFFER_COLOR } from '../../lib/layerColors'
import 'maplibre-gl/dist/maplibre-gl.css'

export function ScopePreviewMap({ scope }: { scope: ScopePreview }) {
  const initialViewState = useMemo(() => {
    const span = Math.max(scope.bbox.maxLon - scope.bbox.minLon, scope.bbox.maxLat - scope.bbox.minLat, 0.01)
    return {
      longitude: scope.centroid[0],
      latitude: scope.centroid[1],
      zoom: Math.max(3, Math.min(12, 8 - Math.log2(span))),
    }
  }, [scope])

  return (
    <Map
      mapStyle="/blank-style.json"
      initialViewState={initialViewState}
      minZoom={2}
      maxZoom={14}
      attributionControl={false}
    >
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
      <Source id="audit-boundary" type="geojson" data={scope.geometry as GeoJSON}>
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
