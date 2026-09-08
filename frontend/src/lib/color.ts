import type { EventStatus } from '../api/types'

// One scale, reused everywhere a magnitude appears (map markers, table
// support-score column, report hypothesis cards) — see UI spec Section 6.
// Bands mirror the 0-20/21-40/41-60/61-80/81-100 support-score bands from
// the original build spec's Section 17.
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
    case 'AWAITING_REVIEW':
      return 'var(--color-status-moderate)'
    case 'STAGE1_REJECTED':
      return 'var(--color-status-quiet)'
    case 'STAGE2_RUNNING':
      return 'var(--color-status-info)'
    case 'CONVERGED':
      return 'var(--color-status-good)'
  }
}

export function statusLabel(status: EventStatus): string {
  switch (status) {
    case 'AWAITING_REVIEW':
      return 'Awaiting review'
    case 'STAGE1_REJECTED':
      return 'Stage 1 rejected'
    case 'STAGE2_RUNNING':
      return 'Stage 2 running'
    case 'CONVERGED':
      return 'Converged'
  }
}
