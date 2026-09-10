import type { OverlayLayerId } from '../api/types'

// Single source of truth for overlay layer colors — used both for MapLibre
// paint expressions (ScopedMapLanding) and the layer legend
// (LayerControlPanel), so the two can never drift apart. One color scheme,
// reused everywhere -- this repo's own convention; `Environmental_Assurance_Spec.md`
// doesn't specify exact colors.
export const LAYER_COLORS: Record<OverlayLayerId, string> = {
  firms: '#ff5a4a',
  'sar-backscatter': '#6fb3a6',
  khg: '#f97316',
  concessions: '#8b96a8',
  'fire-complex-links': '#ef4444',
}

export const KHG_CLASSIFICATION_COLORS = {
  protected_dome: '#f97316',
  production_zone: '#3b82f6',
} as const

export const KHG_FALLBACK_COLOR = '#3f4a5c'

export const SURFACE_FIRE_ENVELOPE_COLOR = '#ef4444'
export const SURFACE_FIRE_INSIDE_COLOR = '#22c55e'
export const SURFACE_FIRE_OUTSIDE_COLOR = '#f97316'
export const SURFACE_FIRE_UNEVALUATED_COLOR = '#8b96a8'

// Deep green landmass fill -- the previous near-black slate (#141a24) barely
// stood out from the map's background. This is now also the hand-synced land
// color in the scoped map's Carto vector style: `scoped-map-style.json`
// can't import a TS constant, so if this value changes, its "background" /
// "landcover" / "landuse" / "park_*" paint colors need the same edit --
// see the note in ScopedMapLanding.tsx next to `mapStyle`.
export const INDONESIA_FILL_COLOR = '#364527'

export const AUDIT_SCOPE_BOUNDARY_COLOR = '#6fb3a6'
export const AUDIT_SCOPE_BUFFER_COLOR = '#eab308'

export const AUDIT_EVENT_COLORS = {
  LIKELY_FIRE: '#22c55e',
  AMBIGUOUS: '#eab308',
  LIKELY_NON_FIRE: '#8b96a8',
} as const
