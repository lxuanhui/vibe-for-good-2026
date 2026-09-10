import type { FeatureCollection } from './geojson'
import type { AnalysisJob, AuditEventSummary, AuditPackReview, AuditProgression, AuditReport, AuditScope, BBox, DemoDatasetSummary, EventEvidenceResponse, EventStatus, FireEvent, InvestigationBundle, InvestigationMap, InvestigationReport, LiveFirmsDetections, OverlayLayerId, ProcessedImageryManifest, StructuredAnalysis } from './types'
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

function apiUnavailable(error: unknown): Error {
  // Vite reports a proxy connection refusal as a fetch TypeError/502, which
  // otherwise reads like a malformed GeoJSON submission. The audit form can
  // give the operator an actionable local-development diagnosis instead.
  if (error instanceof TypeError) {
    return new Error('The local API is unavailable. Start the Flask server on http://127.0.0.1:5001, then try again.')
  }
  return error instanceof Error ? error : new Error('The API request failed.')
}

function delay<T>(value: T, ms = LATENCY_MS): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

async function apiGet<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/api${path}`)
  } catch (error) {
    throw apiUnavailable(error)
  }
  if (!response.ok) {
    throw new Error(`GET /api${path} failed with ${response.status}`)
  }
  return (await response.json()) as T
}

async function apiPost<T>(path: string, body: BodyInit | null, headers?: HeadersInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/api${path}`, { method: 'POST', body, headers })
  } catch (error) {
    throw apiUnavailable(error)
  }
  if (!response.ok) {
    const details = (await response.json().catch(() => null)) as { error?: string } | null
    throw new Error(details?.error ?? `POST /api${path} failed with ${response.status}`)
  }
  return (await response.json()) as T
}

export async function createAuditReview(input: {
  reviewStart: string
  reviewEnd: string
  contextBufferKm: number
}): Promise<AuditScope> {
  return apiPost<AuditScope>(
    '/audits',
    JSON.stringify({
      review_start: input.reviewStart,
      review_end: input.reviewEnd,
      context_buffer_km: input.contextBufferKm,
    }),
    { 'Content-Type': 'application/json' },
  )
}

export async function uploadAuditScope(auditId: string, file: File): Promise<AuditScope> {
  const form = new FormData()
  form.append('file', file)
  return apiPost<AuditScope>(`/audits/${encodeURIComponent(auditId)}/scope/upload`, form)
}

// Same endpoint, no file -- the backend route already accepts a raw GeoJSON
// body when no multipart file is attached. Used when AuditStart falls back
// to a default management-unit geometry instead of an upload.
export async function uploadAuditScopeGeometry(auditId: string, geometry: unknown): Promise<AuditScope> {
  return apiPost<AuditScope>(`/audits/${encodeURIComponent(auditId)}/scope/upload`, JSON.stringify(geometry), { 'Content-Type': 'application/json' })
}

export async function buildFireHistory(auditId: string): Promise<{ audit_id: string; scope_id: string; status: 'HISTORY_BUILD_READY'; duration_ms: number; dataset_mode: string }> {
  return apiPost(`/audits/${encodeURIComponent(auditId)}/history/build`, null)
}

export async function fetchAuditRegister(auditId: string, filters?: { since?: string; until?: string; bbox?: BBox }): Promise<{ events: AuditEventSummary[]; progression: AuditProgression }> {
  const pageSize = 2000
  const query = new URLSearchParams({ limit: String(pageSize) })
  if (filters?.since) query.set('since', filters.since)
  if (filters?.until) query.set('until', filters.until)
  if (filters?.bbox) query.set('bbox', `${filters.bbox.minLon},${filters.bbox.minLat},${filters.bbox.maxLon},${filters.bbox.maxLat}`)
  const first = await apiGet<{ total: number; events: AuditEventSummary[]; progression: AuditProgression }>(`/audits/${encodeURIComponent(auditId)}/events?${query}`)
  const pages = [first.events]
  for (let offset = pageSize; offset < first.total; offset += pageSize) {
    query.set('offset', String(offset))
    const page = await apiGet<{ events: AuditEventSummary[] }>(`/audits/${encodeURIComponent(auditId)}/events?${query}`)
    pages.push(page.events)
  }
  return { events: pages.flat(), progression: first.progression }
}

// The audit id of the one committed real dataset. The events route resolves
// any session-created id back to this artifact anyway (backend/app/audit_events.py
// `get_audit`); naming it directly is what lets the landing screen describe the
// dataset before an audit exists. `limit=1` because only `progression` and
// `source` are wanted -- the 3,610 events would be 240 KB of waste on first paint.
const DEMO_DATASET_AUDIT_ID = 'demo-2019-haze'

export async function fetchDemoDatasetSummary(): Promise<DemoDatasetSummary> {
  const response = await apiGet<{
    source: { dataset?: string; region?: string; window?: string }
    progression: AuditProgression
  }>(`/audits/${DEMO_DATASET_AUDIT_ID}/events?limit=1`)
  const { rawObservations, qualifiedObservations, fireEvents, requiringHumanReview } = response.progression
  return {
    dataset: response.source.dataset ?? 'NASA FIRMS',
    region: response.source.region ?? '',
    window: response.source.window ?? '',
    progression: { rawObservations, qualifiedObservations, fireEvents, requiringHumanReview },
  }
}

