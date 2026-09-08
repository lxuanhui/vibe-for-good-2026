import { useMemo, useState, type FormEvent } from 'react'
import type { AuditScope } from '../../api/types'
import { buildFireHistory, createAuditReview, uploadAuditScope } from '../../api/client'
import { buildScopePreview } from '../../lib/scope'
import { Button } from '../ui/Button'
import { ScopePreviewMap } from './ScopePreviewMap'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The audit review could not be created.'
}

export function AuditStart({ onReady }: { onReady: (scope: AuditScope) => void }) {
  const [reviewStart, setReviewStart] = useState('')
  const [reviewEnd, setReviewEnd] = useState('')
  const [contextBuffer, setContextBuffer] = useState('25')
  const [file, setFile] = useState<File | null>(null)
  const [geometry, setGeometry] = useState<unknown>(null)
  const [fileError, setFileError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)

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
    setGeometry(null)
    setFileError('')
    if (!nextFile) return
    try {
      const parsed: unknown = JSON.parse(await nextFile.text())
      buildScopePreview(parsed, Number(contextBuffer))
      setGeometry(parsed)
    } catch (error) {
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
    if (!file || !preview) {
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
      const uploaded = await uploadAuditScope(created.audit_id, file)
      const handoff = await buildFireHistory(uploaded.audit_id)
      onReady({ ...uploaded, status: handoff.status })
    } catch (error) {
      setSubmitError(errorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-full min-h-screen flex-col bg-bg text-text">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-strong bg-panel px-6">
        <div>
          <div className="text-sm font-semibold tracking-wide">Environmental Assurance Console</div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-text-faint">Create audit review</div>
        </div>
        <span className="rounded border border-accent-muted px-2 py-1 text-[10px] uppercase tracking-widest text-accent">Scope first</span>
      </header>

      <main className="mx-auto grid w-full max-w-6xl flex-1 gap-6 overflow-auto p-6 lg:grid-cols-[minmax(320px,0.8fr)_minmax(420px,1.2fr)]">
        <section className="rounded-xl border border-border-strong bg-panel p-6 shadow-2xl">
          <p className="mb-2 text-xs uppercase tracking-[0.2em] text-accent">01 / Audit scope</p>
          <h1 className="text-2xl font-semibold tracking-tight">Start with the management unit.</h1>
          <p className="mt-3 text-sm leading-6 text-text-muted">
            Set the review period and upload the private boundary authorised for this engagement. No company identity or public concession lookup is required.
          </p>

          <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
            <div className="grid grid-cols-2 gap-3">
              <label className="space-y-2 text-xs text-text-muted">
                <span className="block uppercase tracking-wider">Review start</span>
                <input
                  required
                  type="date"
                  value={reviewStart}
                  onChange={(event) => setReviewStart(event.target.value)}
                  className="w-full rounded border border-border-strong bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent"
                />
              </label>
              <label className="space-y-2 text-xs text-text-muted">
                <span className="block uppercase tracking-wider">Review end</span>
                <input
                  required
                  type="date"
                  value={reviewEnd}
                  onChange={(event) => setReviewEnd(event.target.value)}
                  className="w-full rounded border border-border-strong bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent"
                />
              </label>
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
              <span className="block uppercase tracking-wider">Management-unit GeoJSON</span>
              <input
                required
                type="file"
                accept=".geojson,.json,application/geo+json,application/json"
                onChange={(event) => void handleFileChange(event.target.files?.[0] ?? null)}
                className="block w-full cursor-pointer rounded border border-border-strong bg-bg px-3 py-2 text-xs text-text file:mr-3 file:rounded file:border-0 file:bg-panel-raised file:px-2 file:py-1 file:text-xs file:text-text"
              />
              <span className="block text-[11px] text-text-faint">MVP accepts Polygon, MultiPolygon, Feature, or FeatureCollection GeoJSON.</span>
            </label>

            {(fileError || submitError) && <p className="rounded border border-status-urgent/40 bg-status-urgent/10 px-3 py-2 text-xs leading-5 text-red-200" role="alert">{fileError || submitError}</p>}

            <Button type="submit" variant="primary" disabled={submitting} className="w-full py-3 uppercase tracking-[0.16em]">
              {submitting ? 'Preparing audit review…' : 'BUILD FIRE HISTORY'}
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
              <div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-accent" />Audit boundary</div>
              <div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-status-moderate" />Context buffer</div>
            </div>
          </div>
          <div className="relative min-h-[360px] flex-1 bg-bg">
            {preview ? (
              <ScopePreviewMap scope={preview} />
            ) : (
              <div className="flex h-full min-h-[360px] items-center justify-center px-10 text-center text-sm text-text-faint">
                Upload a valid GeoJSON polygon to inspect the private boundary and its context buffer.
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
