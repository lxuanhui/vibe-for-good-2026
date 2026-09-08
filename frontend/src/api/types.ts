// Stage-1 outcomes (AMBIGUOUS, LIKELY_NON_FIRE) match the triage states in
// `Environmental_Assurance_Spec.md` §10; the remaining values are this
// repo's own naming for Stage-2 adversarial-analysis progress and outcome
// (matches InvestigationReport.status below) since the canonical spec doesn't
// enumerate an AnalysisRun status.
export type EventStatus =
  | 'AMBIGUOUS'
  | 'LIKELY_NON_FIRE'
  | 'STAGE2_RUNNING'
  | 'UNRESOLVED'
  | 'CONVERGED'

export type PeatClassification = 'protected_dome' | 'production_zone' | 'not_applicable'

export type OverlayLayerId = 'firms' | 'sar-backscatter' | 'khg' | 'concessions' | 'fire-complex-links'

export type RasterLayerId = 's2-quicklook' | 'sar-visualization'

export interface ThermalDetection {
  detectionId: string
  acquiredAt: string
  satellite: string
  instrument: string
  frp: number
  confidence: 'low' | 'nominal' | 'high'
}

export interface CurrentConditions {
  temperatureC: number
  relativeHumidity: number
  windSpeedKmh: number
  windDirectionDeg: number
  recentRainfallMm: number
}

export interface FireEvent {
  id: string
  fireComplexId?: string
  lat: number
  lon: number
  location: string
  firstDetected: string
  status: EventStatus
  qualifiesForInvestigation: boolean
  topHypothesis?: string
  supportScore?: number
  peatClassification: PeatClassification
  daysSinceLastSurfaceDetection?: number
  detections: ThermalDetection[]
  currentConditions: CurrentConditions
}

export interface EvidenceObject {
  evidenceId: string
  category: string
  type: string
  observation: string
  source: string
}

export interface TopTheory {
  rank: number
  hypothesis: string
  hypothesisId: string
  supportScore: number
  evidenceIds: string[]
  counterEvidenceIds: string[]
}

export interface AnalysisQuestion {
  question: string
  evidenceIds: string[]
  reason?: string
}

export interface AnalysisFinding {
  hypothesis: string
  support: number
  contra: number
  summary: string
  evidenceIds: string[]
  counterEvidenceIds: string[]
}

export interface AnalysisRound {
  round: number
  phase: 'independent_assessment' | 'rebuttal' | 'final_assessment'
  investigator: AnalysisFinding
  skeptic: AnalysisFinding
  unresolvedQuestions: AnalysisQuestion[]
}

export interface Stage1Check {
  id: string
  label: string
  passed: boolean
  detail: string
}

export interface Stage1GateResult {
  outcome: 'passed' | 'rejected'
  checks: Stage1Check[]
}

export interface FwiKbdiPoint {
  date: string
  fwi: number
  kbdi: number
  vpd: number
}

export interface SarBackscatterPoint {
  date: string
  vhDb: number
}

export type SurfaceFireCompatibility = 'COMPATIBLE' | 'PARTIAL' | 'INCOMPATIBLE' | 'NOT_EVALUATED'

export interface SurfaceFireObservedCluster {
  clusterId: string
  elapsedHours: number
  eastKm: number
  northKm: number
  distanceKm: number
  insideExpectedEnvelope: boolean | null
}

export interface FireGrowthProjection {
  centroid: [number, number]
  majorAxisKm: number
  minorAxisKm: number
  orientationDeg: number
  headSpreadKmh?: number
  backSpreadKmh?: number
  flankSpreadKmh?: number
  modelVersion?: string
  modelLabel?: string
  compatibility?: SurfaceFireCompatibility
  observedProgression?: SurfaceFireObservedCluster[]
  observationsOutsideExpectedEnvelope?: string[]
  note: string
}

