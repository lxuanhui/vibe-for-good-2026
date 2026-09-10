import type { AuditProgression } from '../../api/types'
import { SummaryHelp } from './HistoricalInvestigation'

const stages = [
  { key: 'observations', label: 'fire observations' },
  { key: 'clusters', label: 'clusters' },
  { key: 'human-review', label: 'Human Review recommended' },
] as const

export function RegisterSummary({ progression }: { progression: AuditProgression }) {
  const values = {
    observations: progression.qualifiedObservations,
    clusters: progression.fireEvents,
    'human-review': progression.requiringHumanReview,
  }

  return <section aria-label="Historical register population summary" className="shrink-0 border-b border-border bg-panel">
    <div aria-label="Register processing flow" className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
      {stages.map((stage, index) => <span key={stage.key} className="flex items-center gap-2" data-flow-stage={stage.key}>
        {index > 0 && <span aria-hidden="true" data-flow-arrow className="text-text-faint">→</span>}
        <span className="font-semibold text-accent">{values[stage.key].toLocaleString()}</span>
        <span className="text-[10px] tracking-[0.08em] text-text-faint">{stage.label}</span>
      </span>)}
      <SummaryHelp label="methodology chain">Qualified FIRMS observations are deterministically clustered into FireEvents, followed by a deterministic recommendation for human review.</SummaryHelp>
    </div>
  </section>
}
