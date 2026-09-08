import type { AuditEvent, TriageEvidence, TriageRule } from '../../api/types'
import { useAuditEvent } from '../../api/hooks'
import { STAGE1_STATE_COLORS, STAGE1_STATE_LABELS } from '../../lib/layerColors'

function formatTimestamp(iso: string): string {
  return iso.replace('T', ' ').replace('+00:00', ' UTC').replace('Z', ' UTC')
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-text-faint">{label}</div>
      <div className="mt-0.5 font-mono text-xs text-text">{value}</div>
    </div>
  )
}

function RuleRow({ rule }: { rule: TriageRule }) {
  const neutral = rule.points === 0
  return (
    <li className="border-l-2 py-1.5 pl-3" style={{ borderColor: neutral ? '#303947' : STAGE1_STATE_COLORS.LIKELY_FIRE }}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium text-text">{rule.feature}</span>
        <span className="shrink-0 font-mono text-[10px] text-text-faint">
          {rule.effect}
          {rule.points !== 0 && ` ${rule.points > 0 ? '+' : ''}${rule.points}`}
        </span>
      </div>
      <p className="mt-1 text-[11px] leading-5 text-text-muted">{rule.explanation}</p>
    </li>
  )
}

function EvidenceRow({ evidence }: { evidence: TriageEvidence }) {
  return (
    <li className="rounded border border-border bg-bg/60 p-2.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-[10px] break-all text-accent">{evidence.evidence_id}</span>
        <span className="shrink-0 text-[10px] text-text-faint">quality {evidence.quality.toFixed(2)}</span>
      </div>
      <p className="mt-1.5 text-[11px] leading-5 text-text">{evidence.observation}</p>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-text-faint">
        <span>{evidence.source}</span>
        <span>{evidence.category}</span>
        <span>{evidence.time_window}</span>
      </div>
      {evidence.limitations.length > 0 && (
        // Absence and imprecision are findings, not gaps to write around
        // (spec Section 17) -- so limitations render at the same weight as the
        // observation, never folded away behind a disclosure.
        <ul className="mt-1.5 space-y-0.5">
          {evidence.limitations.map((limitation) => (
            <li key={limitation} className="text-[10px] leading-4 text-status-moderate">
              Limitation: {limitation}
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

interface Props {
  auditId: string
  event: AuditEvent
  onClose: () => void
}

export function EventEvidencePanel({ auditId, event, onClose }: Props) {
  const { detail, error } = useAuditEvent(auditId, event.eventId)
  const triage = event.triage

  return (
    <aside className="pointer-events-auto flex h-full w-[380px] flex-col border-l border-border-strong bg-panel/95 backdrop-blur">
      <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="font-mono text-xs break-all text-text">{event.eventId}</div>
          <div className="mt-1 flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: STAGE1_STATE_COLORS[triage.state] }}
            />
            <span className="text-xs text-text">{STAGE1_STATE_LABELS[triage.state]}</span>
            <span className="font-mono text-[10px] text-text-faint">{triage.state}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded border border-border-strong px-2 py-1 text-[10px] text-text-muted hover:text-text"
        >
          Close
        </button>
      </header>

      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
        <section>
          <h3 className="text-[10px] uppercase tracking-[0.18em] text-text-faint">Observed</h3>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <Row label="First detection" value={formatTimestamp(event.firstDetection)} />
            <Row label="Last detection" value={formatTimestamp(event.lastDetection)} />
            <Row label="Observations" value={String(event.observationCount)} />
            <Row label="Duration" value={`${event.durationHours.toFixed(1)} h`} />
            <Row label="Max FRP" value={event.maxFrp === null ? 'not reported' : `${event.maxFrp} MW`} />
            <Row label="Mean FRP" value={event.meanFrp === null ? 'not reported' : `${event.meanFrp} MW`} />
            <Row
              label="Centroid"
              value={`${event.centroid.lat.toFixed(4)}, ${event.centroid.lon.toFixed(4)}`}
            />
            <Row label="Extent" value={`${event.spatialExtentKm.toFixed(2)} km`} />
          </div>
          {!event.sensorMix && (
            <p className="mt-2 text-[10px] leading-4 text-text-faint">
              Satellite and instrument are not present in this export, so the sensor mix is unknown
              rather than empty.
            </p>
          )}
        </section>

        <section>
          <h3 className="text-[10px] uppercase tracking-[0.18em] text-text-faint">
            Derived — Stage-1 triage
          </h3>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <Row label="Fire support" value={String(triage.fireSupportScore)} />
            <Row label="Non-fire support" value={String(triage.nonFireSupportScore)} />
          </div>
          <p className="mt-2 text-[11px] leading-5 text-text-muted">{triage.budgetReason}</p>
          <p className="mt-2 text-[10px] text-text-faint">
            Algorithm {triage.algorithmVersion}. This is a statement about whether the observations
            support a fire, not about how it started or who is answerable for it.
          </p>
        </section>

        {detail?.triageDetail && (
          <section>
            <h3 className="text-[10px] uppercase tracking-[0.18em] text-text-faint">
              Rules evaluated ({detail.triageDetail.rules.length})
            </h3>
            <ul className="mt-2 space-y-1">
              {detail.triageDetail.rules.map((rule) => (
                <RuleRow key={rule.rule_id} rule={rule} />
              ))}
            </ul>
          </section>
        )}

        {detail?.triageDetail && (
          <section>
            <h3 className="text-[10px] uppercase tracking-[0.18em] text-text-faint">
              Evidence ({detail.triageDetail.evidence.length})
            </h3>
            <ul className="mt-2 space-y-2">
              {detail.triageDetail.evidence.map((evidence) => (
                <EvidenceRow key={evidence.evidence_id} evidence={evidence} />
              ))}
            </ul>
          </section>
        )}

        {!detail && !error && (
          <p className="text-[11px] text-text-faint">Loading the Stage-1 breakdown…</p>
        )}
        {error && (
          <p className="rounded border border-status-urgent/40 bg-status-urgent/10 px-3 py-2 text-[11px] text-red-200">
            {error}
          </p>
        )}
      </div>

      <footer className="border-t border-border px-4 py-3">
        <p className="text-[10px] leading-4 text-text-faint">
          Triage narrows what a person reviews. Disposition remains an auditor decision.
        </p>
      </footer>
    </aside>
  )
}
