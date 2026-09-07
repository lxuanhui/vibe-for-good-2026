import type { ReasoningRound } from '../../api/types'

interface ReasoningLogProps {
  rounds: ReasoningRound[]
  expanded: boolean
  onToggle: () => void
  highlightRound: number | null
  registerRoundRef: (round: number, el: HTMLDivElement | null) => void
}

export function ReasoningLog({ rounds, expanded, onToggle, highlightRound, registerRoundRef }: ReasoningLogProps) {
  if (rounds.length === 0) return null
  return (
    <section>
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between rounded-lg border border-border-strong bg-panel-raised px-3 py-2 text-left text-sm font-semibold"
      >
        <span>Full reasoning log</span>
        <span className="text-xs font-normal text-text-muted">
          {expanded ? 'Hide' : 'Show'} ({rounds.length} rounds)
        </span>
      </button>
      {expanded && (
        <div className="mt-2 space-y-3">
          {rounds.map((round) => (
            <div
              key={round.round}
              ref={(el) => registerRoundRef(round.round, el)}
              className={`rounded-lg border p-3 transition-colors ${
                highlightRound === round.round ? 'border-accent bg-accent/5' : 'border-border-strong bg-panel-raised'
              }`}
            >
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="font-semibold text-text-muted">Round {round.round}</span>
                <span className={round.converged ? 'text-status-good' : 'text-status-moderate'}>
                  {round.converged ? 'Agreement reached' : 'Unresolved disagreement'}
                </span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <div className="mb-1 text-[11px] font-semibold text-status-good">
                    INVESTIGATOR — {round.investigator.hypothesis}
                  </div>
                  <p className="text-xs text-text-muted">{round.investigator.text}</p>
                  <div className="mt-1 text-[10px] text-text-faint">
                    support {round.investigator.support} · contra {round.investigator.contra}
                  </div>
                </div>
                <div>
                  <div className="mb-1 text-[11px] font-semibold text-status-urgent">
                    SKEPTIC — {round.skeptic.hypothesis}
                  </div>
                  <p className="text-xs text-text-muted">{round.skeptic.text}</p>
                  <div className="mt-1 text-[10px] text-text-faint">
                    support {round.skeptic.support} · contra {round.skeptic.contra}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
