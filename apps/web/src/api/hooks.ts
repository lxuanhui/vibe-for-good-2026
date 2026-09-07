import { useEffect, useState } from 'react'
import type { FeatureCollection } from './geojson'
import type { FireEvent, InvestigationReport, OverlayLayerId } from './types'
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

// The 'firms' layer merges two sources into one FeatureCollection: the
// mock per-case detections (timeline-scoped, from fixtures/overlays.ts --
// see the real-endpoint note there) and the real one-off NASA FIRMS
// pipeline pull (static, not timeline-scoped -- see fixtures/pipelineFirms.ts).
// Once a real backend exists, both go away in favor of a single
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
    Promise.all([client.fetchOverlay('firms', date), fetchPipelineFirms()]).then(([mock, real]) => {
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
