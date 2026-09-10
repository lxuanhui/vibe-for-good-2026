import { expect, test } from 'vitest'
import { buildScopePreview } from './scope'

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
