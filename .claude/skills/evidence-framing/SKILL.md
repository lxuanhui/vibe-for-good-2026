---
name: evidence-framing
description: The product's hard boundary on attribution, causation, and evidence provenance. Load BEFORE writing or editing any text a user will read that describes a fire event - report copy, executive summaries, hypothesis labels, agent system prompts, UI status labels, chart captions, PDF text, commit-facing docs about findings. Also load when adding a field that names an organisation, when wording anything about peat "underground travel", and when deciding what an agent is allowed to cite.
---

# Evidence framing rules

This tool is an investigative-**efficiency** product. It narrows what a human
auditor looks at. It does not conclude anything about blame. Getting the
wording wrong here is not a style problem — it is the difference between a
triage aid and a defamation risk. Sources:
`DesignSpecs/environmental_assurance_claude_code_spec.md` §20, §42–45, and
`DesignSpecs/environmental_assurance_spec_v2.md` §2, §7, §8.

## Never generate

- A statement that a named company, concession holder, smallholder, or person
  caused, set, permitted, or is responsible for a fire.
- A guilt, culpability, intent, negligence, or legal-liability score, or any
  label that reads as one ("suspicious operator", "likely arson", "violation
  detected").
- A legal conclusion, a regulatory finding, or a recommendation to prosecute,
  fine, or sanction.
- A claim that a fire "travelled underground" from A to B, or that a path was
  "tracked". Underground persistence is *inferred* from SAR persistence,
  elapsed time, and absence of revegetation — never observed.
- A confident claim sourced from the fire-growth ellipse. It is a first-order
  geometric estimate, not a validated fire-behaviour forecast.
- Raw concession or peatland boundary geometry in any output, stored or
  rendered. Attribute lookups return attributes only (spec v2 §2, §9.1).

## Always

- Trace every factual claim to an evidence ID that exists in the report's
  `evidence` map. No evidence ID, no claim.
- Say what was measured, then what it is consistent with — in that order.
- Surface competing hypotheses rather than one answer. "Resurfaced fire
  complex" and "independent new ignition nearby" are both hypotheses with
  support scores; neither is a conclusion.
- State missing evidence explicitly. Absence of data is a finding, not a gap
  to write around.
- Keep the human decision last. The four layers (observed → derived → AI
  interpretation → human decision) never collapse into each other.

## Wording swaps

| Don't write | Write |
|---|---|
| "PT X burned this concession" | "The detection falls within a concession registered to PT X (E12). Concession overlap is recorded as context and does not indicate cause." |
| "The fire spread underground to the second site" | "A VH-backscatter drop persisted across the same KHG unit between 03 and 09 Sep with no revegetation signal (E7), consistent with sustained subsurface combustion." |
| "Arson is likely" | "Environmental conditions alone do not account for the ignition timing (E4, E9); a land-management ignition hypothesis carries support 61." |
| "Confirmed burn area: 240 ha" | "Estimated burn extent 240 ha from dNBR composite (E15); cloud gaps on 04–05 Sep limit confidence." |
| "High risk operator" | *(no equivalent — do not produce this)* |

## Entity handling

Organisations may be named **only** as a factual location attribute, sourced
from a government or GFW attribute lookup, with the non-attribution caveat
attached. An entity name may never appear in a hypothesis label, a support
score rationale, an executive summary sentence that also contains a causal
verb, or anything the Context/OSINT agent produced from open-web search.

## Check before finishing

- [ ] Every claim carries an evidence ID that exists.
- [ ] No causal verb has a named entity as its subject.
- [ ] Inferred things are labelled inferred; estimated things labelled
      estimated.
- [ ] Limitations are present and specific to this event, not boilerplate.
- [ ] The human-decision framing survives — nothing reads as a verdict.
