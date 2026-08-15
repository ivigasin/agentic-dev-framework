---
name: grill
description: Stress-test a feature idea or request before any design or code.
  Use whenever the user proposes a new feature, a significant change, or says
  "build X" without an approved spec — even if the request sounds clear.
---

# Grill

ENTRY: a feature request or idea with no spec in `artifacts/specs/`.
EXIT: an approved spec file `artifacts/specs/<slug>.md` explicitly confirmed
by the user. Do NOT proceed to plan/implement without confirmation.

## Process

1. Read `wiki/INDEX.md`; follow links to concepts and past decisions (ADRs)
   relevant to this request. Cite anything that contradicts the request.
2. Ask questions in batches of max 3, prioritized by:
   - What breaks if we're wrong? (risk)
   - What did the user NOT say? (hidden assumptions)
   - What existing decision does this touch? (from wiki/decisions/)
3. Forbidden: proposing a solution before at least one round of questions.
4. When intent is clear, write the spec:

```md
# Spec: <title>
Status: draft | approved
## Problem
## Non-goals
## Constraints (link wiki decisions: [[decisions/adr-xxx]])
## Acceptance criteria (testable, numbered)
## Open questions
```

5. Present the spec, ask for approval. On approval, set Status: approved.

## Anti-patterns (hard stops)

- Writing code in this skill: delete it and return to questioning.
- Marking your own spec approved without the user's explicit "yes".
