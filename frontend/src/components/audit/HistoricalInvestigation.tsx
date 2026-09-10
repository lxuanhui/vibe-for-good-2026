import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { AuditEventSummary, AuditProgression, AuditScope } from '../../api/types'
import { fetchAuditRegister } from '../../api/client'
import { useAppStore } from '../../store/useAppStore'
import { Button } from '../ui/Button'

type RegisterFilters = {
  triage: AuditEventSummary['triage']['state'] | 'ALL'
  sufficiency: AuditEventSummary['evidenceSufficiency'] | 'ALL'
  priority: AuditEventSummary['investigationPriority'] | 'ALL'
  workflow: AuditEventSummary['reviewState'] | 'ALL'
  firstDetected: string
  minMaxFrp: string
}

type SortKey = 'eventId' | 'firstDetection' | 'observationCount' | 'maxFrp' | 'triage' | 'evidenceSufficiency' | 'investigationPriority' | 'reviewState'

const defaultFilters: RegisterFilters = { triage: 'ALL', sufficiency: 'ALL', priority: 'ALL', workflow: 'ALL', firstDetected: '', minMaxFrp: '' }

const sortLabels: Record<SortKey, string> = {
  eventId: 'FireEvent ID', firstDetection: 'First detected', observationCount: 'FIRMS observations', maxFrp: 'Max FRP',
  triage: 'Stage-1 state', evidenceSufficiency: 'Sufficiency', investigationPriority: 'Priority', reviewState: 'Workflow',
}

function eventRows(events: AuditEventSummary[], selected: string[], toggle: (id: string) => void) {
  return events.map((event) => (
    <tr key={event.eventId} className="border-b border-border/60 hover:bg-panel-raised">
      <td className="px-3 py-2"><input className="h-5 w-5 cursor-pointer accent-accent" aria-label={`Select ${event.eventId}`} type="checkbox" checked={selected.includes(event.eventId)} onChange={() => toggle(event.eventId)} /></td>
      <td className="px-3 py-2 font-mono">{event.eventId}</td>
      <td className="px-3 py-2 text-text-muted">{event.firstDetection.slice(0, 10)}</td>
      <td className="px-3 py-2 text-right tabular-nums" aria-label={`${event.observationCount} FIRMS observations`}>{event.observationCount.toLocaleString()}</td>
      <td className="px-3 py-2 text-text-muted">{event.triage.state}</td>
      <td className="px-3 py-2 text-text-muted">{event.evidenceSufficiency}</td>
      <td className="px-3 py-2">{event.investigationPriority}</td>
      <td className="px-3 py-2 text-text-muted">{event.reviewState}</td>
      <td className="px-3 py-2 text-right">{event.maxFrp?.toFixed(1) ?? '—'}</td>
    </tr>
  ))
}

function selectOptions(values: string[]) {
  return values.map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)
}

function compareEvents(a: AuditEventSummary, b: AuditEventSummary, key: SortKey) {
  const aValue = key === 'maxFrp' ? a.maxFrp ?? -Infinity : key === 'triage' ? a.triage.state : a[key]
  const bValue = key === 'maxFrp' ? b.maxFrp ?? -Infinity : key === 'triage' ? b.triage.state : b[key]
  return String(aValue).localeCompare(String(bValue), undefined, { numeric: true, sensitivity: 'base' })
}

function SummaryHelp({ label, children }: { label: string; children: ReactNode }) {
  return <details className="relative inline-block align-middle"><summary aria-label={`About ${label}`} className="flex h-4 w-4 cursor-pointer list-none items-center justify-center rounded-full border border-border-strong text-[10px] text-text-muted hover:text-text"><span aria-hidden="true">?</span></summary><div role="note" className="absolute right-0 z-10 mt-2 w-64 rounded border border-border-strong bg-panel-raised p-3 text-left text-[11px] leading-4 text-text shadow-lg">{children}</div></details>
}

