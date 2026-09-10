import { useEffect, useMemo, useState, type FormEvent } from 'react'
import type { AuditScope } from '../../api/types'
import { buildFireHistory, createAuditReview, fetchDemoDatasetSummary, uploadAuditScope, uploadAuditScopeGeometry } from '../../api/client'
import { buildScopePreview, DEFAULT_MANAGEMENT_UNIT_GEOMETRY } from '../../lib/scope'
import { INDONESIA_FILL_COLOR } from '../../lib/layerColors'
import { Button } from '../ui/Button'
import { ScopePreviewMap } from './ScopePreviewMap'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The audit review could not be created.'
}

// The committed real dataset behind this demo is the 2019 Kalimantan haze
// window (docs/demo.md). Pre-filling it means a user who skips the upload
// still lands on a register with real FireEvents, not an empty one.
const DEFAULT_REVIEW_START = '2019-09-01'
const DEFAULT_REVIEW_END = '2019-09-05'

/** The artifact states its own coverage as "YYYY-MM-DD..YYYY-MM-DD".

  Read at runtime rather than hardcoded beside the defaults above: a second
  copy of the dates in this file would keep passing every check while the
  committed dataset moved underneath it, and the bound would then be a claim
  about a window nothing holds. */
function parseCoverage(window: string): { start: string; end: string } | null {
  const match = /^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$/.exec(window.trim())
  return match ? { start: match[1], end: match[2] } : null
}

