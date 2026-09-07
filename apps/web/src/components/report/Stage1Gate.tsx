import type { Stage1GateResult } from '../../api/types'

export function Stage1Gate({ gate }: { gate: Stage1GateResult }) {
  const passed = gate.outcome === 'passed'
  return (
    <div className="rounded-lg border border-border-strong bg-panel-raised p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Stage 1 validation</h3>
        <span
          className={`rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
            passed ? 'border-status-good/50 text-status-good' : 'border-status-urgent/50 text-status-urgent'
          }`}
        >
          {passed ? 'Passed — qualified for investigation' : 'Rejected — no investigation budget spent'}
        </span>
      </div>
      <ol className="space-y-2">
        {gate.checks.map((check) => (
          <li key={check.id} className="flex items-start gap-2 text-xs">
            <span
              className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                check.passed ? 'bg-status-good/20 text-status-good' : 'bg-status-urgent/20 text-status-urgent'
              }`}
            >
              {check.passed ? '✓' : '✕'}
            </span>
            <div>
              <div className="text-text">{check.label}</div>
              {check.detail && <div className="text-text-faint">{check.detail}</div>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
