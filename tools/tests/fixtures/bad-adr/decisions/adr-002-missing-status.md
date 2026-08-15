# ADR-002: Omit the Status line entirely
Date: 2026-08-16

## Context
The positive control for the ADR status check. The file name, the date, and all
three required sections of the [[SCHEMA]] ADR template are present; the
`Status:` line is not, so nothing says whether this decision still stands.

## Decision
Leave the rest of the page conformant, so this page yields an `adr-bad-status`
error and nothing else.

## Consequences (including what we gave up)
The fixture cannot also exercise a malformed `Status:` value here; that case is
asserted in a temporary directory instead. See [[decisions/adr-001-example]].