export function AuditStart({ onReady, overlay = false, fullScreen = false, onClose }: { onReady: (scope: AuditScope) => void; overlay?: boolean; fullScreen?: boolean; onClose?: () => void }) {
  const [reviewStart, setReviewStart] = useState(DEFAULT_REVIEW_START)
  const [reviewEnd, setReviewEnd] = useState(DEFAULT_REVIEW_END)
  const [contextBuffer, setContextBuffer] = useState('25')
  const [file, setFile] = useState<File | null>(null)
  const [geometry, setGeometry] = useState<unknown>(DEFAULT_MANAGEMENT_UNIT_GEOMETRY)
  const [fileError, setFileError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [coverage, setCoverage] = useState<{ start: string; end: string } | null>(null)

  // The register is served from one committed artifact, and the review window
  // is currently a label on it rather than a filter (#161). A period outside
  // the artifact's coverage therefore does not return nothing -- it returns
  // the same 2019 events under someone else's dates, and the engagement
  // report prints that period as the audit scope. Bounding the pickers is
  // what keeps the printed window a period the evidence actually comes from.
  useEffect(() => {
    let live = true
    fetchDemoDatasetSummary()
      // No fallback bound on failure. An unreachable API is not knowledge of
      // what the dataset covers, and inventing a range here would state one.
      .then((summary) => { if (live) setCoverage(parseCoverage(summary.window)) })
      .catch(() => undefined)
    return () => { live = false }
  }, [])

  const preview = useMemo(() => {
    if (!geometry) return null
    try {
      return buildScopePreview(geometry, Number(contextBuffer))
    } catch {
      return null
    }
  }, [contextBuffer, geometry])

  async function handleFileChange(nextFile: File | null) {
    setFile(nextFile)
    setFileError('')
    if (!nextFile) {
      // No upload -- fall back to the default area rather than an empty preview.
      setGeometry(DEFAULT_MANAGEMENT_UNIT_GEOMETRY)
      return
    }
    try {
      const parsed: unknown = JSON.parse(await nextFile.text())
      buildScopePreview(parsed, Number(contextBuffer))
      setGeometry(parsed)
    } catch (error) {
      setGeometry(null)
      setFileError(errorMessage(error))
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitError('')
    if (!reviewStart || !reviewEnd) {
      setSubmitError('Choose a review start and end date.')
      return
    }
    if (reviewEnd < reviewStart) {
      setSubmitError('Review end must be on or after review start.')
      return
    }
    // Belt and braces. `min`/`max` already make the browser refuse the
    // submit, so this is unreachable through the button -- it is here for a
    // caller that reaches the form without interactive validation, which must
    // not produce an audit whose printed period the evidence cannot support.
    if (coverage && (reviewStart < coverage.start || reviewEnd > coverage.end)) {
      setSubmitError(`This build holds real FireEvents for ${coverage.start} to ${coverage.end} only. Choose a review period inside it.`)
      return
    }
    if (file && !preview) {
      setSubmitError(fileError || 'Upload a valid GeoJSON management-unit polygon.')
      return
    }

    setSubmitting(true)
    try {
      const created = await createAuditReview({
        reviewStart,
        reviewEnd,
        contextBufferKm: Number(contextBuffer),
      })
      const uploaded = file
        ? await uploadAuditScope(created.audit_id, file)
        : await uploadAuditScopeGeometry(created.audit_id, DEFAULT_MANAGEMENT_UNIT_GEOMETRY)
      const handoff = await buildFireHistory(uploaded.audit_id)
      onReady({ ...uploaded, status: handoff.status, historyBuild: handoff })
    } catch (error) {
      setSubmitError(errorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={`flex h-full flex-col overflow-hidden bg-bg text-text ${overlay && !fullScreen ? 'rounded-xl border border-border-strong shadow-2xl' : 'min-h-screen'}`}>
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-strong bg-panel px-6">
        <div>
          <div className="text-sm font-semibold tracking-wide">Environmental Assurance Console</div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-text-faint">Create audit review</div>
        </div>
        {onClose && <Button onClick={onClose}>CLOSE</Button>}
      </header>

      <main className="mx-auto grid w-full max-w-6xl flex-1 gap-6 overflow-auto p-6 lg:grid-cols-[minmax(320px,0.8fr)_minmax(420px,1.2fr)]">
        <section className="rounded-xl border border-border-strong bg-panel p-6 shadow-2xl">
          <p className="mb-2 text-xs uppercase tracking-[0.2em] text-accent">01 / Audit scope</p>
          <h1 className="text-2xl font-semibold tracking-tight">Start with the management unit.</h1>
          <p className="mt-3 text-sm leading-6 text-text-muted">
            Set the review period and upload the private boundary authorised for this engagement. No company identity or public concession lookup is required.
          </p>

          <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-3">
                <label className="space-y-2 text-xs text-text-muted">
                  <span className="block uppercase tracking-wider">Review start</span>
                  <input
                    required
                    type="date"
                    value={reviewStart}
                    min={coverage?.start}
                    max={coverage?.end}
                    onChange={(event) => setReviewStart(event.target.value)}
                    className="w-full rounded border border-border-strong bg-bg px-3 py-2 text-sm text-text outline-none [color-scheme:dark] focus:border-accent"
                  />
                </label>
                {/* The end picker's floor tracks the chosen start, so an
                    inverted range is unreachable rather than only refused
                    after submitting. */}
                <label className="space-y-2 text-xs text-text-muted">
                  <span className="block uppercase tracking-wider">Review end</span>
                  <input
                    required
                    type="date"
                    value={reviewEnd}
                    min={reviewStart || coverage?.start}
                    max={coverage?.end}
                    onChange={(event) => setReviewEnd(event.target.value)}
                    className="w-full rounded border border-border-strong bg-bg px-3 py-2 text-sm text-text outline-none [color-scheme:dark] focus:border-accent"
                  />
                </label>
              </div>
              {coverage && (
                <span className="block text-[11px] text-text-faint">
                  Selectable range is {coverage.start} to {coverage.end} — the window this build holds real
                  observations for. A period outside it would label the register with dates the evidence
                  does not come from.
                </span>
              )}
            </div>

            <label className="block space-y-2 text-xs text-text-muted">
              <span className="block uppercase tracking-wider">Context buffer (km)</span>
              <input
                required
                min="0"
                max="1000"
                step="1"
                type="number"
                value={contextBuffer}
                onChange={(event) => setContextBuffer(event.target.value)}
                className="w-full rounded border border-border-strong bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent"
              />
              <span className="block text-[11px] text-text-faint">Default 25 km. External context is kept distinct from the audit boundary.</span>
            </label>

            <label className="block space-y-2 text-xs text-text-muted">
              <span className="block uppercase tracking-wider">Management-unit GeoJSON (optional)</span>
              <input
                type="file"
                accept=".geojson,.json,application/geo+json,application/json"
                onChange={(event) => void handleFileChange(event.target.files?.[0] ?? null)}
                className="block w-full cursor-pointer rounded border border-border-strong bg-bg px-3 py-2 text-xs text-text file:mr-3 file:rounded file:border-0 file:bg-panel-raised file:px-2 file:py-1 file:text-xs file:text-text"
              />
              <ul className="list-disc space-y-1 pl-4 text-[11px] text-text-faint">
                <li>Accepts Polygon, MultiPolygon, Feature, or FeatureCollection GeoJSON.</li>
                <li>Leave empty to use the default area; invalid or unsupported geometry is rejected.</li>
              </ul>
            </label>

            {(fileError || submitError) && <p className="rounded border border-status-urgent/40 bg-status-urgent/10 px-3 py-2 text-xs leading-5 text-red-200" role="alert">{fileError || submitError}</p>}

            <Button type="submit" variant="primary" disabled={submitting} className="w-full py-3 uppercase tracking-[0.16em]">
              {submitting ? 'Building cached fire history…' : 'BUILD FIRE HISTORY'}
            </Button>
          </form>
        </section>

        <section className="flex min-h-[460px] flex-col overflow-hidden rounded-xl border border-border-strong bg-panel shadow-2xl">
          <div className="flex items-start justify-between border-b border-border px-5 py-4">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-text-faint">Preview before reconstruction</p>
              <h2 className="mt-1 text-sm font-semibold">Boundary and context buffer</h2>
            </div>
            <div className="space-y-1 text-right text-[10px] text-text-muted">
              <div><span className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: INDONESIA_FILL_COLOR }} />Indonesia context</div>
              <div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-accent" />Audit boundary</div>
              <div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-status-moderate" />Context buffer</div>
            </div>
          </div>
          {submitting && <div role="status" className="border-t border-border px-5 py-3 text-xs text-text-muted">Scope uploaded. Checking the cached real historical dataset and preparing the register…</div>}
          <div className="relative min-h-[360px] flex-1 bg-bg">
            {preview ? (
              <ScopePreviewMap scope={preview} />
            ) : (
              <div className="flex h-full min-h-[360px] items-center justify-center px-10 text-center text-sm text-text-faint">
                That file could not be previewed. Fix it and re-upload, or remove the file to use the default area.
              </div>
            )}
          </div>
          {preview && (
            <div className="grid grid-cols-3 gap-3 border-t border-border px-5 py-4 text-xs">
              <div><div className="text-text-faint">Bounds</div><div className="mt-1 font-mono text-text">{preview.bbox.minLon.toFixed(3)}, {preview.bbox.minLat.toFixed(3)} → {preview.bbox.maxLon.toFixed(3)}, {preview.bbox.maxLat.toFixed(3)}</div></div>
              <div><div className="text-text-faint">Centroid</div><div className="mt-1 font-mono text-text">{preview.centroid[0].toFixed(3)}, {preview.centroid[1].toFixed(3)}</div></div>
              <div><div className="text-text-faint">Buffer</div><div className="mt-1 font-mono text-text">{Number(contextBuffer).toFixed(0)} km</div></div>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
