import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { fetchProcessedImageryManifest } from '../../api/client'
import type { EventEvidenceResponse, EvidenceObject, InvestigationMap, ProcessedImageryAsset, StructuredAnalysis, StructuredAnalysisAssessment } from '../../api/types'
import { Button } from '../ui/Button'
import { Toggle } from '../ui/Toggle'
import { AnalysisProgress } from './AnalysisProgress'

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

function AvailabilityStatus({ status }: { status: EventEvidenceResponse['availability'][number]['status'] }) {
  if (status === 'available') return { symbol: '✓', label: 'Available', className: 'text-status-good' }
  if (status === 'no_suitable_pass') return { symbol: '!', label: 'Limited · no suitable pass', className: 'text-status-moderate' }
  return { symbol: '×', label: 'Unavailable', className: 'text-status-urgent' }
}

function AvailabilitySummary({ items }: { items: EventEvidenceResponse['availability'] }) {
  return <Section title="Availability">
    <div className="divide-y divide-border/60 rounded border border-border bg-bg/60 text-[11px] print:border-black/20 print:bg-transparent">
      {items.map((item) => {
        const status = AvailabilityStatus({ status: item.status })
        return <div key={item.kind} className="flex items-center justify-between gap-3 px-2 py-1.5" title={item.reason}>
          <span className="capitalize">{item.kind}</span>
          <span className={`flex items-center gap-1 text-right ${status.className}`} aria-label={`${item.kind}: ${status.label}. ${item.reason}`}>
            <span aria-hidden="true">{status.symbol}</span>
            {status.label}
          </span>
        </div>
      })}
    </div>
  </Section>
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

// Weather is real for the first time now (18 variables x 2 windows = up to
// 38 items) and the original per-item card treatment made it the new
// "boatload" the moment it stopped being empty. A compact table -- one row
// per variable, one column per window -- shows every variable (nothing
// hidden, per direct instruction that this should be "everything") without
// 38 expand/collapse cards. Window name is parsed from the observation
// text ("... during current" / "... during T-7d") since the EvidenceObject
// schema itself has no separate window field; every template this drawer's
// own export script writes ends that way, so this is not guessing at
// someone else's format.
function windowFromObservation(observation: string): string {
  const match = /during (\S+)/.exec(observation)
  return match ? match[1] : 'unknown'
}

function formatWeatherValue(item: EvidenceObject): string {
  if (item.value && typeof item.value === 'object' && 'mean' in (item.value as Record<string, unknown>)) {
    const v = item.value as { mean: number; min: number; max: number }
    return `${v.mean} (${v.min}–${v.max})`
  }
  if (typeof item.value === 'number') return `${item.value}${item.unit ? ` ${item.unit}` : ''}`
  return valueText(item.value)
}

function WeatherSummary({ items }: { items: EvidenceObject[] }) {
  if (!items.length) return <p className="text-[11px] text-text-faint">No EvidenceObjects are available for this metric in the current audit artifact.</p>
  const byType = new Map<string, Map<string, EvidenceObject>>()
  const typeOrder: string[] = []
  const windowOrder: string[] = []
  for (const item of items) {
    const window = windowFromObservation(item.observation)
    if (!byType.has(item.type)) { byType.set(item.type, new Map()); typeOrder.push(item.type) }
    byType.get(item.type)!.set(window, item)
    if (!windowOrder.includes(window)) windowOrder.push(window)
  }
  return <table className="w-full text-[11px]">
    <thead><tr className="text-left text-text-faint"><th className="pb-1 font-normal">Variable</th>{windowOrder.map((w) => <th key={w} className="pb-1 pl-2 text-right font-normal">{w}</th>)}</tr></thead>
    <tbody>{typeOrder.map((type) => <tr key={type} className="border-t border-border/60">
      <td className="py-1 pr-2 capitalize">{type.replace(/_/g, ' ')}</td>
      {windowOrder.map((w) => { const item = byType.get(type)?.get(w); return <td key={w} className="py-1 pl-2 text-right">{item ? formatWeatherValue(item) : 'n/a'}</td> })}
    </tr>)}</tbody>
  </table>
}

// Portal to <body>, not rendered inline -- the drawer itself is
// `absolute` with `overflow-y-auto`, so an inline overlay would be
// clipped/scrolled with the rest of the panel instead of covering the
// viewport.
function ImageLightbox({ url, caption, onClose }: { url: string; caption: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={caption}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6"
      onClick={onClose}
    >
      <button type="button" className="absolute top-4 right-4 text-sm text-white/80 hover:text-white" onClick={onClose}>CLOSE ✕</button>
      <figure className="max-h-full max-w-full" onClick={(event) => event.stopPropagation()}>
        {/* The committed Process API render is shown at its native size in the
            lightbox; it remains a display product, not analytical imagery. */}
        <img src={url} alt={caption} className="max-h-[85vh] max-w-full rounded object-contain" />
        <figcaption className="mt-2 text-center text-xs text-white/70">{caption} · processed display product, not analytical imagery</figcaption>
      </figure>
    </div>,
    document.body,
  )
}

// Four scenes is not a reason to make the actual imagery tiny. Processed
// artifacts use the drawer width; catalogue quicklooks remain metadata-only.
function ImagerySummary({ eventId, items }: { eventId: string; items: EvidenceObject[] }) {
  const [lightbox, setLightbox] = useState<{ url: string; caption: string } | null>(null)
  const [assets, setAssets] = useState<ProcessedImageryAsset[]>([])
  const [manifestError, setManifestError] = useState(false)
  const [failedPaths, setFailedPaths] = useState<Set<string>>(new Set())

  useEffect(() => {
    let active = true
    setAssets([])
    setManifestError(false)
    setFailedPaths(new Set())
    if (!items.length) return () => { active = false }
    fetchProcessedImageryManifest()
      .then((manifest) => { if (active) setAssets(manifest.events[eventId]?.assets ?? []) })
      .catch(() => { if (active) setManifestError(true) })
    return () => { active = false }
  }, [eventId, items.length])

  if (!items.length) return <p className="text-[11px] text-text-faint">Processed imagery unavailable; no imagery EvidenceObjects are present in the current audit artifact.</p>
  return <div className="space-y-1.5">{items.map((item) => {
    const v = (item.value ?? {}) as Record<string, unknown>
    const sensor = typeof v.sensor === 'string' ? v.sensor : item.type
    const position = typeof v.position === 'string' ? v.position.replace('_', '-') : ''
    const cloud = v.cloud_cover
    const asset = assets.find((candidate) => candidate.source_evidence_id === (item.evidence_id ?? item.evidenceId))
    const processed = asset && !failedPaths.has(asset.path) ? asset : null
    const caption = `${sensor} ${position}`.trim()
    const processing = typeof v.display_processing === 'string' ? v.display_processing : undefined
    const product = typeof v.product === 'string' ? v.product : undefined
    return <div key={item.evidence_id ?? item.evidenceId ?? `${sensor}-${position}`} className="rounded border border-border bg-bg/60 p-2 text-[11px] print:border-black/20 print:bg-transparent">
      {processed && <button
        type="button"
        onClick={() => setLightbox({ url: processed.path, caption })}
        className="mb-2 block w-full print:pointer-events-none"
        aria-label={`Enlarge ${caption} processed imagery`}
      >
        <img
          src={processed.path}
          alt={`${caption} processed imagery`}
          loading="lazy"
          width={processed.width}
          height={processed.height}
          className="max-h-[420px] w-full cursor-zoom-in rounded border border-border object-contain object-center hover:border-accent"
          onError={() => setFailedPaths((paths) => new Set(paths).add(processed.path))}
        />
      </button>}
      {!processed && <p className="mb-2 rounded border border-status-moderate/30 bg-status-moderate/5 p-2 text-text-faint">{manifestError ? 'Processed imagery manifest unavailable for this event.' : 'Processed imagery unavailable for this scene. Catalogue quicklook metadata is retained, but no small legacy preview is displayed as investigation evidence.'}</p>}
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-2"><span className="font-mono text-accent print:text-black">{sensor} {position}</span>{typeof cloud === 'number' && <span className="text-text-muted">{cloud.toFixed(0)}% cloud</span>}</div>
        <div className="mt-0.5 text-text-muted">{item.time_window}</div>
        {(product || processing) && <div className="mt-1 text-[10px] text-text-faint">{product && <>Product: {product}</>}{product && processing && ' · '}{processing && <>Display: {processing}</>}</div>}
      </div>
    </div>
  })}
  {lightbox && <ImageLightbox url={lightbox.url} caption={lightbox.caption} onClose={() => setLightbox(null)} />}
  </div>
}

const DRAWER_MIN_WIDTH = 360
const DRAWER_MAX_WIDTH = 900
const DRAWER_DEFAULT_WIDTH = 440

// Plain pointerdown/pointermove/pointerup, not a library -- one drag handle,
// no need for a resize dependency. Width lives in this component only; it
// does not need to survive a remount or be shared with anything else.
function useDrawerWidth() {
  const [width, setWidth] = useState(DRAWER_DEFAULT_WIDTH)
  const [dragging, setDragging] = useState(false)
  const dragStart = useRef({ x: 0, width: DRAWER_DEFAULT_WIDTH })

  // Listeners live only while a drag is in progress, added/removed by this
  // effect rather than by hand in the down/up handlers -- avoids the two
  // handlers needing to reference each other to clean up after themselves.
  useEffect(() => {
    if (!dragging) return
    const onPointerMove = (event: PointerEvent) => {
      // Dragging left (toward the map) widens the drawer since it is
      // anchored to the right edge -- width grows as x - clientX increases.
      const next = dragStart.current.width + (dragStart.current.x - event.clientX)
      setWidth(Math.min(DRAWER_MAX_WIDTH, Math.max(DRAWER_MIN_WIDTH, next)))
    }
    const onPointerUp = () => setDragging(false)
    document.addEventListener('pointermove', onPointerMove)
    document.addEventListener('pointerup', onPointerUp)
    return () => {
      document.removeEventListener('pointermove', onPointerMove)
      document.removeEventListener('pointerup', onPointerUp)
    }
  }, [dragging])

  const onPointerDown = useCallback((event: ReactPointerEvent) => {
    event.preventDefault()
    dragStart.current = { x: event.clientX, width }
    setDragging(true)
  }, [width])

  return { width, onPointerDown }
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

function AnalysisAssessmentSummary({ assessment }: { assessment: StructuredAnalysisAssessment }) {
  return <div className="space-y-2 rounded border border-border bg-bg/60 p-2 text-[11px]">
    <div className="font-semibold text-accent">{assessment.role}</div>
    {assessment.findings.map((finding) => <article key={finding.hypothesis_id} className="border-t border-border/60 pt-2 first:border-0 first:pt-0">
      <div className="flex justify-between gap-2"><span className="font-mono">{finding.hypothesis_id}</span><span>{finding.support_score}/100 · {finding.evidence_sufficiency}</span></div>
      <p className="mt-1 text-text-muted">{finding.summary}</p>
      <p className="mt-1 text-[10px] text-text-faint">Supports: {finding.supporting_evidence_ids.join(', ') || 'n/a'} · Contradicts: {finding.contradicting_evidence_ids.join(', ') || 'n/a'}</p>
    </article>)}
  </div>
}

function StructuredAnalysisSection({ analysis, loading, error, startedAt, stage, onGenerate }: { analysis?: StructuredAnalysis; loading: boolean; error?: string; startedAt?: string; stage?: string | null; onGenerate: () => void }) {
  return <Section title="AI interpretation: Investigator / Skeptic">
    {!analysis && loading && startedAt && <AnalysisProgress startedAt={startedAt} stage={stage} returnMessage="The job keeps running if you close this drawer. Reopen it to see the result." />}
    {!analysis && <><p className="text-[11px] leading-4 text-text-muted">No structured analysis has been run for this FireEvent. Generation uses only the EvidenceObjects and relationship summaries shown in this audit.</p><Button variant="primary" className="mt-3 w-full text-[10px]" disabled={loading} onClick={onGenerate}>{loading ? 'GENERATING INVESTIGATION ANALYSIS…' : 'GENERATE INVESTIGATION ANALYSIS'}</Button></>}
    {error && <div role="alert" className="mt-3 rounded border border-status-urgent/40 bg-status-urgent/10 p-2 text-[11px] text-red-200">{error}</div>}
    {analysis && <><p className="mb-2 text-[11px] leading-4 text-text-muted">Final structured assessments are evidence-linked interpretations, separate from deterministic evidence and human review. They do not establish cause or responsibility.</p><div className="grid gap-2 lg:grid-cols-2"><AnalysisAssessmentSummary assessment={analysis.final_assessment.investigator} /><AnalysisAssessmentSummary assessment={analysis.final_assessment.skeptic} /></div><div className="mt-3 rounded border border-border bg-bg/60 p-2 text-[11px]"><div className="font-semibold">Unresolved disagreement / verification</div>{analysis.unresolved_questions.length ? <ul className="mt-1 space-y-1 text-text-muted">{analysis.unresolved_questions.map((question, index) => <li key={`${question.question}-${index}`}>• {question.question} <span className="font-mono text-text-faint">({question.evidence_ids.join(', ')})</span></li>)}</ul> : <p className="mt-1 text-text-faint">No final disagreement was retained.</p>}</div><p className="mt-2 text-[10px] text-text-faint">Model/pipeline: {analysis.algorithm_version}. Evidence IDs are shown above; no private reasoning transcript is stored or displayed.</p></>}
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
  analysis,
  analysisLoading,
  analysisStartedAt,
  analysisStage,
  analysisError,
  onGenerateAnalysis,
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
  analysis?: StructuredAnalysis
  analysisLoading: boolean
  analysisStartedAt?: string
  analysisStage?: string | null
  analysisError?: string
  onGenerateAnalysis: () => void
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
  const { width, onPointerDown } = useDrawerWidth()

  return <aside aria-label="FireEvent evidence drawer" data-print-layout="evidence-document" className="evidence-drawer absolute top-0 right-0 z-20 h-full overflow-y-auto border-l border-border-strong bg-panel/98 text-text shadow-2xl print:static print:h-auto print:w-full print:overflow-visible print:border-0 print:bg-white print:text-black print:shadow-none" style={{ width: `min(${width}px, 92vw)` }}>
    {/* Drag left/right to resize -- anchored to the left edge since the
        drawer itself is pinned to the right side of the screen. */}
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize evidence drawer"
      onPointerDown={onPointerDown}
      className="absolute top-0 left-0 z-20 h-full w-1.5 cursor-ew-resize touch-none hover:bg-accent/40 print:hidden"
    />
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
        <div className="grid grid-cols-2 gap-2 text-xs"><div><span className="text-text-muted">Scope relation</span><div>{data.scopeRelation}</div></div><div><span className="text-text-muted">Sufficiency</span><div>{data.evidenceSufficiency.value}</div></div><div><span className="text-text-muted">Investigation priority</span><div>{data.investigationPriority}</div></div><div><span className="text-text-muted">Human workflow</span><div>{data.reviewState}</div></div><div><span className="text-text-muted">Chronology</span><div>{data.event.firstDetection.slice(0, 16)} → {data.event.lastDetection.slice(0, 16)}</div></div><div><span className="text-text-muted">Observations</span><div>{data.event.observationCount} · max FRP {data.event.maxFrp?.toFixed(2) ?? 'n/a'} MW</div></div></div>
        <DetectionWindow firstDetection={data.event.firstDetection} lastDetection={data.event.lastDetection} reviewStart={reviewStart} reviewEnd={reviewEnd} />
        <p className="mt-2 text-[10px] text-text-muted">{data.evidenceSufficiency.reason}</p>
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
      <AvailabilitySummary items={data.availability} />
      <RelatedFireEvents graph={graph} error={graphError} eventId={eventId} />
      <DerivedSummary complexity={grouped.complexity} priority={grouped.priority} />
      <StructuredAnalysisSection analysis={analysis} loading={analysisLoading} error={analysisError} startedAt={analysisStartedAt} stage={analysisStage} onGenerate={onGenerateAnalysis} />
      <MetricSection title="Peat / event-buffer intersection" note="The drawer shows the event footprint or buffer intersection only when a peat EvidenceObject is available. Peat overlap is environmental context and does not establish an underground path, cause, or responsibility." items={grouped.peat} />
      <Section title="Weather time window"><p className="mb-2 text-[11px] leading-4 text-text-muted">Every Open-Meteo/ERA5 hourly variable, during the event and the 7 days before it. Historical values, not a forecast; missing weather is not negative evidence.</p><WeatherSummary items={grouped.weather} /></Section>
      <Section title="Imagery acquisition metadata"><p className="mb-2 text-[11px] leading-4 text-text-muted">Closest usable Sentinel-1 (SAR) and Sentinel-2 (optical) scenes before and after the event. Processed display assets are loaded from the committed imagery manifest; catalogue quicklooks are metadata only.</p><ImagerySummary eventId={eventId} items={grouped.imagery} /></Section>

      {/* Print-only: the full log "EXPORT TO PDF" produces -- every observed-
          evidence item and every complexity/priority component, including
          NOT_EVALUATED ones, plus the full per-edge relationship evidence.
          Kept off-screen so the interactive drawer stays succinct. */}
      <div className="hidden print:block">
        <Section title="Observed evidence (full)"><EvidenceList items={data.observedEvidence} /></Section>
        <Section title="Fire Complexity: every candidate feature"><EvidenceList items={grouped.complexity} /></Section>
        <Section title="Investigation Priority: every component"><EvidenceList items={grouped.priority} /></Section>
        <Section title="Weather: every variable/window as full EvidenceObjects"><EvidenceList items={grouped.weather} /></Section>
        <Section title="Imagery: full scene metadata"><EvidenceList items={grouped.imagery} /></Section>
        {graph && graph.edges.length > 0 && <Section title="Related FireEvents: full relationship evidence">
          <div className="space-y-2">{graph.edges.map((edge) => <article key={`${edge.sourceEventId}-${edge.targetEventId}`} className="rounded border border-black/20 p-2 text-[11px]">
            <div className="flex justify-between gap-2"><span className="font-mono">{edge.sourceEventId} → {edge.targetEventId}</span><span>{edge.distanceKm} km</span></div>
            <div className="mt-1">{edge.state} · {edge.supportingEvidenceIds?.join(', ') || 'no supporting IDs'} · {edge.modelVersion}</div>
            <div className="mt-2"><EvidenceList items={edge.evidence ?? []} /></div>
          </article>)}</div>
        </Section>}
        {grouped.other.length > 0 && <Section title="Other deterministic evidence"><EvidenceList items={grouped.other} /></Section>}
      </div>
    </>}
  </aside>
}
