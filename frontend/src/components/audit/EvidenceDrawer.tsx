import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchAuditEventEvidence } from '../../api/client'
import type { EventEvidenceResponse, EvidenceObject } from '../../api/types'

function EvidenceList({ items }: { items: EvidenceObject[] }) {
  return <div className="space-y-2">{items.map((item) => <article key={item.evidence_id ?? item.evidenceId} className="rounded border border-border bg-bg/60 p-2">
    <div className="flex items-start justify-between gap-2"><span className="font-mono text-[10px] text-accent">{item.evidence_id ?? item.evidenceId}</span><span className="text-[10px] text-text-faint">{item.quality == null ? 'quality n/a' : `quality ${(item.quality * 100).toFixed(0)}%`}</span></div>
    <p className="mt-1 text-[11px] leading-4">{item.observation}</p>
    <p className="mt-1 text-[10px] text-text-muted">{item.source} · {item.time_window ?? 'time window unavailable'}</p>
    {item.algorithm_version && <p className="text-[10px] text-text-faint">Algorithm: {item.algorithm_version}</p>}
    {(item.limitations ?? []).length > 0 && <p className="mt-1 text-[10px] text-status-moderate">Limitation: {item.limitations?.join(' ')}</p>}
  </article>)}</div>
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="border-t border-border-strong px-4 py-3"><h3 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-text-muted">{title}</h3>{children}</section>
}

export function EvidenceDrawer({ auditId, eventId, onClose }: { auditId: string; eventId: string; onClose: () => void }) {
  const [state, setState] = useState<{ loading: boolean; data?: EventEvidenceResponse; error?: string }>({ loading: true })
  useEffect(() => {
    let active = true
    setState({ loading: true })
    fetchAuditEventEvidence(auditId, eventId).then((data) => { if (active) setState({ loading: false, data }) }).catch((reason: unknown) => { if (active) setState({ loading: false, error: reason instanceof Error ? reason.message : 'Evidence could not be loaded.' }) })
    return () => { active = false }
  }, [auditId, eventId])
  const grouped = useMemo(() => {
    const items = state.data?.derivedEvidence ?? []
    return { complexity: items.filter((item) => item.category === 'fire-complexity'), priority: items.filter((item) => item.category === 'investigation-priority'), other: items.filter((item) => !['fire-complexity', 'investigation-priority'].includes(item.category)) }
  }, [state.data])
  return <aside aria-label="FireEvent evidence drawer" className="absolute top-0 right-0 z-20 h-full w-[min(440px,92vw)] overflow-y-auto border-l border-border-strong bg-panel/98 text-text shadow-2xl">
    <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-strong bg-panel px-4 py-3"><div><div className="text-sm font-semibold">FireEvent evidence</div><div className="font-mono text-[10px] text-accent">{eventId}</div></div><button className="text-xs text-text-muted hover:text-text" onClick={onClose} aria-label="Close evidence drawer">CLOSE</button></div>
    {state.loading && <div role="status" className="p-4 text-xs text-text-muted">Loading current-audit evidence…</div>}
    {state.error && <div role="alert" className="m-4 rounded border border-status-urgent/40 bg-status-urgent/10 p-3 text-xs text-red-200">{state.error}</div>}
    {state.data && <>
      <Section title="Summary"><div className="grid grid-cols-2 gap-2 text-xs"><div><span className="text-text-muted">Scope relation</span><div>{state.data.scopeRelation}</div></div><div><span className="text-text-muted">Sufficiency</span><div>{state.data.evidenceSufficiency.value}</div></div><div><span className="text-text-muted">Chronology</span><div>{state.data.event.firstDetection.slice(0, 16)} → {state.data.event.lastDetection.slice(0, 16)}</div></div><div><span className="text-text-muted">Observations</span><div>{state.data.event.observationCount} · max FRP {state.data.event.maxFrp?.toFixed(2) ?? '—'} MW</div></div></div><p className="mt-2 text-[10px] text-text-muted">{state.data.evidenceSufficiency.reason}</p></Section>
      <Section title="Observed evidence"><EvidenceList items={state.data.observedEvidence} /></Section>
      <Section title="Deterministic / derived evidence"><EvidenceList items={grouped.other} /><div className="mt-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Fire Complexity components</div><div className="mt-2"><EvidenceList items={grouped.complexity} /></div><div className="mt-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Investigation Priority components</div><div className="mt-2"><EvidenceList items={grouped.priority} /></div></Section>
      <Section title="Availability / limitations"><div className="space-y-2">{state.data.availability.map((item) => <div key={item.kind} className="rounded border border-border bg-bg/60 p-2 text-[11px]"><div className="flex justify-between"><span className="capitalize">{item.kind}</span><span className="text-status-moderate">{item.status}</span></div><p className="mt-1 text-text-muted">{item.reason}</p></div>)}</div><p className="mt-3 text-[10px] text-text-faint">Imagery is never replaced with stale or unrelated imagery. Loading is shown while this request is pending; the API reports available metadata/product, no suitable pass, or unavailable/error.</p></Section>
      <Section title="Provenance"><div className="text-[10px] text-text-muted">Algorithms: {state.data.provenance.algorithmVersions.join(' · ')}</div><div className="mt-1 text-[10px] text-text-faint">Evidence IDs, source, time window, quality and limitations are retained per metric.</div></Section>
    </>}
  </aside>
}
