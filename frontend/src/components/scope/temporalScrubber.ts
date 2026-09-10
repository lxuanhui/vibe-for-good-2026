import type { AuditEventSummary, EventEvidenceResponse, FireEventObservation } from '../../api/types'

export type ScopedMapDay = string | null

export function investigationDays(reviewStart: string, reviewEnd: string): string[] {
  const start = new Date(`${reviewStart}T00:00:00Z`)
  const end = new Date(`${reviewEnd}T00:00:00Z`)
  if (Number.isNaN(start.valueOf()) || Number.isNaN(end.valueOf()) || start > end) return []
  const days: string[] = []
  for (const cursor = new Date(start); cursor <= end; cursor.setUTCDate(cursor.getUTCDate() + 1)) days.push(cursor.toISOString().slice(0, 10))
  return days
}

export function eventOverlapsDay(event: Pick<AuditEventSummary, 'firstDetection' | 'lastDetection'>, day: ScopedMapDay): boolean {
  if (!day) return true
  return event.firstDetection.slice(0, 10) <= day && event.lastDetection.slice(0, 10) >= day
}

export function observationsForDay(evidence: EventEvidenceResponse | undefined, day: ScopedMapDay): FireEventObservation[] {
  const observations = evidence?.event.triageDetail?.observations ?? []
  return day ? observations.filter((observation) => observation.acqDate === day) : observations
}
