# Spec: wiki-health CLI

Status: approved

## Problem

Wiki health is currently enforced by `skills/wiki-lint/SKILL.md`, a model-invoked
skill. Every check runs as LLM judgment over the file tree, which means the
results are non-deterministic, unavailable to CI, un-testable, and cost tokens
on every invocation. Checks that are purely mechanical — does this `[[link]]`
resolve, is this page reachable from `INDEX.md` — are being paid for as
inference.

Replace it with a deterministic CLI that enforces the `wiki/SCHEMA.md` contract,
serving three consumers from one implementation:

- **CI / pre-commit** — exit code gates the commit.
- **Agents** (`finish`, and any skill that writes to the wiki) — stable JSON.
- **Human at the terminal** — readable, grouped report with `file:line` refs.

`skills/wiki-lint/` is deleted as part of this work; the CLI is its replacement,
not its companion.

## Non-goals

- **Contradiction aging (old wiki-lint check #4) and speculation drift (#5) are
  dropped.** Deliberate: both require judging whether a `^[inferred]` tag is
  *correct*, which deterministic code cannot do. Consequence, stated plainly:
  once `wiki-lint` is deleted, nothing in the framework performs these checks.
  Reintroducing them later means a new spec and probably an LLM pass.
- Not a wiki *authoring* tool. It does not create concepts, ADRs, or projects.
- Not a link *renderer* or static site generator.
- No network access, no API calls, no third-party dependencies.
- Does not police `raw/` — SCHEMA declares it immutable and unstructured.
- Does not validate prose quality, tone, or factual accuracy.

## Constraints

- Enforces the contract in `wiki/SCHEMA.md` — that file is the source of truth
  for page shape, filename conventions, and the three-layer model. If SCHEMA
  changes, the CLI is what must change with it.
- No ADRs exist in `wiki/decisions/` yet, so no prior decision constrains this.
  The choices below (replacement over coexistence; dropping semantic checks;
  fuzzy link repair) are ADR-worthy and should be recorded by `finish`.
- The wiki is currently **empty** — zero concepts, zero ADRs, zero projects.
  All testing must run against committed fixture wikis, not the live one.
- Python 3 standard library only, no `pip install`, no virtualenv. `python3` is
  present (3.14.6). Confirmed.
- Lives under `tools/` in this repo and is invoked as
  `python3 tools/wiki-health.py [args]` from the repo root. Confirmed. Whether
  that path is a single module or a package directory with an entrypoint is a
  planning decision; the invocation string above is what `skills/finish/SKILL.md`
  must contain (criterion 23), so it is fixed here.
- SCHEMA rule 5 (`wiki/log.md` is append-only) binds the tool itself: the CLI
  inherits wiki-lint's obligation to write one log line per lint.

## Acceptance criteria

Numbered, testable. Each maps to a test against a fixture wiki.

### Invocation and output

1. Running `wiki-health` with no arguments checks the wiki at the repo root and
   prints a human-readable report grouped by severity, each finding carrying a
   `path:line` reference where a line number is meaningful.
2. `--json` emits a machine-readable report on stdout and nothing else on
   stdout, so an agent can parse it without stripping preamble. Schema is
   versioned with a top-level `schemaVersion` field.
3. Exit code is `0` when no findings at or above the failure threshold exist,
   `1` when such findings exist, and `2` on tool error (unreadable wiki, bad
   arguments). CI can therefore distinguish "wiki is unhealthy" from "tool
   broke".
4. Every finding has a severity of `error` or `warn`. `--strict` promotes
   `warn` to failure; by default only `error` affects the exit code.
5. `--path <dir>` checks a wiki at an arbitrary location, so fixtures can be
   checked without touching the real wiki.

### Structural checks

6. **Broken links** — every `[[target]]` in any `wiki/**/*.md` resolves to an
   existing page. Resolution handles both bare names (`[[concept-a]]`) and
   directory-qualified names (`[[decisions/adr-003]]`), matching the two forms
   used in SCHEMA. Unresolved targets are `error`.
7. **Orphans** — every page reachable by graph walk from `wiki/INDEX.md`
   is identified; pages with zero inbound links are reported as `warn`.
   `wiki/INDEX.md`, `wiki/SCHEMA.md`, and `wiki/log.md` are exempt roots.
8. **Index drift** — every page under `wiki/` is reachable from `wiki/INDEX.md`
   within 2 link hops (SCHEMA rule 2). Pages beyond 2 hops, and index entries
   pointing at deleted files, are `error`.
9. **Scale** — any directory under `wiki/` holding more than 40 pages without
   its own `INDEX.md` is `warn`, quoting SCHEMA rule 2.

### SCHEMA conformance checks

10. **Concept pages** (`wiki/concepts/*.md`) carry the headings required by
    SCHEMA: `## What it is`, `## How we use it`, `## Related:`, `## Sources:`.
    Missing headings are `warn`; a missing H1 title is `error`.
11. **ADR pages** match filename pattern `adr-NNN-<kebab-slug>.md`, carry a
    `Status:` line of `accepted` or `superseded by [[adr-MMM]]`, a `Date:` line
    parseable as `YYYY-MM-DD`, and the headings `## Context`, `## Decision`,
    `## Consequences`. Violations are `error` — ADRs are the framework's
    audit trail.
12. **ADR numbering** — duplicate `NNN` numbers across `wiki/decisions/` are
    `error`. Gaps in the sequence are not reported; ADRs may be withdrawn.
13. **Superseded ADRs** — a `superseded by [[adr-MMM]]` pointer resolves to an
    existing ADR. Unresolved is `error`.
14. **Filenames** — every page under `wiki/` is kebab-case (SCHEMA's
    `<kebab-name>` convention). Violations are `warn`.

### Auto-fix

15. `--fix` repairs **index drift** by adding missing pages to the correct
    section of `wiki/INDEX.md` and removing entries whose target no longer
    exists. Fixed items appear in the report as fixed, not as findings.
16. `--fix` repairs **broken links** only when exactly one candidate page
    matches above a confidence threshold; ambiguous or low-confidence cases are
    reported unfixed, never guessed. A wrong rewrite silently changes meaning,
    so the tool must prefer reporting to guessing. Threshold — see Open
    questions.
17. `--fix` appends exactly one line to `wiki/log.md` per run, satisfying
    SCHEMA rule 5, and never rewrites existing lines in that file.
18. Without `--fix`, the tool writes **nothing** — no log line, no index edit.
    A read-only default is what makes it safe in CI and pre-commit.
19. `--fix --dry-run` prints what would change and writes nothing.

### Framework rewiring

20. `skills/wiki-lint/` is deleted.
21. `CLAUDE.md:30` no longer lists `wiki-lint` among model-invoked skills.
22. `skills/INDEX.md:13` row for `wiki-lint` is removed.
23. `skills/finish/SKILL.md:26` invokes the CLI instead of the skill, and
    interprets its JSON output.
24. `README.md:23` no longer claims `wiki-lint` keeps the graph healthy.
25. After rewiring, no file in the repo references `wiki-lint` — verified by
    grep as a test.

### Testing

26. Fixture wikis committed under a test directory cover, at minimum: a clean
    wiki (exits 0), each individual check failing in isolation, and a wiki
    where `--fix` resolves index drift and one unambiguous broken link.
27. `--fix` tests operate on a copy of a fixture, asserting the original is
    untouched.

## Open questions

Resolved 2026-08-16: language is Python 3 stdlib-only; the tool lives under
`tools/` and is invoked as `python3 tools/wiki-health.py`. Both moved to
Constraints. Remaining:

1. **Fuzzy-match threshold for criterion 16.** Proposal: normalized edit
   distance ≤ 0.25 *and* exactly one candidate within it, otherwise report.
   This is the riskiest behavior in the tool — worth pinning a number now.
2. **log.md in CI.** Criterion 18 means read-only runs skip the log line, so CI
   never mutates the wiki. That reads SCHEMA rule 5 as "every lint that acts
   logs". If you'd rather every run log unconditionally, CI needs write access
   and a commit step — confirm the narrower reading is right.
3. **Losing checks #4 and #5.** Recorded as a non-goal. Confirm you're content
   for contradiction-aging and speculation-drift to have no owner in the
   framework once `wiki-lint` is gone.
4. **Pre-commit hook.** `.claude/hooks/` exists. Should this task also install a
   hook that runs the CLI, or is wiring it into CI left to you?
