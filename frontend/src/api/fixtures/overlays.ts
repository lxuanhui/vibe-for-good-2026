import {
  featureCollection,
  type Feature,
  type FeatureCollection,
  type LineStringGeometry,
  type PointGeometry,
  type PolygonGeometry,
  type Position,
} from '../geojson'
import type { OverlayLayerId, RasterLayerId } from '../types'
import { FIRMS_AVAILABLE_DATES, SAR_AVAILABLE_DATES, S2_AVAILABLE_DATES } from './dates'
import { ALL_EVENTS, CASE_B, CASE_C } from './events'

export interface FirmsProperties {
  eventId: string
  frp: number
  confidence: string
  satellite: string
  instrument: string
  acquiredAt: string
}

export interface SarBackscatterProperties {
  eventId: string
  vhDropDb: number
  persistenceDays: number
}

export interface KhgProperties {
  khgId: string
  classification: 'protected_dome' | 'production_zone'
}

export interface ConcessionProperties {
  concessionName: string
  holder: string
  concessionType: string
}

export interface FireComplexLinkProperties {
  fireComplexId: string
  daysElapsed: number
}

function square(center: Position, halfWidthDeg: number): Position[][] {
  const [lon, lat] = center
  return [
    [
      [lon - halfWidthDeg, lat - halfWidthDeg],
      [lon + halfWidthDeg, lat - halfWidthDeg],
      [lon + halfWidthDeg, lat + halfWidthDeg],
      [lon - halfWidthDeg, lat + halfWidthDeg],
      [lon - halfWidthDeg, lat - halfWidthDeg],
    ],
  ]
}

// FAKE DATA -- replace with a real endpoint call when the backend exists.
// Target: GET /api/overlays/firms?bbox={minLon,minLat,maxLon,maxLat}&date={date}
// (assurance_console_ui_spec.md Section 2.2 -- same contract as every other
// overlay, see isLayerAvailable/getOverlay below), returning this same
// FeatureCollection<PointGeometry, FirmsProperties> shape. That endpoint's
// backing ingestion is NASA FIRMS's area/csv API, proven out in
// data_pipeline/sources/nasa_firms.py (fetch_area()) -- MAP_KEY-gated,
// day_range capped at 5, ~daily cadence (VIIRS ~2x/day overpass); see
// data_pipeline/README.md. Once that Worker exists, delete this function
// (and fixtures/pipelineFirms.ts + public/pipeline/, the interim static
// stand-in -- see hooks.ts useFirms()) and call client.fetchOverlay('firms',
// date) exactly as today; no caller changes needed.
function firmsForDate(date: string): FeatureCollection<PointGeometry, FirmsProperties> {
  if (!FIRMS_AVAILABLE_DATES.has(date)) return featureCollection([])
  const features: Feature<PointGeometry, FirmsProperties>[] = []
  for (const event of ALL_EVENTS) {
    for (const d of event.detections) {
      if (d.acquiredAt.slice(0, 10) !== date) continue
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [event.lon, event.lat] },
        properties: {
          eventId: event.id,
          frp: d.frp,
          confidence: d.confidence,
          satellite: d.satellite,
          instrument: d.instrument,
          acquiredAt: d.acquiredAt,
        },
      })
    }
  }
  return featureCollection(features)
}

const SAR_PASS_INDEX: Record<string, number> = { '2026-08-29': 0, '2026-09-04': 1 }

function sarBackscatterForDate(date: string): FeatureCollection<PointGeometry, SarBackscatterProperties> {
  if (!SAR_AVAILABLE_DATES.has(date)) return featureCollection([])
  const passIndex = SAR_PASS_INDEX[date] ?? 0
  // Case C shows a persistent VH-backscatter drop across both passes — the
  // deterministic signal FireComplex linking keys off. Case B shows a single
  // pass with no persistence trend.
  const features: Feature<PointGeometry, SarBackscatterProperties>[] = [
    {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [CASE_C.lon, CASE_C.lat] },
      properties: {
        eventId: CASE_C.id,
        vhDropDb: passIndex === 0 ? -3.1 : -4.6,
        persistenceDays: passIndex === 0 ? 0 : 6,
      },
    },
  ]
  if (passIndex === 0) {
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [CASE_B.lon, CASE_B.lat] },
      properties: { eventId: CASE_B.id, vhDropDb: -1.2, persistenceDays: 0 },
    })
  }
  return featureCollection(features)
}

const KHG_POLYGONS: FeatureCollection<PolygonGeometry, KhgProperties> = featureCollection([
  {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: square([CASE_C.lon, CASE_C.lat], 0.06) },
    properties: { khgId: 'KHG-KT-0417', classification: 'protected_dome' },
  },
  {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: square([CASE_B.lon, CASE_B.lat], 0.05) },
    properties: { khgId: 'KHG-SS-1122', classification: 'production_zone' },
  },
])

const CONCESSIONS: FeatureCollection<PointGeometry, ConcessionProperties> = featureCollection([
  {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [CASE_B.lon + 0.01, CASE_B.lat - 0.01] },
    properties: {
      concessionName: 'PT Sawit Lestari Makmur (illustrative)',
      holder: 'PT Sawit Lestari Makmur (illustrative)',
      concessionType: 'oil_palm',
    },
  },
])

const FIRE_COMPLEX_LINKS: FeatureCollection<LineStringGeometry, FireComplexLinkProperties> = featureCollection([
  {
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates: [
        [CASE_C.lon - 0.018, CASE_C.lat + 0.006],
        [CASE_C.lon, CASE_C.lat],
      ],
    },
    properties: { fireComplexId: CASE_C.fireComplexId ?? '', daysElapsed: 6 },
  },
])

export function isLayerAvailable(layer: OverlayLayerId | RasterLayerId, date: string): boolean {
  switch (layer) {
    case 'firms':
      return FIRMS_AVAILABLE_DATES.has(date)
    case 'sar-backscatter':
    case 'sar-visualization':
      return SAR_AVAILABLE_DATES.has(date)
    case 's2-quicklook':
      return S2_AVAILABLE_DATES.has(date)
    case 'khg':
    case 'concessions':
    case 'fire-complex-links':
      return true
  }
}

export function getOverlay(layer: OverlayLayerId, date: string) {
  switch (layer) {
    case 'firms':
      return firmsForDate(date)
    case 'sar-backscatter':
      return sarBackscatterForDate(date)
    case 'khg':
      return KHG_POLYGONS
    case 'concessions':
      return CONCESSIONS
    case 'fire-complex-links':
      return FIRE_COMPLEX_LINKS
  }
}
