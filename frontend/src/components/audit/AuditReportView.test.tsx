/** The engagement report's AI section: explicit trigger, honest empty state (#61).
 *
 * Three of this component's behaviours are product-boundary rules rather than
 * conveniences, and nothing else checks them:
 *
 *  - analysis runs only when a human presses GENERATE INVESTIGATION ANALYSIS,
 *    never on load and never as a side effect of opening the pack;
 *  - an event with no analysis says so, and keeps saying so when a run fails;
 *  - what reaches the page is the bounded final assessment with its evidence
 *    IDs -- not the intermediate rounds, which are the model's working.
 *
 * The API seam is mocked rather than the network: these assert what the
 * component asks for and what it renders, and `client.ts` decides how a job is
 * polled (#143). Testing through `fetch` here would tie these to that.
 */
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { AuditEventSummary, AuditReport, EventEvidenceResponse, StructuredAnalysis, StructuredAnalysisAssessment } from '../../api/types'
import { AuditReportView } from './AuditReportView'
import { fetchAuditReport, generateInvestigationAnalysis } from '../../api/client'

vi.mock('../../api/client', () => ({
  fetchAuditReport: vi.fn(),
  generateInvestigationAnalysis: vi.fn(),
  addToAuditPack: vi.fn(),
  removeFromAuditPack: vi.fn(),
}))

const AUDIT_ID = 'demo-2019-haze'
const ANALYSED = 'FE-20190901-1ecb99d2e4'
const NOT_RUN = 'FE-20190903-77c0b21ab9'

// Rounds are where the debate happens. If this string ever reaches the DOM,
// the report is showing chain-of-thought.
const WORKING_NOTE = 'Round-one working note that must not reach the report.'

const fetchAuditReportMock = vi.mocked(fetchAuditReport)
const generateInvestigationAnalysisMock = vi.mocked(generateInvestigationAnalysis)

afterEach(cleanup)

function event(eventId: string): AuditEventSummary {
  return {
    eventId,
    auditId: AUDIT_ID,
    firstDetection: '2019-09-01T04:55:00Z',
    lastDetection: '2019-09-03T05:58:00Z',
    durationHours: 49.05,
    observationCount: 6,
    centroid: { lat: -2.1234, lon: 113.5678 },
    bbox: [113.5, -2.2, 113.6, -2.1],
    spatialExtentKm: 3.2,
    maxFrp: 16.84,
    meanFrp: 10.34,
    triage: { state: 'LIKELY_FIRE', deeperInvestigationEligible: true },
    evidenceSufficiency: 'PARTIAL',
    investigationPriority: 'HIGH',
    reviewState: 'HUMAN_REVIEW',
    reviewRouting: { priorityScore: 61, escalationReasonCodes: [], components: [] },
  }
}

function evidence(summary: AuditEventSummary): EventEvidenceResponse {
  return {
    auditId: AUDIT_ID,
    event: summary,
    scopeRelation: 'INSIDE_SCOPE',
    observedEvidence: [],
    derivedEvidence: [],
    availability: [],
    evidenceSufficiency: { value: 'PARTIAL', reason: 'No peat classification for this cell.', algorithmVersion: 'evidence-1.0' },
    investigationPriority: 'HIGH',
    reviewState: 'HUMAN_REVIEW',
    reviewRouting: {},
    provenance: { source: {}, algorithmVersions: ['stage1-triage-1.0'] },
  }
}

function assessment(role: StructuredAnalysisAssessment['role'], summary: string): StructuredAnalysisAssessment {
  return {
    role,
    round: 2,
    phase: 'FINAL_ASSESSMENT',
    findings: [{
      hypothesis_id: 'H3',
      support_score: role === 'INVESTIGATOR' ? 72 : 44,
      evidence_sufficiency: 'PARTIAL',
      supporting_evidence_ids: ['E-OBS-014'],
      contradicting_evidence_ids: ['E-DER-003'],
      summary,
      verification_questions: [],
    }],
    unresolved_questions: [],
  }
}

