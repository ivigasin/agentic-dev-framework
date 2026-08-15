# ADR-002: Take a number that is already taken
Status: accepted
Date: 2026-08-17

## Context
The other half of the positive control for the duplicate-number check.
`wiki/SCHEMA.md` makes ADRs append-only, which only works while the number is
an identity: two ADRs numbered 002 make a supersede pointer at 002 ambiguous
and the record unciteable. See [[decisions/adr-002-original]] for the holder.

## Decision
Keep this page conformant apart from its number, so it yields an
`adr-duplicate-number` error and nothing else.

## Consequences (including what we gave up)
The fixture cannot also show a three-way collision here; that case is asserted
in a temporary directory instead. See [[decisions/adr-001-example]].
