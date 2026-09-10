/** The review period cannot name a window the evidence does not cover (#95).
 *
 * The window is a real filter now (#161), so a period outside the artifact's
 * coverage comes back empty rather than as the same 2019 events under someone
 * else's dates. That removes the mislabel but not the reason for this bound:
 * an auditor who can pick 2024 gets a register that is empty for a reason the
 * screen cannot explain, and the engagement report still prints the period as
 * the audit scope. The bound keeps the input inside what the evidence covers,
 * and it is an absence -- nothing on screen shows it working, so nothing but
 * a test notices when it stops.
 *
 * The API seam is mocked rather than the network, and the preview map with
 * it -- jsdom draws no canvas and MapLibre needs one.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { AuditStart } from './AuditStart'
import { createAuditReview, fetchDemoDatasetSummary } from '../../api/client'

vi.mock('../../api/client', () => ({
  fetchDemoDatasetSummary: vi.fn(),
  createAuditReview: vi.fn(),
  uploadAuditScope: vi.fn(),
  uploadAuditScopeGeometry: vi.fn(),
  buildFireHistory: vi.fn(),
}))

vi.mock('./ScopePreviewMap', () => ({ ScopePreviewMap: () => <div data-testid="scope-preview" /> }))

const COVERAGE_START = '2019-09-01'
const COVERAGE_END = '2019-09-05'

const fetchDemoDatasetSummaryMock = vi.mocked(fetchDemoDatasetSummary)
const createAuditReviewMock = vi.mocked(createAuditReview)

function summary(window: string) {
  return {
    dataset: 'NASA FIRMS VIIRS/MODIS',
    region: 'Sumatra / Kalimantan',
    window,
    progression: { rawObservations: 21519, qualifiedObservations: 20471, fireEvents: 3610, requiringHumanReview: 396 },
  }
}

afterEach(cleanup)

test('renders the audit scope step label without a slash', () => {
  fetchDemoDatasetSummaryMock.mockRejectedValue(new Error('the API did not answer'))
  render(<AuditStart onReady={vi.fn()} />)

  expect(screen.getByText('01 Audit scope')).toBeTruthy()
  expect(screen.queryByText('01 / Audit scope')).toBeNull()
})

test('the pickers are bounded to the window the artifact says it covers', async () => {
  fetchDemoDatasetSummaryMock.mockResolvedValue(summary(`${COVERAGE_START}..${COVERAGE_END}`))
  render(<AuditStart onReady={vi.fn()} />)

  const start = screen.getByLabelText('Review start')
  const end = screen.getByLabelText('Review end')
  await waitFor(() => expect(start.getAttribute('max')).toBe(COVERAGE_END))

  expect(start.getAttribute('min')).toBe(COVERAGE_START)
  expect(end.getAttribute('max')).toBe(COVERAGE_END)
  // The end floor tracks the chosen start, not the coverage floor, so an
  // inverted range is unreachable in the picker rather than refused later.
  expect(end.getAttribute('min')).toBe('2019-09-01')
  expect(screen.getByText(/Selectable range is 2019-09-01 to 2019-09-05/)).toBeTruthy()
})

test('a period outside the coverage is refused and creates no audit', async () => {
  fetchDemoDatasetSummaryMock.mockResolvedValue(summary(`${COVERAGE_START}..${COVERAGE_END}`))
  const { container } = render(<AuditStart onReady={vi.fn()} />)

  const start = screen.getByLabelText('Review start')
  await waitFor(() => expect(start.getAttribute('max')).toBe(COVERAGE_END))

  // `fireEvent.change` rather than `userEvent.type`: a date input takes
  // keystrokes per segment in a locale-dependent order, and the value here is
  // the point, not the typing.
  fireEvent.change(start, { target: { value: '2024-01-01' } })
  // A well-ordered period, so this asserts on the coverage bound rather than
  // tripping the start-before-end check that runs ahead of it.
  fireEvent.change(screen.getByLabelText('Review end'), { target: { value: '2024-01-31' } })
  expect(start).toHaveProperty('value', '2024-01-01')

  // Submitted directly rather than through the button, because `min`/`max`
  // make the browser refuse the click -- which is the first line of defence
  // and is what test one covers. This is the second: a caller that reaches
  // the form without interactive validation (`form.submit()`, an automation
  // driver, a future `noValidate`) must not get an audit whose printed period
  // the evidence cannot support.
  const form = container.querySelector('form')
  if (!form) throw new Error('The scope panel has no form to submit.')
  fireEvent.submit(form)

  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toContain('2019-09-01 to 2019-09-05')
  expect(createAuditReviewMock).not.toHaveBeenCalled()
})

test('an unreachable dataset summary leaves the form usable rather than guessing a bound', async () => {
  fetchDemoDatasetSummaryMock.mockRejectedValue(new Error('the API did not answer'))
  render(<AuditStart onReady={vi.fn()} />)

  const start = screen.getByLabelText('Review start')
  await waitFor(() => expect(fetchDemoDatasetSummaryMock).toHaveBeenCalled())

  // Not knowing the coverage is not the same as knowing it is unlimited, but
  // an unbounded picker is the honest render of "we could not ask" -- and
  // stating a range here would be inventing one.
  expect(start.getAttribute('min')).toBeNull()
  expect(start.getAttribute('max')).toBeNull()
  expect(screen.queryByText(/Selectable range is/)).toBeNull()
  expect(screen.getByRole('button', { name: /BUILD FIRE HISTORY/i })).toHaveProperty('disabled', false)
})

test('keeps upload guidance concise and validates unsupported geometry clearly', async () => {
  fetchDemoDatasetSummaryMock.mockRejectedValue(new Error('the API did not answer'))
  const { container } = render(<AuditStart onReady={vi.fn()} />)

  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  expect(screen.getByText('Accepts Polygon, MultiPolygon, Feature, or FeatureCollection GeoJSON.')).toBeTruthy()
  expect(screen.queryByText(/Showing the default demo area/)).toBeNull()

  const input = container.querySelector('input[type="file"]')
  if (!input) throw new Error('The scope panel has no GeoJSON file input.')
  const invalidFile = { name: 'point.geojson', text: async () => '{"type":"Point","coordinates":[100,1]}' } as File
  fireEvent.change(input, { target: { files: [invalidFile] } })

  expect((await screen.findByRole('alert')).textContent).toContain('Polygon or MultiPolygon')
})

test('does not render the redundant scope-first control', () => {
  fetchDemoDatasetSummaryMock.mockRejectedValue(new Error('the API did not answer'))
  const onClose = vi.fn()
  render(<AuditStart onReady={vi.fn()} onClose={onClose} />)

  expect(screen.queryByText('Scope first')).toBeNull()
  expect(screen.getByRole('button', { name: 'CLOSE' })).toBeTruthy()
})
