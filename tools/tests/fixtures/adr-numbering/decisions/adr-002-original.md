# ADR-002: Hold the number 002 legitimately
Status: accepted
Date: 2026-08-16

## Context
Half of the positive control for the duplicate-number check. This page was
written first and owns number 002; the collision is created by its neighbour,
not by this page. Everything else about it follows the [[SCHEMA]] ADR template.

## Decision
Keep this page conformant in every respect, so the duplicate-number finding
lands on the page that took the number second and names this one as the holder.

## Consequences (including what we gave up)
A reader of the report has to open both files to decide which one to renumber;
the check only reports the collision. See [[decisions/adr-001-example]].
