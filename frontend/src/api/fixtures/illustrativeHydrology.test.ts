import { describe, expect, it } from 'vitest'
import { HYDROLOGY_PLACEHOLDER_RANGES, illustrativeHydrologyField } from './illustrativeHydrology'

const bbox = { minLon: 115, minLat: -4, maxLon: 117, maxLat: -2 }

describe('illustrativeHydrologyField', () => {
  it('is deterministic, labelled, and stays inside the plausible range for every layer', () => {
    for (const layer of ['groundwater', 'peatclsm', 'soil-moisture'] as const) {
      const first = illustrativeHydrologyField(layer, bbox, '2019-09-01')
      const second = illustrativeHydrologyField(layer, bbox, '2019-09-01')
      expect(second).toEqual(first)
      expect(first.features.length).toBeGreaterThan(100)
      const range = HYDROLOGY_PLACEHOLDER_RANGES[layer]
      for (const feature of first.features) {
        expect(feature.properties.illustrative).toBe(true)
        expect(feature.properties.weight).toBeGreaterThanOrEqual(0)
        expect(feature.properties.weight).toBeLessThanOrEqual(1)
        expect(feature.properties.value).toBeGreaterThanOrEqual(range.min)
        expect(feature.properties.value).toBeLessThanOrEqual(range.max)
      }
    }
  })

  it('differs between layers and between days so the toggles and the timeline visibly do something', () => {
    const groundwater = illustrativeHydrologyField('groundwater', bbox, '2019-09-01')
    const soil = illustrativeHydrologyField('soil-moisture', bbox, '2019-09-01')
    const nextDay = illustrativeHydrologyField('groundwater', bbox, '2019-09-02')
    expect(groundwater.features.map((f) => f.properties.weight)).not.toEqual(soil.features.map((f) => f.properties.weight))
    expect(groundwater.features.map((f) => f.properties.weight)).not.toEqual(nextDay.features.map((f) => f.properties.weight))
  })

  it('coarsens the grid over a wide buffer instead of emitting tens of thousands of cells', () => {
    const wide = illustrativeHydrologyField('peatclsm', { minLon: 95, minLat: -10, maxLon: 141, maxLat: 6 }, null)
    expect(wide.features.length).toBeLessThanOrEqual(4500)
    expect(wide.features.length).toBeGreaterThan(1000)
  })
})
