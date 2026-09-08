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

export interface OverlayAvailability {
  date: string
  layers: Partial<Record<OverlayLayerId | RasterLayerId, boolean>>
}
