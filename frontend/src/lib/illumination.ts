import type { FeatureCollection, Polygon } from 'geojson'

const DEGREE = Math.PI / 180
const SOLAR_GRID_STEP = 5

function normaliseLongitude(longitude: number): number {
  const wrapped = ((longitude + 540) % 360) - 180
  return Math.max(-180, Math.min(180, wrapped))
}

function solarDeclination(date: Date): number {
  const start = Date.UTC(date.getUTCFullYear(), 0, 0)
  const dayOfYear = (date.getTime() - start) / 86_400_000
  const hour = date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600
  const gamma = (2 * Math.PI / 365) * (dayOfYear - 1 + (hour - 12) / 24)
  return 0.006918 - 0.399912 * Math.cos(gamma) + 0.070257 * Math.sin(gamma) - 0.006758 * Math.cos(2 * gamma) + 0.000907 * Math.sin(2 * gamma) - 0.002697 * Math.cos(3 * gamma) + 0.00148 * Math.sin(3 * gamma)
}

function equationOfTimeMinutes(date: Date): number {
  const start = Date.UTC(date.getUTCFullYear(), 0, 0)
  const dayOfYear = (date.getTime() - start) / 86_400_000
  const gamma = (2 * Math.PI / 365) * (dayOfYear - 1)
  return 229.18 * (0.000075 + 0.001868 * Math.cos(gamma) - 0.032077 * Math.sin(gamma) - 0.014615 * Math.cos(2 * gamma) - 0.040849 * Math.sin(2 * gamma))
}

function terminatorLongitude(latitude: number, declination: number, subsolarLongitude: number): [number, number] {
  const hourAngle = Math.acos(Math.max(-1, Math.min(1, -Math.tan(latitude * DEGREE) * Math.tan(declination)))) / DEGREE
  return [normaliseLongitude(subsolarLongitude + hourAngle * 15), normaliseLongitude(subsolarLongitude - hourAngle * 15)]
}

/**
 * Returns the portion of the world in solar night at the supplied instant.
 * It is a visual orientation layer only. The coarse five-degree grid keeps
 * timeline changes cheap and avoids treating illumination as evidence.
 */
export function nightCoverage(date: Date): FeatureCollection<Polygon> {
  const declination = solarDeclination(date)
  const subsolarLongitude = normaliseLongitude(-(date.getUTCHours() * 60 + date.getUTCMinutes() + equationOfTimeMinutes(date)) / 4)
  const evening: [number, number][] = []
  const morning: [number, number][] = []

  for (let latitude = -90; latitude <= 90; latitude += SOLAR_GRID_STEP) {
    const [sunset, sunrise] = terminatorLongitude(latitude, declination, subsolarLongitude)
    evening.push([sunset, latitude])
    morning.push([sunrise, latitude])
  }

  const ring: [number, number][] = [
    ...evening,
    [180, 90],
    [-180, 90],
    ...morning.reverse(),
    [-180, -90],
    [180, -90],
    evening[0],
  ]

  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { reference: date.toISOString() }, geometry: { type: 'Polygon', coordinates: [ring] } }] }
}

export function illuminationReference(activeDay: string | null, now: Date): Date {
  return activeDay ? new Date(`${activeDay}T12:00:00Z`) : now
}
