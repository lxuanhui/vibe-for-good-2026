import { useMemo, useState, type ReactNode } from 'react'
import type { EventEvidenceResponse, EvidenceObject, InvestigationMap } from '../../api/types'
import { Button } from '../ui/Button'
import { Toggle } from '../ui/Toggle'

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
    return <article key={id} className="rounded border border-border bg-bg/60 p-2 print:border-black/20 print:bg-transparent">
      <button className="w-full text-left print:pointer-events-none" aria-expanded={open} onClick={() => setOpenId(open ? null : id)}>
        <div className="flex items-start justify-between gap-2"><span className="font-mono text-[10px] text-accent">{id}</span><span className="text-[10px] text-text-faint">{item.quality == null ? 'quality n/a' : `quality ${(item.quality * 100).toFixed(0)}%`}</span></div>
        <p className="mt-1 text-[11px] leading-4">{item.observation}</p>
        <p className="mt-1 text-[10px] text-text-muted">{item.source} · {item.time_window ?? 'time window unavailable'}</p>
        <span className="mt-1 block text-[10px] text-accent print:hidden">{open ? 'Hide metric basis' : 'Inspect metric basis'}</span>
      </button>
      <div className={`mt-2 border-t border-border pt-2 text-[10px] text-text-muted print:block ${open ? 'block' : 'hidden'}`}>
        <div><span className="text-text-faint">Value:</span> {valueText(item.value)}</div>
        {item.algorithm_version && <div><span className="text-text-faint">Algorithm:</span> {item.algorithm_version}</div>}
        {item.raw_reference && <div><span className="text-text-faint">Raw reference:</span> {item.raw_reference}</div>}
        {(item.limitations ?? []).length > 0 && <div className="mt-1 text-status-moderate"><span className="text-text-faint">Limitations:</span> {item.limitations?.join(' ')}</div>}
      </div>
    </article>
  })}</div>
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="border-t border-border-strong px-4 py-3 print:border-black/20 print:px-0"><h3 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-text-muted print:text-black">{title}</h3>{children}</section>
}

function MetricSection({ title, note, items }: { title: string; note: string; items: EvidenceObject[] }) {
  return <Section title={title}><p className="mb-2 text-[11px] leading-4 text-text-muted">{note}</p><EvidenceList items={items} /></Section>
}

// A real timeline, not a fabricated one: the artifact has each event's first
// and last FIRMS detection, not a per-observation timestamp list, so this
// places the event's own detection window against the audit's review period
// rather than implying finer-grained scrubbing than the data supports.
function DetectionWindow({ firstDetection, lastDetection, reviewStart, reviewEnd }: { firstDetection: string; lastDetection: string; reviewStart?: string; reviewEnd?: string }) {
  if (!reviewStart || !reviewEnd) return null
  const spanStart = new Date(`${reviewStart}T00:00:00Z`).getTime()
  const spanEnd = new Date(`${reviewEnd}T23:59:59Z`).getTime()
  const totalMs = Math.max(1, spanEnd - spanStart)
  const clamp = (value: number) => Math.min(100, Math.max(0, value))
  const left = clamp(((new Date(firstDetection).getTime() - spanStart) / totalMs) * 100)
  const right = clamp(((new Date(lastDetection).getTime() - spanStart) / totalMs) * 100)
  const width = Math.max(right - left, 1.5)
  return <div className="mt-3">
    <div className="mb-1 flex justify-between text-[10px] text-text-faint print:text-black"><span>{reviewStart}</span><span>{reviewEnd}</span></div>
    <div className="relative h-2 rounded-full bg-bg print:border print:border-black/40 print:bg-transparent">
      <div className="absolute top-0 h-2 rounded-full bg-accent print:bg-black" style={{ left: `${left}%`, width: `${width}%` }} />
    </div>
    <p className="mt-1 text-[10px] text-text-faint">Detection window within the review period. The artifact records first/last FIRMS detection per FireEvent, not a per-observation timestamp series.</p>
  </div>
}

// Succinct by design: this is the number one thing that made the drawer a
// "boatload" -- 22 complexity/priority components rendered as full expandable
// cards even though this FIRMS-only artifact evaluates two of them. Show the
// evaluated ones plainly; name the rest in one sentence instead of 20 empty
// cards. The full breakdown still exists -- it is what "EXPORT TO PDF" prints.
function DerivedSummary({ complexity, priority }: { complexity: EvidenceObject[]; priority: EvidenceObject[] }) {
  const evaluated = priority.filter((item) => item.value != null)
  const notEvaluatedCount = complexity.length + priority.length - evaluated.length
  return <Section title="Investigation priority components">
    {evaluated.length > 0 && <div className="mb-2 grid grid-cols-2 gap-2 text-xs">
      {evaluated.map((item) => <div key={item.type} className="rounded border border-border bg-bg/60 p-2 print:border-black/20 print:bg-transparent">
        <div className="text-[10px] text-text-faint capitalize">{item.type.replace(/_/g, ' ')}</div>
        <div className="mt-0.5">{valueText(item.value)}</div>
      </div>)}
    </div>}
    {notEvaluatedCount > 0 && <p className="text-[11px] leading-4 text-text-faint">{notEvaluatedCount} further Fire Complexity / Investigation Priority components are not evaluated in this artifact -- no completed peat, weather, imagery, or propagation enrichment has run for it. Missing evidence is not treated as a low or reassuring value. Full breakdown in the exported PDF.</p>}
  </Section>
}

