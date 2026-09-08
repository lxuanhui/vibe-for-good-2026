import { useEffect, useState } from 'react'
import type { FeatureCollection } from './geojson'
import type {
  AuditEvent,
  AuditEventDetail,
  AuditEventScope,
  AuditEventSource,
  FireEvent,
  InvestigationReport,
  OverlayLayerId,
} from './types'
import * as client from './client'
import { fetchPipelineFirms } from './fixtures/pipelineFirms'

export function useEvents(): FireEvent[] {
  const [events, setEvents] = useState<FireEvent[]>([])
  useEffect(() => {
    let active = true
    client.fetchEvents().then((e) => {
      if (active) setEvents(e)
    })
    return () => {
      active = false
    }
  }, [])
  return events
}

export function useOverlay(
  layer: OverlayLayerId,
  date: string,
  enabled: boolean,
): FeatureCollection<unknown, unknown> | null {
  const [data, setData] = useState<FeatureCollection<unknown, unknown> | null>(null)
  useEffect(() => {
    if (!enabled) {
      setData(null)
      return
    }
    let active = true
    client.fetchOverlay(layer, date).then((d) => {
      if (active) setData(d)
    })
    return () => {
      active = false
    }
  }, [layer, date, enabled])
  return data
}

// The 'firms' layer merges two sources into one FeatureCollection, both
// scoped to the same `date`: the mock per-case detections (from
// fixtures/overlays.ts -- see the real-endpoint note there) and the real
// NASA FIRMS pipeline pull (from fixtures/pipelineFirms.ts, temporally
// separated into its own per-date buckets rather than dumped all at once).
// fixtures/dates.ts populates the timeline's date config directly from both
// sources, so `date` always lands on a day at least one of them has data
// for. Once a real backend exists, both go away in favor of a single
// client.fetchOverlay('firms', date) call -- see that note for the target
// endpoint contract.
export function useFirms(date: string, enabled: boolean): FeatureCollection<unknown, unknown> | null {
  const [data, setData] = useState<FeatureCollection<unknown, unknown> | null>(null)
  useEffect(() => {
    if (!enabled) {
      setData(null)
      return
    }
    let active = true
    Promise.all([client.fetchOverlay('firms', date), fetchPipelineFirms(date)]).then(([mock, real]) => {
      if (!active) return
      setData({ type: 'FeatureCollection', features: [...mock.features, ...real.features] })
    })
    return () => {
      active = false
    }
  }, [date, enabled])
  return data
}

export function useReport(eventId: string | null): InvestigationReport | null {
  const [report, setReport] = useState<InvestigationReport | null>(null)
  useEffect(() => {
    if (!eventId) {
      setReport(null)
      return
    }
    let active = true
    client.fetchReport(eventId).then((r) => {
      if (active) setReport(r ?? null)
    })
    return () => {
      active = false
    }
  }, [eventId])
  return report
}

const AUDIT_PAGE_SIZE = 2000

export interface AuditEventsState {
  events: AuditEvent[]
  scope: AuditEventScope | null
  source: AuditEventSource | null
  total: number
  loading: boolean
  error: string | null
}

/**
 * Every event in an audit's reconstructed history, paged in.
 *
 * The API caps a page at 2,000 and the demo scope holds 3,610, so this walks
 * the pages rather than asking for a bigger one -- and appends each page as it
 * lands, so the map paints on the first rather than after the last. Showing a
 * truncated register without saying so would misstate the auditor's workload,
 * which is the one number the product exists to report.
 */
export function useAuditEvents(auditId: string): AuditEventsState {
  const [state, setState] = useState<AuditEventsState>({
    events: [],
    scope: null,
    source: null,
    total: 0,
    loading: true,
    error: null,
  })

  useEffect(() => {
    let active = true
    setState({ events: [], scope: null, source: null, total: 0, loading: true, error: null })

    async function loadAll() {
      try {
        const collected: AuditEvent[] = []
        let offset = 0
        let total = Infinity
        while (active && collected.length < total) {
          const page = await client.fetchAuditEvents(auditId, { limit: AUDIT_PAGE_SIZE, offset })
          if (!active) return
          total = page.total
          collected.push(...page.events)
          offset += AUDIT_PAGE_SIZE
          const done = collected.length >= total
          setState({
            events: [...collected],
            scope: page.scope,
            source: page.source,
            total,
            loading: !done,
            error: null,
          })
          if (page.events.length === 0) break
        }
      } catch (error) {
        if (!active) return
        setState((prev) => ({
          ...prev,
          loading: false,
          error: error instanceof Error ? error.message : 'The audit history could not be loaded.',
        }))
      }
    }

    void loadAll()
    return () => {
      active = false
    }
  }, [auditId])

  return state
}

/** One event's full Stage-1 breakdown, fetched only when it is opened. */
export function useAuditEvent(auditId: string, eventId: string | null) {
  const [detail, setDetail] = useState<AuditEventDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!eventId) {
      setDetail(null)
      setError(null)
      return
    }
    let active = true
    setDetail(null)
    setError(null)
    client
      .fetchAuditEvent(auditId, eventId)
      .then((d) => {
        if (active) setDetail(d)
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : 'Evidence could not be loaded.')
      })
    return () => {
      active = false
    }
  }, [auditId, eventId])

  return { detail, error }
}
