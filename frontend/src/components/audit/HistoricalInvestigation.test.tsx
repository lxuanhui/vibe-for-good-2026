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
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { HistoricalInvestigation } from './HistoricalInvestigation'
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

  expect(await screen.findByText(/2 FireEvents/)).toBeTruthy()
  expect(screen.getByText('fe-1')).toBeTruthy()
  expect(screen.getByText('fe-2')).toBeTruthy()
  expect(screen.getByText(/2019-09-02 → 2019-09-03/)).toBeTruthy()
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
