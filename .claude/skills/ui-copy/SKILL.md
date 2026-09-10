---
name: ui-copy
description: Rules for any text a user of the console will see. Load before writing or editing JSX text, labels, placeholders, error messages, fixture strings, evidence descriptions, report copy, or an agent prompt whose output is displayed. The one hard rule is no em-dashes; this file says what to write instead and where UI text comes from.
---

# Console copy

Owner's call, 2026-09-10: **text a user sees never contains an em-dash.**
Not in JSX, not in a fixture, not in an API error message, not in a string the
pipeline writes into an artifact, and not in what the analysis model returns.

This is a house style, not a grammar preference. Em-dash-heavy copy reads as
machine-written, and the console's credibility rests on every sentence
sounding like something an auditor would put their name to. The
`evidence-framing` skill governs *what* a sentence may claim; this one governs
how it is punctuated.

## The rule

- No U+2014 (`—`) anywhere in user-facing text.
- No double hyphen (`--`) standing in for one.
- An en-dash (U+2013, `–`) is allowed **only** inside a numeric or date range
  (`03–09 Sep`, `2–98 %`). Never as a clause break.
- A hyphen (`-`) is a hyphen: `pre-event`, `sub-surface`, `false-colour`.

## What to write instead

| You were about to write | Write |
|---|---|
| `Scope ready — 3,610 events in range` | `Scope ready. 3,610 events in range.` |
| `computed offline — the API serves the artifact` | `computed offline, so the API serves the artifact` |
| `Sentinel-1 — radar` | `Sentinel-1 · Radar` or `Sentinel-1 (radar)` |
| `H1 — Environmental fire-weather conditions` | `H1: Environmental fire-weather conditions` |
| `{value === null ? '—' : value}` | `{value === null ? 'n/a' : value}` |
| `Limited — cloud gaps 04–05 Sep` | `Limited by cloud gaps on 04–05 Sep` |

The pattern: an em-dash is almost always joining two things that are either
two sentences (use a full stop), a label and its value (use a colon or the
middle dot the evidence drawer already uses), or an aside (use a comma or cut
the aside). A placeholder for a missing value is a word, never a dash glyph;
a dash reads as "nothing here" when the honest message is "not available",
which is a finding.

## Where UI text comes from

Five places. Check the one you are editing and the ones downstream of it.

1. **`frontend/src/`**: JSX text, `aria-label`s, `placeholder`s, `title`s,
   constant label maps, and everything under `api/fixtures/`. Fixtures count:
   they are what the demo shows.
2. **Backend responses**: error `message`s, `reason` strings such as the
   imagery-unavailable text in `backend/app/audit_events.py`, and any field a
   component renders verbatim.
3. **Committed artifacts**: `backend/app/data/*.json.gz` and `events.json`.
   These are written by `data_pipeline/enrich_*.py` and `export_*.py`, so the
   string to fix is in the pipeline, and the artifact is regenerated (the
   `audit-artifact` skill says how). A `source` attribution or `limitations`
   sentence in a pipeline module is UI text.
4. **Static assets under `frontend/public/`**: `imagery/manifest.json`
   `description`s and `limitations` come from
   `data_pipeline/imagery/process_api.py`.
5. **Model output**: `backend/app/analysis_provider.py` builds the prompt and
   validates the reply. Claude uses em-dashes freely unless told not to. Two
   guards, both needed: the prompt's output rules state "no em-dashes; use a
   full stop, comma or colon", and the validator normalises any that arrive
   (`—` surrounded by spaces becomes `. ` or `, ` by position; a bare `—`
   becomes `: `) before the text is stored, so a model that ignores the
   instruction still cannot put one on screen.

## Check before finishing

Until #194 lands a lint rule, the check is a grep. Run it over what you
touched, and over the artifact if you regenerated one:

```bash
grep -rn $'—' frontend/src backend/app data_pipeline --include='*.ts' --include='*.tsx' --include='*.py' --include='*.json' | grep -v '/tests/'
for f in backend/app/data/*.json.gz; do printf '%s: ' "$f"; gzip -dc "$f" | grep -o $'—' | wc -l; done
```

Both should print nothing (or zeros) for the files you changed. The
pre-existing occurrences are tracked in #194; do not add to them, and do not
fix unrelated ones in a PR about something else.

- [ ] No `—` or `--` in any string a user can see, including fixtures.
- [ ] Every en-dash is inside a range.
- [ ] Missing values render as a word, not a dash.
- [ ] If you touched the analysis prompt, the reply is normalised, not just asked nicely.
- [ ] Rewritten sentences still read as sentences. Deleting the dash and leaving the two halves jammed together is worse than the dash.

## Related

- `evidence-framing`: what a sentence about a fire event may and may not say.
- `audit-artifact`: regenerating a committed artifact after a pipeline string changes.
