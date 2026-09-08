import type { FireEvent } from '../api/types'

export function isActiveOnDate(event: FireEvent, date: string): boolean {
  if (!event.detections?.length) {
    const first = event.firstDetected.slice(0, 10)
    const last = (event.lastDetected ?? event.firstDetected).slice(0, 10)
    return first <= date && date <= last
  }
  return event.detections.some((d) => d.acquiredAt.slice(0, 10) === date)
}