export function RegisterSummary({ progression }: { progression: AuditProgression }) {
  const eventDenominator = progression.fireEvents.toLocaleString()
  return <>
    <section aria-label="Historical register population summary" className="shrink-0 border-b border-border bg-border">
    <div className="grid gap-px bg-border md:grid-cols-3">
      <section aria-labelledby="clustering-summary" className="bg-panel px-4 py-3">
        <div className="mb-2 flex items-center gap-2"><h2 id="clustering-summary" className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-faint">Observation derivation</h2><SummaryHelp label="observation derivation">Spatially and temporally related FIRMS observations are deterministically clustered into FireEvents. An observation is a satellite detection, not an individual fire.</SummaryHelp></div>
        <div className="flex items-end gap-3"><div><div className="font-semibold text-accent">{progression.qualifiedObservations.toLocaleString()}</div><div className="text-[10px] text-text-faint">QUALIFIED FIRMS OBSERVATIONS</div></div><div className="pb-3 text-text-faint">→</div><div><div className="font-semibold text-accent">{eventDenominator}</div><div className="text-[10px] text-text-faint">CLUSTERED FIREEVENTS</div></div></div>
        <p className="mt-2 text-[10px] text-text-muted">{progression.observationsToEventsCompression?.toFixed(1) ?? '—'} observations per FireEvent on average. This is clustering, not a review queue.</p>
      </section>
      <section aria-labelledby="scope-summary" className="bg-panel px-4 py-3">
        <div className="mb-2 flex items-center gap-2"><h2 id="scope-summary" className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-faint">Current audit scope</h2></div>
        <div className="font-semibold text-accent">{progression.inScopeAndBuffer?.toLocaleString() ?? '—'}</div>
        <div className="text-[10px] text-text-faint">IN SCOPE</div>
        <p className="mt-2 text-[10px] text-text-muted">{progression.scopeBoundaryAvailable ? `Count includes the configured context buffer: ${progression.inScopeAndBuffer?.toLocaleString() ?? '—'} of ${eventDenominator} FireEvents.` : 'No private audit boundary supplied; scope count is unavailable.'}</p>
      </section>
      <section aria-labelledby="routing-summary" className="bg-panel px-4 py-3">
        <div className="mb-2 flex items-center gap-2"><h2 id="routing-summary" className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-faint">Scoped routing diagnostic</h2><SummaryHelp label="routing dimensions"><p>FIRMS observations are clustered into FireEvents. Stage 1 classification indicates fire support and is separate from evidence sufficiency.</p><p className="mt-2">Priority is a review-routing aid, separate from workflow status. Routing is not proof of causality or responsibility.</p><p className="mt-2">Because you control filtering, the register can include low-confidence or likely-non-fire events for inspection.</p></SummaryHelp></div>
        <div className="font-semibold text-accent">{progression.requiringHumanReview.toLocaleString()}</div>
        <div className="text-[10px] text-text-faint">ROUTED TO HUMAN REVIEW IN CURRENT REGISTER</div>
        <p className="mt-2 text-[10px] text-text-muted">{(progression.routingDiagnostics.humanReviewPercentage * 100).toFixed(1)}% of {eventDenominator} FireEvents in this register.</p>
      </section>
    </div>
    </section>
  </>
}

