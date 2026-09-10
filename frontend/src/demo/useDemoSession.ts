import { useEffect, useState } from 'react'
import {
  buildFireHistory,
  createAuditReview,
  readInvestigationAnalysis,
  setAuditScopeDemo,
  startInvestigationAnalysis,
} from '../api/client'
import type { AnalysisJob, AuditScope } from '../api/types'
import { DEMO_CONTEXT_BUFFER_KM, DEMO_FOCUS_EVENT_ID, DEMO_REVIEW_END, DEMO_REVIEW_START, isDemoScope } from './demoScript'

// The demo audit is created once per browser and reused on every load of
// /demo. Two reasons. The analysis for the focus event takes ~51 s of
// Bedrock time (decision log, 2026-09-10, async job), which is nearly half
// the demo budget, so the presenter opens /demo before walking on and the
// job is COMPLETE by the time the drawer is on screen. And a session is
// what audit state hangs off in DynamoDB, so reusing it is what makes the
// pre-generated analysis reachable at all.
//
// The stored scope is only trusted after the API confirms the audit still
// exists (a local dev server keeps sessions in memory and forgets them on
// restart). A failed probe means a fresh session, never a broken screen.
const STORAGE_KEY = 'eac.demo.session'

export interface DemoSession {
  status: 'loading' | 'ready' | 'error'
  scope?: AuditScope
  error?: string
  // The focus event's analysis job as last read; null until known.
  analysis: AnalysisJob | null
}

function readStored(): AuditScope | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { scope?: AuditScope }
    return parsed.scope && isDemoScope(parsed.scope) ? parsed.scope : null
  } catch {
    return null
  }
}

function writeStored(scope: AuditScope): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ scope }))
  } catch {
    // Not persisting only means the next load creates another session.
  }
}

async function createDemoAudit(): Promise<AuditScope> {
  const created = await createAuditReview({
    reviewStart: DEMO_REVIEW_START,
    reviewEnd: DEMO_REVIEW_END,
    contextBufferKm: DEMO_CONTEXT_BUFFER_KM,
  })
  const scoped = await setAuditScopeDemo(created.audit_id)
  const handoff = await buildFireHistory(scoped.audit_id)
  return { ...scoped, status: handoff.status, historyBuild: handoff }
}

// Shared across mounts so React StrictMode's double effect, or two quick
// reloads, cannot create two audits and prime two analyses.
let bootstrap: Promise<{ scope: AuditScope; analysis: AnalysisJob }> | null = null

async function bootstrapSession(): Promise<{ scope: AuditScope; analysis: AnalysisJob }> {
  const stored = readStored()
  if (stored) {
    try {
      // GET only reads (routes.py): it confirms the audit and the event exist
      // and reports the job without spending tokens.
      const analysis = await readInvestigationAnalysis(stored.audit_id, DEMO_FOCUS_EVENT_ID)
      return { scope: stored, analysis }
    } catch {
      // Fall through to a fresh session.
    }
  }
  const scope = await createDemoAudit()
  writeStored(scope)
  const analysis = await readInvestigationAnalysis(scope.audit_id, DEMO_FOCUS_EVENT_ID)
  return { scope, analysis }
}

export function useDemoSession(): DemoSession {
  const [state, setState] = useState<DemoSession>({ status: 'loading', analysis: null })

  useEffect(() => {
    let active = true
    bootstrap ??= bootstrapSession()
    bootstrap
      .then(({ scope, analysis }) => {
        if (active) setState({ status: 'ready', scope, analysis })
      })
      .catch((reason: unknown) => {
        bootstrap = null
        if (active) {
          setState({
            status: 'error',
            analysis: null,
            error: reason instanceof Error ? reason.message : 'The demo audit could not be created.',
          })
        }
      })
    return () => { active = false }
  }, [])

  // Prime the analysis once the session is known, then follow the job until
  // it settles. POST is idempotent while a job is RUNNING and returns the
  // stored outcome once COMPLETE, so this never bills a second assessment.
  // Only NOT_RUN and FAILED start work; a failed job is retried exactly once
  // per page load, which is the retry an auditor would press.
  const auditId = state.scope?.audit_id
  const jobStatus = state.analysis?.jobStatus
  const pollAfter = state.analysis?.pollAfterSeconds ?? 5
  useEffect(() => {
    if (!auditId || !jobStatus) return
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const settle = (job: AnalysisJob) => { if (active) setState((current) => ({ ...current, analysis: job })) }
    if (jobStatus === 'NOT_RUN' || jobStatus === 'FAILED') {
      startInvestigationAnalysis(auditId, DEMO_FOCUS_EVENT_ID).then(settle).catch(() => undefined)
    } else if (jobStatus === 'RUNNING') {
      timer = setTimeout(() => {
        readInvestigationAnalysis(auditId, DEMO_FOCUS_EVENT_ID).then(settle).catch(() => undefined)
      }, Math.max(1, pollAfter) * 1000)
    }
    return () => { active = false; if (timer) clearTimeout(timer) }
    // A FAILED job retried once: the status changes to RUNNING on the
    // response, so the effect does not loop on the same FAILED value.
  }, [auditId, jobStatus, pollAfter])

  return state
}

// Test seam: the module-level promise would otherwise leak between tests.
export function resetDemoSessionForTests(): void {
  bootstrap = null
}
