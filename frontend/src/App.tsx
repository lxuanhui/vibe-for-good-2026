import { useEffect, useState } from 'react'
import type { AuditScope } from './api/types'
import { AuditStart } from './components/scope/AuditStart'
import { DEMO_SCOPE, ScopedMapLanding } from './components/scope/ScopedMapLanding'
import { HistoricalInvestigation } from './components/audit/HistoricalInvestigation'
import { useAppStore } from './store/useAppStore'

export default function App() {
  const [scope, setScope] = useState<AuditScope>(DEMO_SCOPE)
  const [scopePanelOpen, setScopePanelOpen] = useState(false)
  const setAuditSession = useAppStore((state) => state.setAuditSession)
  const viewMode = useAppStore((state) => state.viewMode)

  useEffect(() => {
    if (scope) setAuditSession(scope.audit_id)
  }, [scope, setAuditSession])

  return (
    <div className="relative h-screen overflow-hidden bg-bg text-text">
      <ScopedMapLanding scope={scope} onOpenScope={() => setScopePanelOpen(true)} onOpenRegister={() => useAppStore.getState().setViewMode('table')} />
      {viewMode === 'table' && <div className="absolute inset-0 z-20 bg-bg"><HistoricalInvestigation scope={scope} /></div>}
      {scopePanelOpen && <div className="absolute inset-y-3 right-3 z-30 w-[min(680px,calc(100%-1.5rem))]"><AuditStart onReady={(next) => { setScope(next); setScopePanelOpen(false) }} overlay onClose={() => setScopePanelOpen(false)} /></div>}
    </div>
  )
}
