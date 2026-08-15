---
name: finish
description: Close out a completed task by compiling what was learned into the
  wiki. Model-invoked — run this yourself whenever a review returns APPROVED,
  without waiting to be asked.
---

# Finish

ENTRY: review verdict APPROVED.
EXIT: wiki updated, `wiki/log.md` appended, plan archived.

## Process

1. Extract from the completed work:
   - New concepts introduced → create/update `wiki/concepts/<name>.md`
   - Decisions made along the way (tradeoffs chosen, approaches rejected)
     → new ADR in `wiki/decisions/` (format in wiki/SCHEMA.md)
   - Gotchas/surprises → note on the relevant existing concept page
2. MERGE into existing pages; never duplicate. If a page contradicts the new
   knowledge, flag the contradiction explicitly rather than silently overwriting.
3. Update `wiki/INDEX.md` if new pages were created.
4. Append one line to `wiki/log.md`:
   `YYYY-MM-DD | finish | <slug> | pages touched: [[a]], [[b]]`
5. Move the plan to `artifacts/plans/done/`.
6. If 3+ wiki pages were touched, invoke `wiki-lint`.

## Anti-patterns

- Dumping the whole diff into the wiki. The wiki stores understanding,
  not code. Link to commits instead.
- Creating a new page when an existing one covers the concept.
