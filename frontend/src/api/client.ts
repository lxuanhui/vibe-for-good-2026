import type { FeatureCollection } from './geojson'
import type { BBox, EventStatus, FireEvent, InvestigationReport, OverlayLayerId } from './types'
import { getOverlay, isLayerAvailable } from './fixtures/overlays'
import { REPORTS } from './fixtures/reports'

// Every function here mirrors the endpoint contract in
// DesignSpecs/Environmental_Assurance_Spec.md Section 24 (API) -- bbox/date
// filters, response shapes. Functions move from fixture to real `fetch()`
// one at a time without any caller changing -- events have moved; overlays
// and reports have not.

// Empty in dev: Vite proxies /api to the Flask server on :5001. Set
// VITE_API_BASE_URL when the console is served from somewhere that is not
// the same origin as the API.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

const LATENCY_MS = 220

function delay<T>(value: T, ms = LATENCY_MS): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}/api${path}`)
  if (!response.ok) {
    throw new Error(`GET /api${path} failed with ${response.status}`)
  }
  return (await response.json()) as T
}

export async function fetchEvents(opts?: { bbox?: BBox; since?: string; status?: EventStatus }): Promise<FireEvent[]> {
  const params = new URLSearchParams()
  if (opts?.bbox) {
    const { minLon, minLat, maxLon, maxLat } = opts.bbox
    params.set('bbox', `${minLon},${minLat},${maxLon},${maxLat}`)
  }
  if (opts?.since) params.set('since', opts.since)
  if (opts?.status) params.set('status', opts.status)

  const query = params.toString()
  const { events } = await apiGet<{ events: FireEvent[] }>(`/events${query ? `?${query}` : ''}`)
  return events
}

export async function fetchEvent(eventId: string): Promise<FireEvent | undefined> {
  const response = await fetch(`${API_BASE}/api/events/${encodeURIComponent(eventId)}`)
  // Absent is not an error here: the mock returned undefined for an unknown
  // id and callers still branch on that.
  if (response.status === 404) return undefined
  if (!response.ok) {
    throw new Error(`GET /api/events/${eventId} failed with ${response.status}`)
  }
  return (await response.json()) as FireEvent
}

export async function fetchOverlay(layer: OverlayLayerId, date: string): Promise<FeatureCollection<unknown, unknown>> {
  return delay(getOverlay(layer, date) as FeatureCollection<unknown, unknown>, 120)
}

export { isLayerAvailable }

export async function fetchReport(eventId: string): Promise<InvestigationReport | undefined> {
  return delay(REPORTS[eventId])
}

/**
 * Simulates the bounded Investigator/Skeptic run: reveals structured analysis
 * rounds progressively (status "running") before settling on the final
 * cached report. Returns a cancel function; rejected events have no rounds.
 */
export function generateReport(eventId: string, onUpdate: (report: InvestigationReport) => void): () => void {
  const final = REPORTS[eventId]
  if (!final || final.analysisRounds.length === 0) {
    if (final) onUpdate(final)
    return () => {}
  }

  let cancelled = false
  const timers: ReturnType<typeof setTimeout>[] = []
  const totalRounds = final.analysisRounds.length

  onUpdate({
    ...final,
    status: 'running',
    analysisRounds: [],
    unresolvedQuestions: [],
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
          analysisRounds: final.analysisRounds.slice(0, round),
          unresolvedQuestions: isLast ? final.unresolvedQuestions : [],
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
