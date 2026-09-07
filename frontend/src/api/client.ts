import type { FeatureCollection } from './geojson'
import type { BBox, EventStatus, FireEvent, InvestigationReport, OverlayLayerId } from './types'
import { ALL_EVENTS } from './fixtures/events'
import { getOverlay, isLayerAvailable } from './fixtures/overlays'
import { REPORTS } from './fixtures/reports'

// Every function here mirrors the real endpoint contract in
// assurance_console_ui_spec.md Section 5 (bbox/date/status filters, response
// shapes). Swapping this module for real `fetch()` calls against a Cloudflare
// Workers backend should not require changing any caller.

const LATENCY_MS = 220

function delay<T>(value: T, ms = LATENCY_MS): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

function inBBox(event: FireEvent, bbox?: BBox): boolean {
  if (!bbox) return true
  return event.lon >= bbox.minLon && event.lon <= bbox.maxLon && event.lat >= bbox.minLat && event.lat <= bbox.maxLat
}

export async function fetchEvents(opts?: { bbox?: BBox; since?: string; status?: EventStatus }): Promise<FireEvent[]> {
  const events = ALL_EVENTS.filter((e) => inBBox(e, opts?.bbox))
    .filter((e) => !opts?.since || e.firstDetected >= opts.since)
    .filter((e) => !opts?.status || e.status === opts.status)
  return delay(events)
}

export async function fetchEvent(eventId: string): Promise<FireEvent | undefined> {
  return delay(ALL_EVENTS.find((e) => e.id === eventId))
}

export async function fetchOverlay(layer: OverlayLayerId, date: string): Promise<FeatureCollection<unknown, unknown>> {
  return delay(getOverlay(layer, date) as FeatureCollection<unknown, unknown>, 120)
}

export { isLayerAvailable }

export async function fetchReport(eventId: string): Promise<InvestigationReport | undefined> {
  return delay(REPORTS[eventId])
}

/**
 * Simulates the Investigator/Skeptic agent run: reveals reasoning rounds
 * progressively (status "running") before settling on the final cached
 * report (status per fixture, usually "converged"). Returns a cancel
 * function; ignores cases with no Stage-2 rounds to run (rejected events).
 */
export function generateReport(eventId: string, onUpdate: (report: InvestigationReport) => void): () => void {
  const final = REPORTS[eventId]
  if (!final || final.reasoningLog.length === 0) {
    if (final) onUpdate(final)
    return () => {}
  }

  let cancelled = false
  const timers: ReturnType<typeof setTimeout>[] = []
  const totalRounds = final.reasoningLog.length

  onUpdate({
    ...final,
    status: 'running',
    reasoningLog: [],
    executiveSummary: '',
    topTheories: [],
    limitations: [],
  })

  for (let round = 1; round <= totalRounds; round++) {
    const isLast = round === totalRounds
    timers.push(
      setTimeout(() => {
        if (cancelled) return
        onUpdate({
          ...final,
          status: isLast ? final.status : 'running',
          reasoningLog: final.reasoningLog.slice(0, round),
          executiveSummary: isLast ? final.executiveSummary : '',
          topTheories: isLast ? final.topTheories : [],
          limitations: isLast ? final.limitations : [],
        })
      }, round * 900),
    )
  }

  return () => {
    cancelled = true
    timers.forEach(clearTimeout)
  }
}
