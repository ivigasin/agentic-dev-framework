# Gamma
> The one unreachable page in the orphan fixture.

## What it is
A concept page shaped exactly like [[alpha]] and conformant with [[SCHEMA]],
whose only defect is that nothing in this wiki links to it.

## How we use it (project-specific!)
As the positive control for the orphan check: this fixture must yield exactly
one orphan finding, and it must name this page. Its own outbound links resolve,
so the broken-link check stays silent here — an orphan is about inbound links.

## Related: [[decisions/adr-001-example]], [[demo]]

## Sources: raw/clean-fixture-notes.md
