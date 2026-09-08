import type { EventStatus } from '../api/types'

// One scale, reused everywhere a magnitude appears (map markers, table
// support-score column, report hypothesis cards) -- this repo's own
// convention, not spec text. Scores this coloring the hypothesis-support/
// investigation-priority values from `Environmental_Assurance_Spec.md`
// §19-20; the 0-20/21-40/41-60/61-80/81-100 breakpoints are ours, the spec
// doesn't mandate specific bands.
export function scoreColor(score: number): string {
  if (score <= 20) return 'var(--color-status-quiet)'
  if (score <= 40) return 'var(--color-status-info)'
  if (score <= 60) return 'var(--color-status-moderate)'
  if (score <= 80) return 'var(--color-status-elevated)'
  return 'var(--color-status-urgent)'
}

export function scoreLabel(score: number): string {
  if (score <= 20) return 'Very weak'
  if (score <= 40) return 'Weak'
  if (score <= 60) return 'Mixed'
  if (score <= 80) return 'Strong'
  return 'Very strong'
}

export function statusColor(status: EventStatus): string {
  switch (status) {
    case 'AMBIGUOUS':
      return 'var(--color-status-moderate)'
    case 'LIKELY_NON_FIRE':
      return 'var(--color-status-quiet)'
    case 'STAGE2_RUNNING':
      return 'var(--color-status-info)'
    case 'UNRESOLVED':
      return 'var(--color-status-moderate)'
    case 'CONVERGED':
      return 'var(--color-status-good)'
  }
}

export function statusLabel(status: EventStatus): string {
  switch (status) {
    case 'AMBIGUOUS':
      return 'Ambiguous'
    case 'LIKELY_NON_FIRE':
      return 'Likely non-fire'
    case 'STAGE2_RUNNING':
      return 'Stage 2 running'
    case 'UNRESOLVED':
      return 'Unresolved'
    case 'CONVERGED':
      return 'Converged'
  }
}
