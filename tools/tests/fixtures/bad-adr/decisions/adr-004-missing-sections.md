# ADR-004: Record the context and stop there
Status: accepted
Date: 2026-08-16

## Context
The positive control for the ADR heading check. The file name, the status, and
the date are all conformant with the [[SCHEMA]] ADR template, and `## Context`
is present, but `## Decision` and `## Consequences` are missing — so the page
records a situation and never records what was decided about it.

That is the failure mode the check exists to catch: an ADR that reads like a
note. See [[decisions/adr-001-example]] for the conformant shape.