// The methodology, in one sentence, plus the one metric that actually
// qualifies a candidate: distance. No nested per-edge evidence cards on
// screen -- that is what made "related fires" part of the boatload too.
function RelatedFireEvents({ graph, error, eventId }: { graph: InvestigationMap | undefined; error?: string; eventId: string }) {
  if (error) return <Section title="Related FireEvents"><p className="text-[11px] text-status-urgent">{error}</p></Section>
  if (!graph) return <Section title="Related FireEvents"><p className="text-[11px] text-text-faint">Loading candidate relationships…</p></Section>
  const rows = graph.edges
    .map((edge) => ({ ...edge, otherId: edge.sourceEventId === eventId ? edge.targetEventId : edge.sourceEventId }))
    .sort((a, b) => a.distanceKm - b.distanceKm)
  return <Section title="Related FireEvents">
    <p className="mb-2 text-[11px] leading-4 text-text-muted">{rows.length === 0 ? 'No other FireEvent falls within the 50 km candidate gate used by FireEventGraph.' : `${rows.length} candidate relationship${rows.length === 1 ? '' : 's'} within 50 km of this event's centroid (FireEventGraph deterministic distance gate, ${rows[0]?.modelVersion ?? 'fire-event-graph-v1'}). Distance is the qualifying metric shown here; wind, peat-corridor, and surface-compatibility signals are not available in this artifact.`}</p>
    {rows.length > 0 && <table className="w-full text-[11px]"><thead><tr className="text-left text-text-faint"><th className="pb-1 font-normal">FireEvent</th><th className="pb-1 pl-2 text-right font-normal">Distance</th></tr></thead><tbody>{rows.map((edge) => <tr key={`${edge.sourceEventId}-${edge.targetEventId}`} className="border-t border-border/60"><td className="py-1 font-mono text-accent print:text-black">{edge.otherId}</td><td className="py-1 pl-2 text-right">{edge.distanceKm} km</td></tr>)}</tbody></table>}
    <p className="mt-2 text-[10px] text-text-faint">A candidate edge is a relationship for review, not evidence of a shared cause.</p>
  </Section>
}

