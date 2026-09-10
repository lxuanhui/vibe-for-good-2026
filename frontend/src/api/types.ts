import type { FeatureCollection, PointGeometry } from './geojson'

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
  evidenceId?: string
  category: string
  type: string
  observation: string
  source: string
  evidence_id?: string
  time_window?: string
  value?: unknown
  unit?: string | null
  quality?: number | null
  limitations?: string[]
  algorithm_version?: string | null
  raw_reference?: string | null
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
  historyBuild?: { duration_ms: number; dataset_mode: string }
}

export type ScopeRelation = 'INSIDE_SCOPE' | 'BOUNDARY_INTERSECTING' | 'EXTERNAL_CONTEXT'

export interface AuditEventSummary {
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
  triage: { state: 'LIKELY_FIRE' | 'LIKELY_NON_FIRE' | 'AMBIGUOUS'; deeperInvestigationEligible: boolean }
  evidenceSufficiency: 'SUFFICIENT' | 'PARTIAL' | 'INSUFFICIENT'
  investigationPriority: 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT'
  reviewState: 'SCREENED' | 'REVIEW_RECOMMENDED' | 'HUMAN_REVIEW'
  reviewRouting: { priorityScore: number; escalationReasonCodes: string[]; components: { factor: string; value: number | null; weight: number; contribution: number; status: 'EVALUATED' | 'NOT_EVALUATED'; evidenceIds: string[]; reason: string }[] }
}

export interface InvestigationMapNode extends AuditEventSummary {
  scopeRelation: ScopeRelation
  mapRole: 'SELECTED' | 'EXTERNAL_CONTEXT'
}

export interface InvestigationMap {
  auditId: string
  selectedEventIds: string[]
  scope: Record<string, unknown>
  nodes: InvestigationMapNode[]
  edges: {
    sourceEventId: string
    targetEventId: string
    state: string
    distanceKm: number
    modelVersion: string
    supportingEvidenceIds?: string[]
    contradictingEvidenceIds?: string[]
    evidence?: EvidenceObject[]
    // Present only for a precomputed FireEventGraph edge with real
    // historical wind (`data_pipeline/enrich_fire_spread_audit_events.py`) --
    // a wind-oriented surface-fire compatibility envelope, not a claim about
    // what happened. `polygon` is a closed [lon, lat] ring.
    envelope?: {
      polygon: number[][]
      orientationDeg: number
      semiMajorKm: number
      semiMinorKm: number
    } | null
  }[]
  layers: Record<string, boolean>
}

// One raw FIRMS detection this FireEvent's clustering compressed. Real
// cluster membership (data_pipeline FireEvent.observation_indices), not a
// bbox/time approximation -- this is why the console can show precisely
// which detections a FireEvent came from.
export interface FireEventObservation {
  lat: number
  lon: number
  acqDate: string
  acqTime: number
  frp: number | null
  confidence: string
}

export interface TriageDetail {
  algorithm_version: string
  state: string
  fire_support_score: number
  non_fire_support_score: number
  requires_ai_review: boolean
  deeper_investigation_eligible: boolean
  decisive_rule_ids: string[]
  decision_reasons: string[]
  budget_reason: string | null
  evaluated_at: string
  event_id: string
  rules: Record<string, unknown>[]
  evidence: EvidenceObject[]
  observations: FireEventObservation[]
}

export interface EventEvidenceResponse {
  auditId: string
  event: AuditEventSummary & { triageDetail?: TriageDetail }
  scopeRelation: ScopeRelation
  observedEvidence: EvidenceObject[]
  derivedEvidence: EvidenceObject[]
  availability: { kind: 'peat' | 'weather' | 'imagery'; status: 'unavailable' | 'no_suitable_pass' | 'available'; reason: string }[]
  evidenceSufficiency: { value: 'SUFFICIENT' | 'PARTIAL' | 'INSUFFICIENT'; reason: string; algorithmVersion: string }
  investigationPriority: 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT'
  reviewState: 'SCREENED' | 'REVIEW_RECOMMENDED' | 'HUMAN_REVIEW'
  reviewRouting: Record<string, unknown>
  provenance: { source: Record<string, unknown>; algorithmVersions: string[] }
}

export interface StructuredAnalysisQuestion {
  question: string
  evidence_ids: string[]
  reason?: string
}

export interface StructuredAnalysisFinding {
  hypothesis_id: string
  support_score: number
  evidence_sufficiency: 'SUFFICIENT' | 'PARTIAL' | 'INSUFFICIENT'
  supporting_evidence_ids: string[]
  contradicting_evidence_ids: string[]
  summary: string
  verification_questions: StructuredAnalysisQuestion[]
}

export interface StructuredAnalysisAssessment {
  role: 'INVESTIGATOR' | 'SKEPTIC'
  round: number
  phase: 'INDEPENDENT_ASSESSMENT' | 'REBUTTAL' | 'FINAL_ASSESSMENT'
  findings: StructuredAnalysisFinding[]
  unresolved_questions: StructuredAnalysisQuestion[]
}

