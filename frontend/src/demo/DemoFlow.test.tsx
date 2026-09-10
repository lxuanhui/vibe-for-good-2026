import { StrictMode } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AnalysisJob, AuditScope } from '../api/types'
import {
  addToAuditPack,
  buildFireHistory,
  createAuditReview,
  readInvestigationAnalysis,
  setAuditScopeDemo,
  startInvestigationAnalysis,
} from '../api/client'
import { useAppStore } from '../store/useAppStore'
import { DemoFlow } from './DemoFlow'
import { DEMO_FOCUS_EVENT_ID, DEMO_REGISTER_SELECTION, DEMO_STEPS } from './demoScript'
import { resetDemoSessionForTests } from './useDemoSession'

// The screens themselves are tested in their own files. Here they are
// stand-ins that report which one is mounted and with what, so the test is
// about the flow: step order, the keys, the session, the pack.
vi.mock('../components/scope/AuditLanding', () => ({
  AuditLanding: () => <div data-testid="screen">landing</div>,
}))
vi.mock('../components/scope/AuditStart', () => ({
  AuditStart: ({ initialScope }: { initialScope?: AuditScope }) => <div data-testid="screen">scope {initialScope?.audit_id}</div>,
}))
vi.mock('../components/audit/HistoricalInvestigation', () => ({
  HistoricalInvestigation: ({ scope }: { scope: AuditScope }) => <div data-testid="screen">register {scope.audit_id}</div>,
}))
vi.mock('../components/scope/ScopedMapLanding', () => ({
  ScopedMapLanding: ({ scope, focusEventId }: { scope: AuditScope; focusEventId?: string }) => (
    <div data-testid="screen">map {scope.audit_id} focus={focusEventId ?? 'none'}</div>
  ),
}))
vi.mock('../components/audit/AuditReportView', () => ({
  AuditReportView: ({ auditId }: { auditId: string }) => <div data-testid="screen">report {auditId}</div>,
}))
vi.mock('../api/client', () => ({
  addToAuditPack: vi.fn(),
  buildFireHistory: vi.fn(),
  createAuditReview: vi.fn(),
  readInvestigationAnalysis: vi.fn(),
  setAuditScopeDemo: vi.fn(),
  startInvestigationAnalysis: vi.fn(),
}))

const storedScope: AuditScope = {
  audit_id: 'audit-stored',
  scope_id: 'scope-stored',
  review_start: '2019-09-01',
  review_end: '2019-09-05',
  context_buffer_km: 25,
  status: 'HISTORY_BUILD_READY',
  bbox: null,
  centroid: null,
  buffer_bbox: null,
  buffer_geometry: null,
}

const complete: AnalysisJob = {
  auditId: 'audit-stored',
  eventId: DEMO_FOCUS_EVENT_ID,
  jobStatus: 'COMPLETE',
  completedAt: '2026-09-11T02:10:00+00:00',
}

