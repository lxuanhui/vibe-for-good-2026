import type { InvestigationReport } from '../types'

const STAGE1_CHECKS_TEMPLATE = [
  { id: 'land_cover', label: 'Vegetated land cover present' },
  { id: 'repeat_detections', label: 'Detection pattern consistent with active burn, not a persistent point source' },
  { id: 'industrial_mask', label: 'No known industrial or urban heat source at location' },
  { id: 'volcano_mask', label: 'No volcanic or geothermal proximity' },
  { id: 'neighbouring_hotspots', label: 'Neighbouring thermal activity consistent with vegetation fire spread' },
]

const REPORT_A: InvestigationReport = {
  eventId: 'IND-01120',
  status: 'converged',
  stage1Gate: {
    outcome: 'rejected',
    checks: STAGE1_CHECKS_TEMPLATE.map((c) => {
      if (c.id === 'land_cover')
        return { ...c, passed: false, detail: 'Land cover classified dense_urban; no vegetation within 500m' }
      if (c.id === 'repeat_detections')
        return { ...c, passed: false, detail: '2 detections at the same coordinates on consecutive days, near-identical FRP' }
      if (c.id === 'industrial_mask')
        return { ...c, passed: false, detail: 'Coordinates match a mapped industrial facility heat signature' }
      return { ...c, passed: true, detail: '' }
    }),
  },
  executiveSummary: '',
  topTheories: [],
  dataVisualizations: { fwiKbdiTimeseries: [], sarBackscatterTrend: [], fireGrowthProjection: null },
  limitations: [],
  analysisRounds: [],
  unresolvedQuestions: [],
  evidence: {},
}

