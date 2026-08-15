# ADR-003: Point at an ADR nobody ever wrote
Status: superseded by [[adr-999]]
Date: 2026-08-16

## Context
The positive control for the supersede-pointer check. The `Status:` line is one
of the two forms the [[SCHEMA]] ADR template allows, so it is well-formed; what
it names does not exist. That is the failure mode of an append-only record —
the decision reads as retired, and nothing says what replaced it.

## Decision
Keep this page conformant apart from the dangling pointer, so it yields an
`adr-superseded-missing` error and — deliberately — the `broken-link` error
that any unresolvable wikilink earns.

## Consequences (including what we gave up)
The two findings overlap by construction: a pointer to a missing ADR is always
also a link to a missing page. Their messages are worded to stay
distinguishable. See [[decisions/adr-001-example]].
