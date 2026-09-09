import type { BBox } from '../api/types'

// The one real dataset behind this demo is the committed 2019 Kalimantan
// haze-window FIRMS export (see docs/demo.md). A management-unit polygon
// inside it is the only geometry that will show real FireEvents, so this is
// what AuditStart submits when a user skips the GeoJSON upload entirely.
export const DEFAULT_MANAGEMENT_UNIT_GEOMETRY = {
  type: 'Polygon' as const,
  coordinates: [[[116.0, -4.05], [116.5, -4.05], [116.5, -3.55], [116.0, -3.55], [116.0, -4.05]]] as [number, number][][],
}

export interface ScopePreview {
  geometry: unknown
  bbox: BBox
  centroid: [number, number]
  bufferBbox: BBox
  bufferGeometry: {
    type: 'Polygon'
    coordinates: [number, number][][]
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function geometryPolygons(geometry: unknown): number[][][][] {
  const record = asRecord(geometry)
  if (!record) throw new Error('GeoJSON feature must contain a geometry object.')
  const type = record.type
  if (type !== 'Polygon' && type !== 'MultiPolygon') {
    throw new Error('Management-unit geometry must be a Polygon or MultiPolygon.')
  }
  if (!Array.isArray(record.coordinates)) throw new Error('GeoJSON geometry must contain coordinates.')
  return type === 'Polygon' ? [record.coordinates as number[][][]] : record.coordinates as number[][][][]
}

function polygonGroups(geojson: unknown): number[][][][] {
  const record = asRecord(geojson)
  if (!record) throw new Error('Upload a GeoJSON object.')

  if (record.type === 'FeatureCollection') {
    if (!Array.isArray(record.features) || record.features.length === 0) {
      throw new Error('GeoJSON FeatureCollection must contain at least one feature.')
    }
    return record.features.flatMap((feature) => {
      const featureRecord = asRecord(feature)
      if (!featureRecord || featureRecord.type !== 'Feature') throw new Error('GeoJSON FeatureCollection contains an invalid feature.')
      return geometryPolygons(featureRecord.geometry)
    })
  }
  if (record.type === 'Feature') return geometryPolygons(record.geometry)
  return geometryPolygons(record)
}

function validatePosition(position: unknown): [number, number] {
  if (!Array.isArray(position) || position.length < 2) {
    throw new Error('GeoJSON coordinates must be [longitude, latitude] positions.')
  }
  const longitude = Number(position[0])
  const latitude = Number(position[1])
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
    throw new Error('GeoJSON coordinates must be finite numbers.')
  }
  if (longitude < -180 || longitude > 180) throw new Error('Longitude must be between -180 and 180.')
  if (latitude < -90 || latitude > 90) {
    throw new Error('Latitude must be between -90 and 90; GeoJSON order is [longitude, latitude].')
  }
  return [longitude, latitude]
}

function ringArea(ring: [number, number][]): number {
  return 0.5 * ring.slice(0, -1).reduce(
    (area, position, index) => area + position[0] * ring[index + 1][1] - ring[index + 1][0] * position[1],
    0,
  )
}

export function buildScopePreview(geojson: unknown, contextBufferKm: number): ScopePreview {
  if (!Number.isFinite(contextBufferKm) || contextBufferKm < 0 || contextBufferKm > 1000) {
    throw new Error('Context buffer must be between 0 and 1,000 km.')
  }

  const positions: [number, number][] = []
  for (const polygon of polygonGroups(geojson)) {
    if (!Array.isArray(polygon) || polygon.length === 0) throw new Error('Polygon must contain an outer ring.')
    polygon.forEach((rawRing, ringIndex) => {
      if (!Array.isArray(rawRing) || rawRing.length < 4) throw new Error('Polygon rings must contain at least four positions.')
      const ring = rawRing.map(validatePosition)
      if (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1]) {
        throw new Error('Each polygon ring must be closed (first position equals last).')
      }
      if (Math.abs(ringArea(ring)) <= 1e-12) {
        throw new Error(`${ringIndex === 0 ? 'Outer ring' : 'Polygon ring'} must enclose a non-empty area.`)
      }
      positions.push(...ring)
    })
  }

  if (positions.length === 0) throw new Error('GeoJSON must contain at least one polygon.')
  const longitudes = positions.map(([longitude]) => longitude)
  const latitudes = positions.map(([, latitude]) => latitude)
  const bbox: BBox = {
    minLon: Math.min(...longitudes),
    minLat: Math.min(...latitudes),
    maxLon: Math.max(...longitudes),
    maxLat: Math.max(...latitudes),
  }
  if (bbox.minLon === bbox.maxLon || bbox.minLat === bbox.maxLat) throw new Error('Management-unit bounds must be non-empty.')

  const centroid: [number, number] = [(bbox.minLon + bbox.maxLon) / 2, (bbox.minLat + bbox.maxLat) / 2]
  const latDelta = contextBufferKm / 111.32
  const longitudeScale = Math.max(Math.abs(Math.cos((centroid[1] * Math.PI) / 180)), 0.01)
  const lonDelta = contextBufferKm / (111.32 * longitudeScale)
  const bufferBbox: BBox = {
    minLon: Math.max(-180, bbox.minLon - lonDelta),
    minLat: Math.max(-90, bbox.minLat - latDelta),
    maxLon: Math.min(180, bbox.maxLon + lonDelta),
    maxLat: Math.min(90, bbox.maxLat + latDelta),
  }
  const bufferRing: [number, number][] = [
    [bufferBbox.minLon, bufferBbox.minLat],
    [bufferBbox.maxLon, bufferBbox.minLat],
    [bufferBbox.maxLon, bufferBbox.maxLat],
    [bufferBbox.minLon, bufferBbox.maxLat],
    [bufferBbox.minLon, bufferBbox.minLat],
  ]
  const bufferGeometry: ScopePreview['bufferGeometry'] = {
    type: 'Polygon',
    coordinates: [bufferRing],
  }

  return { geometry: geojson, bbox, centroid, bufferBbox, bufferGeometry }
}
