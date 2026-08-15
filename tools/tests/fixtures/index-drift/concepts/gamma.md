# Gamma
> The one drifted page in this fixture: three hops from the index.

## What it is
A concept page reachable only as INDEX.md → [[alpha]] → [[beta]] → here. Every
link on the path resolves, so nothing is broken; the page is simply too deep
for [[SCHEMA]] rule 2.

## How we use it (project-specific!)
As the positive control for the index-drift check: this fixture must yield
exactly one hop-depth finding, and it must name this page.

## Related: [[decisions/adr-001-example]], [[demo]]

## Sources: raw/clean-fixture-notes.md
