import { useEffect, useState } from 'react'
import type { AuditScope } from './api/types'
import { AuditStart } from './components/scope/AuditStart'
import { HistoricalInvestigation } from './components/audit/HistoricalInvestigation'
import { useAppStore } from './store/useAppStore'

export default function App() {
  const [scope, setScope] = useState<AuditScope | null>(null)
  const setAuditSession = useAppStore((state) => state.setAuditSession)

  useEffect(() => {
    if (scope) setAuditSession(scope.audit_id)
  }, [scope, setAuditSession])

  if (!scope) return <AuditStart onReady={setScope} />

  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-strong bg-panel px-6">
        <div>
          <div className="text-sm font-semibold tracking-wide">Environmental Assurance Console</div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-text-faint">Audit review ready</div>
        </div>
        <span className="font-mono text-xs text-accent">{scope.audit_id}</span>
      </header>
      <main className="min-h-0 flex-1 overflow-hidden"><HistoricalInvestigation scope={scope} /></main>
    </div>
  )
}
