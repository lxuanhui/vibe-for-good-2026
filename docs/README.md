# docs/

Project memory. What was decided, why, and what state things are actually in
— the things that are true about this project but not visible by reading the
code.

| File | Holds |
|---|---|
| [`decision-log.md`](decision-log.md) | Dated decisions with their reasoning, including the ones that were reversed and the approaches that failed |
| [`environments.md`](environments.md) | Where it's deployed, under whose account, live URLs, what CI needs |
| [`infra.md`](infra.md) | Every AWS service switched on, why, and what it actually costs |

## What goes where

This is not the only documentation, and duplicating the others is worse than
not writing anything — a stale copy is read as current.

- **How to run or change a thing** → the README next to it (`infra/README.md`,
  `data_pipeline/README.md`, root `README.md`).
- **Rules an agent must follow** → `.claude/skills/`.
- **Orientation for a new session** → `CLAUDE.md`.
- **Why we chose this over that, and what we already tried** → here.

The test: if someone would otherwise re-litigate a settled decision, or repeat
a debugging session that already happened, it belongs in `decision-log.md`.

## Keeping it current

Add an entry when a decision is made, not when it is remembered. Each entry:
what was decided, why, what was rejected and why, and its current status.
Record failed approaches — knowing that DynamoDB state locking is a dead end
saves the next person the same afternoon.

Prepend new entries so the most recent is at the top.
