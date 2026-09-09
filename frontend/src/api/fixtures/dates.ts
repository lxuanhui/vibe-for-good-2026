import { ALL_EVENTS } from './events'
import { PIPELINE_FIRMS_DATES } from './pipelineFirms'

// Every date with an actual FIRMS thermal-hotspot detection -- the mock
// per-case detections (events.ts) and the real NASA FIRMS pipeline pull
// (pipelineFirms.ts) -- populates the timeline directly, instead of a fixed
// 10-day calendar window carrying its own separately hand-maintained
// availability list (which had drifted out of sync with the actual mock
// data: it excluded 2026-09-03, which has a real detection, while including
// 2026-08-31, which has none).
const MOCK_FIRMS_DATES = new Set(ALL_EVENTS.flatMap((e) => e.detections.map((d) => d.acquiredAt.slice(0, 10))))

// ISO 'YYYY-MM-DD' strings sort chronologically as plain strings. The real
// pipeline's 2019 window and the mock demo's 2026 window don't overlap, so
// this reads as two clusters -- the timeline scrubber renders whatever's
// here, in order, with no assumption of evenly-spaced consecutive days.
export const TIMELINE_DATES: string[] = Array.from(new Set([...MOCK_FIRMS_DATES, ...PIPELINE_FIRMS_DATES])).sort()

// By construction every timeline date has FIRMS coverage from at least one
// source -- kept as its own export since isLayerAvailable('firms', date)
// (fixtures/overlays.ts) reads it independently of TIMELINE_DATES. Also once
// backed a per-layer availability badge in the deleted TimelineScrubber.tsx;
// rebuild that against this same set if a scrubber returns.
export const FIRMS_AVAILABLE_DATES = new Set(TIMELINE_DATES)

// Sentinel-1 nominal ~6-day revisit — sparse by design, not a UI simplification.
export const SAR_AVAILABLE_DATES = new Set(['2026-08-29', '2026-09-04'])

// Cloud-free Sentinel-2 passes are intermittent.
export const S2_AVAILABLE_DATES = new Set(['2026-08-30', '2026-09-02', '2026-09-06'])
