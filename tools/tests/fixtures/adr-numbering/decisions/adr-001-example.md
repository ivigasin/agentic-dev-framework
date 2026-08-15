# ADR-001: Keep one hand-written fixture that is correct by construction
Status: accepted
Date: 2026-08-16

## Context
Every check in the wiki-health CLI needs a negative control: a wiki that is
known-good, so that a finding against it is evidence of a broken check. See
[[alpha]] for the concept-page half of that control.

## Decision
Keep this fixture small — six pages — and schema-conformant, and assert in
every check's tests that it yields zero findings.

## Consequences (including what we gave up)
The fixture must be updated whenever SCHEMA.md changes, which is deliberate
friction: a schema change that nothing notices is a schema change nothing
enforces. We gave up the convenience of a generated fixture, because a
generator would encode the same assumptions the checks do and hide their bugs.
See [[projects/demo]] for how the fixture is exercised end to end.
