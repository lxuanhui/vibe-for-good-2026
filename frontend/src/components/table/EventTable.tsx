import { useMemo, useState } from 'react'
import type { EventStatus, FireEvent, PeatClassification } from '../../api/types'
import { formatDate } from '../../lib/format'
import { useAppStore } from '../../store/useAppStore'
import { ScoreBadge } from '../ui/ScoreBadge'
import { StatusBadge } from '../ui/StatusBadge'

type SortKey = 'id' | 'location' | 'firstDetected' | 'status' | 'supportScore'
type SortDir = 'asc' | 'desc'

const STATUS_FILTERS: { value: EventStatus | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'All statuses' },
  { value: 'AMBIGUOUS', label: 'Ambiguous' },
  { value: 'LIKELY_NON_FIRE', label: 'Likely non-fire' },
  { value: 'STAGE2_RUNNING', label: 'Stage 2 running' },
  { value: 'UNRESOLVED', label: 'Unresolved' },
  { value: 'CONVERGED', label: 'Converged' },
]

const PEAT_LABEL: Record<PeatClassification, string> = {
  protected_dome: 'Protected dome',
  production_zone: 'Production zone',
  not_applicable: 'N/A',
}

export function EventTable({ events }: { events: FireEvent[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('firstDetected')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [statusFilter, setStatusFilter] = useState<EventStatus | 'ALL'>('ALL')
  const selectedEventId = useAppStore((s) => s.selectedEventId)
  const selectEvent = useAppStore((s) => s.selectEvent)

  const rows = useMemo(() => {
    const filtered = events.filter((e) => statusFilter === 'ALL' || e.status === statusFilter)
    const dir = sortDir === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => {
      switch (sortKey) {
        case 'id':
          return a.id.localeCompare(b.id) * dir
        case 'location':
          return a.location.localeCompare(b.location) * dir
        case 'firstDetected':
          return a.firstDetected.localeCompare(b.firstDetected) * dir
        case 'status':
          return a.status.localeCompare(b.status) * dir
        case 'supportScore':
          return ((a.supportScore ?? -1) - (b.supportScore ?? -1)) * dir
      }
    })
  }, [events, statusFilter, sortKey, sortDir])

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  function SortHeader({ sortableKey, label }: { sortableKey: SortKey; label: string }) {
    return (
      <button
        onClick={() => toggleSort(sortableKey)}
        className="flex items-center gap-1 text-[11px] font-semibold tracking-wide text-text-faint uppercase hover:text-text-muted"
      >
        {label}
        {sortKey === sortableKey && <span>{sortDir === 'asc' ? '↑' : '↓'}</span>}
      </button>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border p-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as EventStatus | 'ALL')}
          className="w-full rounded border border-border-strong bg-panel-raised px-2 py-1.5 text-xs text-text"
        >
          {STATUS_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 bg-panel">
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left">
                <SortHeader sortableKey="id" label="Event / complex ID" />
              </th>
              <th className="px-3 py-2 text-left">
                <SortHeader sortableKey="location" label="Location" />
              </th>
              <th className="px-3 py-2 text-left">
                <SortHeader sortableKey="firstDetected" label="First detected" />
              </th>
              <th className="px-3 py-2 text-left">
                <SortHeader sortableKey="status" label="Status" />
              </th>
              <th className="px-3 py-2 text-left text-[11px] font-semibold tracking-wide text-text-faint uppercase">
                Top hypothesis
              </th>
              <th className="px-3 py-2 text-left">
                <SortHeader sortableKey="supportScore" label="Support" />
              </th>
              <th className="px-3 py-2 text-left text-[11px] font-semibold tracking-wide text-text-faint uppercase">
                Peat class.
              </th>
              <th className="px-3 py-2 text-left text-[11px] font-semibold tracking-wide text-text-faint uppercase">
                Days since surface
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((event) => (
              <tr
                key={event.id}
                onClick={() => selectEvent(event.id)}
                className={`cursor-pointer border-b border-border/60 hover:bg-panel-raised ${
                  selectedEventId === event.id ? 'bg-panel-raised' : ''
                }`}
              >
                <td className="px-3 py-2 font-mono">{event.id}</td>
                <td className="px-3 py-2 text-text-muted">{event.location}</td>
                <td className="px-3 py-2 whitespace-nowrap text-text-muted">{formatDate(event.firstDetected)}</td>
                <td className="px-3 py-2">
                  <StatusBadge status={event.status} />
                </td>
                <td className="max-w-[160px] truncate px-3 py-2 text-text-muted" title={event.topHypothesis}>
                  {event.topHypothesis ?? '—'}
                </td>
                <td className="px-3 py-2">
                  {event.supportScore != null ? (
                    <ScoreBadge score={event.supportScore} showLabel={false} />
                  ) : (
                    '—'
                  )}
                </td>
                <td className="px-3 py-2 text-text-muted">{PEAT_LABEL[event.peatClassification]}</td>
                <td className="px-3 py-2 text-text-muted">{event.daysSinceLastSurfaceDetection ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
