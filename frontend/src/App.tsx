import { useEffect, useState } from 'react'
import type { AuditScope } from './api/types'
import { AuditStart } from './components/scope/AuditStart'
import { ScopedMapLanding } from './components/scope/ScopedMapLanding'
import { HistoricalInvestigation } from './components/audit/HistoricalInvestigation'
import { useAppStore } from './store/useAppStore'

// Canonical spec §5: create audit review -> build fire history -> historical
// register (table) -> spatial investigation (map). AuditStart is the entry
// point until a scope exists; the register is the default view after that,
// with the scoped map and the selected-events investigation map both reached
// from it, not shown before it.
export default function App() {
  const [scope, setScope] = useState<AuditScope | null>(null)
  const [scopePanelOpen, setScopePanelOpen] = useState(false)
  const setAuditSession = useAppStore((state) => state.setAuditSession)
  const viewMode = useAppStore((state) => state.viewMode)
  const setViewMode = useAppStore((state) => state.setViewMode)

  useEffect(() => {
    if (scope) setAuditSession(scope.audit_id)
  }, [scope, setAuditSession])

  if (!scope) return <AuditStart onReady={setScope} />

  return (
    <div className="relative h-screen overflow-hidden bg-bg text-text">
      {viewMode === 'scoped-map'
        ? <ScopedMapLanding scope={scope} onOpenScope={() => setScopePanelOpen(true)} onOpenRegister={() => setViewMode('table')} />
        : <HistoricalInvestigation scope={scope} onOpenScopedMap={() => setViewMode('scoped-map')} />}
      {scopePanelOpen && (
        <div className="absolute inset-y-3 right-3 z-30 w-[min(680px,calc(100%-1.5rem))]">
          <AuditStart
            onReady={(next) => { setScope(next); setViewMode('table'); setScopePanelOpen(false) }}
            overlay
            onClose={() => setScopePanelOpen(false)}
          />
        </div>
      )}
    </div>
  )
}
