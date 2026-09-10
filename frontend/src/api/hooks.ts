import { useEffect, useState } from 'react'
import type { FeatureCollection as MapFeatureCollection, GeoJsonProperties, Geometry } from 'geojson'
import type { FeatureCollection } from './geojson'
import type { BBox, FireEvent, InvestigationReport, OverlayLayerId } from './types'
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

export function useScopedOverlay(
  auditId: string,
  layer: OverlayLayerId,
  date: string | null,
  bbox: BBox | null | undefined,
  enabled: boolean,
): MapFeatureCollection<Geometry, GeoJsonProperties> | null {
  const [data, setData] = useState<MapFeatureCollection<Geometry, GeoJsonProperties> | null>(null)
  const minLon = bbox?.minLon
  const minLat = bbox?.minLat
  const maxLon = bbox?.maxLon
  const maxLat = bbox?.maxLat
  useEffect(() => {
    if (!enabled) {
      setData(null)
      return
    }
    let active = true
    const overlayBbox = minLon == null || minLat == null || maxLon == null || maxLat == null
      ? undefined
      : { minLon, minLat, maxLon, maxLat }
    client.fetchAuditOverlay(auditId, layer, { bbox: overlayBbox, date: date ?? undefined }).then((result) => {
      if (active) setData(result as MapFeatureCollection<Geometry, GeoJsonProperties>)
    })
    return () => { active = false }
  }, [auditId, layer, date, minLon, minLat, maxLon, maxLat, enabled])
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
