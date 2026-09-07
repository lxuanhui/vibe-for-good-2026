import type { FeatureCollection, PointGeometry } from '../geojson'
import { isInsideIndonesia } from '../../lib/indonesiaGeo'

// STILL FAKE, in the sense that matters here: a real NASA FIRMS pull (see
// data_pipeline/README.md and export_web_geojson.py) but a one-off static
// snapshot -- the 2019-09-01..05 Sumatra/Kalimantan haze window, 21,519
// hotspots -- not a live query. Served from public/pipeline/ and fetched at
// runtime (not bundled) for a quick "does pipeline output actually render
// on the map" proof of concept; not wired to the demo timeline scrubber
// (dates don't overlap the 2026 mock case dates in fixtures/dates.ts).
//
// Merged into the 'firms' layer alongside the mock per-case detections --
// see hooks.ts useFirms(). Delete this whole file + public/pipeline/ once
// GET /api/overlays/firms?bbox=...&date=... is real (same target as the
// mock generator -- see fixtures/overlays.ts firmsForDate()): that endpoint
// replaces both fake sources with one live, bbox/date-filtered query.

export interface PipelineFirmsProperties {
  frp: number
  confidence: 'low' | 'nominal' | 'high'
  acquiredAt: string
}

export const PIPELINE_FIRMS_DATE_RANGE = ['2019-09-01', '2019-09-05'] as const

// Indonesia's overall extent (Sabang to Merauke, Aceh to Rote) -- a cheap
// reject before the real point-in-polygon check below.
const INDONESIA_BBOX = { minLon: 94, maxLon: 142, minLat: -12, maxLat: 7 }

function isCleanHotspot(f: { geometry: PointGeometry; properties: PipelineFirmsProperties }): boolean {
  const [lon, lat] = f.geometry.coordinates

  // 1. Broad cheap bounding box.
  if (lon < INDONESIA_BBOX.minLon || lon > INDONESIA_BBOX.maxLon || lat < INDONESIA_BBOX.minLat || lat > INDONESIA_BBOX.maxLat) {
    return false
  }

  // 2. Exact Indonesia land geometry -- gates out Malaysia, the strait, and
  // open water in one check, no need to model any of them separately.
  if (!isInsideIndonesia(lon, lat)) return false

  // 3. FIRMS quality filtering -- low-confidence detections are more often
  // false positives (flares, sensor noise) than real fires.
  if (f.properties.confidence === 'low') return false

  return true
}

let cached: Promise<FeatureCollection<PointGeometry, PipelineFirmsProperties>> | null = null

export function fetchPipelineFirms(): Promise<FeatureCollection<PointGeometry, PipelineFirmsProperties>> {
  if (!cached) {
    cached = fetch('/pipeline/firms-2019-09.json')
      .then((res) => res.json())
      .then((byDate: Record<string, FeatureCollection<PointGeometry, PipelineFirmsProperties>>) => ({
        type: 'FeatureCollection' as const,
        features: Object.values(byDate).flatMap((fc) => fc.features).filter(isCleanHotspot),
      }))
  }
  return cached
}
