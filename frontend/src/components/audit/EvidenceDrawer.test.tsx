import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EventEvidenceResponse } from '../../api/types'
import { EvidenceDrawer } from './EvidenceDrawer'

const evidence = {
  auditId: 'AUDIT-1',
  event: {
    eventId: 'FE-1',
    auditId: 'AUDIT-1',
    firstDetection: '2019-09-01T00:00:00Z',
    lastDetection: '2019-09-01T01:00:00Z',
    durationHours: 1,
    observationCount: 2,
    centroid: { lat: -3, lon: 116 },
    bbox: [116, -3, 116.01, -2.99],
    spatialExtentKm: 1,
    maxFrp: 2,
    meanFrp: 1,
    triage: { state: 'LIKELY_FIRE' as const, deeperInvestigationEligible: true },
    evidenceSufficiency: 'PARTIAL' as const,
    investigationPriority: 'HIGH' as const,
    reviewState: 'REVIEW_RECOMMENDED' as const,
    reviewRouting: { priorityScore: 1, escalationReasonCodes: [], components: [] },
  },
  scopeRelation: 'INSIDE_SCOPE' as const,
  observedEvidence: [{ evidence_id: 'OBS-FIRMS', category: 'thermal', type: 'chronology', observation: 'FIRMS observations', source: 'NASA FIRMS', quality: 0.82 }],
  derivedEvidence: [{ evidence_id: 'ENV-SURFACE', category: 'surface', type: 'surface_compatibility', observation: 'compatibility', source: 'model', time_window: 'event', value: 'COMPATIBLE' }],
  availability: [{ kind: 'imagery' as const, status: 'no_suitable_pass' as const, reason: 'No suitable pass.' }],
  evidenceSufficiency: { value: 'PARTIAL' as const, reason: 'Partial evidence.', algorithmVersion: 'triage-v1' },
  investigationPriority: 'HIGH' as const,
  reviewState: 'REVIEW_RECOMMENDED' as const,
  reviewRouting: {},
  provenance: { source: { provider: 'FIRMS' }, algorithmVersions: ['triage-v1'] },
} satisfies EventEvidenceResponse

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('EvidenceDrawer sidebar hierarchy', () => {
  it('explains the FIRMS quality value and omits the redundant PDF provenance sentence', () => {
    render(<EvidenceDrawer {...{ eventId: 'FE-1', loading: false, data: evidence, showObservations: false, onToggleObservations: () => undefined, onClose: () => undefined, onRetry: () => undefined, analysisLoading: false, onGenerateAnalysis: () => undefined }} />)

    expect(screen.getByText('Sourced from NASA FIRMS, quality 82%')).toBeTruthy()
    expect(screen.queryByText('Full observed-evidence provenance is in the exported PDF.')).toBeNull()
    expect(screen.queryByRole('note')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Explain FIRMS quality' }))

    expect(screen.getByRole('note').textContent).toContain('The backend assigns 0.82 (82%) to these observed FIRMS records.')
    expect(screen.getByRole('note').textContent).toContain('It is not a fire probability or burned-area estimate.')
  })

  it('shows an animated, time-aware analysis status while generation is running', () => {
    render(<EvidenceDrawer {...{ eventId: 'FE-1', loading: false, data: evidence, showObservations: false, onToggleObservations: () => undefined, onClose: () => undefined, onRetry: () => undefined, analysisLoading: true, analysisStartedAt: new Date().toISOString(), analysisStage: 'Round 1 of 2: independent assessment', onGenerateAnalysis: () => undefined }} />)

    const status = screen.getByRole('status')
    expect(status.textContent).toContain('Usually takes about a minute.')
    expect(status.textContent).toContain('The job keeps running if you close this drawer.')
    expect(status.textContent).toContain('Round 1 of 2: independent assessment')
    expect(status.querySelector('.animate-spin')).toBeTruthy()
  })

  it('shows compact availability statuses near the summary', () => {
    render(
      <EvidenceDrawer
        eventId="FE-1"
        loading={false}
        data={evidence}
        graph={{ auditId: 'AUDIT-1', selectedEventIds: ['FE-1'], scope: {}, nodes: [], edges: [], layers: {} }}
        showObservations={false}
        onToggleObservations={() => undefined}
        onClose={() => undefined}
        onRetry={() => undefined}
        analysisLoading={false}
        onGenerateAnalysis={() => undefined}
      />,
    )

    const drawer = screen.getByRole('complementary', { name: 'FireEvent evidence drawer' })
    expect(drawer.getAttribute('data-print-layout')).toBe('evidence-document')
    expect(drawer.className).toContain('evidence-drawer')
    const headings = within(drawer).getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)

    expect(headings.slice(0, 2)).toEqual(['Summary', 'Availability'])
    expect(screen.getByText('Limited · no suitable pass')).toBeTruthy()
    expect(screen.queryByText('No suitable pass.', { selector: 'p' })).toBeNull()
    expect(headings).not.toContain('Surface compatibility')
    expect(headings).not.toContain('Provenance')
  })

  it('omits the deterministic-routing disclaimer while keeping routing values visible', () => {
    render(<EvidenceDrawer {...{ eventId: 'FE-1', loading: false, data: evidence, showObservations: false, onToggleObservations: () => undefined, onClose: () => undefined, onRetry: () => undefined, analysisLoading: false, onGenerateAnalysis: () => undefined }} />)

    expect(screen.queryByText('Priority and workflow are deterministic routing aids; neither establishes cause, responsibility, or exoneration.')).toBeNull()
    expect(screen.getByText('Investigation priority')).toBeTruthy()
    expect(screen.getByText('Human workflow')).toBeTruthy()
    expect(screen.getByText('HIGH')).toBeTruthy()
    expect(screen.getByText('REVIEW_RECOMMENDED')).toBeTruthy()
  })

  it('keeps available and unavailable states explicit', () => {
    render(<EvidenceDrawer {...{ eventId: 'FE-1', loading: false, data: {
      ...evidence,
      availability: [
        { kind: 'peat', status: 'available', reason: 'Peat evidence is present.' },
        { kind: 'weather', status: 'unavailable', reason: 'Weather evidence is not present.' },
      ],
    }, showObservations: false, onToggleObservations: () => undefined, onClose: () => undefined, onRetry: () => undefined, analysisLoading: false, onGenerateAnalysis: () => undefined }} />)

    expect(screen.getByText('Available')).toBeTruthy()
    expect(screen.getByText('Unavailable')).toBeTruthy()
  })

  it('joins a manifest asset by source evidence ID and renders it at drawer width', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ events: { 'FE-1': { assets: [{ asset_id: 'asset-1', event_id: 'FE-1', source_evidence_id: 'ENV-IMG', sensor: 'Sentinel-2', position: 'post_event', label: 'Optical context', path: '/imagery/FE-1/s2-post.jpg', format: 'image/jpeg', width: 1024, height: 1024 }] } } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    const imagery = {
      ...evidence,
      derivedEvidence: [{
        evidence_id: 'ENV-IMG', category: 'imagery', type: 'imagery-scene', observation: 'scene', source: 'pipeline', time_window: '2019-09-01',
        value: { sensor: 'Sentinel-2', position: 'post_event', thumbnail_url: '/legacy-small.jpg' },
      }],
    } satisfies EventEvidenceResponse
    render(<EvidenceDrawer {...{ eventId: 'FE-1', loading: false, data: imagery, showObservations: false, onToggleObservations: () => undefined, onClose: () => undefined, onRetry: () => undefined, analysisLoading: false, onGenerateAnalysis: () => undefined }} />)
    await waitFor(() => expect(screen.getByAltText('Sentinel-2 post-event processed imagery')).toBeTruthy())
    const image = screen.getByAltText('Sentinel-2 post-event processed imagery')
    expect(image.getAttribute('src')).toBe('/imagery/FE-1/s2-post.jpg')
    expect(image.className).toContain('w-full')
    expect(screen.queryByAltText('Sentinel-2 post-event quicklook')).toBeNull()
  })

  it('states that processed imagery is unavailable without showing a legacy thumbnail', async () => {
    const imagery = {
      ...evidence,
      derivedEvidence: [{
        evidence_id: 'ENV-IMG', category: 'imagery', type: 'imagery-scene', observation: 'scene', source: 'pipeline', time_window: '2019-09-01',
        value: { sensor: 'Sentinel-1', position: 'pre_event', thumbnail_url: '/legacy-small.jpg' },
      }],
    } satisfies EventEvidenceResponse
    render(<EvidenceDrawer {...{ eventId: 'FE-2', loading: false, data: imagery, showObservations: false, onToggleObservations: () => undefined, onClose: () => undefined, onRetry: () => undefined, analysisLoading: false, onGenerateAnalysis: () => undefined }} />)
    await waitFor(() => expect(screen.getByText(/Processed imagery unavailable for this scene/)).toBeTruthy())
    expect(screen.queryByRole('img')).toBeNull()
  })
})
