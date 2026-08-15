# Some Page
> A concept page whose only defect is the name of the file it lives in.

## What it is
The positive control for the kebab-case filename check. Everything inside this
page follows the concept template in [[SCHEMA]] exactly — H1, definition, and
all four sections — so any finding against it is a finding about `Some_Page.md`
and nothing else.

## How we use it (project-specific!)
As the one page in this fixture that yields a `filename-case` warning. It is
linked from [[INDEX]] so that it is neither orphaned nor beyond two hops: a
badly named page is still a page in the graph, and the fixture would prove
nothing if the rename were tangled up with a reachability problem.

## Related: [[alpha]], [[decisions/adr-001-example]]

## Sources: raw/clean-fixture-notes.md