function analysis(): StructuredAnalysis {
  const working = assessment('INVESTIGATOR', WORKING_NOTE)
  return {
    event_id: ANALYSED,
    status: 'UNRESOLVED',
    algorithm_version: 'investigator-skeptic-1.0',
    evidence_ids: ['E-OBS-014', 'E-DER-003'],
    rounds: [{ round: 1, phase: 'INDEPENDENT_ASSESSMENT', investigator: working, skeptic: working, unresolved_questions: [] }],
    final_assessment: {
      investigator: assessment('INVESTIGATOR', 'Detections persist across the same KHG unit for 49 h (E-OBS-014).'),
      skeptic: assessment('SKEPTIC', 'Repeat overpass geometry alone accounts for part of that persistence (E-DER-003).'),
    },
    unresolved_questions: [],
  }
}

function report({ analysed }: { analysed: boolean }): AuditReport {
  const events = [event(ANALYSED), event(NOT_RUN)]
  return {
    auditId: AUDIT_ID,
    auditScope: { reviewStart: '2019-09-01', reviewEnd: '2019-09-30', scope: {} },
    sourceMethodSummary: { observed: 'NASA FIRMS VIIRS.', derived: 'Clustering and Stage-1 triage.', ai: 'Investigator/Skeptic.', source: {} },
    compressionSummary: {},
    counts: { identified: 2, screened: 2, reviewed: 2, selected: 2, verify: 0, insufficient: 0 },
    selectedFireEvents: events.map((summary) => ({
      event: summary,
      review: { eventId: summary.eventId, note: '', disposition: '', addedAt: '2019-09-04T00:00:00Z' },
      evidence: evidence(summary),
    })),
    maps: { selectedEventIds: events.map((summary) => summary.eventId), layers: {} },
    chronology: [],
    deterministicEvidence: [{
      eventId: ANALYSED,
      observed: [{ evidence_id: 'E-OBS-014', category: 'thermal', type: 'observation', observation: 'Six FIRMS detections across the event window.', source: 'NASA FIRMS' }],
      derived: [{ evidence_id: 'E-DER-003', category: 'triage', type: 'repeat_geometry', observation: 'The repeat detections share the same mapped geometry.', source: 'deterministic event reconstruction' }],
    }],
    graphRelationships: [],
    aiAnalysis: analysed ? [{ eventId: ANALYSED, analysis: analysis() }] : [],
    analysisNotRunEventIds: analysed ? [NOT_RUN] : [ANALYSED, NOT_RUN],
    unresolvedQuestions: analysed
      ? [{ eventId: ANALYSED, question: 'Does a Sentinel-1 pass separate persistence from repeat geometry?', evidence_ids: ['E-DER-003'] }]
      : [],
    verificationRecommendations: analysed
      ? [{ eventId: ANALYSED, question: 'Request the concession-level burn permit record for 01 Sep.', evidence_ids: ['E-OBS-014'] }]
      : [],
    limitations: ['Cloud gaps on 04-05 Sep.'],
    provenance: { source: {}, algorithmVersions: ['investigator-skeptic-1.0'] },
    humanNotes: [],
    disclaimer: 'This pack supports a human decision and does not conclude responsibility.',
  }
}

test('an event with no analysis says so, and nothing runs on load', async () => {
  fetchAuditReportMock.mockResolvedValue(report({ analysed: false }))

  render(<AuditReportView auditId={AUDIT_ID} onBack={() => {}} />)

  expect(await screen.findByText(/does not fabricate an AI assessment/)).toBeTruthy()
  expect(screen.getByText('Analysis not run')).toBeTruthy()
  expect(screen.getAllByRole('button', { name: 'GENERATE INVESTIGATION ANALYSIS' })).toHaveLength(2)
  // The whole point of the explicit control: opening the pack must not spend a
  // Bedrock run, and must not put an assessment on the page nobody asked for.
  expect(generateInvestigationAnalysisMock).not.toHaveBeenCalled()
})

test('analysis runs only when the explicit control is pressed, and the report is re-read after it', async () => {
  fetchAuditReportMock.mockResolvedValue(report({ analysed: false }))
  generateInvestigationAnalysisMock.mockResolvedValue(analysis())

  render(<AuditReportView auditId={AUDIT_ID} onBack={() => {}} />)
  const [first] = await screen.findAllByRole('button', { name: 'GENERATE INVESTIGATION ANALYSIS' })

  fetchAuditReportMock.mockResolvedValue(report({ analysed: true }))
  await userEvent.click(first)

  await waitFor(() => expect(generateInvestigationAnalysisMock).toHaveBeenCalledWith(AUDIT_ID, ANALYSED, expect.any(Function)))
  expect(generateInvestigationAnalysisMock).toHaveBeenCalledTimes(1)
  // Re-read rather than patched in place: the analysis reaches the pack
  // through the report the API assembles, so the two cannot disagree.
  await waitFor(() => expect(fetchAuditReportMock).toHaveBeenCalledTimes(2))
})

