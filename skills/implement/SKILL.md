---
name: implement
description: Execute a plan task-by-task with TDD, dispatching each task to a
  fresh subagent. Use whenever a plan with unchecked tasks exists and the user
  says "implement", "continue", or "execute the plan".
---

# Implement

ENTRY: `artifacts/plans/<slug>.md` with Status: ready or in-progress.
EXIT: all tasks checked, repo green, plan Status: done. Then hand off to
`review` — do not self-certify.

## Per-task loop (dispatch to a FRESH subagent per task)

The subagent receives ONLY: the task block, linked wiki pages, and repo access.
Not the conversation. Subagent instructions:

1. RED: write the test from the task. Run it. It MUST fail.
   If it passes immediately, the test is wrong — rewrite it.
2. GREEN: write the minimum code to pass. Run the full test suite.
3. REFACTOR: only with all tests green.
4. Report back: diff summary + test output. Parent marks the checkbox.

## Enforcement (hard rules)

- Implementation code written before its failing test → DELETE the
  implementation and restart the task at RED.
- 3 consecutive failed attempts on one task → STOP. Do not brute-force.
  Write findings into the plan and escalate to the user (likely a plan or
  architecture problem).

## Stack conventions (this repo)

- TypeScript/NestJS: strict mode, no `any`; DI via constructor; tests with
  the repo's existing runner — match existing spec file patterns.
- Go: table-driven tests; errors wrapped with `fmt.Errorf("...: %w", err)`;
  no panics in library code.
- Match surrounding code style over personal preference, always.
