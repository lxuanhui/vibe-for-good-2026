---
name: decision-log
description: Record a decision in docs/decision-log.md. Load whenever opening a pull request or creating an issue, and whenever a choice is made that someone could later re-litigate — an approach rejected, a service switched on, a platform limitation discovered, a previous entry reversed. Covers what earns an entry versus what is noise, the entry format, how to annotate a reversal, and the cost row that a new AWS service also needs.
---

# Recording decisions

Two people build this repo, each driving their own Claude sessions, neither
watching the other work. The decision log is the only thing that stops the
same argument being had twice, or — worse — being had once and then silently
reversed by an agent who never knew it happened.

That has already cost this project real time. `main` carried two opposite
answers to "what does the console open on" within two days, because #126 and
#131 were built in parallel by different sessions and neither log entry
existed yet when the second one started.

## The rule

**Every pull request and every issue: check whether there is a decision to
record.** The check is not optional. The *entry* is — most changes do not
contain a decision, and a log with an entry for every typo fix stops being
read, which defeats the point.

### What earns an entry

Ask: *would someone six commits from now waste time re-deriving this, or
undo it without knowing why?* If yes, write it.

- An approach that was **tried and rejected** — this is the most valuable
  kind, and the one most often lost. Include what actually went wrong.
- A **platform limitation** discovered the hard way (an API cap, a silent
  failure mode, a tool that lies about success).
- A **service switched on** — see the cost rule below.
- A **deliberate deviation** from the canonical spec, or from a previous
  entry.
- A **reversal** of anything already in the log.
- A number that will be quoted later — a benchmark, a compression figure, a
  measured cost — with how it was measured.

### What does not

Renames, formatting, dependency bumps Renovate made, a bug fixed the obvious
way, anything the code and its comments already explain. If a PR has no
entry, that is normal; say so in one line in the PR body rather than leaving
the reader wondering whether it was forgotten.

### Issues

An issue records a decision when it *closes off* an option — "we are not
doing X, because Y" — or when investigating it produced a finding worth
keeping even though nothing was built. An issue that merely describes work to
do needs no entry; the issue itself is the record.

## The format

Newest first, at the top of `docs/decision-log.md`, under the intro:

```markdown
---

## YYYY-MM-DD - A sentence that says what was decided

**Status:** done - PR #<n>        (or: implemented, <path> / superseded by ...)

**Decision.** What is now true, in the present tense.

**Why.** The reasoning, including the constraint that forced it.

**Rejected: <the alternative>.** What it was, and the specific reason it
lost. One of these per serious alternative.

**Open.** Anything deliberately left unsettled, with the issue number.
```

Write it for the other person, who has none of your context. "Chose DynamoDB"
tells them nothing; "chose DynamoDB because Lambda served later calls from a
different warm container, so process-local state 404'd" tells them why the
next person should not swap it back for a dict.

Add the entry **in the same pull request as the change**. A decision that
lives only in a PR description is not findable later, and one added in a
follow-up PR usually never arrives.

## Reversing an earlier entry

**Annotate the old entry; never delete it, and never leave it reading as
current.** A log that confidently states something that stopped being true is
worse than no log. Add a line directly under the old entry's heading:

```markdown
> **Reversed 2026-09-09 by PR #131.** The console lands scope-first now; see
> the entry of that date for why.
```

The original stays, because *what was tried and abandoned* is the half of the
log that saves the most time.

## If the change switches on an AWS service

DynamoDB and S3 are authorised (2026-09-09), so a new table or bucket does
not need a fresh service-selection argument. It does need two things in the
same PR:

1. A log entry covering the **design** — key shape, what is stored, what is
   deliberately not stored, what it costs at scale.
2. A row in [`docs/infra.md`](../../../docs/infra.md) with the service, why it
   is there, and its cost.

Serverless stays the default, and **anything always-on still needs
justification before it is switched on** — that constraint was not relaxed.

## Related

- `branch-and-pr` — how work starts and lands; it points here for the
  recording step. Do not duplicate its branch or CI rules into a log entry.
- `docs/README.md` — what belongs in `docs/` versus a README versus a skill.
