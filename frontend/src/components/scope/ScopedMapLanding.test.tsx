import { describe, expect, it } from 'vitest'
import { envelopePolygons } from './propagationEnvelopes'

const edge = (sourceEventId: string, ownerEventId: string) => ({
  sourceEventId,
  targetEventId: 'FE-TARGET',
  state: 'PROPAGATION_COMPATIBLE',
  distanceKm: 2,
  modelVersion: 'surface-fire-ellipse-v1',
  origin: 'selection' as const,
  envelope: {
    polygon: [[116, -3], [116.01, -3], [116.01, -3.01], [116, -3]],
    orientationDeg: 90,
    semiMajorKm: 4,
    semiMinorKm: 2,
    ownerEventId,
  },
})

describe('ScopedMapLanding propagation envelopes', () => {
  it('renders only envelopes owned by the focused FireEvent', () => {
    const result = envelopePolygons([edge('FE-ONE', 'FE-ONE'), edge('FE-TWO', 'FE-TWO')], 'FE-ONE')

    expect(result.features).toHaveLength(1)
    expect(result.features[0].properties).toEqual({ state: 'PROPAGATION_COMPATIBLE', sourceEventId: 'FE-ONE', targetEventId: 'FE-TARGET' })
  })

  it('renders no envelopes when focus is cleared or ownership is absent', () => {
    const owned = edge('FE-ONE', 'FE-ONE')
    const withoutOwner = { ...owned, envelope: { ...owned.envelope, ownerEventId: undefined as unknown as string } }

    expect(envelopePolygons([owned])).toEqual({ type: 'FeatureCollection', features: [] })
    expect(envelopePolygons([withoutOwner], 'FE-ONE')).toEqual({ type: 'FeatureCollection', features: [] })
  })
})
