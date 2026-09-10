import { describe, expect, it } from 'vitest'
import { illuminationReference, nightCoverage } from './illumination'

describe('solar illumination', () => {
  it('uses the selected historical day at a stable UTC reference', () => {
    const now = new Date('2026-09-10T04:30:00Z')
    expect(illuminationReference('2019-09-03', now).toISOString()).toBe('2019-09-03T12:00:00.000Z')
    expect(illuminationReference(null, now)).toBe(now)
  })

  it('returns a world-sized night polygon that moves with the reference time', () => {
    const morning = nightCoverage(new Date('2019-09-03T00:00:00Z'))
    const evening = nightCoverage(new Date('2019-09-03T12:00:00Z'))
    const morningRing = morning.features[0].geometry.coordinates[0]
    const eveningRing = evening.features[0].geometry.coordinates[0]

    expect(morningRing).toHaveLength(eveningRing.length)
    expect(morningRing.every(([longitude, latitude]) => longitude >= -180 && longitude <= 180 && latitude >= -90 && latitude <= 90)).toBe(true)
    expect(morningRing).not.toEqual(eveningRing)
  })
})
