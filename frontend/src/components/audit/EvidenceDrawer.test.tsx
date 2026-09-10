import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
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
})
