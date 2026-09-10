import { forwardRef, type PropsWithChildren, type ReactNode } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { vi } from 'vitest'
import type { EventEvidenceResponse } from '../../api/types'
import type { AuditEventSummary, AuditProgression, AuditScope } from '../../api/types'
import { fetchAuditRegister } from '../../api/client'
import { envelopePolygons } from './propagationEnvelopes'
import { ScopedMapLanding } from './ScopedMapLanding'
import { eventOverlapsDay, investigationDays, observationDays, observationsForDay } from './temporalScrubber'

vi.mock('react-map-gl/maplibre', () => ({
  Map: forwardRef<HTMLDivElement, PropsWithChildren<{ children?: ReactNode }>>(({ children }, _ref) => <div data-testid="map">{children}</div>),
  Source: ({ children }: PropsWithChildren<{ id: string }>) => <div>{children}</div>,
  Layer: () => <div />,
}))

vi.mock('../../api/client', () => ({
  addToAuditPack: vi.fn(),
  fetchAuditRegister: vi.fn(),
  fetchInvestigationBundle: vi.fn(),
  fetchInvestigationMap: vi.fn(),
  generateInvestigationAnalysis: vi.fn(),
}))

const fetchAuditRegisterMock = vi.mocked(fetchAuditRegister)

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

const scope: AuditScope = {
  audit_id: 'audit-1',
  scope_id: 'scope-1',
  review_start: '2019-09-01',
  review_end: '2019-09-01',
  context_buffer_km: 25,
  status: 'HISTORY_BUILD_READY',
  bbox: null,
  centroid: [116, -3],
  buffer_bbox: { minLon: 115, minLat: -4, maxLon: 117, maxLat: -2 },
  buffer_geometry: null,
}

const event: AuditEventSummary = {
  eventId: 'FE-1',
  auditId: 'audit-1',
  firstDetection: '2019-09-01T03:00:00Z',
  lastDetection: '2019-09-01T04:00:00Z',
  durationHours: 1,
  observationCount: 1,
  centroid: { lat: -3, lon: 116 },
  bbox: [116, -3, 116, -3],
  spatialExtentKm: 1,
  maxFrp: 1,
  meanFrp: 1,
  triage: { state: 'LIKELY_FIRE', deeperInvestigationEligible: true },
  evidenceSufficiency: 'PARTIAL',
  investigationPriority: 'MEDIUM',
  reviewState: 'REVIEW_RECOMMENDED',
  reviewRouting: { priorityScore: 1, escalationReasonCodes: [], components: [] },
}

it('selects candidates from the full keyboard-accessible row surface', async () => {
  const progression: AuditProgression = {
    rawObservations: 1,
    qualifiedObservations: 1,
    fireEvents: 1,
    requiringHumanReview: 1,
    selected: 0,
    selectedEventIds: [],
    compression: null,
    observationsToEventsCompression: null,
    inScopeAndBuffer: 1,
    scopeBoundaryAvailable: false,
    scopeCompression: null,
    routingDiagnostics: {
      humanReviewCount: 1,
      humanReviewPercentage: 100,
      priorityDistribution: {},
      reviewStateDistribution: {},
      evidenceSufficiencyDistribution: {},
      escalationReasonCodes: {},
      componentContributionDistribution: {},
    },
  }
  fetchAuditRegisterMock.mockResolvedValue({ events: [event], progression })

  render(<ScopedMapLanding scope={scope} onOpenScope={() => undefined} onOpenRegister={() => undefined} onViewReport={() => undefined} />)

  await screen.findByRole('list', { name: 'Available observation dates' })
  expect(screen.queryByText(/Night shade shows/)).toBeNull()
  const candidate = screen.getByRole('button', { name: 'Select FE-1 for audit report' })
  const list = candidate.closest('ul') as HTMLElement
  const user = userEvent.setup()
  const eventCount = screen.getByText((_, element) => element?.tagName === 'P' && element.textContent?.replace(/\s+/g, ' ').trim() === 'Events shown 1')
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(eventCount.tagName).toBe('P')
  expect(eventCount.className).not.toContain('rounded')
  expect(eventCount.className).not.toContain('border')
  expect(eventCount.className).not.toContain('bg-bg')
  expect(screen.queryByText('0 IN REPORT')).toBeNull()
  expect(screen.queryByText(/Peat is environmental context/)).toBeNull()
  expect(screen.getByRole('button', { name: 'SHOW PEATLAND' })).toBeTruthy()
  expect(candidate.getAttribute('aria-pressed')).toBe('false')
  await user.click(candidate)
  expect(candidate.getAttribute('aria-pressed')).toBe('true')
  expect(candidate.className).toContain('border-accent')
  await user.keyboard('{Enter}')
  expect(candidate.getAttribute('aria-pressed')).toBe('false')
  expect(screen.queryByText('FireEvents in scope + context')).toBeNull()
  expect(screen.queryByText('Review scoped FireEvents and optional peat context.')).toBeNull()
  expect(screen.queryByText('OPEN A FIRE EVENT TO ADD IT')).toBeNull()
  expect(screen.queryByText(/separate from Fire Register map comparison/i)).toBeNull()
  expect(list.className).not.toContain('overflow-y-auto')
  expect(list.className).not.toContain('max-h-64')
  expect(list.closest('aside')?.className).toContain('overflow-y-auto')
})

