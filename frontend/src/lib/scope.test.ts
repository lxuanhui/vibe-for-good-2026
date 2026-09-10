import { expect, test } from 'vitest'
import { buildScopePreview, circlePolygon } from './scope'

const polygon = { type: 'Polygon', coordinates: [[[100, 1], [101, 1], [101, 2], [100, 2], [100, 1]]] }
const multiPolygon = { type: 'MultiPolygon', coordinates: [[[[100, 1], [101, 1], [101, 2], [100, 2], [100, 1]]]] }

test.each([
  ['Polygon', polygon],
  ['MultiPolygon', multiPolygon],
  ['Feature', { type: 'Feature', geometry: polygon, properties: {} }],
  ['FeatureCollection', { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: multiPolygon, properties: {} }] }],
])('normalizes %s GeoJSON for the preview source', (_type, input) => {
  const preview = buildScopePreview(input, 25)
  expect(preview.displayGeometry.type).toBe('FeatureCollection')
  expect(preview.displayGeometry.features).toHaveLength(1)
  expect(preview.displayGeometry.features[0].geometry.type).toBe(input.type === 'Feature' || input.type === 'FeatureCollection' ? (input as { geometry: { type: string } }).geometry?.type ?? 'MultiPolygon' : input.type)
})

test('rejects unsupported geometry with actionable validation', () => {
  expect(() => buildScopePreview({ type: 'Point', coordinates: [100, 1] }, 25)).toThrow('Polygon or MultiPolygon')
})

test('a point-and-radius circle matches the polygon the API will store', () => {
  const circle = circlePolygon(-3.8, 116.25, 25)
  const ring = circle.coordinates[0]
  // 64 vertices plus the closing repeat of the first, like backend circle_polygon.
  expect(ring).toHaveLength(65)
  expect(ring[0]).toEqual(ring[64])
  // Radius in degrees of latitude at 111.32 km per degree.
  const preview = buildScopePreview(circle, 0)
  expect(preview.bbox.maxLat - preview.bbox.minLat).toBeCloseTo((2 * 25) / 111.32, 6)
  expect(preview.centroid[0]).toBeCloseTo(116.25, 6)
  expect(preview.centroid[1]).toBeCloseTo(-3.8, 6)
})
