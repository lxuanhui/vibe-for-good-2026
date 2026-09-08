import { useMemo, useState } from 'react'
import type {
  EvidenceSufficiency,
  FireEvent,
  InvestigationPriority,
  ReviewState,
  ScopeRelation,
} from '../../api/types'
import { formatDateTime } from '../../lib/format'
import { useAppStore } from '../../store/useAppStore'

type SortKey = 'id' | 'firstDetected' | 'durationHours' | 'observationCount' | 'investigationPriorityScore'
type SortDir = 'asc' | 'desc'

const SCOPE_RELATIONS: ScopeRelation[] = ['INSIDE_SCOPE', 'BOUNDARY_INTERSECTING', 'EXTERNAL_CONTEXT']
const SUFFICIENCIES: EvidenceSufficiency[] = ['SUFFICIENT', 'PARTIAL', 'INSUFFICIENT']
const PRIORITIES: InvestigationPriority[] = ['URGENT', 'HIGH', 'MEDIUM', 'LOW']
const REVIEW_STATES: ReviewState[] = ['UNREVIEWED', 'IN_REVIEW', 'REVIEWED']

function MultiFilter({
  label,
  values,
  selected,
  onChange,
}: {
  label: string
  values: string[]
  selected: string[]
  onChange: (values: string[]) => void
}) {
  return (
    <label className="flex min-w-[145px] flex-col gap-1 text-[10px] font-semibold tracking-wide text-text-faint uppercase">
      {label}
      <select
        multiple
        value={selected}
        onChange={(event) => onChange(Array.from(event.target.selectedOptions, (option) => option.value))}
        className="h-16 rounded border border-border-strong bg-panel-raised px-1 text-[11px] font-normal normal-case text-text"
      >
        {values.map((value) => (
          <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>
        ))}
      </select>
    </label>
  )
}

function SortHeader({
  sortableKey,
  label,
  sortKey,
  sortDir,
  onSort,
}: {
  sortableKey: SortKey
  label: string
  sortKey: SortKey
  sortDir: SortDir
  onSort: (key: SortKey) => void
}) {
  return (
    <button onClick={() => onSort(sortableKey)} className="flex items-center gap-1 whitespace-nowrap text-[10px] font-semibold tracking-wide text-text-faint uppercase hover:text-text-muted">
      {label}{sortKey === sortableKey && <span>{sortDir === 'asc' ? '↑' : '↓'}</span>}
    </button>
  )
}

