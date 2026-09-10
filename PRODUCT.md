# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: the environmental/certification assurance auditor**, working an
engagement against a defined management unit in Indonesia. They arrive with an
authorised audit scope — a boundary and a review period — and a fixed, small
budget of desk-review and field-verification hours. Their job, before or during
fieldwork, is to reconstruct the historical fire record for that unit, find the
relationships and evidence gaps inside it, and decide which handful of events
deserve a human question.

They are not remote-sensing specialists. The satellite record is already
public; what they lack is a way to turn twenty thousand raw detections into a
short list they can defend.

**Design target: an auditor tool that a first-time viewer can follow.** The
auditor is the user and the workflow is built for them, but every screen has to
explain itself without narration — the near-term audience includes ACCA
challenge judges meeting the product cold. This resolves in favour of density
plus self-explanation, never in favour of persuasion surfaces. *(Recorded as
the assistant's recommendation, adopted by the user rather than specified by
them.)*

Secondary audiences named in the spec — sustainability assurance firms,
commodity buyers, lenders and insurers, regulators, NGOs — are acknowledged but
have not shaped anything. Do not design for them.

## Product Purpose

The product reconstructs a management unit's environmental history so that
scarce human attention lands on the right events.

It takes an audit scope and a review period, clusters raw satellite fire
detections into coherent FireEvents, screens them deterministically, lets the
auditor investigate them spatially and temporally, and then uses adversarial AI
to surface competing explanations and the specific questions a human should go
and verify.

Success is a **narrower, better-justified verification list** — not a verdict,
a score against a company, or an answer. The measured chain is
observations → events → in scope → ranked; the product earns its place by
compressing that chain, and by showing its work at every step.

## Positioning

The differentiator is **decision context, not detection capability**.
Indonesian authorities already run sophisticated geospatial intelligence; the
product does not compete with enforcement monitoring, and must never be
positioned as if it does.

| Enforcement intelligence | This product |
|---|---|
| territory-wide mandate | engagement-defined scope |
| current/recent monitoring | historical review period |
| detect and escalate incidents | reconstruct and screen event history |
| intervention priority | verification priority |
| the authority resolves concession context | the auditor brings authorised scope |

The mechanism a neighbouring product could not truthfully copy: **an audit
scope is the first-class input**, and everything downstream — clustering,
triage, ranking, the evidence pack — is derived inside that scope with a
context buffer around it. Not a monitoring feed the user filters afterwards.

## Operating Context

The canonical workflow, in order:

1. **Scope entry.** The auditor supplies a management-unit boundary (GeoJSON
   upload, or a coordinate fallback) and a review period. A context buffer
   around the boundary is visible, because events outside the unit can explain
   events inside it.
2. **Build fire history.** Raw FIRMS observations cluster into FireEvents.
   The compression from observations to events is shown, not asserted.
3. **Historical Fire Register.** A table, first — sortable, filterable,
   multi-select. Table before map is deliberate: screening is a temporal job.
4. **Investigate on map.** Selected events plus relevant neighbours and the
   context buffer open spatially.
5. **Evidence Drawer.** Cheap deterministic metrics render immediately;
   imagery and expensive sources hydrate asynchronously with explicit
   missing-data states. Every metric is inspectable back to its provenance.
6. **Adversarial analysis, run explicitly.** An Investigator and a Skeptic
   disagree — local ignition versus a neighbouring or peat explanation — and
   the output is an unresolved question plus a recommended field check.
7. **Evidence pack.** The auditor adds events to a pack; an engagement-level
   report is generated.

The deliverable that leaves the product is an audit evidence pack a human
signs off on. Reports must be reproducible.

## Capabilities and Constraints

**The safety boundary is the architecture, not a tone preference.** Four layers
never collapse into each other: observed evidence → derived metrics → AI
interpretation → human decision. Every AI factual claim carries an evidence ID
that exists in the report's evidence map.

Never produced, at any layer including UI copy:

- a statement that a named company, smallholder or person caused, set,
  permitted or is responsible for a fire;
- a guilt, culpability, intent, negligence or liability score, or a label that
  reads as one;
- a legal conclusion or a recommendation to prosecute, fine or sanction;
- a public named-concession directory, or third-party concession polygon
  geometry beyond an attribute-only lookup. *(An auditor's own uploaded
  boundary is different — that is legitimate private audit-scope data.)*

