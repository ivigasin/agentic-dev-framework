# Wiki Schema (maintainer contract)

Three layers:
- `raw/` — immutable sources. Never edit, never delete. Inbox for ingestion.
- `wiki/` — compiled knowledge. The ONLY layer agents read for context.
- This file — the rules for writing to wiki/.

## Page types

### Concept page → `wiki/concepts/<kebab-name>.md`
```md
# <Name>
> One-line definition.
## What it is
## How we use it (project-specific!)
## Related: [[concept-a]], [[decisions/adr-003]]
## Sources: raw/<file> or URL
```

### Decision (ADR) → `wiki/decisions/adr-NNN-<slug>.md`
```md
# ADR-NNN: <decision>
Status: accepted | superseded by [[adr-MMM]]
Date: YYYY-MM-DD
## Context
## Decision
## Consequences (including what we gave up)
```
ADRs are append-only. To change a decision, write a new ADR that supersedes.

### Project page → `wiki/projects/<name>.md`
Living overview: current state, links to active plans, key concepts.

## Writing rules

1. Merge, don't duplicate. Search for the concept before creating a page.
2. Every page reachable from `wiki/INDEX.md` within 2 link hops.
   Beyond ~40 pages per directory → add a directory INDEX.md.
3. Confidence tags on claims: `^[extracted]`, `^[inferred]`, `^[ambiguous]`.
4. Contradictions get flagged in a `## Contradictions` section, never
   silently resolved.
5. `wiki/log.md` is append-only: every ingest/finish/lint writes one line.
