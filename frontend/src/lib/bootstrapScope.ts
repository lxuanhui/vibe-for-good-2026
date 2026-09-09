import { buildFireHistory, createAuditReview, uploadAuditScope, uploadAuditScopeGeometry } from '../api/client'
import type { AuditScope } from '../api/types'
import { DEFAULT_MANAGEMENT_UNIT_GEOMETRY } from './scope'

// The committed real dataset behind this demo is the 2019 Kalimantan haze
// window (docs/demo.md). These defaults put a scope inside it, so a visitor
// who never opens the scope form still sees real FireEvents rather than an
// empty map.
export const DEFAULT_REVIEW_START = '2019-09-01'
export const DEFAULT_REVIEW_END = '2019-09-05'
export const DEFAULT_CONTEXT_BUFFER_KM = 25

/**
 * The one real scope-creation path: POST /audits -> scope/upload ->
 * history/build. Both callers go through it -- the landing map's automatic
 * bootstrap and the scope form's submit -- so the map can never be showing a
 * hand-built scope object that never touched the API. That divergence is
 * exactly what hid the bbox-shape bug PR #118 found.
 */
export async function createScope(input: {
  reviewStart: string
  reviewEnd: string
  contextBufferKm: number
  file?: File | null
}): Promise<AuditScope> {
  const created = await createAuditReview({
    reviewStart: input.reviewStart,
    reviewEnd: input.reviewEnd,
    contextBufferKm: input.contextBufferKm,
  })
  const uploaded = input.file
    ? await uploadAuditScope(created.audit_id, input.file)
    : await uploadAuditScopeGeometry(created.audit_id, DEFAULT_MANAGEMENT_UNIT_GEOMETRY)
  const handoff = await buildFireHistory(uploaded.audit_id)
  return { ...uploaded, status: handoff.status, historyBuild: handoff }
}

export function createDefaultScope(): Promise<AuditScope> {
  return createScope({
    reviewStart: DEFAULT_REVIEW_START,
    reviewEnd: DEFAULT_REVIEW_END,
    contextBufferKm: DEFAULT_CONTEXT_BUFFER_KM,
  })
}