it('keeps scope editing and register navigation in the same map header', async () => {
  fetchAuditRegisterMock.mockResolvedValue({ events: [], progression: { selectedEventIds: [] } as unknown as AuditProgression })
  const onOpenScope = vi.fn()
  const onOpenRegister = vi.fn()

  render(<ScopedMapLanding scope={scope} onOpenScope={onOpenScope} onOpenRegister={onOpenRegister} onViewReport={() => undefined} />)

  await screen.findByRole('list', { name: 'Available observation dates' })
  const header = screen.getByRole('button', { name: 'EDIT SCOPE' }).closest('header')
  expect(header?.querySelectorAll('button')).toHaveLength(2)
  fireEvent.click(screen.getByRole('button', { name: 'EDIT SCOPE' }))
  fireEvent.click(header?.querySelectorAll('button')[1] as HTMLButtonElement)
  expect(onOpenScope).toHaveBeenCalledOnce()
  expect(onOpenRegister).toHaveBeenCalledOnce()
})

const edge = (sourceEventId: string, ownerEventId: string) => ({
  sourceEventId,
  targetEventId: 'FE-TARGET',
  state: 'PROPAGATION_COMPATIBLE',
  distanceKm: 2,
  modelVersion: 'surface-fire-ellipse-v1',
  origin: 'selection' as const,
  envelope: {
    polygon: [[116, -3], [116.01, -3], [116.01, -3.01], [116, -3]],
    orientationDeg: 90,
    semiMajorKm: 4,
    semiMinorKm: 2,
    ownerEventId,
  },
})

const edgeWithState = (state: string) => ({ ...edge('FE-ONE', 'FE-ONE'), state })

describe('ScopedMapLanding propagation envelopes', () => {
  it('renders only envelopes owned by explicitly selected FireEvents', () => {
    const result = envelopePolygons([edge('FE-ONE', 'FE-ONE'), edge('FE-TWO', 'FE-TWO')], ['FE-ONE'])

    expect(result.features).toHaveLength(1)
    expect(result.features[0].properties).toEqual({ state: 'PROPAGATION_COMPATIBLE', sourceEventId: 'FE-ONE', targetEventId: 'FE-TARGET' })
  })

  it('renders an eligible envelope from the focused event graph without register selection', () => {
    const result = envelopePolygons([edge('FE-ONE', 'FE-OTHER')], [], 'FE-TARGET')

    expect(result.features).toHaveLength(1)
  })

  it('renders no envelopes when focus is cleared or ownership is absent', () => {
    const owned = edge('FE-ONE', 'FE-ONE')
    const withoutOwner = { ...owned, envelope: { ...owned.envelope, ownerEventId: undefined as unknown as string } }

    expect(envelopePolygons([owned])).toEqual({ type: 'FeatureCollection', features: [] })
    expect(envelopePolygons([withoutOwner], ['FE-ONE'])).toEqual({ type: 'FeatureCollection', features: [] })
    expect(envelopePolygons([owned], ['FE-OTHER'])).toEqual({ type: 'FeatureCollection', features: [] })
  })

  it('renders no envelope when the graph relationship is not spatially and temporally compatible', () => {
    expect(envelopePolygons([edgeWithState('PROPAGATION_WEAK')], ['FE-ONE']).features).toHaveLength(0)
    expect(envelopePolygons([edgeWithState('INDEPENDENT_PLAUSIBLE')], ['FE-ONE']).features).toHaveLength(0)
    expect(envelopePolygons([edgeWithState('UNRESOLVED')], ['FE-ONE']).features).toHaveLength(0)
  })
})

