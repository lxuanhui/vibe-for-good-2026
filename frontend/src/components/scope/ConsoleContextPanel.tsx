import { useEffect, useRef, useState } from 'react'
import { fetchDemoDatasetSummary } from '../../api/client'
import type { RefObject } from 'react'
import type { DemoDatasetSummary } from '../../api/types'
import { APP_DESCRIPTOR } from '../../lib/brand'
import { Brand } from '../brand/Brand'

function Chevron() {
  return (
    <svg viewBox="0 0 12 12" className="mt-1.5 hidden h-3.5 w-3.5 shrink-0 text-text-muted sm:block" aria-hidden="true">
      <path d="M4 2.5 7.5 6 4 9.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// The four steps are the efficiency chain the product is built to make
// visible (CLAUDE.md, "State of things"): observations -> events -> in scope
// -> ranked. `layer` marks where the record stops being observed and starts
// being derived -- the first of the four layers the spec forbids collapsing.
function chainSteps(summary: DemoDatasetSummary) {
  const { rawObservations, qualifiedObservations, fireEvents, requiringHumanReview } = summary.progression
  return [
    { value: rawObservations, label: 'raw detections', layer: 'Observed' as const },
    { value: qualifiedObservations, label: 'pass the confidence gate', layer: 'Observed' as const },
    { value: fireEvents, label: 'clustered FireEvents', layer: 'Derived' as const },
    { value: requiringHumanReview, label: 'routed to human review', layer: 'Derived' as const },
  ]
}

function ProgressionChain({ summary }: { summary: DemoDatasetSummary }) {
  const steps = chainSteps(summary)
  return (
    <ol className="grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-4">
      {steps.map((step, index) => (
        <li key={step.label} className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {/* An unknowable count prints as a dash rather than a zero. This
                panel reads the full artifact, where every step is measured,
                so the dash is a guard against a future caller passing a
                narrowed scope through (#161), not a state seen today. */}
            <div className="text-xl font-semibold tabular-nums tracking-tight text-text">{step.value === null ? 'n/a' : step.value.toLocaleString()}</div>
            <div className="mt-0.5 text-xs leading-4 text-text-muted">{step.label}</div>
            <div
              className={`mt-1.5 text-[10px] uppercase tracking-[0.18em] ${
                step.layer === 'Observed' ? 'text-text-faint' : 'text-accent'
              }`}
            >
              {step.layer}
            </div>
          </div>
          {index < steps.length - 1 && <Chevron />}
        </li>
      ))}
    </ol>
  )
}

export function ConsoleContextPanel({ onDismiss, closeRef }: { onDismiss: () => void; closeRef?: RefObject<HTMLButtonElement | null> }) {
  const [summary, setSummary] = useState<DemoDatasetSummary | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    fetchDemoDatasetSummary()
      .then((next) => { if (live) setSummary(next) })
      .catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [])

  return (
    <div className="p-6">
      <div className="flex items-start justify-between gap-6">
        <div className="max-w-[68ch]">
          <Brand subtitle={APP_DESCRIPTOR} className="mb-4" />
          <h2 id="console-context-heading" className="text-lg font-semibold tracking-tight">
            What this console does
          </h2>
          <p className="mt-2 text-sm leading-6 text-text-muted">
            It reconstructs the historical fire record inside an audit scope you define: a management-unit
            boundary and a review period, so that limited desk-review and field-verification time lands on
            the events worth a human question.
          </p>
          <p className="mt-2 text-sm leading-6 text-text-muted">
            It does not determine blame, responsibility, intent or legal liability. It scores FireEvents,
            never companies, and geographic association is recorded as context rather than cause. Every
            metric opens back to the evidence it came from, and the decision stays with you.
          </p>
        </div>
        <button
          ref={closeRef}
          type="button"
          onClick={onDismiss}
          className="shrink-0 rounded border border-border-strong px-3 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-panel-raised hover:text-text"
        >
          Dismiss
        </button>
      </div>

      <div className="mt-6 border-t border-border pt-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h3 className="text-sm font-semibold">The dataset behind this build</h3>
          {summary && (
            <p className="text-xs text-text-faint">
              {summary.dataset}
              {summary.region && ` · ${summary.region}`}
              {summary.window && ` · ${summary.window.replace('..', ' → ')}`}
            </p>
          )}
        </div>

        <div className="mt-4">
          {summary && <ProgressionChain summary={summary} />}
          {!summary && !failed && (
            <p className="text-xs text-text-faint" role="status">Reading the committed dataset…</p>
          )}
          {failed && (
            // No cached copy of these counts exists in the client, and inventing
            // plausible ones would be exactly the fabrication the product bans.
            <p className="text-xs text-text-faint">
              The dataset summary could not be read. The register reports the same counts once the fire
              history is built.
            </p>
          )}
        </div>

        <dl className="mt-6 grid gap-x-8 gap-y-4 text-xs leading-5 sm:grid-cols-3">
          <div>
            <dt className="font-semibold text-text">Observed</dt>
            <dd className="mt-1 text-text-muted">
              NASA FIRMS satellite detections, committed to the repository so the same review is
              reproducible offline.
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-text">Derived here</dt>
            <dd className="mt-1 text-text-muted">
              Clustering detections into FireEvents, Stage-1 triage, and priority routing. Computed from
              those observations, not observed.
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-text">Not live in this build</dt>
            <dd className="mt-1 text-text-muted">
              Satellite imagery, weather and peat enrichment, the peat hydrology map layers, and the
              Investigator/Skeptic analysis. Each appears as an explicit unavailable state or a labelled
              demo fixture, never as a finding. The hydrology layers draw an illustrative placeholder
              field until the cached SMAP subset exists.
            </dd>
          </div>
        </dl>
      </div>
    </div>
  )
}

/**
 * The explanation as a closable dialog over the map. A modal rather than an
 * inline band because the map has to be the first thing on screen, and an
 * inline explainer would push it below the fold -- the whole reason this
 * moved. Closing is unconditional: it never gates the workflow.
 */
export function ConsoleContextModal({ onClose }: { onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-bg/45 p-4 sm:p-8"
      // Backdrop only: a click that started inside the dialog and ended here
      // (a drag over text) must not close it.
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="console-context-heading"
        className="relative my-auto w-full max-w-4xl rounded-xl border border-border-strong bg-panel shadow-2xl"
      >
        <ConsoleContextPanel onDismiss={onClose} closeRef={closeRef} />
      </div>
    </div>
  )
}
