import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { AuditEventSummary, AuditProgression, AuditScope } from '../../api/types'
import { fetchAuditRegister } from '../../api/client'
import { useAppStore } from '../../store/useAppStore'
import { Button } from '../ui/Button'

function eventRows(events: AuditEventSummary[], selected: string[], toggle: (id: string) => void) {
  return events.map((event) => (
    <tr key={event.eventId} className="border-b border-border/60 hover:bg-panel-raised">
      <td className="px-3 py-2"><input aria-label={`Select ${event.eventId}`} type="checkbox" checked={selected.includes(event.eventId)} onChange={() => toggle(event.eventId)} /></td>
      <td className="px-3 py-2 font-mono">{event.eventId}</td>
      <td className="px-3 py-2 text-text-muted">{event.firstDetection.slice(0, 10)}</td>
      <td className="px-3 py-2 text-right">{event.observationCount}</td>
      <td className="px-3 py-2 text-text-muted">{event.triage.state}</td>
      <td className="px-3 py-2 text-text-muted">{event.evidenceSufficiency}</td>
      <td className="px-3 py-2">{event.investigationPriority}</td>
      <td className="px-3 py-2 text-text-muted">{event.reviewState}</td>
      <td className="px-3 py-2 text-right">{event.maxFrp?.toFixed(1) ?? '—'}</td>
    </tr>
  ))
}

function SummaryHelp({ label, children }: { label: string; children: ReactNode }) {
  return <details className="relative inline-block align-middle"><summary aria-label={`About ${label}`} className="flex h-4 w-4 cursor-pointer list-none items-center justify-center rounded-full border border-border-strong text-[10px] text-text-muted hover:text-text"><span aria-hidden="true">?</span></summary><div role="note" className="absolute right-0 z-10 mt-2 w-64 rounded border border-border-strong bg-panel-raised p-3 text-left text-[11px] leading-4 text-text shadow-lg">{children}</div></details>
}

