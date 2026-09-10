import { useEffect, useState } from 'react'
import type { AuditScope } from './api/types'
import { AuditStart } from './components/scope/AuditStart'
import { AuditLanding } from './components/scope/AuditLanding'
import { ConsoleContextModal } from './components/scope/ConsoleContextPanel'
import { ScopedMapLanding } from './components/scope/ScopedMapLanding'
import { HistoricalInvestigation } from './components/audit/HistoricalInvestigation'
import { useConsoleContextPanel } from './lib/useConsoleContextPanel'
import { AuditReportView } from './components/audit/AuditReportView'
import { useAppStore } from './store/useAppStore'

// Canonical spec §5: create audit review -> build fire history -> historical
// register (table) -> spatial investigation (map). AuditStart is the entry
// point until a scope exists; the register is the default view after that,
// with the scoped map and the selected-events investigation map both reached
// from it, not shown before it.
//
// This reverses PR #126, which opened straight onto a Borneo map with an
// auto-created default scope. Both cannot hold: #126's landing showed the
// console before a scope existed, and the audit-scope-first flow exists to
// stop FireEvents being drawn outside an authorised boundary. The
// scope-first flow won -- see #127 for the open question about how much
// regional context the pre-scope screen should carry.
//
// The first-load explainer from #124 survives that reversal: it is a modal
// over the landing rather than over the map, because the thing it explains
// (what this console refuses to conclude) is what a first-time user needs
// before they define a scope, not after.
export default function App() {
  const [scope, setScope] = useState<AuditScope | null>(null)
  const [scopePanelOpen, setScopePanelOpen] = useState(false)
  const setAuditSession = useAppStore((state) => state.setAuditSession)
  const viewMode = useAppStore((state) => state.viewMode)
  const setViewMode = useAppStore((state) => state.setViewMode)
  const contextPanel = useConsoleContextPanel()

  function handleScopeReady(next: AuditScope) {
    // A rebuilt scope is a new audit session. Reset the register selection as
    // well as the view so FireEvents from the previous geometry cannot appear
    // selected while the replacement register loads.
    setAuditSession(next.audit_id)
    setScope(next)
    setViewMode('table')
    setScopePanelOpen(false)
  }

  useEffect(() => {
    if (scope) setAuditSession(scope.audit_id)
  }, [scope, setAuditSession])

  if (!scope) return (
    <div className="relative h-screen overflow-hidden">
      <AuditLanding onStartAudit={() => setScopePanelOpen(true)} onOpenContext={contextPanel.reopen} />
      {scopePanelOpen && (
        <div className="absolute inset-3 z-30">
          <AuditStart
            onReady={handleScopeReady}
            overlay
            onClose={() => setScopePanelOpen(false)}
          />
        </div>
      )}
      {contextPanel.open && <ConsoleContextModal onClose={contextPanel.dismiss} />}
    </div>
  )

  // The audit-package report is reached from the scoped map (the AI
  // Investigator/Skeptic loop belongs next to the investigation surface, not
  // bolted onto the register table) so it renders back into that same map
  // rather than the register on close.
  if (viewMode === 'report') {
    return (
      <div className="relative h-screen overflow-hidden bg-bg text-text">
        <AuditReportView auditId={scope.audit_id} onBack={() => setViewMode('scoped-map')} />
      </div>
    )
  }

  return (
    <div className="relative h-screen overflow-hidden bg-bg text-text">
      {viewMode === 'scoped-map'
        ? <ScopedMapLanding
            scope={scope}
            onOpenScope={() => setScopePanelOpen(true)}
            onOpenRegister={() => setViewMode('table')}
            onViewReport={() => setViewMode('report')}
          />
        : <HistoricalInvestigation scope={scope} onOpenScope={() => setScopePanelOpen(true)} onOpenScopedMap={() => setViewMode('scoped-map')} />}
      {scopePanelOpen && (
        <div className="absolute inset-3 z-30">
          <AuditStart
            onReady={handleScopeReady}
            initialScope={scope}
            overlay
            onClose={() => setScopePanelOpen(false)}
          />
        </div>
      )}
      {contextPanel.open && <ConsoleContextModal onClose={contextPanel.dismiss} />}
    </div>
  )
}
