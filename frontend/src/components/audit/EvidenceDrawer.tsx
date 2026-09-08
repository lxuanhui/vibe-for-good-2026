import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchAuditEventEvidence, fetchInvestigationMap } from '../../api/client'
import type { EventEvidenceResponse, EvidenceObject, InvestigationMap } from '../../api/types'

function valueText(value: unknown): string {
  if (value == null) return 'not evaluated'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function EvidenceList({ items }: { items: EvidenceObject[] }) {
  const [openId, setOpenId] = useState<string | null>(null)
  if (!items.length) return <p className="text-[11px] text-text-faint">No EvidenceObjects are available for this metric in the current audit artifact.</p>
  return <div className="space-y-2">{items.map((item) => {
    const id = item.evidence_id ?? item.evidenceId ?? `${item.category}-${item.type}`
    const open = openId === id
    return <article key={id} className="rounded border border-border bg-bg/60 p-2">
      <button className="w-full text-left" aria-expanded={open} onClick={() => setOpenId(open ? null : id)}>
        <div className="flex items-start justify-between gap-2"><span className="font-mono text-[10px] text-accent">{id}</span><span className="text-[10px] text-text-faint">{item.quality == null ? 'quality n/a' : `quality ${(item.quality * 100).toFixed(0)}%`}</span></div>
        <p className="mt-1 text-[11px] leading-4">{item.observation}</p>
        <p className="mt-1 text-[10px] text-text-muted">{item.source} · {item.time_window ?? 'time window unavailable'}</p>
        <span className="mt-1 block text-[10px] text-accent">{open ? 'Hide metric basis' : 'Inspect metric basis'}</span>
      </button>
      {open && <div className="mt-2 border-t border-border pt-2 text-[10px] text-text-muted">
        <div><span className="text-text-faint">Value:</span> {valueText(item.value)}</div>
        {item.algorithm_version && <div><span className="text-text-faint">Algorithm:</span> {item.algorithm_version}</div>}
        {item.raw_reference && <div><span className="text-text-faint">Raw reference:</span> {item.raw_reference}</div>}
        {(item.limitations ?? []).length > 0 && <div className="mt-1 text-status-moderate"><span className="text-text-faint">Limitations:</span> {item.limitations?.join(' ')}</div>}
      </div>}
    </article>
  })}</div>
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="border-t border-border-strong px-4 py-3"><h3 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-text-muted">{title}</h3>{children}</section>
}

function MetricSection({ title, note, items }: { title: string; note: string; items: EvidenceObject[] }) {
  return <Section title={title}><p className="mb-2 text-[11px] leading-4 text-text-muted">{note}</p><EvidenceList items={items} /></Section>
}

function GraphEvidence({ graph }: { graph: InvestigationMap | undefined }) {
  if (!graph) return <p className="text-[11px] text-text-faint">Relationship graph is loading or unavailable.</p>
  if (!graph.edges.length) return <p className="text-[11px] text-text-faint">No candidate graph edges were returned for this event.</p>
  return <div className="space-y-2">
    <p className="text-[11px] text-text-muted">Highlighted nodes: {graph.nodes.length} ({graph.nodes.filter((node) => node.mapRole === 'SELECTED').length} selected, {graph.nodes.filter((node) => node.mapRole === 'EXTERNAL_CONTEXT').length} context).</p>
    {graph.edges.map((edge) => <article key={`${edge.sourceEventId}-${edge.targetEventId}`} className="rounded border border-border bg-bg/60 p-2 text-[11px]">
      <div className="flex justify-between gap-2"><span className="font-mono text-accent">{edge.sourceEventId} → {edge.targetEventId}</span><span>{edge.distanceKm} km</span></div>
      <div className="mt-1 text-text-muted">{edge.state} · {edge.supportingEvidenceIds?.join(', ') || 'no supporting IDs'} · {edge.modelVersion}</div>
      <div className="mt-2"><EvidenceList items={edge.evidence ?? []} /></div>
    </article>)}
  </div>
}

export function EvidenceDrawer({ auditId, eventId, onClose }: { auditId: string; eventId: string; onClose: () => void }) {
  const [state, setState] = useState<{ loading: boolean; data?: EventEvidenceResponse; error?: string }>({ loading: true })
  const [graph, setGraph] = useState<InvestigationMap>()
  useEffect(() => {
    let active = true
    setState({ loading: true })
    setGraph(undefined)
    Promise.all([fetchAuditEventEvidence(auditId, eventId), fetchInvestigationMap(auditId, [eventId])]).then(([data, map]) => {
      if (active) { setState({ loading: false, data }); setGraph(map) }
    }).catch((reason: unknown) => { if (active) setState({ loading: false, error: reason instanceof Error ? reason.message : 'Evidence could not be loaded.' }) })
    return () => { active = false }
  }, [auditId, eventId])
  const grouped = useMemo(() => {
    const items = state.data?.derivedEvidence ?? []
    const categories = ['peat', 'weather', 'surface', 'propagation', 'imagery']
    return {
      complexity: items.filter((item) => item.category === 'fire-complexity'),
      priority: items.filter((item) => item.category === 'investigation-priority'),
      peat: items.filter((item) => item.category === 'peat'),
      weather: items.filter((item) => item.category === 'weather'),
      surface: items.filter((item) => categories.includes(item.category) && (item.type.includes('surface') || item.type.includes('envelope') || item.category === 'propagation')),
      imagery: items.filter((item) => item.category === 'imagery'),
      other: items.filter((item) => !['fire-complexity', 'investigation-priority', ...categories].includes(item.category)),
    }
  }, [state.data])
  return <aside aria-label="FireEvent evidence drawer" className="absolute top-0 right-0 z-20 h-full w-[min(440px,92vw)] overflow-y-auto border-l border-border-strong bg-panel/98 text-text shadow-2xl">
    <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-strong bg-panel px-4 py-3"><div><div className="text-sm font-semibold">FireEvent evidence</div><div className="font-mono text-[10px] text-accent">{eventId}</div></div><button className="text-xs text-text-muted hover:text-text" onClick={onClose} aria-label="Close evidence drawer">CLOSE</button></div>
    {state.loading && <div role="status" className="p-4 text-xs text-text-muted">Loading current-audit evidence...</div>}
    {state.error && <div role="alert" className="m-4 rounded border border-status-urgent/40 bg-status-urgent/10 p-3 text-xs text-red-200">{state.error}</div>}
    {state.data && <>
      <Section title="Summary"><div className="grid grid-cols-2 gap-2 text-xs"><div><span className="text-text-muted">Scope relation</span><div>{state.data.scopeRelation}</div></div><div><span className="text-text-muted">Sufficiency</span><div>{state.data.evidenceSufficiency.value}</div></div><div><span className="text-text-muted">Chronology</span><div>{state.data.event.firstDetection.slice(0, 16)} → {state.data.event.lastDetection.slice(0, 16)}</div></div><div><span className="text-text-muted">Observations</span><div>{state.data.event.observationCount} · max FRP {state.data.event.maxFrp?.toFixed(2) ?? '—'} MW</div></div></div><p className="mt-2 text-[10px] text-text-muted">{state.data.evidenceSufficiency.reason}</p></Section>
      <Section title="Observed evidence"><EvidenceList items={state.data.observedEvidence} /></Section>
      <MetricSection title="Peat / event-buffer intersection" note="The drawer shows the event footprint or buffer intersection only when a peat EvidenceObject is available. Peat overlap is environmental context and does not establish an underground path, cause, or responsibility." items={grouped.peat} />
      <MetricSection title="Weather time window" note="Historical component values and time-series points appear here when weather enrichment is present. Missing weather is not negative evidence." items={grouped.weather} />
      <MetricSection title="Surface compatibility" note="Any ellipse/envelope comparison is first-order surface-fire compatibility only; it does not model underground peat propagation." items={grouped.surface} />
      <MetricSection title="Imagery acquisition metadata" note="Only selected product metadata is shown when available: acquisition, sensor/product, cloud/orbit and temporal context. No suitable pass is not replaced with stale imagery." items={grouped.imagery} />
      <Section title="Related FireEvents"><GraphEvidence graph={graph} /></Section>
      <Section title="Deterministic / derived evidence"><EvidenceList items={grouped.other} /><div className="mt-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Fire Complexity contributing features</div><div className="mt-2"><EvidenceList items={grouped.complexity} /></div><div className="mt-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Investigation Priority contributing components</div><p className="mb-2 text-[11px] leading-4 text-text-muted">This is review routing, not culpability or responsibility.</p><EvidenceList items={grouped.priority} /></Section>
      <Section title="Availability / limitations"><div className="space-y-2">{state.data.availability.map((item) => <div key={item.kind} className="rounded border border-border bg-bg/60 p-2 text-[11px]"><div className="flex justify-between"><span className="capitalize">{item.kind}</span><span className="text-status-moderate">{item.status}</span></div><p className="mt-1 text-text-muted">{item.reason}</p></div>)}</div></Section>
      <Section title="Provenance"><div className="text-[10px] text-text-muted">Algorithms: {state.data.provenance.algorithmVersions.join(' · ')}</div><p className="mt-1 text-[10px] text-text-faint">Expand any metric to inspect its Evidence ID, source, time window, value, quality, raw reference and limitations.</p></Section>
    </>}
  </aside>
}
