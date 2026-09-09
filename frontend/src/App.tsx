import { useEffect, useState } from 'react'
import type { AuditScope } from './api/types'
import { AuditStart } from './components/scope/AuditStart'
import { ConsoleContextModal } from './components/scope/ConsoleContextPanel'
import { ScopedMapLanding } from './components/scope/ScopedMapLanding'
import { HistoricalInvestigation } from './components/audit/HistoricalInvestigation'
import { createDefaultScope } from './lib/bootstrapScope'
import { useConsoleContextPanel } from './lib/useConsoleContextPanel'
import { useAppStore } from './store/useAppStore'

// The map is on screen before any scope exists. This reverses the
// scope-form-first entry PR #118 took from canonical spec §28 ("table first,
// map second") -- see docs/decision-log.md, 2026-09-09, for what was weighed.
// What §28 protects is the *screening* order, and that survives: the register
// is still where events are screened, and the map still draws nothing outside
// an audit boundary and its buffer. Only the landing surface changed.
//
// The default scope is created through the same real endpoints the scope form
// uses, never a hand-built object. #118 removed a hardcoded DEMO_SCOPE for
// exactly that reason, and putting the map back must not put that back too.
export default function App() {
  const [scope, setScope] = useState<AuditScope | null>(null)
  const [bootstrapError, setBootstrapError] = useState('')
  const [scopePanelOpen, setScopePanelOpen] = useState(false)
  const setAuditSession = useAppStore((state) => state.setAuditSession)
  const viewMode = useAppStore((state) => state.viewMode)
  const setViewMode = useAppStore((state) => state.setViewMode)
  const contextPanel = useConsoleContextPanel()

  // The store defaults to the register, which was right while the form was the
  // entry point. The landing is the map now.
  useEffect(() => {
    setViewMode('scoped-map')
  }, [setViewMode])

  useEffect(() => {
    let live = true
    createDefaultScope()
      .then((next) => { if (live) setScope(next) })
      .catch((reason) => {
        if (live) setBootstrapError(reason instanceof Error ? reason.message : 'The default audit scope could not be created.')
      })
    return () => { live = false }
  }, [])

  useEffect(() => {
    if (scope) setAuditSession(scope.audit_id)
  }, [scope, setAuditSession])

  return (
    <div className="relative h-screen overflow-hidden bg-bg text-text">
      {viewMode === 'scoped-map' || !scope
        ? (
          <ScopedMapLanding
            scope={scope}
            onOpenScope={() => setScopePanelOpen(true)}
            onOpenRegister={() => setViewMode('table')}
            onOpenContext={contextPanel.reopen}
          />
        )
        : <HistoricalInvestigation scope={scope} onOpenScopedMap={() => setViewMode('scoped-map')} />}

      {bootstrapError && !scope && (
        <div role="alert" className="absolute inset-x-0 bottom-0 z-20 border-t border-status-urgent/40 bg-status-urgent/10 px-5 py-3 text-xs text-red-200">
          {bootstrapError}
          <button type="button" className="ml-3 underline hover:text-red-100" onClick={() => setScopePanelOpen(true)}>Build a scope by hand</button>
        </div>
      )}

      {scopePanelOpen && (
        <div className="absolute inset-y-3 right-3 z-30 w-[min(680px,calc(100%-1.5rem))]">
          <AuditStart
            onReady={(next) => { setScope(next); setViewMode('table'); setScopePanelOpen(false) }}
            overlay
            onClose={() => setScopePanelOpen(false)}
          />
        </div>
      )}

      {contextPanel.open && <ConsoleContextModal onClose={contextPanel.dismiss} />}
    </div>
  )
}
