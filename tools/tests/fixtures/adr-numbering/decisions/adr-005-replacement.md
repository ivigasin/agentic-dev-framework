# ADR-005: Replace ADR-004
Status: accepted
Date: 2026-08-17

## Context
The target of the one valid supersede pointer in this fixture. It exists so
that [[decisions/adr-004-superseded-properly]] can be retired without leaving
the record pointing at nothing.

## Decision
Carry the next unused number rather than reusing 004, so that both halves of
the chain stay citeable.

## Consequences (including what we gave up)
The fixture's numbers run 001, 002, 002, 003, 004, 005 — dense apart from the
collision, so gaps are asserted elsewhere. See [[decisions/adr-001-example]].
