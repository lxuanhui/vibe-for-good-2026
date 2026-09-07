import { useEffect, useRef, useState } from 'react'
import { useEvents, useReport } from '../../api/hooks'
import { generateReport } from '../../api/client'
import type { InvestigationReport } from '../../api/types'
import { formatCoord, formatDate } from '../../lib/format'
import { useAppStore } from '../../store/useAppStore'
import { Button } from '../ui/Button'
import { DataVisualizations } from './DataVisualizations'
import { ExecutiveSummary } from './ExecutiveSummary'
import { Limitations } from './Limitations'
import { ReasoningLog } from './ReasoningLog'
import { Stage1Gate } from './Stage1Gate'
import { TopTheories } from './TopTheories'

export function ReportPanel() {
  const reportEventId = useAppStore((s) => s.reportEventId)
  const closeReport = useAppStore((s) => s.closeReport)
  const events = useEvents()
  const cachedReport = useReport(reportEventId)

  const [liveReport, setLiveReport] = useState<InvestigationReport | null>(null)
  const [logExpanded, setLogExpanded] = useState(false)
  const [highlightRound, setHighlightRound] = useState<number | null>(null)
  const roundRefs = useRef<Map<number, HTMLDivElement>>(new Map())
  const cancelRef = useRef<() => void>(() => {})

  useEffect(() => {
    setLiveReport(cachedReport)
    setLogExpanded(false)
    setHighlightRound(null)
  }, [cachedReport])

  useEffect(() => {
    return () => cancelRef.current()
  }, [reportEventId])

  if (!reportEventId) return null
  const event = events.find((e) => e.id === reportEventId)
  const report = liveReport

  if (!event || !report) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 backdrop-blur-sm">
        <div className="text-sm text-text-muted">Loading report…</div>
      </div>
    )
  }

  const handleGenerate = () => {
    cancelRef.current()
    cancelRef.current = generateReport(reportEventId, setLiveReport)
  }

  const handleEvidenceClick = (evidenceId: string) => {
    const round = report.reasoningLog.find(
      (r) => r.investigator.text.includes(evidenceId) || r.skeptic.text.includes(evidenceId),
    )
    if (!round) return
    setLogExpanded(true)
    setHighlightRound(round.round)
    requestAnimationFrame(() => {
      roundRefs.current.get(round.round)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
    setTimeout(() => setHighlightRound(null), 1800)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-center overflow-y-auto bg-bg/80 p-6 backdrop-blur-sm"
      onClick={closeReport}
    >
      <div
        className="h-fit w-full max-w-3xl rounded-xl border border-border-strong bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            <div className="text-xs font-semibold tracking-wide text-text-faint uppercase">
              Environmental Fire Investigation Pack
            </div>
            <div className="mt-1 font-mono text-lg font-semibold">{event.id}</div>
            <div className="text-xs text-text-muted">
              {event.location} · {formatCoord(event.lat, event.lon)} · First detected {formatDate(event.firstDetected)}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {event.qualifiesForInvestigation && (
              <Button variant="ghost" onClick={handleGenerate} disabled={report.status === 'running'}>
                {report.status === 'running' ? 'Generating…' : 'Generate investigation pack'}
              </Button>
            )}
            <button
              onClick={closeReport}
              className="rounded p-1.5 text-text-muted hover:bg-panel-raised hover:text-text"
              aria-label="Close report"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="space-y-5 p-5">
          <Stage1Gate gate={report.stage1Gate} />

          {report.stage1Gate.outcome === 'passed' && (
            <>
              {report.status === 'running' && (
                <div className="rounded-lg border border-status-info/40 bg-status-info/10 px-3 py-2 text-xs text-status-info">
                  Investigator and Skeptic agents are running fixed adversarial rounds…
                </div>
              )}
              {report.executiveSummary && <ExecutiveSummary text={report.executiveSummary} />}
              {report.topTheories.length > 0 && (
                <TopTheories
                  theories={report.topTheories}
                  evidence={report.evidence}
                  onEvidenceClick={handleEvidenceClick}
                />
              )}
              <DataVisualizations
                fwiKbdi={report.dataVisualizations.fwiKbdiTimeseries}
                sarTrend={report.dataVisualizations.sarBackscatterTrend}
                fireGrowth={report.dataVisualizations.fireGrowthProjection}
              />
              <ReasoningLog
                rounds={report.reasoningLog}
                expanded={logExpanded}
                onToggle={() => setLogExpanded((v) => !v)}
                highlightRound={highlightRound}
                registerRoundRef={(round, el) => {
                  if (el) roundRefs.current.set(round, el)
                  else roundRefs.current.delete(round)
                }}
              />
              <Limitations items={report.limitations} />
            </>
          )}

          <p className="border-t border-border pt-4 text-[11px] text-text-faint">
            This report is an investigative-support product. It does not establish legal responsibility, intent,
            culpability, ownership liability, or criminal wrongdoing. Findings require human verification.
          </p>
        </div>
      </div>
    </div>
  )
}
