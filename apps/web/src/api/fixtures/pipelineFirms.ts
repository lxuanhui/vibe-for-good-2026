import type { FeatureCollection, PointGeometry } from '../geojson'
import { isInsideIndonesia } from '../../lib/indonesiaGeo'

// STILL FAKE, in the sense that matters here: a real NASA FIRMS pull (see
// data_pipeline/README.md and export_web_geojson.py) but a one-off static
// snapshot -- the 2019-09-01..05 Sumatra/Kalimantan haze window, 21,519
// hotspots -- not a live query. Served from public/pipeline/ and fetched at
// runtime (not bundled) for a quick "does pipeline output actually render
// on the map" proof of concept, temporally scoped by date same as every
// other overlay (see fixtures/overlays.ts) -- see fixtures/dates.ts, which
// populates the timeline's date config directly from PIPELINE_FIRMS_DATES
// below (and the mock per-case detections) rather than a disconnected
// fixed calendar window.
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

// Matches the top-level date keys in public/pipeline/firms-2019-09.json --
// export_web_geojson.py buckets by acq_date, so this is the exact set of
// dates the real pull actually has data for.
export const PIPELINE_FIRMS_DATES = ['2019-09-01', '2019-09-02', '2019-09-03', '2019-09-04', '2019-09-05'] as const

export const PIPELINE_FIRMS_DATE_RANGE = [
  PIPELINE_FIRMS_DATES[0],
  PIPELINE_FIRMS_DATES[PIPELINE_FIRMS_DATES.length - 1],
] as const

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

type ByDate = Record<string, FeatureCollection<PointGeometry, PipelineFirmsProperties>>

let cached: Promise<ByDate> | null = null

function loadByDate(): Promise<ByDate> {
  if (!cached) {
    cached = fetch('/pipeline/firms-2019-09.json').then((res) => res.json())
  }
  return cached
}

export async function fetchPipelineFirms(date: string): Promise<FeatureCollection<PointGeometry, PipelineFirmsProperties>> {
  const byDate = await loadByDate()
  const features = byDate[date]?.features ?? []
  return { type: 'FeatureCollection', features: features.filter(isCleanHotspot) }
}
