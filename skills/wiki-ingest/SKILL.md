---
name: wiki-ingest
description: Compile raw sources (files in raw/, or a URL) into the wiki.
  Use whenever the user drops sources into raw/, shares a URL/article to
  remember, or says "ingest", "add to the wiki", "remember this".
---

# Wiki Ingest

ENTRY: unprocessed source in `raw/` or URL provided.
EXIT: source compiled into wiki pages, `raw/manifest.md` updated.

## Process

1. Check `raw/manifest.md` — skip already-ingested sources (delta only).
2. Read the source fully. Identify: concepts, entities, claims, decisions.
3. For each concept: merge into the existing page or create one per
   `wiki/SCHEMA.md`. Cross-link with [[wiki-links]] aggressively — links are
   the retrieval mechanism.
4. Tag claims by confidence: `^[extracted]` (stated in source),
   `^[inferred]` (your synthesis), `^[ambiguous]`.
5. Flag contradictions with existing pages in a `## Contradictions` section —
   never silently overwrite.
6. Append to `raw/manifest.md`:
   `YYYY-MM-DD | <source> | pages: [[a]], [[b]] | status: ingested`
7. Update `wiki/INDEX.md` for new pages. Expect one source to touch 5–15 pages.

## Anti-patterns

- Copy-pasting source text into pages. Compile: summarize, restructure, link.
- Creating orphan pages with no inbound links from the index or other pages.
