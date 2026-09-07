import type { OverlayLayerId } from '../api/types'

// Single source of truth for overlay layer colors — used both for MapLibre
// paint expressions (MapView) and the layer legend (LayerControlPanel), so
// the two can never drift apart. See UI spec Section 6: one color scheme,
// reused everywhere.
export const LAYER_COLORS: Record<OverlayLayerId, string> = {
  firms: '#ef4444',
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
