---
name: branch-and-pr
description: How work lands in this repo — typed branches, pull requests, and what must be true before merging. Load BEFORE the first edit of any task that changes a tracked file, and again before merging. Covers branch naming, when CI blocks a merge, what belongs in a commit message, and the checks that are advisory versus binding.
---

# Landing work in this repo

Two people build this, each driving their own Claude sessions. The pull
request is the only place either of them sees what the other's agent did
before it is in the trunk. That is what these rules protect; they are not
ceremony.

**Nothing lands on `main` directly.** Not a typo fix, not a comment, not a
version bump. `main` has no branch protection — the GitHub plan does not
offer it for a private repo, so the API returns 403 on every ruleset call.
Nothing will stop you pushing to `main`. That makes this convention the only
guard there is.

## Before the first edit

Branch first, not after. `git status` on a dirty `main` at the end of a task
is the failure this prevents.

```bash
git checkout main && git pull --ff-only
git checkout -b <type>/<short-kebab-description>
```

| Prefix | For |
|---|---|
| `feat/` | New behaviour a user could notice |
| `fix/` | Correcting behaviour that was already meant to work |
| `refactor/` | Restructuring with no behaviour change |
| `docs/` | Docs, specs, comments, `CLAUDE.md`, skills |
| `chore/` | Config, CI, dependencies, tooling |

Pick the prefix for what the change *is*, not for what prompted it. Adding a
scanner because a dependency broke is `chore/`, not `fix/`.

## The commit message

The repo's convention is a subject line, then prose explaining **why** — what
was rejected as well as what was chosen. Write it for the other person on the
team, who has none of your context. "Bump X to 2.0" tells them nothing; "Bump
X to 2.0; 1.9 resolves the worker URL wrong under Vite's pre-bundler" tells
them why the next bump might break again.

End every commit message with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Opening the PR

The description carries the reasoning a reviewer needs before they can agree
or disagree: what changed, why this approach, what you rejected, what you
verified, and what you deliberately did not do. Anything you could not finish
or chose to leave belongs in it explicitly — a PR that hides an unfinished
edge is worse than one that names it.

## Before merging

Wait for checks. Which workflows run depends on the paths touched:

| Workflow | Runs on | Blocks on |
|---|---|---|
| `CI` | every PR | frontend lint + build, backend ruff + pytest |
| `Security` | every PR, plus weekly | committed secrets (gitleaks, full history), `npm audit` and `pip-audit` for runtime deps, `trivy config` over `infra/` at HIGH/CRITICAL, `ruff --select S` |
| `Infra` | `infra/**`, `backend/**`, or its own file | `terraform plan`; **merging to `main` applies it** |

Three of those deserve specific care:

- **The Terraform plan comment is not decoration.** On an infra PR, merging is
  what deploys. Read the plan before merging; a resource you did not expect to
  change is a reason to stop.
- **A gitleaks finding means rotate first, clean history second.** A secret
  that reached `origin` is compromised whether or not the commit is still
  reachable. Never silence a finding with an allowlist entry without saying in
  the PR why the match is not a real credential.
- **A trivy or SAST finding gets fixed or justified in place**, with an inline
  `# trivy:ignore:<ID>` or `# noqa: <rule>` and the reasoning next to it —
  never by lowering a severity threshold, which silently disables every other
  rule at that level too.

Merge with `--squash --delete-branch`.

## What CI cannot tell you

Every check here is static. `npm run build` proves the frontend *compiles*;
nothing proves it *runs*. This has already cost the team once: a maplibre-gl
major passed every check and the map then rendered nothing in the browser,
because Vite's dependency pre-bundler emitted a broken worker chunk and
MapLibre blocked silently with no console error.

So for any change that touches rendering, the map, or a frontend dependency,
open the app and look at it before merging. If you cannot, say so in the PR
rather than letting green checks imply a verification that did not happen.

## Recording the decision

If the change settles something an agent would otherwise re-litigate — an
approach that was tried and rejected, a limitation of the platform, a
deliberate deviation — add an entry to `docs/decision-log.md` in the same PR,
newest first, with a `**Status:** done · PR #<n>` line. A decision that lives
only in a PR description is not findable six commits later.

If a later change reverses an entry, **annotate the old entry** rather than
leaving it to be read as current. The log is worse than useless when it
confidently states something that stopped being true.