beforeEach(() => {
  resetDemoSessionForTests()
  localStorage.clear()
  useAppStore.setState({ auditId: null, registerSelection: [] })
  vi.mocked(addToAuditPack).mockResolvedValue({ eventId: DEMO_FOCUS_EVENT_ID, note: '', disposition: '', addedAt: '' })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('DemoFlow', () => {
  it('reuses the stored demo audit when the API still knows it, and never creates a second one', async () => {
    localStorage.setItem('eac.demo.session', JSON.stringify({ scope: storedScope }))
    vi.mocked(readInvestigationAnalysis).mockResolvedValue(complete)

    render(<StrictMode><DemoFlow /></StrictMode>)

    await waitFor(() => expect(screen.getByText(/audit audit-st/)).toBeTruthy())
    expect(createAuditReview).not.toHaveBeenCalled()
    expect(startInvestigationAnalysis).not.toHaveBeenCalled()
    // The register selection that seeds the map graph is set from the script.
    expect(useAppStore.getState().registerSelection).toEqual(DEMO_REGISTER_SELECTION)
    expect(useAppStore.getState().auditId).toBe('audit-stored')
  })

  it('creates one demo audit under StrictMode and primes the analysis once', async () => {
    vi.mocked(createAuditReview).mockResolvedValue({ ...storedScope, audit_id: 'audit-new', status: 'AWAITING_SCOPE' })
    vi.mocked(setAuditScopeDemo).mockResolvedValue({ ...storedScope, audit_id: 'audit-new', status: 'SCOPE_READY' })
    vi.mocked(buildFireHistory).mockResolvedValue({ audit_id: 'audit-new', scope_id: 'scope-new', status: 'HISTORY_BUILD_READY', duration_ms: 12, dataset_mode: 'cached_real_historical_dataset' })
    vi.mocked(readInvestigationAnalysis).mockResolvedValue({ auditId: 'audit-new', eventId: DEMO_FOCUS_EVENT_ID, jobStatus: 'NOT_RUN' })
    vi.mocked(startInvestigationAnalysis).mockResolvedValue({ auditId: 'audit-new', eventId: DEMO_FOCUS_EVENT_ID, jobStatus: 'RUNNING', pollAfterSeconds: 60 })

    render(<StrictMode><DemoFlow /></StrictMode>)

    await waitFor(() => expect(startInvestigationAnalysis).toHaveBeenCalledTimes(1))
    expect(createAuditReview).toHaveBeenCalledTimes(1)
    expect(setAuditScopeDemo).toHaveBeenCalledWith('audit-new')
    expect(buildFireHistory).toHaveBeenCalledWith('audit-new')
    expect(JSON.parse(localStorage.getItem('eac.demo.session') ?? '{}').scope.audit_id).toBe('audit-new')
  })

  it('walks the steps in script order with the arrow keys and packs the focus event before the report', async () => {
    localStorage.setItem('eac.demo.session', JSON.stringify({ scope: storedScope }))
    vi.mocked(readInvestigationAnalysis).mockResolvedValue(complete)
    render(<DemoFlow />)
    await waitFor(() => expect(screen.getByText(/audit audit-st/)).toBeTruthy())

    // The scope step keeps the landing underneath its overlay, so that step
    // mounts two screens; the rest mount one.
    const mounted = () => screen.getAllByTestId('screen').map((node) => node.textContent).join(' | ')
    const expected = ['landing', 'landing | scope audit-stored', 'register audit-stored', 'map audit-stored focus=none', `map audit-stored focus=${DEMO_FOCUS_EVENT_ID}`, `map audit-stored focus=${DEMO_FOCUS_EVENT_ID}`]
    expect(expected).toHaveLength(DEMO_STEPS.length - 1)
    for (const [position, text] of expected.entries()) {
      expect(mounted()).toBe(text)
      expect(screen.getByText(`Step ${position + 1} of ${DEMO_STEPS.length}: ${DEMO_STEPS[position].title}.`)).toBeTruthy()
      act(() => { fireEvent.keyDown(window, { key: 'ArrowRight' }) })
    }
    // The analysis step reports when the pre-generated assessment was made,
    // so the presenter can say so rather than imply it ran live.
    act(() => { fireEvent.keyDown(window, { key: 'ArrowLeft' }) })
    expect(screen.getByText(/Analysis generated at/)).toBeTruthy()
    act(() => { fireEvent.keyDown(window, { key: 'ArrowRight' }) })

    await waitFor(() => expect(mounted()).toBe('report audit-stored'))
    expect(addToAuditPack).toHaveBeenCalledWith('audit-stored', DEMO_FOCUS_EVENT_ID)
    // Last step: Next is disabled, nothing beyond the report.
    act(() => { fireEvent.keyDown(window, { key: 'ArrowRight' }) })
    expect(mounted()).toBe('report audit-stored')
  })

  it('shows a waiting state rather than a screen it cannot fill while the audit is being created', async () => {
    let resolveCreate: (scope: AuditScope) => void = () => undefined
    vi.mocked(createAuditReview).mockReturnValue(new Promise((resolve) => { resolveCreate = resolve }))
    render(<DemoFlow />)
    act(() => { fireEvent.keyDown(window, { key: 'ArrowRight' }) })
    expect(screen.getByText('Preparing the demo audit.')).toBeTruthy()
    resolveCreate({ ...storedScope, audit_id: 'audit-late' })
  })
})
