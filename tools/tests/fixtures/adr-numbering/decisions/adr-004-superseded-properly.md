# ADR-004: Retire a decision the way SCHEMA asks for
Status: superseded by [[adr-005-replacement]]
Date: 2026-08-16

## Context
The negative control for the supersede-pointer check: a retired decision whose
pointer names an ADR that exists. `wiki/SCHEMA.md` says ADRs are append-only
and that a decision is changed by writing a new ADR that supersedes it, which
is exactly what happened here.

## Decision
Keep this page in the fixture that trips the numbering checks, not in the clean
one, so the same wiki proves the checks fire and proves they stay quiet.

## Consequences (including what we gave up)
Nothing here exercises a supersede *cycle*; the check reads one pointer at a
time and does not walk the chain. See [[decisions/adr-001-example]].
