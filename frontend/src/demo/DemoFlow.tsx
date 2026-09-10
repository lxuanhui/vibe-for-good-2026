import { useCallback, useEffect, useState } from 'react'
import { addToAuditPack } from '../api/client'
import { AuditReportView } from '../components/audit/AuditReportView'
import { HistoricalInvestigation } from '../components/audit/HistoricalInvestigation'
import { AuditLanding } from '../components/scope/AuditLanding'
import { AuditStart } from '../components/scope/AuditStart'
import { ScopedMapLanding } from '../components/scope/ScopedMapLanding'
import { Button } from '../components/ui/Button'
import { useAppStore } from '../store/useAppStore'
import { DEMO_FOCUS_EVENT_ID, DEMO_REGISTER_SELECTION, DEMO_STEPS } from './demoScript'
import { useDemoSession } from './useDemoSession'

// The /demo path (#274). The same screens the console mounts at /, in a
// fixed order, with a presenter bar that says which step this is and what
// to say. It is not a second console: App.tsx's screens are rendered
// unchanged, driven through the zustand store and their existing props, so
// anything that works here works off the demo path too.
//
// What it deliberately does not do: show the first-load context modal (the
// presenter has read it), or let a step depend on a click inside a screen.
// Every transition is the arrow keys or the bar's buttons.

function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function DemoFlow() {
  const session = useDemoSession()
  const [index, setIndex] = useState(0)
  const [packed, setPacked] = useState(false)
  const [packError, setPackError] = useState('')
  const step = DEMO_STEPS[index]
  const setAuditSession = useAppStore((state) => state.setAuditSession)

  const next = useCallback(() => setIndex((current) => Math.min(current + 1, DEMO_STEPS.length - 1)), [])
  const back = useCallback(() => setIndex((current) => Math.max(current - 1, 0)), [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // Not while typing in a field: the scope form has date inputs.
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
      if (event.key === 'ArrowRight' || event.key === 'PageDown') { event.preventDefault(); next() }
      if (event.key === 'ArrowLeft' || event.key === 'PageUp') { event.preventDefault(); back() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, back])

  // The register selection is what seeds the map's relationship graph and
  // the "INVESTIGATE ON MAP" handoff; set it once the audit exists so the
  // register opens with the three rows already checked.
  const scope = session.scope
  useEffect(() => {
    if (scope) setAuditSession(scope.audit_id, DEMO_REGISTER_SELECTION)
  }, [scope, setAuditSession])

  // The report renders the engagement pack, so the focus event goes into
  // the pack the moment the report step is reached. Idempotent on the API.
  useEffect(() => {
    if (step.view !== 'report' || !scope || packed) return
    let active = true
    addToAuditPack(scope.audit_id, DEMO_FOCUS_EVENT_ID)
      .then(() => { if (active) setPacked(true) })
      .catch((reason: unknown) => {
        if (active) setPackError(reason instanceof Error ? reason.message : 'The FireEvent could not be added to the pack.')
      })
    return () => { active = false }
  }, [step.view, scope, packed])

  const noop = () => undefined
  const needsScope = step.view !== 'landing'

  let body: React.ReactNode
  if (needsScope && !scope) {
    body = (
      <div className="flex h-full items-center justify-center bg-bg text-text">
        <div className="max-w-md rounded-xl border border-border-strong bg-panel p-6 text-sm">
          {session.status === 'error'
            ? <><div className="font-semibold">The demo audit could not be prepared.</div><p className="mt-2 text-text-muted">{session.error}</p><p className="mt-2 text-text-muted">Check that the API is reachable, then reload this page.</p></>
            : <><div className="font-semibold">Preparing the demo audit.</div><p className="mt-2 text-text-muted">Creating the review, setting the demo study area and building the fire history from the 2019 artifact.</p></>}
        </div>
      </div>
    )
  } else if (step.view === 'landing') {
    body = <AuditLanding onStartAudit={next} onOpenContext={noop} />
  } else if (step.view === 'scope' && scope) {
    body = (
      <>
        <AuditLanding onStartAudit={noop} onOpenContext={noop} />
        <div className="absolute inset-3 z-30">
          <AuditStart onReady={next} initialScope={scope} overlay onClose={back} />
        </div>
      </>
    )
  } else if (step.view === 'register' && scope) {
    body = <HistoricalInvestigation scope={scope} onOpenScopedMap={next} onOpenScope={noop} />
  } else if (step.view === 'map' && scope) {
    body = (
      <ScopedMapLanding
        scope={scope}
        onOpenScope={noop}
        onOpenRegister={() => setIndex(2)}
        onViewReport={() => setIndex(DEMO_STEPS.length - 1)}
        focusEventId={step.focus ? DEMO_FOCUS_EVENT_ID : undefined}
      />
    )
  } else if (step.view === 'report' && scope) {
    body = packed
      ? <AuditReportView auditId={scope.audit_id} onBack={back} />
      : (
        <div className="flex h-full items-center justify-center bg-bg text-text">
          <div className="max-w-md rounded-xl border border-border-strong bg-panel p-6 text-sm">
            {packError
              ? <><div className="font-semibold">The FireEvent could not be added to the pack.</div><p className="mt-2 text-text-muted">{packError}</p></>
              : <div className="text-text-muted">Adding the FireEvent to the engagement pack.</div>}
          </div>
        </div>
      )
  }

  const analysis = session.analysis
  let analysisNote = ''
  if (step.analysis) {
    if (analysis?.jobStatus === 'COMPLETE') analysisNote = `Analysis generated at ${formatTime(analysis.completedAt)}, about 50 seconds of Investigator and Skeptic rounds.`
    else if (analysis?.jobStatus === 'RUNNING') analysisNote = 'Analysis is generating now. Two rounds take about 50 seconds.'
    else if (analysis?.jobStatus === 'FAILED') analysisNote = 'The last analysis attempt failed. Press Generate in the drawer to retry.'
    else analysisNote = 'No analysis has been generated yet.'
  }

  return (
    <div className="relative h-screen overflow-hidden bg-bg text-text">
      <div className="absolute inset-x-0 top-0 bottom-16">{body}</div>
      <aside
        aria-label="Demo presenter bar"
        className="absolute inset-x-0 bottom-0 z-40 flex h-16 items-center gap-4 border-t border-border-strong bg-panel px-4 text-xs"
      >
        <span className="rounded bg-status-moderate px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-bg">Demo</span>
        <div className="min-w-0 flex-1">
          <div className="truncate">
            <span className="font-semibold">Step {index + 1} of {DEMO_STEPS.length}: {step.title}.</span>{' '}
            <span className="text-text-muted">{step.cue}</span>
          </div>
          <div className="truncate text-[10px] text-text-faint">
            Real 2019 NASA FIRMS artifact, real API
            {scope ? ` · audit ${scope.audit_id.slice(0, 8)}` : ''}
            {analysisNote ? ` · ${analysisNote}` : ''}
          </div>
        </div>
        <Button onClick={back} disabled={index === 0}>BACK</Button>
        <Button variant="primary" onClick={next} disabled={index === DEMO_STEPS.length - 1}>NEXT</Button>
      </aside>
    </div>
  )
}
