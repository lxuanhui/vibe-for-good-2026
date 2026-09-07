import type { EvidenceObject, TopTheory } from '../../api/types'
import { Chip } from '../ui/Chip'
import { ScoreBadge } from '../ui/ScoreBadge'

interface TopTheoriesProps {
  theories: TopTheory[]
  evidence: Record<string, EvidenceObject>
  onEvidenceClick: (evidenceId: string) => void
}

export function TopTheories({ theories, evidence, onEvidenceClick }: TopTheoriesProps) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">Top {theories.length} theories</h3>
      <div className="space-y-3">
        {theories.map((t) => (
          <div key={t.hypothesisId} className="rounded-lg border border-border-strong bg-panel-raised p-3">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-border text-[11px] font-semibold text-text-muted">
                  {t.rank}
                </span>
                <span className="text-sm font-medium">{t.hypothesis}</span>
              </div>
              <ScoreBadge score={t.supportScore} />
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {t.evidenceIds.map((id) => (
                <Chip key={id} label={id} title={evidence[id]?.observation} onClick={() => onEvidenceClick(id)} />
              ))}
              {t.counterEvidenceIds.map((id) => (
                <Chip
                  key={id}
                  label={id}
                  tone="counter"
                  title={evidence[id]?.observation}
                  onClick={() => onEvidenceClick(id)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
