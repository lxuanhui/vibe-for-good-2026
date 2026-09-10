/** The register's count follows the chosen review period (#161).
 *
 * The window used to be a label: every period returned the same 3,610
 * September 2019 FireEvents, printed under whichever dates the auditor had
 * typed. It is a filter now, and the backend owns the filtering -- the
 * session's own review period, not a query string this component builds.
 *
 * That last part is what these tests are really guarding. The component used
 * to re-send the period as `?since=/?until=`, which looked harmless and was
 * not: the scope stores whole dates, so `until=2019-09-03` parsed as that
 * day's midnight and silently dropped every detection on the closing day the
 * auditor explicitly named. Nothing on screen shows the difference between a
 * register missing its last day and a register that is simply small.
 *
 * The API seam is mocked rather than the network; jsdom fetches nothing.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { HistoricalInvestigation, RegisterSummary } from './HistoricalInvestigation'
import { fetchAuditRegister } from '../../api/client'
import type { AuditEventSummary, AuditProgression, AuditScope } from '../../api/types'

vi.mock('../../api/client', () => ({ fetchAuditRegister: vi.fn() }))

const fetchAuditRegisterMock = vi.mocked(fetchAuditRegister)

function scope(reviewStart: string, reviewEnd: string): AuditScope {
  return {
    audit_id: 'audit-1',
    scope_id: 'scope-1',
    review_start: reviewStart,
    review_end: reviewEnd,
    context_buffer_km: 5,
    status: 'HISTORY_BUILD_READY',
    bbox: null,
    centroid: null,
    buffer_bbox: { minLon: 101, minLat: -2, maxLon: 103, maxLat: 0 },
    buffer_geometry: null,
  }
}

function event(eventId: string, firstDetection: string): AuditEventSummary {
  return {
    eventId,
    auditId: 'audit-1',
    firstDetection,
    lastDetection: firstDetection,
    durationHours: 1,
    observationCount: 4,
    centroid: { lat: -1, lon: 102 },
    bbox: [102, -1, 102, -1],
    spatialExtentKm: 1,
    maxFrp: 12.5,
    meanFrp: 8,
    triage: { state: 'LIKELY_FIRE', deeperInvestigationEligible: true },
    evidenceSufficiency: 'PARTIAL',
    investigationPriority: 'MEDIUM',
    reviewState: 'REVIEW_RECOMMENDED',
    reviewRouting: { priorityScore: 40, escalationReasonCodes: [], components: [] },
  }
}

function progression(fireEvents: number): AuditProgression {
  return {
    rawObservations: null,
    qualifiedObservations: fireEvents * 4,
    fireEvents,
    requiringHumanReview: 0,
    selected: 0,
    selectedEventIds: [],
    compression: null,
    observationsToEventsCompression: null,
    inScopeAndBuffer: null,
    scopeBoundaryAvailable: false,
    scopeCompression: null,
    routingDiagnostics: {
      humanReviewCount: 0,
      humanReviewPercentage: 0,
      priorityDistribution: {},
      reviewStateDistribution: {},
      evidenceSufficiencyDistribution: {},
      escalationReasonCodes: {},
      componentContributionDistribution: {},
    },
  }
}

afterEach(() => {
  cleanup()
  fetchAuditRegisterMock.mockReset()
})

test('the register shows the count the chosen period returned, not the dataset total', async () => {
  fetchAuditRegisterMock.mockResolvedValue({
    events: [event('fe-1', '2019-09-02T03:00:00Z'), event('fe-2', '2019-09-03T10:00:00Z')],
    progression: progression(2),
  })

  render(<HistoricalInvestigation scope={scope('2019-09-02', '2019-09-03')} />)

  // The count is deliberately not just /2 FireEvents/: the register summary
  // (#178) repeats that phrase in its own routing/scope breakdowns, so a loose
  // match is ambiguous once both render together. This pins it to the header.
  expect(await screen.findByText(/2 FireEvents · 2019-09-02 → 2019-09-03/)).toBeTruthy()
  expect(screen.getByText('fe-1')).toBeTruthy()
  expect(screen.getByText('fe-2')).toBeTruthy()
  expect(screen.getByText(/2019-09-02 → 2019-09-03/)).toBeTruthy()
})

test('keeps scope editing beside the scoped-map navigation in one register control area', async () => {
  fetchAuditRegisterMock.mockResolvedValue({ events: [], progression: progression(0) })
  const onOpenScope = vi.fn()
  const onOpenScopedMap = vi.fn()

  render(<HistoricalInvestigation scope={scope('2019-09-02', '2019-09-03')} onOpenScope={onOpenScope} onOpenScopedMap={onOpenScopedMap} />)

  const controls = screen.getByRole('button', { name: 'EDIT SCOPE' }).parentElement
  expect(controls?.querySelectorAll('button')).toHaveLength(3)
  fireEvent.click(screen.getByRole('button', { name: 'EDIT SCOPE' }))
  fireEvent.click(screen.getByRole('button', { name: 'VIEW SCOPED MAP' }))
  expect(onOpenScope).toHaveBeenCalledOnce()
  expect(onOpenScopedMap).toHaveBeenCalledOnce()
})

test('the period is not re-sent as a query filter, so the closing day survives', async () => {
  fetchAuditRegisterMock.mockResolvedValue({ events: [event('fe-1', '2019-09-03T10:00:00Z')], progression: progression(1) })

  render(<HistoricalInvestigation scope={scope('2019-09-02', '2019-09-03')} />)

  await waitFor(() => expect(fetchAuditRegisterMock).toHaveBeenCalled())
  const filters = fetchAuditRegisterMock.mock.calls[0][1]
  expect(filters?.since).toBeUndefined()
  expect(filters?.until).toBeUndefined()
  // Space is still this component's filter to send -- only time moved.
  expect(filters?.bbox).toEqual({ minLon: 101, minLat: -2, maxLon: 103, maxLat: 0 })
})

test('an empty period reads as a measurement rather than a table that failed', async () => {
  fetchAuditRegisterMock.mockResolvedValue({ events: [], progression: progression(0) })

  render(<HistoricalInvestigation scope={scope('2019-09-04', '2019-09-04')} />)

  expect(await screen.findByText('No FireEvents were detected in this period.')).toBeTruthy()
  expect(screen.getByText(/did not fail to load/)).toBeTruthy()
  expect(screen.queryByRole('table')).toBeNull()
  expect(screen.queryByRole('alert')).toBeNull()
})

const summaryProgression: AuditProgression = {
  rawObservations: 21519,
  qualifiedObservations: 20471,
  fireEvents: 3610,
  requiringHumanReview: 396,
  selected: 0,
  selectedEventIds: [],
  compression: 5.67,
  observationsToEventsCompression: 5.67,
  inScopeAndBuffer: 16,
  scopeBoundaryAvailable: true,
  scopeCompression: 225.6,
  routingDiagnostics: {
    humanReviewCount: 396,
    humanReviewPercentage: 396 / 3610,
    priorityDistribution: {
      MEDIUM: { count: 3214, percentage: 3214 / 3610 },
      HIGH: { count: 396, percentage: 396 / 3610 },
    },
    reviewStateDistribution: {
      REVIEW_RECOMMENDED: { count: 3214, percentage: 3214 / 3610 },
      HUMAN_REVIEW: { count: 396, percentage: 396 / 3610 },
    },
    evidenceSufficiencyDistribution: {
      PARTIAL: { count: 3610, percentage: 1 },
    },
    escalationReasonCodes: {},
    componentContributionDistribution: {},
  },
}

test('reports human-review routing for the current register population', () => {
  render(<RegisterSummary progression={summaryProgression} />)

  expect(screen.getByRole('heading', { name: 'Observation derivation' })).toBeTruthy()
  expect(screen.getByText('20,471')).toBeTruthy()
  expect(screen.getAllByText('3,610').length).toBeGreaterThan(0)
  expect(screen.queryByText('5.7 observations per FireEvent on average. This is clustering, not a review queue.')).toBeNull()
  expect(screen.getByText('Count includes the configured context buffer: 16 of 3,610 FireEvents.')).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Scoped routing diagnostic' })).toBeTruthy()
  expect(screen.getByText('ROUTED TO HUMAN REVIEW IN CURRENT REGISTER')).toBeTruthy()
  expect(screen.getByText('11.0% of 3,610 FireEvents in this register.')).toBeTruthy()
  expect(screen.queryByText(/Global routing diagnostics/)).toBeNull()
  expect(screen.queryByText('observations → FireEvents → in scope + buffer → human review')).toBeNull()
})

test('presents derivation, scope, and routing as one connected flow', () => {
  render(<RegisterSummary progression={summaryProgression} />)

  const summary = screen.getByRole('region', { name: 'Historical register population summary' })
  expect(summary.querySelector('[aria-label="Register processing flow"]')).toBeTruthy()
  expect(summary.querySelectorAll('[data-flow-stage]')).toHaveLength(3)
  expect(summary.querySelectorAll('[data-flow-arrow]')).toHaveLength(2)
  expect(summary.className).not.toContain('bg-border')
  expect(summary.querySelector('[data-flow-stage="current-audit-scope"]')?.textContent).toContain('16')
  expect(summary.querySelector('[data-flow-stage="scoped-routing"]')?.textContent).toContain('396')
})

test('shows zero scoped routing without falling back to global numbers', () => {
  render(<RegisterSummary progression={{ ...summaryProgression, fireEvents: 0, requiringHumanReview: 0, routingDiagnostics: { ...summaryProgression.routingDiagnostics, humanReviewCount: 0, humanReviewPercentage: 0 } }} />)

  expect(screen.getByText('0.0% of 0 FireEvents in this register.')).toBeTruthy()
  expect(screen.queryByText(/3,610 FireEvents in this register/)).toBeNull()
})

test('provides contextual help for clustering and routing dimensions', () => {
  render(<RegisterSummary progression={summaryProgression} />)

  const helpButtons = screen.getAllByText('?')
  fireEvent.click(helpButtons[0])
  fireEvent.click(helpButtons[1])

  expect(screen.getByText(/deterministically clustered into FireEvents/)).toBeTruthy()
  expect(screen.getByText(/Stage 1 classification indicates fire support and is separate from evidence sufficiency/)).toBeTruthy()
  expect(screen.getByText(/Priority is a review-routing aid, separate from workflow status/)).toBeTruthy()
  expect(screen.getByText(/not proof of causality or responsibility/)).toBeTruthy()
  expect(screen.getByText(/you control filtering/)).toBeTruthy()
})

test('keeps routing explanation out of the normal register layout', () => {
  render(<RegisterSummary progression={summaryProgression} />)

  expect(screen.queryByRole('heading', { name: 'How to read routing' })).toBeNull()
  expect(screen.queryByRole('region', { name: 'Decision-oriented routing summary' })).toBeNull()
  expect(screen.getByRole('heading', { name: 'Scoped routing diagnostic' })).toBeTruthy()
})
