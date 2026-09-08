import type { OverlayLayerId, Stage1State } from '../api/types'

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

export const SURFACE_FIRE_ENVELOPE_COLOR = '#ef4444'
export const SURFACE_FIRE_INSIDE_COLOR = '#22c55e'
export const SURFACE_FIRE_OUTSIDE_COLOR = '#f97316'
export const SURFACE_FIRE_UNEVALUATED_COLOR = '#8b96a8'

export const BOUNDARY_LINE_COLOR = '#2e3a4a'

// Deep green landmass fill for Indonesia's boundary -- the previous
// near-black slate (#141a24) barely stood out from the map's background.
export const INDONESIA_FILL_COLOR = '#364527'

// Lighter tint of INDONESIA_FILL_COLOR, blurred along the coastline for a
// soft rim-light sheen -- same glow-halo technique as the pulsing event
// marker (EventMarkers.tsx), just muted and static for a landmass-sized shape.
export const INDONESIA_GLOW_COLOR = '#8fbf5c'

export const AUDIT_SCOPE_BOUNDARY_COLOR = '#22d3ee'
export const AUDIT_SCOPE_BUFFER_COLOR = '#eab308'

// Stage-1 triage states (`Environmental_Assurance_Spec.md` §10), mapped onto
// the same --color-status-* ramp every other confidence signal in the console
// uses. These say how well the observations support "this is a fire" -- they
// are not a severity, a priority, or anything about cause, so LIKELY_FIRE
// deliberately does not get the urgent red reserved for escalation.
export const STAGE1_STATE_COLORS: Record<Stage1State, string> = {
  LIKELY_FIRE: '#f97316', // --color-status-elevated
  AMBIGUOUS: '#eab308', // --color-status-moderate
  LIKELY_NON_FIRE: '#3f4a5c', // --color-status-quiet
}

// Plain-language gloss for the enum. The canonical name stays visible next to
// it: an auditor tracing a decision needs the token the algorithm emitted, not
// only our rendering of it.
export const STAGE1_STATE_LABELS: Record<Stage1State, string> = {
  LIKELY_FIRE: 'Likely fire',
  AMBIGUOUS: 'Ambiguous',
  LIKELY_NON_FIRE: 'Likely non-fire',
}
