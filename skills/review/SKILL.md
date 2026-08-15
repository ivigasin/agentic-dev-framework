---
name: review
description: Dual-axis review of a completed implementation — against the plan
  AND against code standards. Use whenever implement finishes, or the user
  asks "review this" / "is this done?".
---

# Review

ENTRY: plan Status: done, diff available.
EXIT: review section appended to the plan with verdict:
APPROVED | CHANGES-REQUIRED (with numbered findings by severity).

## Axis 1 — Spec/plan compliance

- Walk acceptance criteria in the spec one by one: point to the test or code
  that satisfies each. No pointer → CHANGES-REQUIRED.
- Detect scope creep: code not traceable to any task.

## Axis 2 — Standards

- Tests: do they assert behavior, or just mirror the implementation?
- Errors: swallowed exceptions, missing error paths, unwrapped Go errors.
- Contradictions with `wiki/decisions/` ADRs → automatic CHANGES-REQUIRED
  (either fix the code or explicitly propose superseding the ADR).

## Severity

- CRITICAL: blocks merge (broken acceptance criterion, ADR violation, data loss risk)
- MAJOR: fix before finish skill runs
- MINOR: note it; may proceed

## Anti-patterns

- Rubber-stamping: a review with zero findings on a non-trivial diff is
  suspicious — re-read with fresh eyes before approving.
- Reviewing your own conversation memory instead of the actual diff.