describe('ScopedMapLanding temporal scrubber', () => {
  it('offers each UTC day in the review period and an all-days state', () => {
    expect(investigationDays('2019-09-01', '2019-09-05')).toEqual([
      '2019-09-01', '2019-09-02', '2019-09-03', '2019-09-04', '2019-09-05',
    ])
  })

  it('derives timeline dates from scoped event detection windows', () => {
    expect(observationDays([
      { firstDetection: '2019-09-02T03:00:00Z', lastDetection: '2019-09-03T04:00:00Z' },
      { firstDetection: '2019-09-05T03:00:00Z', lastDetection: '2019-09-05T04:00:00Z' },
    ], '2019-09-01', '2019-09-06')).toEqual(['2019-09-02', '2019-09-03', '2019-09-05'])
  })

  it('filters constituent observations by their recorded acquisition date', () => {
    const evidence = { event: { triageDetail: { observations: [
      { lat: -3, lon: 116, acqDate: '2019-09-01', acqTime: 30, frp: 1, confidence: 'nominal' },
      { lat: -3.1, lon: 116.1, acqDate: '2019-09-02', acqTime: 430, frp: 2, confidence: 'high' },
    ] } } } as EventEvidenceResponse

    expect(observationsForDay(evidence, '2019-09-02')).toHaveLength(1)
    expect(observationsForDay(evidence, null)).toHaveLength(2)
  })

  it('keeps an event point while its detection interval overlaps the selected day', () => {
    const event = { firstDetection: '2019-09-02T03:00:00Z', lastDetection: '2019-09-04T04:00:00Z' }

    expect(eventOverlapsDay(event, '2019-09-03')).toBe(true)
    expect(eventOverlapsDay(event, '2019-09-05')).toBe(false)
    expect(eventOverlapsDay(event, null)).toBe(true)
  })
})

describe('ScopedMapLanding timeline controls', () => {
  it('jumps to a date, pauses playback, and restores all days', async () => {
    fetchAuditRegisterMock.mockResolvedValue({
      events: [
        { ...event, firstDetection: '2019-09-01T03:00:00Z', lastDetection: '2019-09-01T04:00:00Z' },
        { ...event, eventId: 'FE-2', firstDetection: '2019-09-02T03:00:00Z', lastDetection: '2019-09-02T04:00:00Z' },
      ],
      progression: { selectedEventIds: [] } as unknown as AuditProgression,
    })

    render(<ScopedMapLanding scope={{ ...scope, review_end: '2019-09-02' }} onOpenScope={() => undefined} onOpenRegister={() => undefined} onViewReport={() => undefined} />)

    await screen.findByRole('list', { name: 'Available observation dates' })
    const day = screen.getByRole('button', { name: 'Show observations for 2019-09-02' })
    fireEvent.click(day)
    expect(day.getAttribute('aria-pressed')).toBe('true')
    expect(day.getAttribute('aria-current')).toBe('date')
    expect(day.className).toContain('bg-accent/15')
    expect(day.className).toContain('ring-1')
    expect(screen.getByText('2019-09-02')).toBeTruthy()
    expect(screen.getByText((_, element) => element?.tagName === 'P' && element.textContent?.replace(/\s+/g, ' ').trim() === 'Events shown 1')).toBeTruthy()

    vi.useFakeTimers()
    const playButton = screen.getByRole('button', { name: 'Play timeline' })
    expect(playButton.querySelector('[data-icon="play"]')).toBeTruthy()
    expect(playButton.getAttribute('title')).toBe('Play timeline')
    fireEvent.click(playButton)
    const pauseButton = screen.getByRole('button', { name: 'Pause timeline' })
    expect(pauseButton.querySelector('[data-icon="pause"]')).toBeTruthy()
    expect(pauseButton.getAttribute('title')).toBe('Pause timeline')
    await vi.advanceTimersByTimeAsync(1500)
    expect(screen.getByRole('button', { name: 'Show observations for 2019-09-02' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(pauseButton)
    expect(screen.getByRole('button', { name: 'Play timeline' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Play timeline' }))
    expect(screen.getByRole('button', { name: 'Pause timeline' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'ALL DAYS' }))
    expect(screen.getByRole('button', { name: 'ALL DAYS' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'ALL DAYS' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText((_, element) => element?.tagName === 'P' && element.textContent?.replace(/\s+/g, ' ').trim() === 'Events shown 2')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Play timeline' })).toBeTruthy()
  })
})