export function EventTable({ events }: { events: FireEvent[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('firstDetected')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [dateStart, setDateStart] = useState('')
  const [dateEnd, setDateEnd] = useState('')
  const [scopeFilter, setScopeFilter] = useState<string[]>([])
  const [peatFilter, setPeatFilter] = useState<string[]>([])
  const [evidenceFilter, setEvidenceFilter] = useState<string[]>([])
  const [priorityFilter, setPriorityFilter] = useState<string[]>([])
  const [reviewFilter, setReviewFilter] = useState<string[]>([])
  const selectedEventId = useAppStore((state) => state.selectedEventId)
  const selectedEventIds = useAppStore((state) => state.selectedEventIds)
  const selectEvent = useAppStore((state) => state.selectEvent)
  const toggleEventSelection = useAppStore((state) => state.toggleEventSelection)
  const clearEventSelection = useAppStore((state) => state.clearEventSelection)
  const investigateSelected = useAppStore((state) => state.investigateSelected)

  const rows = useMemo(() => {
    const filtered = events.filter((event) => {
      const firstDate = event.firstDetected.slice(0, 10)
      const peat = event.peatFraction == null ? 'NO_MAPPED_PEAT' : 'MAPPED_PEAT'
      return (
        (!dateStart || firstDate >= dateStart) &&
        (!dateEnd || firstDate <= dateEnd) &&
        (!scopeFilter.length || scopeFilter.includes(event.scopeRelation ?? '')) &&
        (!peatFilter.length || peatFilter.includes(peat)) &&
        (!evidenceFilter.length || evidenceFilter.includes(event.evidenceSufficiency ?? '')) &&
        (!priorityFilter.length || priorityFilter.includes(event.investigationPriority ?? '')) &&
        (!reviewFilter.length || reviewFilter.includes(event.reviewState ?? ''))
      )
    })
    const dir = sortDir === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => {
      switch (sortKey) {
        case 'id': return a.id.localeCompare(b.id) * dir
        case 'firstDetected': return a.firstDetected.localeCompare(b.firstDetected) * dir
        case 'durationHours': return ((a.durationHours ?? 0) - (b.durationHours ?? 0)) * dir
        case 'observationCount': return ((a.observationCount ?? a.detections.length) - (b.observationCount ?? b.detections.length)) * dir
        case 'investigationPriorityScore': return ((a.investigationPriorityScore ?? -1) - (b.investigationPriorityScore ?? -1)) * dir
      }
    })
  }, [dateEnd, dateStart, evidenceFilter, events, peatFilter, priorityFilter, reviewFilter, scopeFilter, sortDir, sortKey])

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDir((direction) => (direction === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
  }

  function clearFilters() {
    setDateStart(''); setDateEnd(''); setScopeFilter([]); setPeatFilter([]); setEvidenceFilter([]); setPriorityFilter([]); setReviewFilter([])
  }

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex flex-wrap items-end gap-2 border-b border-border p-3">
        <label className="flex flex-col gap-1 text-[10px] font-semibold tracking-wide text-text-faint uppercase">First detected from<input type="date" value={dateStart} onChange={(event) => setDateStart(event.target.value)} className="rounded border border-border-strong bg-panel-raised px-2 py-1.5 text-xs font-normal normal-case text-text" /></label>
        <label className="flex flex-col gap-1 text-[10px] font-semibold tracking-wide text-text-faint uppercase">First detected to<input type="date" value={dateEnd} onChange={(event) => setDateEnd(event.target.value)} className="rounded border border-border-strong bg-panel-raised px-2 py-1.5 text-xs font-normal normal-case text-text" /></label>
        <MultiFilter label="Scope relation" values={SCOPE_RELATIONS} selected={scopeFilter} onChange={setScopeFilter} />
        <MultiFilter label="Peat" values={['MAPPED_PEAT', 'NO_MAPPED_PEAT']} selected={peatFilter} onChange={setPeatFilter} />
        <MultiFilter label="Evidence" values={SUFFICIENCIES} selected={evidenceFilter} onChange={setEvidenceFilter} />
        <MultiFilter label="Priority" values={PRIORITIES} selected={priorityFilter} onChange={setPriorityFilter} />
        <MultiFilter label="Review state" values={REVIEW_STATES} selected={reviewFilter} onChange={setReviewFilter} />
        <button onClick={clearFilters} className="mb-0.5 rounded border border-border-strong px-2 py-1.5 text-[11px] text-text-muted hover:text-text">Clear filters</button>
      </div>
      <div className="flex items-center justify-between border-b border-border bg-panel-raised px-3 py-2 text-xs text-text-muted">
        <span>{rows.length} of {events.length} FireEvents shown · {selectedEventIds.length} selected</span>
        <div className="flex items-center gap-2">
          <button disabled={!selectedEventIds.length} onClick={investigateSelected} className="rounded bg-accent px-3 py-1.5 text-[11px] font-semibold tracking-wide text-bg disabled:cursor-not-allowed disabled:opacity-40">INVESTIGATE ON MAP</button>
          <button disabled={!selectedEventIds.length} onClick={clearEventSelection} className="text-[11px] text-text-muted disabled:opacity-40">Clear selection</button>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 z-10 bg-panel"><tr className="border-b border-border">
            <th className="px-2 py-2" />
            <th className="px-3 py-2 text-left"><SortHeader sortableKey="id" label="FireEvent ID" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} /></th>
            <th className="px-3 py-2 text-left"><SortHeader sortableKey="firstDetected" label="First / last detection" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} /></th>
            <th className="px-3 py-2 text-left"><SortHeader sortableKey="durationHours" label="Duration" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} /></th>
            <th className="px-3 py-2 text-left"><SortHeader sortableKey="observationCount" label="Observations" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} /></th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold tracking-wide text-text-faint uppercase">Scope relation</th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold tracking-wide text-text-faint uppercase">FRP summary</th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold tracking-wide text-text-faint uppercase">Peat</th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold tracking-wide text-text-faint uppercase">Complexity</th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold tracking-wide text-text-faint uppercase">Evidence</th>
            <th className="px-3 py-2 text-left"><SortHeader sortableKey="investigationPriorityScore" label="Priority" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} /></th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold tracking-wide text-text-faint uppercase">Review</th>
          </tr></thead>
          <tbody>{rows.map((event) => {
            const isSelected = selectedEventIds.includes(event.id)
            return <tr key={event.id} onClick={() => selectEvent(event.id)} className={`cursor-pointer border-b border-border/60 hover:bg-panel-raised ${selectedEventId === event.id ? 'bg-panel-raised' : ''}`}>
              <td className="px-2 py-2" onClick={(click) => click.stopPropagation()}><input aria-label={`Select ${event.id}`} type="checkbox" checked={isSelected} onChange={() => toggleEventSelection(event.id)} /></td>
              <td className="px-3 py-2 font-mono whitespace-nowrap">{event.id}</td>
              <td className="px-3 py-2 whitespace-nowrap text-text-muted">{formatDateTime(event.firstDetected)}<br />{formatDateTime(event.lastDetected ?? event.firstDetected)}</td>
              <td className="px-3 py-2 whitespace-nowrap text-text-muted">{event.durationHours != null ? `${event.durationHours.toFixed(1)} h` : '—'}</td>
              <td className="px-3 py-2 text-text-muted">{event.observationCount ?? event.detections.length}</td>
              <td className={`px-3 py-2 whitespace-nowrap ${event.scopeRelation === 'EXTERNAL_CONTEXT' ? 'text-status-moderate' : 'text-text-muted'}`}>{event.scopeRelation?.replaceAll('_', ' ') ?? '—'}</td>
              <td className="px-3 py-2 whitespace-nowrap text-text-muted">{event.peakFrp != null ? `${event.peakFrp.toFixed(1)} MW peak` : '—'}<br />{event.meanFrp != null ? `${event.meanFrp.toFixed(1)} MW mean` : '—'}</td>
              <td className="px-3 py-2 whitespace-nowrap text-text-muted">{event.peatFraction != null ? `${(event.peatFraction * 100).toFixed(0)}%` : 'N/A'}</td>
              <td className="px-3 py-2 text-text-muted">{event.complexity ? `${event.complexity.evaluatedFieldCount}/${event.complexity.fieldCount} fields` : '—'}</td>
              <td className="px-3 py-2 whitespace-nowrap text-text-muted">{event.evidenceSufficiency ?? '—'}<br />{event.evidenceIds?.length ?? 0} IDs</td>
              <td className="px-3 py-2 whitespace-nowrap text-text-muted">{event.investigationPriority ?? '—'}<br />{event.investigationPriorityScore != null ? event.investigationPriorityScore.toFixed(1) : '—'}</td>
              <td className="px-3 py-2 whitespace-nowrap text-text-muted">{event.reviewState ?? '—'}</td>
            </tr>
          })}</tbody>
        </table>
      </div>
    </div>
  )
}
