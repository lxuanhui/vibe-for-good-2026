import { useState } from 'react'
import { buildFireHistory, createAudit, fetchAuditEvents } from '../../api/client'
import { useAppStore } from '../../store/useAppStore'
import { EventTable } from './EventTable'

const DEMO_BOUNDARY = {
  type: 'Polygon',
  coordinates: [[[102, -5], [118, -5], [118, 2], [102, 2], [102, -5]]],
}

export function TableSidebar() {
  const viewMode = useAppStore((s) => s.viewMode)
  const historyEvents = useAppStore((s) => s.historyEvents)
  const setHistoryEvents = useAppStore((s) => s.setHistoryEvents)
  const [reviewStart, setReviewStart] = useState('2019-09-01')
  const [reviewEnd, setReviewEnd] = useState('2019-09-10')
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function buildHistory() {
    setBuilding(true)
    setError(null)
    try {
      const audit = await createAudit({ reviewStart, reviewEnd, boundary: DEMO_BOUNDARY, contextBufferKm: 25 })
      await buildFireHistory(audit.auditId)
      const result = await fetchAuditEvents(audit.auditId)
      setHistoryEvents(result.events)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'History build failed')
    } finally {
      setBuilding(false)
    }
  }

  // The Historical Fire Register must not present the legacy fixture cases as
  // an audit result. The map may still use them before a build, but this table
  // only becomes populated from the generated, scope-aware history response.
  const displayEvents = historyEvents

  return (
    <aside
      className={`h-full shrink-0 overflow-hidden border-r border-border-strong bg-panel shadow-2xl transition-[width] duration-200 ${
        viewMode === 'table' ? 'w-[1180px]' : 'w-0'
      }`}
    >
      <div className="h-full w-[1180px]">
        <div className="flex items-end gap-3 border-b border-border px-4 py-3">
          <div className="mr-auto">
            <h2 className="text-sm font-semibold">Historical Fire Register</h2>
            <p className="text-xs text-text-muted">{historyEvents.length ? `${displayEvents.length} generated FireEvents` : 'Build a scope-aware historical register'}</p>
          </div>
          <label className="flex flex-col gap-1 text-[10px] font-semibold tracking-wide text-text-faint uppercase">Review start<input type="date" value={reviewStart} onChange={(event) => setReviewStart(event.target.value)} className="rounded border border-border-strong bg-panel-raised px-2 py-1 text-xs font-normal normal-case text-text" /></label>
          <label className="flex flex-col gap-1 text-[10px] font-semibold tracking-wide text-text-faint uppercase">Review end<input type="date" value={reviewEnd} onChange={(event) => setReviewEnd(event.target.value)} className="rounded border border-border-strong bg-panel-raised px-2 py-1 text-xs font-normal normal-case text-text" /></label>
          <button onClick={buildHistory} disabled={building} className="rounded bg-accent px-3 py-2 text-[11px] font-semibold tracking-wide text-bg disabled:opacity-50">{building ? 'BUILDING…' : 'BUILD FIRE HISTORY'}</button>
        </div>
        {error && <div role="alert" className="border-b border-status-urgent/40 bg-status-urgent/10 px-4 py-2 text-xs text-status-urgent">{error}</div>}
        {!historyEvents.length && <div className="border-b border-border px-4 py-2 text-[11px] text-text-muted">Demo source: clearly labelled frozen NASA FIRMS 2019 historical observations. External-context events remain visible as context.</div>}
        <div className="h-[calc(100%-73px)]">
          <EventTable events={displayEvents} />
        </div>
      </div>
    </aside>
  )
}
