// Fixture timeline window: 10 days ending "today" for the demo dataset.
export const TIMELINE_END = '2026-09-07'
export const TIMELINE_DAYS = 10

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export const TIMELINE_DATES: string[] = Array.from({ length: TIMELINE_DAYS }, (_, i) => {
  const d = new Date(TIMELINE_END + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() - (TIMELINE_DAYS - 1 - i))
  return isoDate(d)
})

// FIRMS overpasses Indonesia ~2x/day; near-daily coverage with one realistic gap.
export const FIRMS_AVAILABLE_DATES = new Set(TIMELINE_DATES.filter((d) => d !== '2026-09-03'))

// Sentinel-1 nominal ~6-day revisit — sparse by design, not a UI simplification.
export const SAR_AVAILABLE_DATES = new Set(['2026-08-29', '2026-09-04'])

// Cloud-free Sentinel-2 passes are intermittent.
export const S2_AVAILABLE_DATES = new Set(['2026-08-30', '2026-09-02', '2026-09-06'])