Score FireEvents, not companies. Geographic association is not responsibility.
First detection inside a boundary does not establish origin. Client identity
must not influence physical scoring. Evidence must cut both ways: exculpatory
relationships are first-class, and a neighbouring event compatible with later
in-scope observations gets the same prominence as evidence for local ignition.
Absence of data is a finding to state, not a gap to write around.

**Terminology is load-bearing.** FireEvent, audit scope, context buffer,
Historical Fire Register, EvidenceObject, FireEventGraph, evidence pack,
Investigator/Skeptic. Inferred things are labelled inferred; estimated things
estimated. Fire never "travels underground" or is "tracked" — subsurface
persistence is *inferred* from SAR persistence and absence of revegetation.

**Real data and fixture data must never be visually confusable.** Some of the
console is fixture-driven and some is real; the split is documented in
CLAUDE.md and moves one endpoint at a time. Any surface showing both labels
which is which. This is a hard product rule, not a demo nicety.

**One colour system, single-sourced.** Confidence and status use
`lib/layerColors.ts` and the Tailwind `--color-status-*` tokens everywhere; no
inline hexes in components. This is a consistency constraint that survives any
restyle — the tokens' *values* are not binding, but their role as the single
source is.

**Explicitly undecided:**

- No accessibility standard has been adopted. Status and confidence are
  currently encoded by colour alone in several places (map, status ramp, score
  badges). Future work must not cite a standard nobody agreed to, and must not
  assume this is settled.
- The persistence services behind §8's roles (durable/queryable metadata, bulky
  immutable evidence, disposable cache) are deliberately unchosen. Nothing
  persists today.

## Brand Commitments

The name is **atmosclear.ai**, chosen by the team on 2026-09-10 (#257) and
held in `frontend/src/lib/brand.ts`; the earth mark beside it is
`components/brand/EarthMark.tsx`, mirrored in `public/favicon.svg`. That
replaced "Environmental Assurance Console", which had been recorded here as
provisional scaffolding. The dark ground / cyan accent palette in
`frontend/src/index.css` is still provisional and a future session may
replace it. The single-colour-system rule above is a code constraint that
outlives whatever palette replaces it.

## Evidence on Hand

Real:

- **20,471 NASA FIRMS detections** from the 2019 Indonesian haze window,
  clustered offline into **3,610 FireEvents** and run through Stage-1 triage.
  Served by `GET /api/audits/{id}/events` from a committed artifact
  (`backend/app/data/audit_events.json.gz`); clustering happens in
  `data_pipeline/export_audit_events.py`.
- **`data_pipeline/`** — ~58 unit-tested modules: clustering, triage, graph,
  priority, complexity, enrichment, propagation, imagery, plus benchmark and
  golden regression cases.
- **The canonical spec**, `DesignSpecs/Environmental_Assurance_Spec.md` v3.0.
  Three legacy specs are superseded history; do not cite their section numbers.
- **A deployed console** at `https://main.dz8w2n4hd2d22.amplifyapp.com/`,
  Flask on Lambda behind API Gateway, Terraform-managed.

Fixtures, clearly: `fetchOverlay`, `fetchReport`, and `generateReport` — the
last fakes the Investigator/Skeptic loop with `setTimeout`. The events endpoint
is real; the FireEvents it serves are real; the *legacy flat* `/api/events`
fixture cases are invented.

Do not fabricate: customers, pilot auditors, certification-body endorsements,
accuracy benchmarks, or any claim that the tool has been used on a real
engagement. None exist. Stage-1 triage's compression on this dataset is 1.0×
and that is correct behaviour, not a gap more data would close — do not present
it otherwise.

## Product Principles

1. **Compression is the product.** Every surface should make the narrowing
   visible — how many observations became how many events, how many fell in
   scope, how many were ranked. A screen that shows results without showing the
   narrowing has hidden the value.
2. **The human decides, and the interface must look like it.** Nothing renders
   as a verdict. Competing hypotheses appear together with support scores;
   neither is an answer.
3. **Every claim is traceable, one click away.** Inspectability is not a
   feature panel — a metric the auditor cannot open back to its provenance and
   limitations should not be shown.
4. **Say what is missing.** Gaps, cloud cover, absent sources and unreachable
   labels are findings that get rendered, not silence to design around.
5. **Never blur real and fixture.** Where both are present, the interface says
   which is which, plainly, without the auditor having to ask.
