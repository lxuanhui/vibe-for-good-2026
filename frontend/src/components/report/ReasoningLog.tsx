import type { AnalysisQuestion, AnalysisRound, EvidenceObject } from '../../api/types'
import { Chip } from '../ui/Chip'

interface AnalysisRoundsProps {
  rounds: AnalysisRound[]
  evidence: Record<string, EvidenceObject>
  onEvidenceClick: (evidenceId: string) => void
  expanded: boolean
  onToggle: () => void
  highlightRound: number | null
  registerRoundRef: (round: number, el: HTMLDivElement | null) => void
}

export function ReasoningLog({
  rounds,
  evidence,
  onEvidenceClick,
  expanded,
  onToggle,
  highlightRound,
  registerRoundRef,
}: AnalysisRoundsProps) {
  if (rounds.length === 0) return null
  return (
    <section>
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between rounded-lg border border-border-strong bg-panel-raised px-3 py-2 text-left text-sm font-semibold"
      >
        <span>Structured analysis rounds</span>
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
                <span className="text-text-muted">{phaseLabel(round.phase)}</span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <StructuredFinding
                  role="INVESTIGATOR"
                  finding={round.investigator}
                  evidence={evidence}
                  onEvidenceClick={onEvidenceClick}
                />
                <StructuredFinding
                  role="SKEPTIC"
                  finding={round.skeptic}
                  evidence={evidence}
                  onEvidenceClick={onEvidenceClick}
                />
              </div>
              <QuestionList
                questions={round.unresolvedQuestions}
                evidence={evidence}
                onEvidenceClick={onEvidenceClick}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export function UnresolvedQuestions({
  questions,
  evidence,
  onEvidenceClick,
}: {
  questions: AnalysisQuestion[]
  evidence: Record<string, EvidenceObject>
  onEvidenceClick: (evidenceId: string) => void
}) {
  if (questions.length === 0) return null
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">Unresolved questions</h3>
      <QuestionList questions={questions} evidence={evidence} onEvidenceClick={onEvidenceClick} />
    </section>
  )
}

function StructuredFinding({
  role,
  finding,
  evidence,
  onEvidenceClick,
}: {
  role: 'INVESTIGATOR' | 'SKEPTIC'
  finding: AnalysisRound['investigator']
  evidence: Record<string, EvidenceObject>
  onEvidenceClick: (evidenceId: string) => void
}) {
  return (
    <div>
      <div className={`mb-1 text-[11px] font-semibold ${role === 'INVESTIGATOR' ? 'text-status-good' : 'text-status-urgent'}`}>
        {role} â€” {finding.hypothesis}
      </div>
      <p className="text-xs text-text-muted">{finding.summary}</p>
      <div className="mt-1 text-[10px] text-text-faint">
        support {finding.support} Â· contra {finding.contra}
      </div>
      <EvidenceChips
        ids={finding.evidenceIds}
        counterIds={finding.counterEvidenceIds}
        evidence={evidence}
        onEvidenceClick={onEvidenceClick}
      />
    </div>
  )
}

function phaseLabel(phase: AnalysisRound['phase']): string {
  return phase === 'independent_assessment'
    ? 'Independent assessment'
    : phase === 'rebuttal'
      ? 'Rebuttal'
      : 'Final structured assessment'
}

function EvidenceChips({
  ids,
  counterIds = [],
  evidence,
  onEvidenceClick,
}: {
  ids: string[]
  counterIds?: string[]
  evidence: Record<string, EvidenceObject>
  onEvidenceClick: (evidenceId: string) => void
}) {
  if (ids.length === 0 && counterIds.length === 0) return null
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {ids.map((id) => (
        <Chip key={id} label={id} title={evidence[id]?.observation} onClick={() => onEvidenceClick(id)} />
      ))}
      {counterIds.map((id) => (
        <Chip
          key={`counter-${id}`}
          label={id}
          tone="counter"
          title={evidence[id]?.observation}
          onClick={() => onEvidenceClick(id)}
        />
      ))}
    </div>
  )
}

function QuestionList({
  questions,
  evidence,
  onEvidenceClick,
}: {
  questions: AnalysisQuestion[]
  evidence: Record<string, EvidenceObject>
  onEvidenceClick: (evidenceId: string) => void
}) {
  if (questions.length === 0) return null
  return (
    <div className="mt-3 rounded-md border border-status-moderate/30 bg-status-moderate/5 p-2">
      <div className="text-[11px] font-semibold text-status-moderate">Human verification questions</div>
      <ul className="mt-1 space-y-2">
        {questions.map((question) => (
          <li key={`${question.question}-${question.evidenceIds.join(',')}`} className="text-xs text-text-muted">
            <div>{question.question}</div>
            <EvidenceChips ids={question.evidenceIds} evidence={evidence} onEvidenceClick={onEvidenceClick} />
          </li>
        ))}
      </ul>
    </div>
  )
}