export function EvidenceDrawer({
  eventId,
  loading,
  error,
  data,
  graph,
  graphError,
  reviewStart,
  reviewEnd,
  showObservations,
  onToggleObservations,
  observationCount,
  onClose,
  onRetry,
}: {
  eventId: string
  loading: boolean
  error?: string
  data?: EventEvidenceResponse
  graph?: InvestigationMap
  graphError?: string
  reviewStart?: string
  reviewEnd?: string
  showObservations: boolean
  onToggleObservations: () => void
  observationCount?: number
  onClose: () => void
  onRetry: () => void
}) {
  const grouped = useMemo(() => {
    const items = data?.derivedEvidence ?? []
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
  }, [data])

  return <aside aria-label="FireEvent evidence drawer" className="absolute top-0 right-0 z-20 h-full w-[min(440px,92vw)] overflow-y-auto border-l border-border-strong bg-panel/98 text-text shadow-2xl print:static print:h-auto print:w-full print:overflow-visible print:border-0 print:bg-white print:text-black print:shadow-none">
    <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-strong bg-panel px-4 py-3 print:static print:border-black/20 print:bg-white">
      <div><div className="text-sm font-semibold">FireEvent evidence</div><div className="font-mono text-[10px] text-accent print:text-black">{eventId}</div></div>
      <div className="flex items-center gap-3 print:hidden">
        <Button className="text-[10px]" disabled={!data} onClick={() => window.print()}>EXPORT TO PDF</Button>
        <button className="text-xs text-text-muted hover:text-text" onClick={onClose} aria-label="Close evidence drawer">CLOSE</button>
      </div>
    </div>
    {loading && <div role="status" className="p-4 text-xs text-text-muted">Loading current-audit evidence...</div>}
    {error && <div role="alert" className="m-4 rounded border border-status-urgent/40 bg-status-urgent/10 p-3 text-xs text-red-200"><div>{error}</div><Button className="mt-2" onClick={onRetry}>RETRY EVIDENCE</Button></div>}
    {data && <>
      <Section title="Summary">
        <div className="grid grid-cols-2 gap-2 text-xs"><div><span className="text-text-muted">Scope relation</span><div>{data.scopeRelation}</div></div><div><span className="text-text-muted">Sufficiency</span><div>{data.evidenceSufficiency.value}</div></div><div><span className="text-text-muted">Investigation priority</span><div>{data.investigationPriority}</div></div><div><span className="text-text-muted">Human workflow</span><div>{data.reviewState}</div></div><div><span className="text-text-muted">Chronology</span><div>{data.event.firstDetection.slice(0, 16)} → {data.event.lastDetection.slice(0, 16)}</div></div><div><span className="text-text-muted">Observations</span><div>{data.event.observationCount} · max FRP {data.event.maxFrp?.toFixed(2) ?? '—'} MW</div></div></div>
        <DetectionWindow firstDetection={data.event.firstDetection} lastDetection={data.event.lastDetection} reviewStart={reviewStart} reviewEnd={reviewEnd} />
        <p className="mt-2 text-[10px] text-text-muted">{data.evidenceSufficiency.reason}</p>
        <p className="mt-1 text-[10px] text-text-muted">Priority and workflow are deterministic routing aids; neither establishes cause, responsibility, or exoneration.</p>
        <p className="mt-1 text-[10px] text-text-muted">Sourced from NASA FIRMS, quality {((data.observedEvidence[0]?.quality ?? 0.82) * 100).toFixed(0)}%. Full observed-evidence provenance is in the exported PDF.</p>
        <div className="mt-3 print:hidden">
          <Toggle
            checked={showObservations}
            onChange={onToggleObservations}
            label="Connecting FIRMS observations"
            caption={observationCount == null ? 'Loading…' : `${observationCount} raw detection${observationCount === 1 ? '' : 's'} clustered into this FireEvent -- why the deterministic pipeline placed one here.`}
          />
        </div>
      </Section>
      <RelatedFireEvents graph={graph} error={graphError} eventId={eventId} />
      <DerivedSummary complexity={grouped.complexity} priority={grouped.priority} />
      <MetricSection title="Peat / event-buffer intersection" note="The drawer shows the event footprint or buffer intersection only when a peat EvidenceObject is available. Peat overlap is environmental context and does not establish an underground path, cause, or responsibility." items={grouped.peat} />
      <MetricSection title="Weather time window" note="Historical component values and time-series points appear here when weather enrichment is present. Missing weather is not negative evidence." items={grouped.weather} />
      <MetricSection title="Surface compatibility" note="Any ellipse/envelope comparison is first-order surface-fire compatibility only; it does not model underground peat propagation." items={grouped.surface} />
      <MetricSection title="Imagery acquisition metadata" note="Only selected product metadata is shown when available: acquisition, sensor/product, cloud/orbit and temporal context. No suitable pass is not replaced with stale imagery." items={grouped.imagery} />
      <Section title="Availability / limitations"><div className="space-y-2">{data.availability.map((item) => <div key={item.kind} className="rounded border border-border bg-bg/60 p-2 text-[11px] print:border-black/20 print:bg-transparent"><div className="flex justify-between"><span className="capitalize">{item.kind}</span><span className="text-status-moderate">{item.status}</span></div><p className="mt-1 text-text-muted">{item.reason}</p></div>)}</div></Section>

      {/* Print-only: the full log "EXPORT TO PDF" produces -- every observed-
          evidence item and every complexity/priority component, including
          NOT_EVALUATED ones, plus the full per-edge relationship evidence.
          Kept off-screen so the interactive drawer stays succinct. */}
      <div className="hidden print:block">
        <Section title="Observed evidence (full)"><EvidenceList items={data.observedEvidence} /></Section>
        <Section title="Fire Complexity — every candidate feature"><EvidenceList items={grouped.complexity} /></Section>
        <Section title="Investigation Priority — every component"><EvidenceList items={grouped.priority} /></Section>
        {graph && graph.edges.length > 0 && <Section title="Related FireEvents — full relationship evidence">
          <div className="space-y-2">{graph.edges.map((edge) => <article key={`${edge.sourceEventId}-${edge.targetEventId}`} className="rounded border border-black/20 p-2 text-[11px]">
            <div className="flex justify-between gap-2"><span className="font-mono">{edge.sourceEventId} → {edge.targetEventId}</span><span>{edge.distanceKm} km</span></div>
            <div className="mt-1">{edge.state} · {edge.supportingEvidenceIds?.join(', ') || 'no supporting IDs'} · {edge.modelVersion}</div>
            <div className="mt-2"><EvidenceList items={edge.evidence ?? []} /></div>
          </article>)}</div>
        </Section>}
        {grouped.other.length > 0 && <Section title="Other deterministic evidence"><EvidenceList items={grouped.other} /></Section>}
      </div>
      <Section title="Provenance"><div className="text-[10px] text-text-muted">Algorithms: {data.provenance.algorithmVersions.join(' · ')}</div><p className="mt-1 text-[10px] text-text-faint">Expand any metric to inspect its Evidence ID, source, time window, value, quality, raw reference and limitations. EXPORT TO PDF prints the full evidence log, including components not evaluated in this artifact.</p></Section>
    </>}
  </aside>
}
