import { useState } from 'react'
import type { AuditScope } from './api/types'
import { AuditStart } from './components/scope/AuditStart'
import { ScopePreviewMap } from './components/scope/ScopePreviewMap'
import { type ScopePreview } from './lib/scope'

function readyPreview(scope: AuditScope): ScopePreview {
  return {
    geometry: scope.geometry,
    bbox: scope.bbox!,
    centroid: scope.centroid!,
    bufferBbox: scope.buffer_bbox!,
    bufferGeometry: scope.buffer_geometry!,
  }
}

export default function App() {
  const [scope, setScope] = useState<AuditScope | null>(null)

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
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 p-6">
        <section className="rounded-xl border border-border-strong bg-panel p-5">
          <p className="text-xs uppercase tracking-[0.2em] text-accent">Scope captured</p>
          <h1 className="mt-1 text-xl font-semibold">Ready for historical fire reconstruction</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">
            The private management-unit boundary, review period, and external context buffer are now carried by this anonymized review. Issue #57 can address the stable audit ID without requiring company identity.
          </p>
          <div className="mt-4 grid gap-3 text-xs sm:grid-cols-4">
            <div><div className="text-text-faint">Review period</div><div className="mt-1 font-mono">{scope.review_start} → {scope.review_end}</div></div>
            <div><div className="text-text-faint">Context buffer</div><div className="mt-1 font-mono">{scope.context_buffer_km} km</div></div>
            <div><div className="text-text-faint">Scope ID</div><div className="mt-1 font-mono">{scope.scope_id}</div></div>
            <div><div className="text-text-faint">Handoff</div><div className="mt-1 text-status-good">{scope.status}</div></div>
          </div>
        </section>
        <section className="min-h-[480px] flex-1 overflow-hidden rounded-xl border border-border-strong bg-panel shadow-2xl">
          <div className="border-b border-border px-5 py-4 text-sm font-semibold">Boundary and context buffer</div>
          <div className="h-[calc(100%-57px)] min-h-[420px]"><ScopePreviewMap scope={readyPreview(scope)} /></div>
        </section>
      </main>
    </div>
  )
}
