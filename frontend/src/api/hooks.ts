import { useEffect, useState } from 'react'
import type { FeatureCollection, PointGeometry } from './geojson'
import type { FireEvent, InvestigationReport, OverlayLayerId } from './types'
import * as client from './client'
import { fetchPipelineFirms, type PipelineFirmsProperties } from './fixtures/pipelineFirms'

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

export function usePipelineFirms(enabled: boolean): FeatureCollection<PointGeometry, PipelineFirmsProperties> | null {
  const [data, setData] = useState<FeatureCollection<PointGeometry, PipelineFirmsProperties> | null>(null)
  useEffect(() => {
    if (!enabled) {
      setData(null)
      return
    }
    let active = true
    fetchPipelineFirms().then((fc) => {
      if (active) setData(fc)
    })
    return () => {
      active = false
    }
  }, [enabled])
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