test('shows visible analysis progress while the report generation is pending', async () => {
  fetchAuditReportMock.mockResolvedValue(report({ analysed: false }))
  generateInvestigationAnalysisMock.mockImplementation(() => new Promise(() => undefined))

  render(<AuditReportView auditId={AUDIT_ID} onBack={() => {}} />)
  const [first] = await screen.findAllByRole('button', { name: 'GENERATE INVESTIGATION ANALYSIS' })
  await userEvent.click(first)

  const status = await screen.findByRole('status')
  expect(status.textContent).toContain('Usually takes about a minute.')
  expect(status.textContent).toContain('The job keeps running if you leave this report.')
  expect(status.textContent).toContain('Starting')
  expect(status.querySelector('.animate-spin')).toBeTruthy()
})

test('a completed analysis renders its findings with evidence IDs, and keeps the rounds off the page', async () => {
  fetchAuditReportMock.mockResolvedValue(report({ analysed: true }))

  render(<AuditReportView auditId={AUDIT_ID} onBack={() => {}} />)

  expect(await screen.findByText('INVESTIGATOR')).toBeTruthy()
  expect(screen.getByText('SKEPTIC')).toBeTruthy()
  expect(screen.getByText('Detections persist across the same KHG unit for 49 h (E-OBS-014).')).toBeTruthy()
  expect(screen.getAllByText('Six FIRMS detections across the event window.')).toHaveLength(3)
  expect(screen.getAllByText('The repeat detections share the same mapped geometry.')).toHaveLength(3)
  // Support and sufficiency are rendered together but stay distinct values:
  // 72/100 of support at PARTIAL evidence is not 72% of a conclusion.
  expect(screen.getByText('72/100 · PARTIAL')).toBeTruthy()
  expect(screen.getByText('44/100 · PARTIAL')).toBeTruthy()
  expect(screen.getAllByText('+ E-OBS-014 · − E-DER-003')).toHaveLength(2)
  expect(screen.getByText(/Does a Sentinel-1 pass separate persistence/)).toBeTruthy()
  expect(screen.getByText(/Request the concession-level burn permit record/)).toBeTruthy()
  expect(screen.queryByText(WORKING_NOTE)).toBeNull()
  // The second selected event was never analysed and still says so, beside one
  // that was. Scoped to that block because both event IDs also appear in the
  // human-review rows above it.
  const notRun = screen.getByText('Analysis not run').parentElement
  if (!notRun) throw new Error('The not-run block has no container to search.')
  expect(within(notRun).getByText(NOT_RUN)).toBeTruthy()
  expect(within(notRun).queryByText(ANALYSED)).toBeNull()
})

test('main findings precede the selected-event and comprehensive evidence sections', async () => {
  fetchAuditReportMock.mockResolvedValue(report({ analysed: true }))

  render(<AuditReportView auditId={AUDIT_ID} onBack={() => {}} />)

  const findings = await screen.findByTestId('main-findings')
  const selected = screen.getByText('Selected FireEvents')
  const evidenceLog = screen.getByTestId('evidence-log')
  expect(findings.compareDocumentPosition(selected) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(selected.compareDocumentPosition(evidenceLog) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(within(findings).getByText('INVESTIGATOR')).toBeTruthy()
  expect(within(findings).getByText('SKEPTIC')).toBeTruthy()
})

test('a failed run is reported without inventing an assessment', async () => {
  fetchAuditReportMock.mockResolvedValue(report({ analysed: false }))
  generateInvestigationAnalysisMock.mockRejectedValue(new Error('Bedrock could not generate investigation analysis.'))

  render(<AuditReportView auditId={AUDIT_ID} onBack={() => {}} />)
  const [first] = await screen.findAllByRole('button', { name: 'GENERATE INVESTIGATION ANALYSIS' })
  await userEvent.click(first)

  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toContain('Bedrock could not generate investigation analysis.')
  expect(screen.getByText(/does not fabricate an AI assessment/)).toBeTruthy()
  expect(screen.getAllByRole('button', { name: 'GENERATE INVESTIGATION ANALYSIS' })).toHaveLength(2)
})
