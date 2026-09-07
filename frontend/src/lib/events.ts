import type { FireEvent } from '../api/types'

export function isActiveOnDate(event: FireEvent, date: string): boolean {
  return event.detections.some((d) => d.acquiredAt.slice(0, 10) === date)
}
