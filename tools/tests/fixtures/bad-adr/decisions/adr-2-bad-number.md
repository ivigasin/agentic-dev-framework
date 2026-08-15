# ADR-2: Number an ADR with fewer than three digits
Status: accepted
Date: 2026-08-16

## Context
The positive control for the ADR filename check. Everything inside this page
follows the ADR template in [[SCHEMA]]; only the file name is wrong — `adr-2-`
where the template requires `adr-NNN-` with exactly three digits.

## Decision
Keep the body fully conformant, so this page yields an `adr-bad-filename` error
and nothing else and a test can assert the count rather than the presence.

## Consequences (including what we gave up)
A reader has to open the file to see the defect, since the content looks
correct. See [[decisions/adr-001-example]] for the conformant shape.
