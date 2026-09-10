import type { AuditEventSummary, EventEvidenceResponse, FireEventObservation } from '../../api/types'

export type ScopedMapDay = string | null

function datesBetween(startDate: string, endDate: string): string[] {
  const start = new Date(`${startDate}T00:00:00Z`)
  const end = new Date(`${endDate}T00:00:00Z`)
  if (Number.isNaN(start.valueOf()) || Number.isNaN(end.valueOf()) || start > end) return []
  const days: string[] = []
  for (const cursor = new Date(start); cursor <= end; cursor.setUTCDate(cursor.getUTCDate() + 1)) days.push(cursor.toISOString().slice(0, 10))
  return days
}

export function observationDays(events: Pick<AuditEventSummary, 'firstDetection' | 'lastDetection'>[], reviewStart: string, reviewEnd: string): string[] {
  const available = new Set<string>()
  for (const event of events) {
    const eventStart = event.firstDetection.slice(0, 10)
    const eventEnd = event.lastDetection.slice(0, 10)
    for (const day of datesBetween(eventStart, eventEnd)) available.add(day)
  }
  return datesBetween(reviewStart, reviewEnd).filter((day) => available.has(day))
}

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
