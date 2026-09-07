import { useEffect } from 'react'
import { TIMELINE_DATES } from '../../api/fixtures/dates'
import { isLayerAvailable } from '../../api/fixtures/overlays'
import type { OverlayLayerId, RasterLayerId } from '../../api/types'
import { formatDate } from '../../lib/format'
import { useAppStore } from '../../store/useAppStore'

const DATE_GATED_LAYERS: { id: OverlayLayerId | RasterLayerId; label: string }[] = [
  { id: 'firms', label: 'FIRMS' },
  { id: 'sar-backscatter', label: 'SAR' },
  { id: 's2-quicklook', label: 'S2' },
]

export function TimelineScrubber() {
  const activeDate = useAppStore((s) => s.activeDate)
  const setActiveDate = useAppStore((s) => s.setActiveDate)
  const isPlaying = useAppStore((s) => s.isPlaying)
  const togglePlaying = useAppStore((s) => s.togglePlaying)

  useEffect(() => {
    if (!isPlaying) return
    const id = setInterval(() => {
      const current = useAppStore.getState().activeDate
      const idx = TIMELINE_DATES.indexOf(current)
      setActiveDate(TIMELINE_DATES[(idx + 1) % TIMELINE_DATES.length])
    }, 1200)
    return () => clearInterval(id)
  }, [isPlaying, setActiveDate])

  return (
    <div className="pointer-events-auto rounded-lg border border-border-strong bg-panel/95 p-3 shadow-lg backdrop-blur">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold tracking-wide text-text-faint uppercase">Timeline</span>
        <div className="flex items-center gap-1.5">
          {DATE_GATED_LAYERS.map((l) => {
            const available = isLayerAvailable(l.id, activeDate)
            return (
              <span
                key={l.id}
                className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                  available ? 'bg-status-good/15 text-status-good' : 'bg-border text-text-faint'
                }`}
                title={
                  available
                    ? `${l.label} data available on ${formatDate(activeDate)}`
                    : `No ${l.label} pass on ${formatDate(activeDate)}`
                }
              >
                {l.label}
              </span>
            )
          })}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={togglePlaying}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-accent text-[10px] text-bg"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? '❚❚' : '▶'}
        </button>
        <div className="flex flex-1 gap-1">
          {TIMELINE_DATES.map((date) => (
            <button
              key={date}
              onClick={() => setActiveDate(date)}
              className={`flex-1 rounded py-1 text-center text-[10px] transition-colors ${
                date === activeDate ? 'bg-accent font-semibold text-bg' : 'bg-panel-raised text-text-muted hover:text-text'
              }`}
              title={formatDate(date)}
            >
              {date.slice(8, 10)}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
