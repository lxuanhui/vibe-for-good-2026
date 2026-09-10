import { describe, expect, it } from 'vitest'
import type { EventEvidenceResponse } from '../../api/types'
import { envelopePolygons } from './propagationEnvelopes'
import { eventOverlapsDay, investigationDays, observationsForDay } from './temporalScrubber'

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

describe('ScopedMapLanding temporal scrubber', () => {
  it('offers each UTC day in the review period and an all-days state', () => {
    expect(investigationDays('2019-09-01', '2019-09-05')).toEqual([
      '2019-09-01', '2019-09-02', '2019-09-03', '2019-09-04', '2019-09-05',
    ])
  })

  it('filters constituent observations by their recorded acquisition date', () => {
    const evidence = { event: { triageDetail: { observations: [
      { lat: -3, lon: 116, acqDate: '2019-09-01', acqTime: 30, frp: 1, confidence: 'nominal' },
      { lat: -3.1, lon: 116.1, acqDate: '2019-09-02', acqTime: 430, frp: 2, confidence: 'high' },
    ] } } } as EventEvidenceResponse

    expect(observationsForDay(evidence, '2019-09-02')).toHaveLength(1)
    expect(observationsForDay(evidence, null)).toHaveLength(2)
  })

  it('keeps an event point while its detection interval overlaps the selected day', () => {
    const event = { firstDetection: '2019-09-02T03:00:00Z', lastDetection: '2019-09-04T04:00:00Z' }

    expect(eventOverlapsDay(event, '2019-09-03')).toBe(true)
    expect(eventOverlapsDay(event, '2019-09-05')).toBe(false)
    expect(eventOverlapsDay(event, null)).toBe(true)
  })
})
