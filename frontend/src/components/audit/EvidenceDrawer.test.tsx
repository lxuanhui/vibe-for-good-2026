import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
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
  observedEvidence: [],
  derivedEvidence: [{ evidence_id: 'ENV-SURFACE', category: 'surface', type: 'surface_compatibility', observation: 'compatibility', source: 'model', time_window: 'event', value: 'COMPATIBLE' }],
  availability: [{ kind: 'imagery' as const, status: 'no_suitable_pass' as const, reason: 'No suitable pass.' }],
  evidenceSufficiency: { value: 'PARTIAL' as const, reason: 'Partial evidence.', algorithmVersion: 'triage-v1' },
  investigationPriority: 'HIGH' as const,
  reviewState: 'REVIEW_RECOMMENDED' as const,
  reviewRouting: {},
  provenance: { source: { provider: 'FIRMS' }, algorithmVersions: ['triage-v1'] },
} satisfies EventEvidenceResponse

afterEach(cleanup)

describe('EvidenceDrawer sidebar hierarchy', () => {
  it('puts availability near the summary and omits sidebar provenance and surface sections', () => {
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

    expect(headings.slice(0, 2)).toEqual(['Summary', 'Availability / limitations'])
    expect(headings).not.toContain('Surface compatibility')
    expect(headings).not.toContain('Provenance')
  })

  it('prefers a processed imagery artifact and renders it at drawer width', () => {
    const imagery = {
      ...evidence,
      derivedEvidence: [{
        evidence_id: 'ENV-IMG', category: 'imagery', type: 'imagery-scene', observation: 'scene', source: 'pipeline', time_window: '2019-09-01',
        value: { sensor: 'Sentinel-2', position: 'post_event', thumbnail_url: '/legacy-small.jpg', processed_image_url: '/processed-large.png', width: 2048, height: 1536 },
      }],
    } satisfies EventEvidenceResponse
    render(<EvidenceDrawer {...{ eventId: 'FE-1', loading: false, data: imagery, showObservations: false, onToggleObservations: () => undefined, onClose: () => undefined, onRetry: () => undefined, analysisLoading: false, onGenerateAnalysis: () => undefined }} />)
    const image = screen.getByAltText('Sentinel-2 post-event processed imagery')
    expect(image.getAttribute('src')).toBe('/processed-large.png')
    expect(image.className).toContain('w-full')
    expect(screen.queryByAltText('Sentinel-2 post-event quicklook')).toBeNull()
  })

  it('states that processed imagery is unavailable without showing a legacy thumbnail', () => {
    const imagery = {
      ...evidence,
      derivedEvidence: [{
        evidence_id: 'ENV-IMG', category: 'imagery', type: 'imagery-scene', observation: 'scene', source: 'pipeline', time_window: '2019-09-01',
        value: { sensor: 'Sentinel-1', position: 'pre_event', thumbnail_url: '/legacy-small.jpg' },
      }],
    } satisfies EventEvidenceResponse
    render(<EvidenceDrawer {...{ eventId: 'FE-1', loading: false, data: imagery, showObservations: false, onToggleObservations: () => undefined, onClose: () => undefined, onRetry: () => undefined, analysisLoading: false, onGenerateAnalysis: () => undefined }} />)
    expect(screen.getByText(/Processed imagery unavailable for this scene/)).toBeTruthy()
    expect(screen.queryByRole('img')).toBeNull()
  })
})
