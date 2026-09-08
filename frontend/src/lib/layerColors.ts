import type { OverlayLayerId } from '../api/types'

// Single source of truth for overlay layer colors — used both for MapLibre
// paint expressions (MapView) and the layer legend (LayerControlPanel), so
// the two can never drift apart. One color scheme, reused everywhere -- this
// repo's own convention; `Environmental_Assurance_Spec.md` doesn't specify
// exact colors.
export const LAYER_COLORS: Record<OverlayLayerId, string> = {
  firms: '#ff5a4a',
  'sar-backscatter': '#22d3ee',
  khg: '#f97316',
  concessions: '#8b96a8',
  'fire-complex-links': '#ef4444',
}

export const KHG_CLASSIFICATION_COLORS = {
  protected_dome: '#f97316',
  production_zone: '#3b82f6',
} as const

export const KHG_FALLBACK_COLOR = '#3f4a5c'

export const BOUNDARY_LINE_COLOR = '#2e3a4a'

// Deep green landmass fill for Indonesia's boundary -- the previous
// near-black slate (#141a24) barely stood out from the map's background.
export const INDONESIA_FILL_COLOR = '#364527'

// Lighter tint of INDONESIA_FILL_COLOR, blurred along the coastline for a
// soft rim-light sheen -- same glow-halo technique as the pulsing event
// marker (EventMarkers.tsx), just muted and static for a landmass-sized shape.
export const INDONESIA_GLOW_COLOR = '#8fbf5c'