export interface InvestigationReport {
  eventId: string
  status: 'running' | 'converged' | 'unresolved'
  stage1Gate: Stage1GateResult
  executiveSummary: string
  topTheories: TopTheory[]
  dataVisualizations: {
    fwiKbdiTimeseries: FwiKbdiPoint[]
    sarBackscatterTrend: SarBackscatterPoint[]
    fireGrowthProjection: FireGrowthProjection | null
  }
  limitations: string[]
  analysisRounds: AnalysisRound[]
  unresolvedQuestions: AnalysisQuestion[]
  evidence: Record<string, EvidenceObject>
}

export interface BBox {
  minLon: number
  minLat: number
  maxLon: number
  maxLat: number
}

export interface AuditScope {
  audit_id: string
  scope_id: string
  review_start: string
  review_end: string
  context_buffer_km: number
  status: 'AWAITING_SCOPE' | 'SCOPE_READY' | 'HISTORY_BUILD_READY'
  bbox: BBox | null
  centroid: [number, number] | null
  buffer_bbox: BBox | null
  buffer_geometry: {
    type: 'Polygon'
    coordinates: [number, number][][]
  } | null
  geometry?: unknown
}

export interface OverlayAvailability {
  date: string
  layers: Partial<Record<OverlayLayerId | RasterLayerId, boolean>>
}

// --- Reconstructed audit history -------------------------------------------
// The shape served by `GET /api/audits/{id}/events`: FireEvents derived from
// real FIRMS observations by `data_pipeline/export_audit_events.py`.
//
// Deliberately NOT `FireEvent`. That type requires `location`,
// `peatClassification` and `currentConditions`, which FIRMS-only data cannot
// supply. Widening it with optional fields would make a real event and an
// invented fixture indistinguishable at the type level, which is precisely
// the blurring the product boundary forbids. Two types, so the compiler keeps
// them apart.

/** Stage-1 triage outcome (`Environmental_Assurance_Spec.md` §10). */
export type Stage1State = 'LIKELY_FIRE' | 'LIKELY_NON_FIRE' | 'AMBIGUOUS'

export interface AuditEventTriage {
  state: Stage1State
  fireSupportScore: number
  nonFireSupportScore: number
  requiresAiReview: boolean
  deeperInvestigationEligible: boolean
  decisiveRuleIds: string[]
  decisionReasons: string[]
  budgetReason: string
  algorithmVersion: string
}

export interface AuditEvent {
  eventId: string
  auditId: string
  firstDetection: string
  lastDetection: string
  durationHours: number
  observationCount: number
  centroid: { lat: number; lon: number }
  bbox: [number, number, number, number]
  spatialExtentKm: number
  maxFrp: number | null
  meanFrp: number | null
  /** Absent when the source export carries no satellite/instrument column. */
  sensorMix?: string[]
  triage: AuditEventTriage
}

/** One Stage-1 rule's contribution, each pointing at the evidence it read. */
export interface TriageRule {
  rule_id: string
  feature: string
  effect: string
  points: number
  explanation: string
  evidence_ids: string[]
}

/** An observed or derived fact. Every claim in the UI traces to one of these. */
export interface TriageEvidence {
  evidence_id: string
  category: string
  source: string
  observation: string
  quality: number
  limitations: string[]
  time_window: string
  raw_reference: string
  algorithm_version: string
  retrieved_at: string
}

export interface AuditEventDetail extends AuditEvent {
  triageDetail: {
    rules: TriageRule[]
    evidence: TriageEvidence[]
    algorithm_version: string
    evaluated_at: string
  } | null
}

export interface AuditEventScope {
  id: string
  label: string
  reviewStart: string
  reviewEnd: string
  contextBufferKm: number
  eventCount: number
  reviewQueueCount: number
  compression: number
}

/** Provenance for the observations behind the events, served alongside them. */
export interface AuditEventSource {
  dataset: string
  window: string
  region: string
  file: string
  observationsUsed: number
  excluded: string
  note: string
}

export interface AuditEventPage {
  auditId: string
  scope: AuditEventScope
  source: AuditEventSource
  total: number
  limit: number
  offset: number
  events: AuditEvent[]
}