export interface StructuredAnalysis {
  event_id: string
  status: string
  algorithm_version: string
  evidence_ids: string[]
  rounds: { round: number; phase: string; investigator: StructuredAnalysisAssessment; skeptic: StructuredAnalysisAssessment; unresolved_questions: StructuredAnalysisQuestion[] }[]
  final_assessment: { investigator: StructuredAnalysisAssessment; skeptic: StructuredAnalysisAssessment }
  unresolved_questions: StructuredAnalysisQuestion[]
}

// The analysis endpoint is a job, not a synchronous result: a two-round
// assessment outlives API Gateway's 30s response cap. `jobStatus` describes
// the work; the HTTP status describes the request. `status` inside
// StructuredAnalysis is a different thing entirely -- CONVERGED/UNRESOLVED,
// the outcome of the debate -- and the two must not be conflated.
export interface AnalysisJob {
  auditId: string
  eventId: string
  jobStatus: 'NOT_RUN' | 'RUNNING' | 'COMPLETE' | 'FAILED'
  analysis?: StructuredAnalysis | null
  error?: string | null
  startedAt?: string | null
  completedAt?: string | null
  pollAfterSeconds?: number
}

export interface InvestigationBundle {
  event: EventEvidenceResponse
  graph: InvestigationMap | null
  analysis: StructuredAnalysis | null
}

// The committed real dataset, described without building an audit. Narrower
// than the `source` blob the events endpoint returns -- only the fields the
// first-load context panel states as fact are typed here, so a change to the
// artifact's provenance shape cannot silently widen what the UI claims.
export interface DemoDatasetSummary {
  dataset: string
  region: string
  window: string
  progression: Pick<AuditProgression, 'rawObservations' | 'qualifiedObservations' | 'fireEvents' | 'requiringHumanReview'>
}

export interface AuditProgression {
  // Null when a narrowed review period makes the pre-clustering raw count
  // unknowable (#161): the artifact records how many detections were dropped
  // at the confidence gate across the whole dataset, not per day, so a
  // sub-window cannot state its own figure without inventing one.
  rawObservations: number | null
  qualifiedObservations: number
  fireEvents: number
  requiringHumanReview: number
  selected: number
  selectedEventIds: string[]
  compression: number | null
  observationsToEventsCompression: number | null
  inScopeAndBuffer: number | null
  scopeBoundaryAvailable: boolean
  scopeCompression: number | null
  routingDiagnostics: {
    humanReviewCount: number
    humanReviewPercentage: number
    priorityDistribution: Record<string, { count: number; percentage: number }>
    reviewStateDistribution: Record<string, { count: number; percentage: number }>
    evidenceSufficiencyDistribution: Record<string, { count: number; percentage: number }>
    escalationReasonCodes: Record<string, { count: number; percentage: number }>
    componentContributionDistribution: Record<string, { evaluatedCount: number; totalContribution: number; percentageOfContribution: number }>
  }
}

export interface AuditPackReview { eventId: string; note: string; disposition: string; addedAt: string }

export interface AuditReport {
  auditId: string
  auditScope: { reviewStart: string; reviewEnd: string; scope: Record<string, unknown> }
  sourceMethodSummary: { observed: string; derived: string; ai: string; source: Record<string, unknown> }
  compressionSummary: Record<string, unknown> & Partial<AuditProgression>
  counts: { identified: number; screened: number; reviewed: number; selected: number; verify: number; insufficient: number }
  selectedFireEvents: { event: AuditEventSummary; review: AuditPackReview; evidence: EventEvidenceResponse }[]
  maps: { selectedEventIds: string[]; layers: Record<string, boolean> }
  chronology: { eventId: string; firstDetection: string; lastDetection: string }[]
  deterministicEvidence: { eventId: string; observed: EvidenceObject[]; derived: EvidenceObject[] }[]
  graphRelationships: InvestigationMap['edges']
  aiAnalysis: { eventId: string; analysis: StructuredAnalysis }[]
  analysisNotRunEventIds: string[]
  unresolvedQuestions: ({ eventId: string } & StructuredAnalysisQuestion)[]
  verificationRecommendations: ({ eventId: string } & StructuredAnalysisQuestion)[]
  limitations: string[]
  provenance: { source: Record<string, unknown>; algorithmVersions: string[] }
  humanNotes: AuditPackReview[]
  disclaimer: string
}

/** One live NASA FIRMS thermal detection, as the API relays it.

  `acquiredAt` is the raw UTC acquisition time rather than a precomputed age:
  the API caches a response for 15 minutes, so a server-side "hours ago" would
  be wrong for every visitor after the first. The landing map derives the age
  it paints with at render time. */
export interface LiveFirmsDetectionProperties {
  confidence: string
  frp: number
  acquiredAt: string | null
}

export interface LiveFirmsDetections {
  status: 'ready'
  sensor: string
  windowHours: number
  fetchedAt: string
  detections: FeatureCollection<PointGeometry, LiveFirmsDetectionProperties>
}

export interface OverlayAvailability {
  date: string
  layers: Partial<Record<OverlayLayerId | RasterLayerId, boolean>>
}
