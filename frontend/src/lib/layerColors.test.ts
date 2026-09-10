import { describe, expect, it } from 'vitest'
import { FIRE_EVENT_COLORS, FIRMS_HOTSPOT_COLORS, LAYER_COLORS } from './layerColors'

describe('fire map palette', () => {
  it('reuses the FIRMS point color for the shared firms layer', () => {
    expect(LAYER_COLORS.firms).toBe(FIRMS_HOTSPOT_COLORS.point)
  })

  it('keeps raw FIRMS observations distinct from clustered FireEvents', () => {
    expect(FIRMS_HOTSPOT_COLORS.point).not.toBe(FIRE_EVENT_COLORS.point)
    expect(FIRE_EVENT_COLORS.focused).not.toBe(FIRE_EVENT_COLORS.point)
  })
})
