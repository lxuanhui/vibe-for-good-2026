import indonesiaBoundary from '../assets/indonesia-province-simple.json'

// Point-in-polygon gating against the same province boundary data the map
// renders, instead of modeling Malaysia (or open water) as separate shapes.
// A hotspot counts as "in Indonesia" only if it falls inside actual land --
// anything else (Malaysia, the strait, open water) is dropped by construction.

type Ring = number[][]
type PolygonRings = Ring[] // [exterior, ...holes]

interface IndexedFeature {
  bbox: [number, number, number, number] // [minLon, minLat, maxLon, maxLat]
  polygons: PolygonRings[]
}

function pointInRing(lon: number, lat: number, ring: Ring): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

// rings[0] is the exterior; any further rings are holes to subtract.
function pointInPolygon(lon: number, lat: number, rings: PolygonRings): boolean {
  if (!pointInRing(lon, lat, rings[0])) return false
  for (let i = 1; i < rings.length; i++) {
    if (pointInRing(lon, lat, rings[i])) return false
  }
  return true
}

const indexed: IndexedFeature[] = (
  indonesiaBoundary as {
    features: { geometry: { type: string; coordinates: unknown } }[]
  }
).features.map((f) => {
  const geom = f.geometry
  const polygons: PolygonRings[] = geom.type === 'MultiPolygon' ? (geom.coordinates as PolygonRings[]) : [geom.coordinates as PolygonRings]
  const allLons = polygons.flatMap((p) => p[0].map((pt) => pt[0]))
  const allLats = polygons.flatMap((p) => p[0].map((pt) => pt[1]))
  return {
    bbox: [Math.min(...allLons), Math.min(...allLats), Math.max(...allLons), Math.max(...allLats)],
    polygons,
  }
})

export function isInsideIndonesia(lon: number, lat: number): boolean {
  for (const { bbox, polygons } of indexed) {
    if (lon < bbox[0] || lon > bbox[2] || lat < bbox[1] || lat > bbox[3]) continue
    for (const rings of polygons) {
      if (pointInPolygon(lon, lat, rings)) return true
    }
  }
  return false
}