export async function fetchInvestigationMap(auditId: string, eventIds: string[]): Promise<InvestigationMap> {
  const query = encodeURIComponent(eventIds.join(','))
  return apiGet<InvestigationMap>(`/audits/${encodeURIComponent(auditId)}/graph?event_ids=${query}`)
}

export async function fetchAuditEventEvidence(auditId: string, eventId: string): Promise<EventEvidenceResponse> {
  return apiGet<EventEvidenceResponse>(`/audits/${encodeURIComponent(auditId)}/events/${encodeURIComponent(eventId)}/evidence`)
}

export async function fetchInvestigationBundle(auditId: string, eventId: string): Promise<InvestigationBundle> {
  return apiGet<InvestigationBundle>(`/audits/${encodeURIComponent(auditId)}/events/${encodeURIComponent(eventId)}/investigation`)
}

// Processed imagery is static pipeline output, not an API response. Keep the
// manifest lookup in this seam so the drawer joins it to the API's existing
// scene EvidenceObjects by source evidence ID rather than duplicating scene
// selection or treating a catalogue thumbnail as investigation imagery.
let processedImageryManifest: Promise<ProcessedImageryManifest> | undefined

export function fetchProcessedImageryManifest(): Promise<ProcessedImageryManifest> {
  processedImageryManifest ??= fetch('/imagery/manifest.json').then(async (response) => {
    if (!response.ok) throw new Error(`GET /imagery/manifest.json failed with ${response.status}`)
    return (await response.json()) as ProcessedImageryManifest
  })
  return processedImageryManifest
}

// A two-round Investigator/Skeptic assessment measures ~51s, past API
// Gateway's 30s response cap, so the API records a job and this polls it
// (#143). The seam keeps the old promise contract -- callers still await one
// analysis or one error -- rather than pushing job state into every caller.
const ANALYSIS_POLL_DEADLINE_MS = 5 * 60 * 1000

export async function generateInvestigationAnalysis(auditId: string, eventId: string, onProgress?: (job: AnalysisJob) => void): Promise<StructuredAnalysis> {
  const path = `/audits/${encodeURIComponent(auditId)}/events/${encodeURIComponent(eventId)}/analyse`
  let job = await apiPost<AnalysisJob>(path, '')
  onProgress?.(job)
  const deadline = Date.now() + ANALYSIS_POLL_DEADLINE_MS
  while (job.jobStatus === 'RUNNING') {
    if (Date.now() > deadline) {
      // The job itself is not lost -- it keeps running and its result will be
      // there on the next read. Say that rather than implying it failed.
      throw new Error('Investigation analysis is still running. Reopen this event shortly to read the completed assessment.')
    }
    await delay(null, Math.max(1, job.pollAfterSeconds ?? 5) * 1000)
    job = await apiGet<AnalysisJob>(path)
    onProgress?.(job)
  }
  if (job.jobStatus !== 'COMPLETE' || !job.analysis) {
    throw new Error(job.error ?? 'Investigation analysis could not be generated.')
  }
  return job.analysis
}

export async function addToAuditPack(auditId: string, eventId: string, review: Partial<Pick<AuditPackReview, 'note' | 'disposition'>> = {}): Promise<AuditPackReview> {
  return apiPost<AuditPackReview>(`/audits/${encodeURIComponent(auditId)}/events/${encodeURIComponent(eventId)}/add-to-pack`, JSON.stringify(review), { 'Content-Type': 'application/json' })
}

export async function removeFromAuditPack(auditId: string, eventId: string): Promise<void> {
  const path = `/audits/${encodeURIComponent(auditId)}/events/${encodeURIComponent(eventId)}/add-to-pack`
  const response = await fetch(`${API_BASE}/api${path}`, { method: 'DELETE' })
  if (!response.ok) {
    const details = (await response.json().catch(() => null)) as { error?: string } | null
    throw new Error(details?.error ?? `DELETE /api${path} failed with ${response.status}`)
  }
}

export async function fetchAuditReport(auditId: string): Promise<AuditReport> {
  return apiGet<AuditReport>(`/audits/${encodeURIComponent(auditId)}/report`)
}

/** Current regional NASA FIRMS detections for the landing map.

  Proxied by the API rather than fetched from the browser: a FIRMS MAP_KEY
  cannot be restricted to a domain, and Vite inlines every VITE_-prefixed
  variable into the public bundle, so the key can only live server-side. The
  API answers 503 when it has no key or FIRMS did not respond -- the caller
  renders an explicit unavailable state, never an empty region, which would
  read as "nothing is burning". */
export async function fetchLiveFirmsDetections(signal?: AbortSignal): Promise<LiveFirmsDetections> {
  const response = await fetch(`${API_BASE}/api/firms/live`, { signal })
  if (!response.ok) throw new Error(`GET /api/firms/live failed with ${response.status}`)
  return (await response.json()) as LiveFirmsDetections
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
