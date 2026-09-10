import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'
import type { AuditProgression } from '../../api/types'
import { RegisterSummary } from './HistoricalInvestigation'

afterEach(cleanup)

const progression: AuditProgression = {
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
    priorityDistribution: {},
    reviewStateDistribution: {},
    evidenceSufficiencyDistribution: {},
    escalationReasonCodes: {},
    componentContributionDistribution: {},
  },
}

test('keeps scope selection and global routing populations separate', () => {
  render(<RegisterSummary progression={progression} />)

  expect(screen.getByRole('heading', { name: 'Observation derivation' })).toBeTruthy()
  expect(screen.getByText('20,471')).toBeTruthy()
  expect(screen.getByText('3,610')).toBeTruthy()
  expect(screen.getByText('Count includes the configured context buffer: 16 of 3,610 FireEvents.')).toBeTruthy()
  expect(screen.getByText('11.0% of 3,610 FireEvents; this is not a subset count of the In Scope figure.')).toBeTruthy()
  expect(screen.queryByText('observations → FireEvents → in scope + buffer → human review')).toBeNull()
})

test('provides contextual help for clustering and routing dimensions', () => {
  render(<RegisterSummary progression={progression} />)

  const helpButtons = screen.getAllByText('?')
  fireEvent.click(helpButtons[0])
  fireEvent.click(helpButtons[1])

  expect(screen.getByText(/deterministically clustered into FireEvents/)).toBeTruthy()
  expect(screen.getByText(/separate dimensions/)).toBeTruthy()
})
