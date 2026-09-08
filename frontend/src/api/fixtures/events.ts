import type { FireEvent } from '../types'

// NOTE: /api/events is served from backend/app/data/events.json, which is the
// authoritative copy. This file is kept because fixtures/overlays.ts anchors
// its overlay geometry to these coordinates -- change an event's position
// here and the backend copy must move with it, or the overlays will sit away
// from the detection they describe. It is no longer read by client.ts.

// Case A — obvious non-fire: persistent industrial heat source at a
// Pekanbaru facility. Demonstrates cheap Stage-1 triage saving investigation
// budget.
export const CASE_A: FireEvent = {
  id: 'IND-01120',
  lat: 0.507,
  lon: 101.447,
  location: 'Pekanbaru, Riau',
  firstDetected: '2026-09-05T06:12:00Z',
  status: 'LIKELY_NON_FIRE',
  qualifiesForInvestigation: false,
  peatClassification: 'not_applicable',
  detections: [
    {
      detectionId: 'IND-01120-D1',
      acquiredAt: '2026-09-05T06:12:00Z',
      satellite: 'N',
      instrument: 'VIIRS',
      frp: 6.1,
      confidence: 'nominal',
    },
    {
      detectionId: 'IND-01120-D2',
      acquiredAt: '2026-09-06T06:05:00Z',
      satellite: 'N',
      instrument: 'VIIRS',
      frp: 5.8,
      confidence: 'nominal',
    },
  ],
  currentConditions: {
    temperatureC: 31.4,
    relativeHumidity: 58,
    windSpeedKmh: 9,
    windDirectionDeg: 140,
    recentRainfallMm: 0,
  },
}

// Case B — environmentally plausible fire on a production-zone peat area.
// Demonstrates the system deprioritising rather than accusing: strongest
// support lands on regional fire-weather conditions, not plantation activity.
export const CASE_B: FireEvent = {
  id: 'IND-01894',
  lat: -3.021,
  lon: 104.702,
  location: 'Ogan Komering Ilir, South Sumatra',
  firstDetected: '2026-09-02T14:18:00Z',
  status: 'CONVERGED',
  qualifiesForInvestigation: true,
  topHypothesis: 'H1 — Environmental / regional fire-weather conditions',
  supportScore: 82,
  peatClassification: 'production_zone',
  detections: [
    {
      detectionId: 'IND-01894-D1',
      acquiredAt: '2026-09-02T14:18:00Z',
      satellite: 'N',
      instrument: 'VIIRS',
      frp: 18.4,
      confidence: 'nominal',
    },
    {
      detectionId: 'IND-01894-D2',
      acquiredAt: '2026-09-03T02:41:00Z',
      satellite: 'A',
      instrument: 'MODIS',
      frp: 22.1,
      confidence: 'high',
    },
    {
      detectionId: 'IND-01894-D3',
      acquiredAt: '2026-09-04T14:02:00Z',
      satellite: 'N',
      instrument: 'VIIRS',
      frp: 11.6,
      confidence: 'nominal',
    },
  ],
  currentConditions: {
    temperatureC: 29.8,
    relativeHumidity: 71,
    windSpeedKmh: 12,
    windDirectionDeg: 200,
    recentRainfallMm: 8.4,
  },
}

// Case C — the flagship fire-complex resurfacing hypothesis. FIRMS has an
// observation gap after day 3, Sentinel-1 records a VH change, and a later
// detection 2km away lies in the same mapped peat unit and inside the
// first-order surface-fire compatibility envelope. See
// `Environmental_Assurance_Spec.md` §12 (FireEventGraph), §14 (surface
// fire-growth compatibility), and §15 (peat-aware reasoning).
export const CASE_C: FireEvent = {
  id: 'IND-02671',
  fireComplexId: 'FC-2026-0091',
  lat: -2.734,
  lon: 114.083,
  location: 'Pulang Pisau, Central Kalimantan',
  firstDetected: '2026-08-29T05:40:00Z',
  status: 'UNRESOLVED',
  qualifiesForInvestigation: true,
  topHypothesis: 'Resurfaced fire complex (peat-mediated persistence)',
  supportScore: 78,
  peatClassification: 'protected_dome',
  daysSinceLastSurfaceDetection: 6,
  detections: [
    {
      detectionId: 'IND-02671-D1',
      acquiredAt: '2026-08-29T05:40:00Z',
      satellite: 'N',
      instrument: 'VIIRS',
      frp: 14.2,
      confidence: 'nominal',
    },
    {
      detectionId: 'IND-02671-D2',
      acquiredAt: '2026-08-30T05:33:00Z',
      satellite: 'N',
      instrument: 'VIIRS',
      frp: 9.7,
      confidence: 'nominal',
    },
    {
      detectionId: 'IND-02671-D3',
      acquiredAt: '2026-09-01T17:52:00Z',
      satellite: 'A',
      instrument: 'MODIS',
      frp: 4.3,
      confidence: 'low',
    },
    {
      detectionId: 'IND-02671-D4',
      acquiredAt: '2026-09-07T05:21:00Z',
      satellite: 'N',
      instrument: 'VIIRS',
      frp: 19.8,
      confidence: 'high',
    },
  ],
  currentConditions: {
    temperatureC: 27.9,
    relativeHumidity: 84,
    windSpeedKmh: 6,
    windDirectionDeg: 95,
    recentRainfallMm: 2.1,
  },
}

export const ALL_EVENTS: FireEvent[] = [CASE_A, CASE_B, CASE_C]