const REPORT_B: InvestigationReport = {
  eventId: 'IND-01894',
  status: 'converged',
  stage1Gate: {
    outcome: 'passed',
    checks: STAGE1_CHECKS_TEMPLATE.map((c) => ({ ...c, passed: true, detail: '' })),
  },
  executiveSummary:
    'KBDI, rainfall, and FWI indicate fire-weather conditions conducive to ignition and spread before detection (E1, E2, E3). Available vegetation-change, concession-context, and SAR evidence does not distinguish an ignition mechanism (E5, E6, E7). Regional fire weather is the leading hypothesis, while land-management explanations remain unresolved pending human review.',
  topTheories: [
    {
      rank: 1,
      hypothesisId: 'H1',
      hypothesis: 'Environmental / regional fire-weather conditions',
      supportScore: 82,
      evidenceIds: ['E1', 'E2', 'E3'],
      counterEvidenceIds: ['E7'],
    },
    {
      rank: 2,
      hypothesisId: 'H2',
      hypothesis: 'Small-scale agricultural land-management burning',
      supportScore: 46,
      evidenceIds: ['E4'],
      counterEvidenceIds: ['E1', 'E2'],
    },
    {
      rank: 3,
      hypothesisId: 'H3',
      hypothesis: 'Plantation / large-scale land-management activity',
      supportScore: 29,
      evidenceIds: ['E5'],
      counterEvidenceIds: ['E1', 'E6'],
    },
  ],
  dataVisualizations: {
    fwiKbdiTimeseries: [
      { date: '2026-08-29', fwi: 14.2, kbdi: 310, vpd: 1.1 },
      { date: '2026-08-31', fwi: 17.8, kbdi: 356, vpd: 1.4 },
      { date: '2026-09-02', fwi: 22.4, kbdi: 401, vpd: 1.8 },
      { date: '2026-09-04', fwi: 19.6, kbdi: 388, vpd: 1.5 },
      { date: '2026-09-06', fwi: 15.1, kbdi: 349, vpd: 1.2 },
    ],
    sarBackscatterTrend: [
      { date: '2026-08-29', vhDb: -11.4 },
      { date: '2026-09-04', vhDb: -12.6 },
    ],
    fireGrowthProjection: {
      centroid: [104.702, -3.021],
      majorAxisKm: 1.8,
      minorAxisKm: 0.9,
      orientationDeg: 205,
      headSpreadKmh: 3.2,
      backSpreadKmh: 0.7,
      flankSpreadKmh: 1.4,
      modelVersion: 'surface-fire-ellipse-v1',
      modelLabel: 'First-order surface-fire compatibility estimate',
      compatibility: 'PARTIAL',
      observedProgression: [
        { clusterId: 'IND-01894-A', elapsedHours: 24, eastKm: -0.5, northKm: -0.2, distanceKm: 0.54, insideExpectedEnvelope: true },
        { clusterId: 'IND-01894-B', elapsedHours: 48, eastKm: 4.2, northKm: -0.4, distanceKm: 4.22, insideExpectedEnvelope: false },
      ],
      observationsOutsideExpectedEnvelope: ['IND-01894-B'],
      note: 'Estimated surface extent, not a validated fire-behavior forecast.',
    },
  },
  limitations: [
    'Optical imagery unavailable due to cloud cover on 2026-09-03; SAR evidence used where available.',
    'Weather variables are gridded model estimates (ERA5-Land), not local station readings.',
    'KHG classification reflects the last KLHK Geoportal update and is not field-verified.',
  ],
  analysisRounds: [
    {
      round: 1,
      phase: 'independent_assessment',
      investigator: {
        hypothesis: 'H1',
        support: 78,
        contra: 0,
        summary: 'KBDI and FWI both climbed sharply over the 5 days before detection, consistent with drought-driven ignition risk independent of land use.',
        evidenceIds: ['E1', 'E3'],
        counterEvidenceIds: [],
      },
      skeptic: {
        hypothesis: 'H3',
        support: 35,
        contra: 0,
        summary: 'The event location intersects a mapped production-zone concession attribute, which is contextual rather than causal; weather data alone does not distinguish the ignition mechanism.',
        evidenceIds: ['E6'],
        counterEvidenceIds: ['E1', 'E3'],
      },
      unresolvedQuestions: [],
    },
    {
      round: 2,
      phase: 'rebuttal',
      investigator: {
        hypothesis: 'H1',
        support: 82,
        contra: 18,
        summary: 'No vegetation-change signal is strong enough to distinguish land-use explanations under already-dry conditions; rainfall dropped to near zero for 6 consecutive days.',
        evidenceIds: ['E2', 'E5'],
        counterEvidenceIds: ['E6'],
      },
      skeptic: {
        hypothesis: 'H3',
        support: 29,
        contra: 44,
        summary: 'Concession overlap alone is contextual rather than causal evidence. The weather case for H1 is well-supported.',
        evidenceIds: ['E6'],
        counterEvidenceIds: ['E1', 'E2', 'E3'],
      },
      unresolvedQuestions: [],
    },
    {
      round: 3,
      phase: 'final_assessment',
      investigator: {
        hypothesis: 'H1',
        support: 82,
        contra: 18,
        summary: 'Environmental conditions are the best-supported explanation. Recommend standard-priority review rather than urgent escalation.',
        evidenceIds: ['E1', 'E2', 'E3'],
        counterEvidenceIds: ['E6'],
      },
      skeptic: {
        hypothesis: 'H3',
        support: 29,
        contra: 46,
        summary: 'H1 is best-supported. H3 remains open only because concession proximity is unresolved, not because of positive evidence.',
        evidenceIds: ['E6'],
        counterEvidenceIds: ['E1', 'E2', 'E3'],
      },
      unresolvedQuestions: [
        {
          question: 'Does local field or management documentation provide evidence that distinguishes regional fire-weather conditions from land-management activity?',
          evidenceIds: ['E1', 'E2', 'E3', 'E6'],
        },
      ],
    },
  ],
  unresolvedQuestions: [
    {
      question: 'Does local field or management documentation provide evidence that distinguishes regional fire-weather conditions from land-management activity?',
      evidenceIds: ['E1', 'E2', 'E3', 'E6'],
    },
  ],
  evidence: {
    E1: { evidenceId: 'E1', category: 'weather', type: 'kbdi', observation: 'KBDI reached 401 on 2026-09-02, the highest value in the trailing 30 days', source: 'Open-Meteo / ERA5-Land' },
    E2: { evidenceId: 'E2', category: 'weather', type: 'rainfall', observation: '0.0mm rainfall recorded for 6 consecutive days prior to first detection', source: 'Open-Meteo' },
    E3: { evidenceId: 'E3', category: 'weather', type: 'fwi', observation: 'Fire Weather Index peaked at 22.4, in the "high" band for the region', source: 'Derived / ERA5-Land' },
    E4: { evidenceId: 'E4', category: 'context', type: 'land-management', observation: 'Detection timing overlaps the regional small-farm land-clearing season', source: 'Regional agricultural calendar (contextual)' },
    E5: { evidenceId: 'E5', category: 'remote-sensing', type: 'vegetation-change', observation: 'No statistically significant NDVI drop detected in the available Sentinel-2 pre/post composite', source: 'Sentinel-2' },
    E6: { evidenceId: 'E6', category: 'context', type: 'concession', observation: 'Event location intersects a mapped oil-palm production-zone concession', source: 'GFW / KLHK ArcGIS REST (attribute only)' },
    E7: { evidenceId: 'E7', category: 'remote-sensing', type: 'sar', observation: 'SAR VH backscatter drop between passes is modest (-1.2dB) relative to confirmed clearing signatures', source: 'Sentinel-1' },
  },
}

