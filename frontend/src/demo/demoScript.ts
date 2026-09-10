// The guided demo path (#274): the pitch has at most two minutes of demo
// between two 75-second slide halves, so one presenter walks these steps in
// order with the arrow keys and never hunts for a button.
//
// Everything here is *which screen and which real audit* to show. Nothing
// here is data: every number on screen comes from the API and the committed
// 2019 artifact, exactly as it does off the demo path. If the API is down
// the steps show the console's own unavailable states.

import type { AuditScope } from '../api/types'

// The review period and buffer AuditStart already defaults to, and the
// server-owned demo study area (#216) rather than a geometry the console
// posts itself, so the session records itself as a demo scope.
export const DEMO_REVIEW_START = '2019-09-01'
export const DEMO_REVIEW_END = '2019-09-05'
export const DEMO_CONTEXT_BUFFER_KM = 25

// Three of the sixteen in-scope-and-buffer events with real wind-oriented
// edges between them (3 to 4 km apart; propagation-compatible and
// unresolved states), so the relationship graph draws when they are the
// register selection. The focus event is the middle one: it has a
// propagation-compatible edge to one neighbour, an unresolved edge to the
// other, and rendered Sentinel-1 and Sentinel-2 context scenes. Chosen from
// `backend/app/data/audit_triage_detail.json.gz`, not by hand.
export const DEMO_REGISTER_SELECTION = [
  'FE-20190902-1669d60fb3',
  'FE-20190903-f4804c12c7',
  'FE-20190904-c297199844',
]
export const DEMO_FOCUS_EVENT_ID = 'FE-20190903-f4804c12c7'

export type DemoView = 'landing' | 'scope' | 'register' | 'map' | 'report'

export interface DemoStep {
  id: string
  view: DemoView
  title: string
  // One line the presenter can say while the screen is up. Written under
  // the evidence-framing rules: what was measured, what it is consistent
  // with, and never a cause or a company.
  cue: string
  // Open the evidence drawer on the focus event.
  focus?: boolean
  // Show the analysis job's state in the presenter bar.
  analysis?: boolean
}

export const DEMO_STEPS: DemoStep[] = [
  {
    id: 'landing',
    view: 'landing',
    title: 'Live detections',
    cue: 'Every dot is a satellite detection across Southeast Asia in the last 24 hours. None of them is a fire yet.',
  },
  {
    id: 'scope',
    view: 'scope',
    title: 'Audit scope',
    cue: 'The auditor gives us a boundary and a review period. Here: the 2019 Kalimantan study area, 1 to 5 September. The history is already built; press Next.',
  },
  {
    id: 'register',
    view: 'register',
    title: 'Fire register',
    cue: 'Twenty thousand detections become clustered FireEvents, scoped to the boundary and ranked. Three are selected for the map.',
  },
  {
    id: 'map',
    view: 'map',
    title: 'Scoped map',
    cue: 'Boundary, buffer, the events and how they relate. The envelopes are wind-oriented surface-spread reach, capped at 10 km.',
  },
  {
    id: 'evidence',
    view: 'map',
    focus: true,
    title: 'Evidence',
    cue: 'One FireEvent. Observed evidence, derived evidence, radar and optical context, every item with an ID.',
  },
  {
    id: 'analysis',
    view: 'map',
    focus: true,
    analysis: true,
    title: 'Investigation analysis',
    cue: 'Investigator and Skeptic score six hypotheses against the same evidence. Support, not verdicts. Unresolved questions go to a human.',
  },
  {
    id: 'report',
    view: 'report',
    title: 'Engagement report',
    cue: 'Into the engagement pack, and out as a report the auditor signs.',
  },
]

export function isDemoScope(scope: AuditScope): boolean {
  return scope.review_start === DEMO_REVIEW_START && scope.review_end === DEMO_REVIEW_END
}
