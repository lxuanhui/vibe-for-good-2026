import { useState } from 'react'
import type { AuditEventScope, AuditEventSource, AuditScope } from '../../api/types'
import { AuditStart } from '../scope/AuditStart'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-sm text-text">{value}</div>
      <div className="text-[9px] uppercase tracking-wider text-text-faint">{label}</div>
    </div>
  )
}

interface Props {
  scope: AuditEventScope | null
  source: AuditEventSource | null
  total: number
  loaded: number
  loading: boolean
}

export function ScopeHeader({ scope, source, total, loaded, loading }: Props) {
  const [startingReview, setStartingReview] = useState(false)
  const [newScope, setNewScope] = useState<AuditScope | null>(null)

  return (
    <>
      <div className="pointer-events-auto absolute top-4 left-4 w-[320px] rounded-lg border border-border-strong bg-panel/95 backdrop-blur">
        <div className="flex items-start justify-between gap-2 border-b border-border px-4 py-3">
          <div>
            <div className="text-sm font-semibold tracking-wide">Environmental Assurance</div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-text-faint">
              Reconstructed fire history
            </div>
          </div>
          <button
            type="button"
            onClick={() => setStartingReview(true)}
            className="shrink-0 rounded border border-accent-muted px-2 py-1 text-[10px] tracking-wider text-accent hover:bg-accent-muted/20"
          >
            NEW REVIEW
          </button>
        </div>

        {scope && (
          <div className="px-4 py-3">
            <div className="text-xs leading-5 text-text">{scope.label}</div>
            <div className="mt-0.5 font-mono text-[10px] text-text-muted">
              {scope.reviewStart} → {scope.reviewEnd}
            </div>

            {source && (
              <div className="mt-3 grid grid-cols-3 gap-2 border-t border-border pt-3">
                <Stat label="Observations" value={source.observationsUsed.toLocaleString()} />
                <Stat label="Fire events" value={scope.eventCount.toLocaleString()} />
                <Stat label="To review" value={scope.reviewQueueCount.toLocaleString()} />
              </div>
            )}

            {/* Stage-1 currently narrows nothing on FIRMS alone. Saying so is
                the point of the metric -- a queue count presented without its
                ratio would imply a reduction that has not happened. */}
            {scope.reviewQueueCount >= scope.eventCount && (
              <p className="mt-2 text-[10px] leading-4 text-status-moderate">
                Stage-1 narrows nothing here: FIRMS alone carries no peat, land-use or weather
                context, so most rules cannot be evaluated and every event stays in the queue.
              </p>
            )}

            {source && (
              <p className="mt-2 border-t border-border pt-2 text-[10px] leading-4 text-text-faint">
                {source.dataset} · {source.region} · {source.window}. {source.note}
              </p>
            )}

            {loading && (
              <p className="mt-2 font-mono text-[10px] text-accent">
                loading {loaded.toLocaleString()}
                {total ? ` / ${total.toLocaleString()}` : ''}…
              </p>
            )}
          </div>
        )}

        {!scope && loading && (
          <div className="px-4 py-3 text-[11px] text-text-faint">Loading audit history…</div>
        )}
      </div>

      {/* The scope-entry flow from #56, unchanged, over the map instead of in
          front of it. Creating a review still validates the boundary and makes
          the history-build handoff; what it does not yet have is a
          reconstructed history to show, which is why the map stays on the demo
          scope afterwards. */}
      {startingReview && (
        <div className="pointer-events-auto absolute inset-0 z-10 overflow-y-auto bg-bg/80 backdrop-blur-sm">
          <div className="flex min-h-full items-start justify-center p-6">
            <div className="w-full max-w-6xl overflow-hidden rounded-xl border border-border-strong bg-bg shadow-2xl">
              <div className="flex items-center justify-between border-b border-border-strong px-5 py-3">
                <span className="text-xs uppercase tracking-[0.2em] text-text-faint">
                  New audit review
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setStartingReview(false)
                    setNewScope(null)
                  }}
                  className="rounded border border-border-strong px-2 py-1 text-[10px] text-text-muted hover:text-text"
                >
                  Close
                </button>
              </div>
              {newScope ? (
                <div className="space-y-3 px-6 py-8">
                  <p className="text-xs uppercase tracking-[0.2em] text-accent">Scope captured</p>
                  <h2 className="text-lg font-semibold">Handoff recorded</h2>
                  <p className="max-w-2xl text-sm leading-6 text-text-muted">
                    The boundary, review period and context buffer are carried by this anonymised
                    review. Historical reconstruction for a user-supplied scope is issue #57; until
                    it runs, this audit has no events and the map continues to show the demo scope.
                  </p>
                  <div className="grid gap-3 pt-2 text-xs sm:grid-cols-4">
                    <div>
                      <div className="text-text-faint">Audit ID</div>
                      <div className="mt-1 font-mono break-all">{newScope.audit_id}</div>
                    </div>
                    <div>
                      <div className="text-text-faint">Review period</div>
                      <div className="mt-1 font-mono">
                        {newScope.review_start} → {newScope.review_end}
                      </div>
                    </div>
                    <div>
                      <div className="text-text-faint">Context buffer</div>
                      <div className="mt-1 font-mono">{newScope.context_buffer_km} km</div>
                    </div>
                    <div>
                      <div className="text-text-faint">Status</div>
                      <div className="mt-1 text-status-good">{newScope.status}</div>
                    </div>
                  </div>
                </div>
              ) : (
                <AuditStart onReady={setNewScope} />
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