const REPORT_C: InvestigationReport = {
  eventId: 'IND-02671',
  status: 'unresolved',
  stage1Gate: {
    outcome: 'passed',
    checks: STAGE1_CHECKS_TEMPLATE.map((c) => ({ ...c, passed: true, detail: '' })),
  },
  executiveSummary:
    'Sentinel-1 shows a VH backscatter change at the original detection location between 29 August and 4 September (E4). A later detection lies in the same mapped peat hydrological unit (E14) and is compatible with a first-order surface-fire envelope at the modeled elapsed time (E9). These observations support, but do not establish, peat-mediated persistence; independent new ignition remains a competing hypothesis requiring human verification.',
  topTheories: [
    {
      rank: 1,
      hypothesisId: 'FC1',
      hypothesis: 'Resurfaced fire complex (peat-mediated persistence)',
      supportScore: 78,
      evidenceIds: ['E4', 'E9', 'E14'],
      counterEvidenceIds: ['E2'],
    },
    {
      rank: 2,
      hypothesisId: 'H1',
      hypothesis: 'Environmental / regional fire-weather conditions',
      supportScore: 61,
      evidenceIds: ['E1', 'E3'],
      counterEvidenceIds: [],
    },
    {
      rank: 3,
      hypothesisId: 'FC2',
      hypothesis: 'Independent new ignition near existing complex',
      supportScore: 34,
      evidenceIds: ['E6'],
      counterEvidenceIds: ['E4', 'E9'],
    },
  ],
  dataVisualizations: {
    fwiKbdiTimeseries: [
      { date: '2026-08-29', fwi: 26.1, kbdi: 512, vpd: 2.1 },
      { date: '2026-08-31', fwi: 27.4, kbdi: 528, vpd: 2.2 },
      { date: '2026-09-02', fwi: 24.8, kbdi: 519, vpd: 1.9 },
      { date: '2026-09-04', fwi: 21.3, kbdi: 494, vpd: 1.6 },
      { date: '2026-09-06', fwi: 18.9, kbdi: 470, vpd: 1.4 },
    ],
    sarBackscatterTrend: [
      { date: '2026-08-29', vhDb: -3.1 },
      { date: '2026-09-04', vhDb: -4.6 },
    ],
    fireGrowthProjection: {
      centroid: [114.083, -2.734],
      majorAxisKm: 3.4,
      minorAxisKm: 1.6,
      orientationDeg: 95,
      headSpreadKmh: 1.4,
      backSpreadKmh: 0.3,
      flankSpreadKmh: 0.7,
      modelVersion: 'surface-fire-ellipse-v1',
      modelLabel: 'First-order surface-fire compatibility estimate',
      compatibility: 'COMPATIBLE',
      observedProgression: [
        { clusterId: 'IND-02671-2026-09-07', elapsedHours: 216, eastKm: 1.9, northKm: -0.2, distanceKm: 1.91, insideExpectedEnvelope: true },
      ],
      observationsOutsideExpectedEnvelope: [],
      note: 'The later cluster falls inside the first-order surface-fire envelope at the modeled elapsed time (E9). This is geometric compatibility only, not a tracked path.',
    },
  },
  limitations: [
    'The Sentinel-1 VH change is consistent with persistent surface-condition change; it cannot confirm continued combustion or resolve a subsurface travel speed or path.',
    'Soil moisture is a SMAP/ERA5-Land groundwater proxy, not a borehole reading.',
    'The fire-growth ellipse is a first-order geometric estimate, not a calibrated operational fire-behavior model.',
    'Optical confirmation is incomplete for the resurfacing window; SAR evidence carries more weight than usual in this report.',
  ],
  analysisRounds: [
    {
      round: 1,
      phase: 'independent_assessment',
      investigator: {
        hypothesis: 'FC1',
        support: 70,
        contra: 0,
        summary: 'The later detection lies inside the same mapped KHG unit as the original detection, while Sentinel-1 records a VH backscatter change at the original location.',
        evidenceIds: ['E4', 'E14'],
        counterEvidenceIds: [],
      },
      skeptic: {
        hypothesis: 'FC2',
        support: 40,
        contra: 0,
        summary: 'Two kilometers is not close; this could equally be a fresh ignition sharing the same regional drought conditions rather than the same fire.',
        evidenceIds: ['E1', 'E6'],
        counterEvidenceIds: ['E4', 'E14'],
      },
      unresolvedQuestions: [],
    },
    {
      round: 2,
      phase: 'rebuttal',
      investigator: {
        hypothesis: 'FC1',
        support: 76,
        contra: 24,
        summary: 'The first-order surface-fire envelope contains the later cluster at the modeled elapsed time. Combined with the VH change, this supports a same-complex hypothesis without establishing a tracked path.',
        evidenceIds: ['E4', 'E9'],
        counterEvidenceIds: ['E2'],
      },
      skeptic: {
        hypothesis: 'FC2',
        support: 34,
        contra: 38,
        summary: 'Wind direction over the period is not strongly aligned with the ellipse major axis toward the second detection, which weakens the propagation-path reading somewhat.',
        evidenceIds: ['E2'],
        counterEvidenceIds: ['E4', 'E9'],
      },
      unresolvedQuestions: [],
    },
    {
      round: 3,
      phase: 'final_assessment',
      investigator: {
        hypothesis: 'FC1',
        support: 78,
        contra: 22,
        summary: 'Same-dome SAR persistence plus geometric plausibility is the strongest available explanation. Recommend urgent field verification given protected-dome status.',
        evidenceIds: ['E4', 'E9', 'E14'],
        counterEvidenceIds: ['E2'],
      },
      skeptic: {
        hypothesis: 'FC2',
        support: 34,
        contra: 44,
        summary: 'FC1 is best-supported, but wind-direction evidence keeps independent ignition from being ruled out. Present this as unresolved, not confirmed underground tracking.',
        evidenceIds: ['E2', 'E6'],
        counterEvidenceIds: ['E4', 'E9', 'E14'],
      },
      unresolvedQuestions: [
        {
          question: 'Can field inspection or higher-resolution evidence distinguish peat-mediated persistence from an independent ignition within the same peat unit?',
          evidenceIds: ['E2', 'E4', 'E9', 'E14'],
        },
      ],
    },
  ],
  unresolvedQuestions: [
    {
      question: 'Can field inspection or higher-resolution evidence distinguish peat-mediated persistence from an independent ignition within the same peat unit?',
      evidenceIds: ['E2', 'E4', 'E9', 'E14'],
    },
  ],
  evidence: {
    E1: { evidenceId: 'E1', category: 'weather', type: 'kbdi', observation: 'KBDI held above 490 for the full 10-day window, indicating sustained dry conditions conducive to fire', source: 'Open-Meteo / ERA5-Land' },
    E2: { evidenceId: 'E2', category: 'weather', type: 'wind', observation: 'Prevailing wind direction over the period was ~95°, only partially aligned with the ellipse major axis toward the second detection', source: 'Open-Meteo' },
    E3: { evidenceId: 'E3', category: 'weather', type: 'fwi', observation: 'Fire Weather Index remained in the "very high" band for the full pre-detection window', source: 'Derived / ERA5-Land' },
    E4: { evidenceId: 'E4', category: 'remote-sensing', type: 'sar-persistence', observation: 'VH backscatter changed from -3.1dB (2026-08-29) to -4.6dB (2026-09-04) at the original detection location', source: 'Sentinel-1' },
    E6: { evidenceId: 'E6', category: 'context', type: 'alternative-ignition', observation: 'The current OpenStreetMap snapshot contains no mapped infrastructure, road, or settlement adjacent to the later detection; this does not establish conditions at the detection date or an ignition cause', source: 'OpenStreetMap Overpass (current snapshot)' },
    E9: { evidenceId: 'E9', category: 'model', type: 'surface-fire-envelope', observation: 'The later cluster falls inside the wind-oriented first-order surface-fire envelope at 216 elapsed hours; this is a compatibility observation, not a tracked path', source: 'Derived / surface-fire-ellipse-v1' },
    E14: { evidenceId: 'E14', category: 'context', type: 'khg-classification', observation: 'Both detections fall within the same KHG peat hydrological unit, classified as a protected dome', source: 'KLHK Geoportal ArcGIS REST' },
  },
}

export const REPORTS: Record<string, InvestigationReport> = {
  'IND-01120': REPORT_A,
  'IND-01894': REPORT_B,
  'IND-02671': REPORT_C,
}