export function RegisterSummary({ progression }: { progression: AuditProgression }) {
  const eventDenominator = progression.fireEvents.toLocaleString()
  return <section aria-label="Historical register population summary" className="shrink-0 border-b border-border bg-border">
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
        <div className="mb-2 flex items-center gap-2"><h2 id="routing-summary" className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-faint">Global routing diagnostics</h2><SummaryHelp label="routing dimensions">Priority, evidence sufficiency, and workflow are separate dimensions. They are diagnostics over the event population, not sequential funnel stages.</SummaryHelp></div>
        <div className="font-semibold text-accent">{progression.requiringHumanReview.toLocaleString()}</div>
        <div className="text-[10px] text-text-faint">ROUTED TO HUMAN REVIEW</div>
        <p className="mt-2 text-[10px] text-text-muted">{(progression.routingDiagnostics.humanReviewPercentage * 100).toFixed(1)}% of {eventDenominator} FireEvents; this is not a subset count of the In Scope figure.</p>
      </section>
    </div>
  </section>
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

  const loadRegister = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      // Filtered by both time (review period) and space (scope + context
      // buffer) -- canonical spec §11's register is a screening view of the
      // audit's own footprint, not the whole committed artifact.
      const result = await fetchAuditRegister(scope.audit_id, {
        since: scope.review_start,
        until: scope.review_end,
        bbox: scope.buffer_bbox ?? undefined,
      })
      setEvents(result.events)
      setProgression(result.progression)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Register could not be loaded.') } finally { setLoading(false) }
  }, [scope.audit_id, scope.review_start, scope.review_end, scope.buffer_bbox])
  useEffect(() => { void loadRegister() }, [loadRegister])
  const selectedEvents = useMemo(() => events.filter((event) => selection.includes(event.eventId)), [events, selection])

  return <div className="flex h-full flex-col bg-bg text-text">
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border-strong bg-panel px-5 py-3"><div><div className="text-sm font-semibold">Historical Fire Register</div><div className="text-xs text-text-muted">{progression ? `${progression.fireEvents.toLocaleString()} FireEvents` : 'FireEvents'} · {scope.review_start} → {scope.review_end} · {scope.context_buffer_km} km context buffer</div></div><div className="flex items-center gap-2">{onOpenScopedMap && <Button onClick={onOpenScopedMap}>VIEW SCOPED MAP</Button>}<Button variant="primary" disabled={!selection.length || !onOpenScopedMap} onClick={onOpenScopedMap}>{`INVESTIGATE ON MAP (${selection.length})`}</Button></div></div>
    {progression && <RegisterSummary progression={progression} />}
    {progression && <p className="border-b border-border bg-panel px-5 py-2 text-[11px] text-text-muted">Ambiguous events remain review-recommended; only calibrated HIGH/URGENT routes enter human review. The routing diagnostics below describe the full event population.</p>}
    {progression && <div className="flex flex-wrap gap-x-5 gap-y-1 border-b border-border bg-panel px-5 py-2 text-[10px] text-text-muted" aria-label="Review routing diagnostics"><span className="font-semibold uppercase tracking-[0.1em] text-text-faint">Routing diagnostics</span>{Object.entries(progression.routingDiagnostics.priorityDistribution).map(([priority, distribution]) => <span key={priority}>Priority {priority}: {distribution.count.toLocaleString()} ({(distribution.percentage * 100).toFixed(1)}%)</span>)}{Object.entries(progression.routingDiagnostics.reviewStateDistribution).map(([state, distribution]) => <span key={state}>Workflow {state}: {distribution.count.toLocaleString()} ({(distribution.percentage * 100).toFixed(1)}%)</span>)}{Object.entries(progression.routingDiagnostics.evidenceSufficiencyDistribution).map(([sufficiency, distribution]) => <span key={sufficiency}>Sufficiency {sufficiency}: {distribution.count.toLocaleString()} ({(distribution.percentage * 100).toFixed(1)}%)</span>)}{Object.entries(progression.routingDiagnostics.escalationReasonCodes).map(([reason, distribution]) => <span key={reason}>Escalation {reason}: {distribution.count.toLocaleString()}</span>)}{Object.entries(progression.routingDiagnostics.componentContributionDistribution).map(([factor, distribution]) => <span key={factor}>Component {factor}: {distribution.totalContribution.toFixed(1)} ({(distribution.percentageOfContribution * 100).toFixed(1)}%)</span>)}</div>}
    {scope.historyBuild && <div className="border-b border-border bg-panel px-5 py-2 text-[11px] text-text-muted">Cached real historical dataset · build handoff {scope.historyBuild.duration_ms.toFixed(2)} ms · counts below are from the current audit artifact.</div>}
    {error && <div role="alert" className="flex items-center justify-between gap-3 border-b border-status-urgent/40 bg-status-urgent/10 px-5 py-2 text-xs text-red-200"><span>{error}</span><Button onClick={() => void loadRegister()}>RETRY</Button></div>}
    {loading && <div role="status" className="flex flex-1 items-center justify-center text-sm text-text-muted">Loading current-audit FireEvent register…</div>}
    {!loading && <div className="flex-1 overflow-auto"><table className="w-full border-collapse text-xs"><thead className="sticky top-0 bg-panel"><tr className="border-b border-border"><th className="px-3 py-2 text-left">Select</th><th className="px-3 py-2 text-left">FireEvent ID</th><th className="px-3 py-2 text-left">First detected</th><th className="px-3 py-2 text-right">Observations</th><th className="px-3 py-2 text-left">Stage-1 state</th><th className="px-3 py-2 text-left">Sufficiency</th><th className="px-3 py-2 text-left">Priority</th><th className="px-3 py-2 text-left">Workflow</th><th className="px-3 py-2 text-right">Max FRP</th></tr></thead><tbody>{eventRows(events, selection, toggleSelection)}</tbody></table></div>}
    {selectedEvents.length > 0 && <div className="shrink-0 border-t border-border bg-panel px-5 py-2 text-xs text-text-muted">Selected FireEvents remain selected on the scoped map.</div>}
  </div>
}
