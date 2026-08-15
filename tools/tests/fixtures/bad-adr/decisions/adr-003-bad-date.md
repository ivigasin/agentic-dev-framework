# ADR-003: Date an ADR with something that is not a date
Status: accepted
Date: 2026-13-45

## Context
The positive control for the ADR date check. The file name, the status, and all
three required sections of the [[SCHEMA]] ADR template are present; the `Date:`
value names a thirteenth month and a forty-fifth day, so it is not a date.

## Decision
Leave the rest of the page conformant, so this page yields an `adr-bad-date`
error and nothing else.

## Consequences (including what we gave up)
A wrong-but-parseable date would pass this check; the check only proves a date
was written, not that it is the right one. See [[decisions/adr-001-example]].