// The selected-events + graph investigation used to render on its own page
// here (blank-style map, its own EvidenceDrawer mount). It now lives on
// ScopedMapLanding instead -- one map surface, not two -- so
// "INVESTIGATE ON MAP" just hands the current selection off through the
// store and switches to it, the same way "VIEW SCOPED MAP" does.
export function HistoricalInvestigation({ scope, onOpenScopedMap }: { scope: AuditScope; onOpenScopedMap?: () => void }) {
  const selection = useAppStore((s) => s.registerSelection)
  const toggleSelection = useAppStore((s) => s.toggleRegisterSelection)
  const [events, setEvents] = useState<AuditEventSummary[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [progression, setProgression] = useState<AuditProgression | null>(null)
  const [filters, setFilters] = useState<RegisterFilters>(defaultFilters)
  const [sortKey, setSortKey] = useState<SortKey>('firstDetection')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')

  const loadRegister = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      // Space only. The register is still a screening view of the audit's own
      // footprint rather than the whole artifact (canonical spec §11), but the
      // time half is now the backend's job (#161): the session's review period
      // filters the register server-side, so `progression` and the rows agree.
      // Re-sending it as `?since=/?until=` would also *narrow* it wrongly --
      // the scope stores whole dates, and `until=2019-09-03` parses as that
      // day's midnight, dropping every detection on the closing day the
      // auditor explicitly named.
      const result = await fetchAuditRegister(scope.audit_id, {
        bbox: scope.buffer_bbox ?? undefined,
      })
      setEvents(result.events)
      setProgression(result.progression)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Register could not be loaded.') } finally { setLoading(false) }
    // The review period is deliberately not a dependency any more. It is not
    // sent, and it cannot change without a new audit session -- which changes
    // `audit_id` and refetches anyway.
  }, [scope.audit_id, scope.buffer_bbox])
  useEffect(() => { void loadRegister() }, [loadRegister])
  const selectedEvents = useMemo(() => events.filter((event) => selection.includes(event.eventId)), [events, selection])
  const filteredEvents = useMemo(() => {
    const minFrp = filters.minMaxFrp === '' ? null : Number(filters.minMaxFrp)
    return events.filter((event) => (
      (filters.triage === 'ALL' || event.triage.state === filters.triage) &&
      (filters.sufficiency === 'ALL' || event.evidenceSufficiency === filters.sufficiency) &&
      (filters.priority === 'ALL' || event.investigationPriority === filters.priority) &&
      (filters.workflow === 'ALL' || event.reviewState === filters.workflow) &&
      (!filters.firstDetected || event.firstDetection.slice(0, 10) === filters.firstDetected) &&
      (minFrp === null || (event.maxFrp !== null && event.maxFrp >= minFrp))
    )).sort((a, b) => {
      const result = compareEvents(a, b, sortKey)
      return sortDirection === 'asc' ? result : -result
    })
  }, [events, filters, sortDirection, sortKey])
  const allFilteredSelected = filteredEvents.length > 0 && filteredEvents.every((event) => selection.includes(event.eventId))
  const updateFilter = <K extends keyof RegisterFilters>(key: K, value: RegisterFilters[K]) => setFilters((current) => ({ ...current, [key]: value }))
  const changeSort = (key: SortKey) => {
    if (sortKey === key) setSortDirection((current) => current === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDirection('asc') }
  }
  const toggleFilteredSelection = () => filteredEvents.forEach((event) => {
    const selected = selection.includes(event.eventId)
    if (allFilteredSelected && selected) toggleSelection(event.eventId)
    if (!allFilteredSelected && !selected) toggleSelection(event.eventId)
  })

  return <div className="flex h-full flex-col bg-bg text-text">
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border-strong bg-panel px-5 py-3"><div><div className="text-sm font-semibold">Historical Fire Register</div><div className="text-xs text-text-muted">{progression ? `${progression.fireEvents.toLocaleString()} FireEvents` : 'FireEvents'} · {scope.review_start} → {scope.review_end} · {scope.context_buffer_km} km context buffer</div></div><div className="flex items-center gap-2">{onOpenScopedMap && <Button onClick={onOpenScopedMap}>VIEW SCOPED MAP</Button>}<Button variant="primary" disabled={!selection.length || !onOpenScopedMap} onClick={onOpenScopedMap}>{`INVESTIGATE ON MAP (${selection.length})`}</Button></div></div>
    {progression && <RegisterSummary progression={progression} />}
    <section aria-label="Register filters" className="shrink-0 border-b border-border bg-panel px-5 py-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="grid gap-1 text-[10px] uppercase tracking-[0.08em] text-text-faint">Stage-1 state<select className="min-w-36 rounded border border-border-strong bg-bg px-2 py-1.5 text-xs normal-case tracking-normal text-text" value={filters.triage} onChange={(event) => updateFilter('triage', event.target.value as RegisterFilters['triage'])}><option value="ALL">All states</option>{selectOptions(['LIKELY_FIRE', 'LIKELY_NON_FIRE', 'AMBIGUOUS'])}</select></label>
        <label className="grid gap-1 text-[10px] uppercase tracking-[0.08em] text-text-faint">Sufficiency<select className="min-w-32 rounded border border-border-strong bg-bg px-2 py-1.5 text-xs normal-case tracking-normal text-text" value={filters.sufficiency} onChange={(event) => updateFilter('sufficiency', event.target.value as RegisterFilters['sufficiency'])}><option value="ALL">All levels</option>{selectOptions(['SUFFICIENT', 'PARTIAL', 'INSUFFICIENT'])}</select></label>
        <label className="grid gap-1 text-[10px] uppercase tracking-[0.08em] text-text-faint">Priority<select className="min-w-28 rounded border border-border-strong bg-bg px-2 py-1.5 text-xs normal-case tracking-normal text-text" value={filters.priority} onChange={(event) => updateFilter('priority', event.target.value as RegisterFilters['priority'])}><option value="ALL">All bands</option>{selectOptions(['LOW', 'MEDIUM', 'HIGH', 'URGENT'])}</select></label>
        <label className="grid gap-1 text-[10px] uppercase tracking-[0.08em] text-text-faint">Workflow<select className="min-w-40 rounded border border-border-strong bg-bg px-2 py-1.5 text-xs normal-case tracking-normal text-text" value={filters.workflow} onChange={(event) => updateFilter('workflow', event.target.value as RegisterFilters['workflow'])}><option value="ALL">All workflow states</option>{selectOptions(['SCREENED', 'REVIEW_RECOMMENDED', 'HUMAN_REVIEW'])}</select></label>
        <label className="grid gap-1 text-[10px] uppercase tracking-[0.08em] text-text-faint">First detected<input className="rounded border border-border-strong bg-bg px-2 py-1.5 text-xs normal-case tracking-normal text-text" type="date" value={filters.firstDetected} onChange={(event) => updateFilter('firstDetected', event.target.value)} /></label>
        <label className="grid gap-1 text-[10px] uppercase tracking-[0.08em] text-text-faint">Min Max FRP<input className="w-28 rounded border border-border-strong bg-bg px-2 py-1.5 text-xs normal-case tracking-normal text-text" type="number" min="0" step="0.1" placeholder="MW" value={filters.minMaxFrp} onChange={(event) => updateFilter('minMaxFrp', event.target.value)} /></label>
        <button className="rounded border border-border-strong px-2 py-1.5 text-[11px] text-text-muted hover:text-text" type="button" onClick={() => setFilters(defaultFilters)}>CLEAR FILTERS</button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-text-muted"><span>{filteredEvents.length.toLocaleString()} of {events.length.toLocaleString()} FireEvents shown</span><button className="rounded border border-border-strong px-2 py-1 text-text hover:bg-panel-raised" type="button" onClick={toggleFilteredSelection} disabled={!filteredEvents.length}>{allFilteredSelected ? 'CLEAR SHOWN SELECTION' : 'SELECT SHOWN'}</button><label className="flex items-center gap-2">Sort by<select className="rounded border border-border-strong bg-bg px-2 py-1 text-xs text-text" value={sortKey} onChange={(event) => changeSort(event.target.value as SortKey)}>{Object.entries(sortLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><button className="rounded border border-border-strong px-2 py-1 text-text hover:bg-panel-raised" type="button" onClick={() => setSortDirection((current) => current === 'asc' ? 'desc' : 'asc')} aria-label={`Sort ${sortLabels[sortKey]} ${sortDirection === 'asc' ? 'descending' : 'ascending'}`}>{sortDirection === 'asc' ? '↑ ASC' : '↓ DESC'}</button></div>
    </section>
    {error && <div role="alert" className="flex items-center justify-between gap-3 border-b border-status-urgent/40 bg-status-urgent/10 px-5 py-2 text-xs text-red-200"><span>{error}</span><Button onClick={() => void loadRegister()}>RETRY</Button></div>}
    {loading && <div role="status" className="flex flex-1 items-center justify-center text-sm text-text-muted">Loading current-audit FireEvent register…</div>}
    {/* An empty register is a result, not a failure to load one. A blank table
        reads as something that broke; naming the period states what was
        measured over it (#161). Filtering to zero is a separate case, handled
        inside the table below rather than here. */}
    {!loading && !error && events.length === 0 && <div role="status" className="flex flex-1 flex-col items-center justify-center gap-1 px-5 py-6 text-center"><p className="text-sm text-text">No FireEvents were detected in this period.</p><p className="text-xs text-text-muted">{scope.review_start} → {scope.review_end} · {scope.context_buffer_km} km context buffer. The register was built and returned nothing; it did not fail to load.</p></div>}
    {!loading && events.length > 0 && <div className="flex-1 overflow-auto"><table className="w-full min-w-[1060px] border-collapse text-xs"><colgroup><col className="w-20" /><col className="w-[18%]" /><col className="w-[13%]" /><col className="w-[12%]" /><col className="w-[14%]" /><col className="w-[13%]" /><col className="w-[10%]" /><col className="w-[14%]" /><col className="w-[10%]" /></colgroup><thead className="sticky top-0 bg-panel"><tr className="border-b border-border"><th className="px-3 py-2 text-left">Select</th><th className="px-3 py-2 text-left">FireEvent ID</th><th className="px-3 py-2 text-left">First detected</th><th className="px-3 py-2 text-right">FIRMS clustering</th><th className="px-3 py-2 text-left">Stage-1 state</th><th className="px-3 py-2 text-left">Sufficiency</th><th className="px-3 py-2 text-left">Priority</th><th className="px-3 py-2 text-left">Workflow</th><th className="px-3 py-2 text-right">Max FRP (MW)</th></tr></thead><tbody>{eventRows(filteredEvents, selection, toggleSelection)}</tbody></table>{filteredEvents.length === 0 && <p className="p-8 text-center text-sm text-text-muted">No FireEvents match the current register filters.</p>}</div>}
    {selectedEvents.length > 0 && <div className="shrink-0 border-t border-border bg-panel px-5 py-2 text-xs text-text-muted">Selected FireEvents remain selected on the scoped map.</div>}
  </div>
}
