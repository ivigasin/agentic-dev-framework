---
name: wiki-lint
description: Health check for the wiki. Model-invoked — run yourself after any
  operation touching 3+ wiki pages, or when the user asks about wiki quality.
---

# Wiki Lint

ENTRY: wiki exists.
EXIT: lint report (in conversation) + critical fixes applied.

## Checks

1. **Broken links**: [[links]] pointing to non-existent pages.
2. **Orphans**: pages with zero inbound links (unreachable by graph walk).
3. **Index drift**: pages missing from `wiki/INDEX.md` or its sub-indexes.
4. **Contradictions**: pages with unresolved `## Contradictions` sections older
   than 30 days (check wiki/log.md dates).
5. **Speculation drift**: pages where `^[inferred]` claims outnumber
   `^[extracted]` — flag for source-backing.
6. **Scale**: if any directory exceeds ~40 pages, propose a sub-index
   (directory-level INDEX.md) to keep graph walks shallow.

## Fix policy

- Broken links, index drift: fix immediately, note in report.
- Orphans, contradictions, speculation: report only — human decides.
