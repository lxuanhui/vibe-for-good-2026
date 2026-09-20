import type { Feature, FeatureCollection, Polygon } from 'geojson'
import type { BBox, HydrologyLayerId } from '../types'

// A labelled demo fixture, not data. The hydrology overlay routes read a
// cached SMAP L4 PEATCLSM subset that was never materialised (#280), so in
// production they answer `status: "unavailable"` and the scoped map had
// nothing to draw for Groundwater, PEATCLSM water flux or Soil moisture.
// Owner's call for the 2026-09-11 demo: draw a deterministic synthetic
// field, marked "Illustrative" wherever it appears, so the presentation can
// be shown. Retiring it is #284. Nothing here may reach evidence, analysis
// or the audit pack; the only consumer is the map paint.

export interface IllustrativeHydrologyProperties {
  /** In the layer's real unit, so the legend copy stays true to the units. */
  value: number
  /** 0 to 1 over the layer's plausible range, the only thing paint reads. */
  weight: number
  illustrative: true
}

export const HYDROLOGY_PLACEHOLDER_LABEL = 'Illustrative'

// SMAP L4 is a 9 km product; a cell of the same size keeps the placeholder
// from looking finer than the data it stands in for.
const CELL_DEG = 0.09
const MAX_CELLS = 4000

// Plausible ranges for Sumatran and Kalimantan peat in a dry haze season.
// Groundwater is water-table depth below the peat surface (m), so 0 is
// saturated and the top of the range is deeply drained; flux is the
// free-surface water flux (kg m-2 s-1); soil moisture is the 0-5 cm surface
// layer (m3/m3). The ranges bound the fake values; they are not measurements.
export const HYDROLOGY_PLACEHOLDER_RANGES: Record<HydrologyLayerId, { min: number; max: number; unit: string }> = {
  groundwater: { min: 0, max: 1.5, unit: 'm' },
  peatclsm: { min: 0, max: 2e-5, unit: 'kg m-2 s-1' },
  'soil-moisture': { min: 0.15, max: 0.45, unit: 'm3/m3' },
}

// Each layer gets its own phase so the three fields do not look like one
// recoloured picture; the date shifts the phase so scrubbing the timeline
// visibly changes something without pretending to be a time series.
const LAYER_PHASE: Record<HydrologyLayerId, number> = { groundwater: 0.7, peatclsm: 2.9, 'soil-moisture': 4.4 }

function daySeed(date: string | null): number {
  if (!date) return 0
  let hash = 0
  for (const char of date) hash = (hash * 31 + char.charCodeAt(0)) % 1_000_003
  return (hash % 97) / 97
}

// Sum of a few low-frequency sines plus a hashed grain. Deterministic for a
// given cell and seed, so React re-renders and repeated toggles draw the
// same picture and a test can assert on it.
function fieldValue(lon: number, lat: number, seed: number): number {
  const broad = Math.sin(lon * 6.1 + seed) * Math.cos(lat * 5.3 - seed * 0.5)
  const ridge = Math.sin((lon + lat) * 13.7 + seed * 2)
  const grain = Math.sin(lon * 12.9898 + lat * 78.233 + seed) * 43758.5453
  const noise = grain - Math.floor(grain)
  return Math.min(1, Math.max(0, 0.5 + 0.32 * broad + 0.14 * ridge + 0.08 * (noise - 0.5)))
}

export function illustrativeHydrologyField(
  layer: HydrologyLayerId,
  bbox: BBox,
  date: string | null,
): FeatureCollection<Polygon, IllustrativeHydrologyProperties> {
  const width = Math.max(0, bbox.maxLon - bbox.minLon)
  const height = Math.max(0, bbox.maxLat - bbox.minLat)
  // A wide buffer would otherwise produce tens of thousands of polygons;
  // coarsen the grid rather than truncate the coverage.
  const step = Math.max(CELL_DEG, Math.sqrt((width * height) / MAX_CELLS))
  const range = HYDROLOGY_PLACEHOLDER_RANGES[layer]
  const seed = LAYER_PHASE[layer] + daySeed(date)
  const features: Feature<Polygon, IllustrativeHydrologyProperties>[] = []
  for (let lat = bbox.minLat; lat < bbox.maxLat; lat += step) {
    for (let lon = bbox.minLon; lon < bbox.maxLon; lon += step) {
      const east = Math.min(lon + step, bbox.maxLon)
      const north = Math.min(lat + step, bbox.maxLat)
      const weight = fieldValue(lon + step / 2, lat + step / 2, seed)
      features.push({
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [[[lon, lat], [east, lat], [east, north], [lon, north], [lon, lat]]] },
        properties: { value: range.min + weight * (range.max - range.min), weight, illustrative: true },
      })
    }
  }
  return { type: 'FeatureCollection', features }
}
