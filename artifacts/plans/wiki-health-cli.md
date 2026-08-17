# Plan: wiki-health CLI

Spec: artifacts/specs/wiki-health-cli.md
Status: in-progress

## Orientation (every subagent reads this section first)

You are building a deterministic wiki health-checker for this repo. It replaces
`skills/wiki-lint/`, a model-invoked skill, with Python code.

**Wiki pages to read for context: none.** `wiki/concepts/`, `wiki/decisions/`,
and `wiki/projects/` are empty — this is the repo's first feature. The binding
contract is `wiki/SCHEMA.md`; read it for any task touching a check.

### Fixed decisions — do not relitigate

- **Python 3 stdlib only.** No pip, no venv, no pytest, no third-party imports.
  Tests use `unittest`.
- **Layout.** The spec fixes the invocation as `python3 tools/wiki-health.py`.
  A hyphenated filename is not importable, so:
  - `tools/wiki-health.py` — thin entrypoint. Adds its own directory to
    `sys.path`, then `from wiki_health.cli import main; sys.exit(main())`.
  - `tools/wiki_health/` — the actual package (importable by tests).
  - `tools/tests/` — unittest files and fixture wikis.
- **Test command** (run from repo root, and the only command any task should
  use to verify): `python3 -m unittest discover -s tools/tests -t tools`
- **Fuzzy-match threshold** (Task 15): `difflib.SequenceMatcher(None, a, b).ratio()
  >= 0.75`, AND exactly one candidate at or above it. Otherwise report unfixed.
  Define as a module constant `LINK_FIX_MIN_RATIO = 0.75`.
- **Fixtures, never the live wiki.** No test may read or write the repo's real
  `wiki/` directory. Every test passes `--path` to a fixture.
- **Fixed findings do not gate the exit code.** Spec criterion 15: fixed items
  appear "as fixed, not as findings". `model.Report.summary` counts them in
  their severity bucket for reporting; the CLI's threshold logic (Task 13) must
  exclude `fixed=True` findings when deciding exit 0 vs 1. A `--fix` run that
  repairs everything exits 0.

### Severity table (authoritative — checks must match exactly)

| Check | Criterion | Severity |
|---|---|---|
| Broken link | 6 | error |
| Orphan page | 7 | warn |
| Index drift / >2 hops | 8 | error |
| Directory >40 pages, no INDEX.md | 9 | warn |
| Concept missing H1 | 10 | error |
| Concept missing required heading | 10 | warn |
| ADR shape/filename/Status/Date | 11 | error |
| Duplicate ADR number | 12 | error |
| Unresolved `superseded by` | 13 | error |
| Non-kebab-case filename | 14 | warn |

---

## Task 1: Scaffold package, entrypoint, and argument parsing

- Files: `tools/wiki-health.py`, `tools/wiki_health/__init__.py`,
  `tools/wiki_health/cli.py`, `tools/tests/__init__.py`,
  `tools/tests/test_cli.py`
- Test first: `tools/tests/test_cli.py` — `"unknown flag exits 2"`,
  `"--help exits 0"`, `"--path pointing at a missing directory exits 2"`.
  Invoke via `subprocess.run([sys.executable, "tools/wiki-health.py", ...])`
  from the repo root so the entrypoint itself is under test.
- Context: spec criteria 3, 5. No wiki pages.
- Details: `argparse` with flags `--path` (default `wiki` relative to repo
  root), `--json`, `--strict`, `--fix`, `--dry-run`. `main()` returns an int
  exit code; argparse errors must surface as **2**, not argparse's default of 2
  by accident — set `exit_on_error` handling explicitly or catch `SystemExit`
  and normalize. For now `main()` returns 0 for any valid invocation.
- Done when: the three tests pass and `python3 tools/wiki-health.py --help`
  prints usage listing all five flags.
- [x] completed — `main()` returns int, normalizes argparse `SystemExit` to 2;
  `EXIT_OK/EXIT_FINDINGS/EXIT_TOOL_ERROR` constants; `--path` defaults to
  repo-anchored `wiki/`, path errors go to stderr so stdout stays JSON-clean.

## Task 2: Finding model and JSON report

- Files: `tools/wiki_health/model.py`, `tools/tests/test_model.py`
- Test first: `tools/tests/test_model.py` — `"finding serializes to json with
  required keys"`, `"report carries schemaVersion"`, `"json is stable across
  runs"` (sort findings by `(path, line, check)` and assert byte-identical
  output across two constructions).
- Context: spec criteria 2, 4. No wiki pages.
- Details: `Severity` (str enum: `error`, `warn`), `Finding` dataclass with
  fields `check`, `severity`, `path`, `line` (int or None), `message`, and
  `fixed` (bool, default False). `Report` holds `findings` plus
  `schemaVersion = 1` and a `to_json()` producing
  `{"schemaVersion": 1, "findings": [...], "summary": {"error": N, "warn": N,
  "fixed": N}}`. Paths in output are relative to the checked wiki root.
- Done when: tests pass; `to_json()` output is deterministic.
- [x] completed — `Finding` frozen; sort key extended to a *total* order
  `(path, line, check, severity, message, fixed)` so JSON is byte-identical;
  `entries()` is the one canonical-order accessor (Task 3 must call it, not
  re-sort); `schemaVersion` is a class attribute, not a field.

## Task 3: Human-readable renderer

- Files: `tools/wiki_health/report.py`, `tools/tests/test_report.py`
- Test first: `tools/tests/test_report.py` — `"findings grouped by severity"`,
  `"line reference rendered as path:line"`, `"finding without line omits colon"`,
  `"clean report says no findings"`.
- Context: spec criterion 1. Reads `tools/wiki_health/model.py` from Task 2.
- Details: errors printed before warnings, each as `path:line  [check]  message`
  (omit `:line` when line is None). Ends with a one-line summary count. Plain
  text, no color codes — output is read in terminals and CI logs alike.
- Done when: tests pass.
- [x] completed — `render()` filters `entries()` and never sorts (locked by a
  test), so text and JSON can't diverge. `format_location/format_entry/
  format_summary` exported for reuse by Tasks 13 and 16 (`--dry-run` output).
  Fixed findings render with a `(fixed)` marker. No-ANSI test guards CI logs.

## Task 4: Page discovery, wikilink parsing, and the clean fixture

- Files: `tools/wiki_health/pages.py`, `tools/tests/test_pages.py`,
  `tools/tests/fixtures/clean/` (a small valid wiki: `INDEX.md`, `SCHEMA.md`,
  `log.md`, `concepts/alpha.md`, `decisions/adr-001-example.md`,
  `projects/demo.md`, all mutually linked and schema-conformant)
- Test first: `tools/tests/test_pages.py` — `"discovers every markdown page"`,
  `"parses bare wikilink"`, `"parses directory-qualified wikilink"`,
  `"records link line numbers"`, `"ignores wikilinks inside fenced code blocks"`.
- Context: `wiki/SCHEMA.md` (page templates, the two link forms). Mirror the
  templates exactly when writing the fixture.
- Details: `Page` holds `path`, `rel_path`, `name` (stem), `lines`, `headings`,
  `links` (list of `(target, line_no)`), `h1`. Link regex matches `[[target]]`
  including `[[decisions/adr-003]]`. Skip fenced ``` blocks so documentation of
  link syntax is not treated as links. `discover(root)` returns all `*.md`
  under root recursively.
- Done when: tests pass and the clean fixture is fully schema-conformant —
  later tasks assume it produces **zero findings**.
- [x] completed — `Page` frozen; `headings` keep their `#` markers verbatim so
  Tasks 9/10 can prefix-match SCHEMA's parentheticals. Fenced blocks suppress
  **headings as well as links**, so SCHEMA.md's own templates stay inert.
  `links` are unresolved `(target, line_no)` pairs — resolution is Task 5's job.
  `TestCleanFixtureShape` asserts the zero-findings guarantee directly, so a
  later fixture edit fails here rather than mysteriously in Tasks 5–12.

## Task 5: Check — broken links

- Files: `tools/wiki_health/checks/__init__.py`,
  `tools/wiki_health/checks/structural.py`, `tools/tests/test_broken_links.py`,
  `tools/tests/fixtures/broken-links/` (clean fixture + one page with
  `[[does-not-exist]]`)
- Test first: `tools/tests/test_broken_links.py` — `"unresolved target is an
  error"`, `"bare name resolves against any directory"`, `"directory-qualified
  name resolves"`, `"clean fixture yields no broken-link findings"`.
- Context: spec criterion 6; `wiki/SCHEMA.md`.
- Details: resolution order — exact `rel_path` match without extension, then
  unique stem match anywhere in the wiki. Ambiguous stems (same name in two
  directories) are themselves an `error` with a distinct message.
- Done when: tests pass.
- [x] completed — convention for Tasks 6–12: `@check("id")` decorator stamps
  `fn.check_id` and registers into `ALL_CHECKS`; signature is
  `fn(pages, root) -> list[Finding]`. `checks.run_all(pages, root)` is what
  Task 13 wires in. New check modules must be imported ABOVE the
  `ALL_CHECKS = tuple(_REGISTRY)` line. `LinkIndex`/`Resolution` are exported
  for reuse by Tasks 6 and 7 — do not rebuild link resolution.
  A qualified `[[projects/alpha]]` deliberately does NOT fall back to
  `concepts/alpha.md`; silently retargeting would hide the stale link.

## Task 6: Check — orphan pages

- Files: `tools/wiki_health/checks/structural.py` (extend),
  `tools/tests/test_orphans.py`, `tools/tests/fixtures/orphan/`
- Test first: `tools/tests/test_orphans.py` — `"page with no inbound links is a
  warn"`, `"INDEX SCHEMA and log are exempt"`, `"clean fixture yields no
  orphans"`.
- Context: spec criterion 7.
- Details: build inbound-link counts from all resolved links. Exempt roots:
  `INDEX.md`, `SCHEMA.md`, `log.md` at the wiki root.
- Done when: tests pass.
- [x] completed — reuses `LinkIndex`; only *resolved* links count as inbound, so
  a rename surfaces as both a broken link and an orphan rather than masking
  itself. Self-links excluded. Exemption is by exact root `rel_path`, so a
  `concepts/INDEX.md` is an ordinary node and can itself be reported orphaned —
  consistent with Task 7 treating directory indexes as hop nodes.

## Task 7: Check — index drift (2-hop reachability)

- Files: `tools/wiki_health/checks/structural.py` (extend),
  `tools/tests/test_index_drift.py`, `tools/tests/fixtures/index-drift/`
  (one page 3 hops from INDEX.md, plus an INDEX entry pointing at a deleted file)
- Test first: `tools/tests/test_index_drift.py` — `"page beyond two hops is an
  error"`, `"index entry pointing at missing file is an error"`, `"page at
  exactly two hops passes"`, `"clean fixture yields no drift"`.
- Context: spec criterion 8; `wiki/SCHEMA.md` rule 2.
- Details: BFS from `INDEX.md` following resolved links, depth ≤ 2. Directory
  `INDEX.md` files count as hop nodes like any other page.
- Done when: tests pass.
- [x] completed — `hop_depths(pages, index=None)` does a FULL BFS (not truncated
  at 2) so messages can say "is 3 hops"; exported for Task 14's auto-fix.
  Two arms under one id: depth violations, and stale/ambiguous root-index
  entries. The stale arm is scoped to the ROOT `INDEX.md` only — otherwise
  every broken link would double as index drift. Missing root `INDEX.md`
  yields one finding, not one per page.

## Task 8: Check — directory scale

- Files: `tools/wiki_health/checks/structural.py` (extend),
  `tools/tests/test_scale.py`, `tools/tests/fixtures/scale/` (a directory with
  41 generated stub pages and no `INDEX.md`)
- Test first: `tools/tests/test_scale.py` — `"directory over forty pages without
  index is a warn"`, `"same directory with an INDEX.md passes"`.
- Context: spec criterion 9; `wiki/SCHEMA.md` rule 2.
- Details: threshold is a named constant `MAX_DIR_PAGES = 40`; the finding
  message quotes SCHEMA rule 2. Generate the 41 stubs with a small loop in the
  fixture-creation step rather than hand-writing them.
- Done when: tests pass.
- [x] completed — chose **tempfile generation over a committed fixture**: 41
  near-identical stubs are unreadable, and suppressing orphan/index-drift would
  need 41 INDEX entries maintained forever. `TestNoIncidentalFindings` asserts
  `run_all` over the generated wiki yields exactly `["directory-scale"]`.
  Counts per DIRECTORY, not subtree (rule 2's repair is a directory INDEX.md).
  **`Finding.path` is a directory here, not a page** — the only such check;
  wiki root serializes as `"."`. Tasks 13/20 can rely on that.

## Task 9: Check — concept page conformance

- Files: `tools/wiki_health/checks/schema.py`, `tools/tests/test_concepts.py`,
  `tools/tests/fixtures/bad-concept/`
- Test first: `tools/tests/test_concepts.py` — `"missing H1 is an error"`,
  `"missing required heading is a warn"`, `"conformant concept page passes"`.
- Context: spec criterion 10; `wiki/SCHEMA.md` concept template.
- Details: required headings `## What it is`, `## How we use it`,
  `## Related:`, `## Sources:` — match on heading prefix, since SCHEMA's
  `## How we use it (project-specific!)` carries a parenthetical.
- Done when: tests pass.
- [x] completed — TWO check ids (`concept-missing-h1` error,
  `concept-missing-heading` warn), not one, so Task 20's once-each assertion
  holds. One finding per page per check (message names all missing sections).
  Shared helpers for Tasks 10–12: `FRAMEWORK_FILENAMES`/`is_framework_page`
  (basename match, so `concepts/INDEX.md` is exempt — Task 12 must use these),
  `typed_pages(pages, dir)`, `missing_headings(page, required)`, `has_h1`.
  Concept scope is RECURSIVE (`concepts/sub/x.md` counts).

## Task 10: Check — ADR page conformance

- Files: `tools/wiki_health/checks/schema.py` (extend),
  `tools/tests/test_adr.py`, `tools/tests/fixtures/bad-adr/`
- Test first: `tools/tests/test_adr.py` — `"filename not matching adr-NNN-slug
  is an error"`, `"missing Status line is an error"`, `"unparseable Date is an
  error"`, `"missing Context Decision or Consequences heading is an error"`,
  `"conformant ADR passes"`.
- Context: spec criterion 11; `wiki/SCHEMA.md` ADR template.
- Details: filename regex `^adr-(\d{3})-[a-z0-9]+(-[a-z0-9]+)*\.md$`. `Status:`
  must be `accepted` or `superseded by [[adr-MMM]]`. `Date:` parsed with
  `datetime.strptime(..., "%Y-%m-%d")`. Headings: `## Context`, `## Decision`,
  `## Consequences` (prefix match — SCHEMA's has a parenthetical).
- Done when: tests pass.
- [x] completed — FOUR ids: `adr-bad-filename`, `adr-bad-status`,
  `adr-bad-date`, `adr-missing-heading`. A shared id would let a dead check
  stay invisible to Task 20's once-each assertion. New shared helper
  `labelled_line(page, label)` → `(line_no, value)`, fence-aware.
  **`Status:` is case-sensitive and exact** because Task 11 re-parses the
  supersede pointer out of that string — flagged for review as a judgment call.
  Date is `strptime`-parsed, so `2026-02-30` is rejected. Badly-named ADRs are
  still body-validated, so a rename can't smuggle a page out of validation.

## Task 11: Check — ADR numbering and supersede pointers

- Files: `tools/wiki_health/checks/schema.py` (extend),
  `tools/tests/test_adr_numbering.py`, `tools/tests/fixtures/adr-numbering/`
  (two ADRs numbered 002; one ADR superseded by a nonexistent adr-999)
- Test first: `tools/tests/test_adr_numbering.py` — `"duplicate ADR number is an
  error"`, `"gaps in sequence are not reported"`, `"superseded pointer to
  missing ADR is an error"`, `"valid supersede chain passes"`.
- Context: spec criteria 12, 13; `wiki/SCHEMA.md` ("ADRs are append-only").
- Done when: tests pass.
- [x] completed — `adr-duplicate-number`, `adr-superseded-missing`. A duplicate
  group of N yields N−1 findings on later-sorting pages, so a two-ADR clash
  yields exactly one (keeps Task 20's once-each assertion viable). Supersede
  pointers matched by ADR **number**, not wikilink resolution — the two
  diverge in both directions. Capture group added to the existing
  `ADR_SUPERSEDED_RE` so validation and extraction can't drift.
  Overlap with `broken-link` **accepted** (Task 7 precedent): a pointer to a
  never-written ADR is intrinsically also an unresolvable link.

## Task 12: Check — kebab-case filenames

- Files: `tools/wiki_health/checks/schema.py` (extend),
  `tools/tests/test_filenames.py`, `tools/tests/fixtures/bad-filename/`
  (contains `Some_Page.md`)
- Test first: `tools/tests/test_filenames.py` — `"non kebab-case filename is a
  warn"`, `"INDEX.md SCHEMA.md and log.md are exempt"`, `"kebab-case passes"`.
- Context: spec criterion 14; `wiki/SCHEMA.md` `<kebab-name>` convention.
- Details: the three uppercase framework files are exempt by name.
- Done when: tests pass.
- [x] completed — **skips `decisions/` entirely**, handing it to
  `adr-bad-filename`. Justified by containment, and the containment is
  *asserted* on five name shapes rather than assumed: both regexes derive from
  `ADR_SLUG_PATTERN`, so any name failing kebab-case necessarily fails the ADR
  pattern too. Deliberately the opposite call from Task 11's accepted overlap
  (there the checks diverge in both directions; here one strictly contains the
  other). Exemption is exact-name, so `concepts/Index.md` IS reported.
  Registry closes at **13 unique check ids**.

## Task 13: Wire checks into the CLI and set exit codes

- Files: `tools/wiki_health/cli.py` (extend), `tools/tests/test_exit_codes.py`
- Test first: `tools/tests/test_exit_codes.py` — `"clean fixture exits 0"`,
  `"fixture with errors exits 1"`, `"fixture with only warns exits 0"`,
  `"fixture with only warns and --strict exits 1"`, `"--json emits parseable
  json and nothing else on stdout"`, `"--json on a dirty fixture still exits 1"`.
- Context: spec criteria 1–5. This is the task that makes the tool usable.
- Details: run every check, collect findings, render human text or JSON. With
  `--json`, **nothing** but JSON may reach stdout — send any diagnostics to
  stderr. Exit 1 when any `error` exists, or any `warn` exists under `--strict`.
- Done when: all six tests pass, and running
  `python3 tools/wiki-health.py --path wiki` against the repo's real (empty)
  wiki completes without crashing. Record its output in the task notes; a
  finding count of zero is not required, only that it does not error.
- [x] completed — real wiki: `No findings.`, exit 0. `exit_code_for(report,
  strict)` is a pure function that skips `fixed=True`, so Tasks 14–16 get
  correct exit codes without touching threshold logic. `build_report(path)`
  extracted as the read-only pipeline for fix-mode to reuse.
  Discovery wrapped in `(OSError, UnicodeDecodeError)` → exit 2: without it an
  unreadable file tracebacks to exit 1, indistinguishable from "wiki unhealthy"
  and violating criterion 3. `--fix`/`--dry-run` inert but emit a stderr notice
  rather than silently no-op'ing.

## Task 14: Auto-fix — index drift

- Files: `tools/wiki_health/fixes.py`, `tools/tests/test_fix_index.py`
- Test first: `tools/tests/test_fix_index.py` — `"missing page is added to the
  correct INDEX section"`, `"entry for a deleted file is removed"`, `"fixed
  items are reported as fixed not as findings"`, `"original fixture is
  untouched"` (copy fixture to a temp dir with `shutil.copytree`, operate on the
  copy, assert the source directory hash is unchanged).
- Context: spec criteria 15, 27.
- Details: section is chosen by the page's directory — `concepts/` → `##
  Concepts`, `decisions/` → `## Decisions (ADRs)`, `projects/` → `## Projects`,
  matching the real `wiki/INDEX.md`. If the expected section heading is absent,
  report rather than invent it.
- Done when: tests pass.
- [x] completed — **the dry-run seam is the write seam**:
  `plan_fixes(pages, root, findings)` is filesystem-pure, `apply_plan(plan)` is
  the ONLY writer, `run_fixes(..., dry_run)` chooses. One code path, so a fix
  pass physically cannot write. `@fix(<check id>)` registry mirrors `@check`.
  Passes do NOT declare what they fixed — `FixPlan.settle()` re-runs the full
  check suite over the hypothetical post-fix wiki and diffs, so a repair that
  doesn't clear its check can't be reported as fixed. Diff matches on
  `(check, path, message)` ignoring `line`, since deletions shift lines.
  Three guards on stale-entry deletion: list entries only, only when no link on
  the line resolves, never an ambiguous link.

## Task 15: Auto-fix — broken links, threshold-gated

- Files: `tools/wiki_health/fixes.py` (extend),
  `tools/tests/test_fix_links.py`
- Test first: `tools/tests/test_fix_links.py` — `"single close match above
  threshold is rewritten"`, `"two candidates above threshold are left unfixed"`,
  `"match below threshold is left unfixed"`, `"unfixed cases remain as
  findings"`, `"original fixture is untouched"`.
- Context: spec criterion 16. **Read the threshold decision in Orientation.**
- Details: `LINK_FIX_MIN_RATIO = 0.75` using
  `difflib.SequenceMatcher(None, target, candidate_stem).ratio()`. Rewrite only
  when exactly one candidate meets it. This is the riskiest behavior in the
  tool: when in doubt, report. Rewrite must preserve the rest of the line
  verbatim — replace only the text inside `[[ ]]`.
- Done when: tests pass, and the threshold lives in exactly one named constant.
- [x] completed — `_sole_candidate` collects ALL pages ≥ threshold and returns
  one only when `len == 1`; no argmax anywhere. Killer test uses *different*
  scores (0.909 vs 0.800, both above) — passes under "closest wins", fails
  here. Threshold uniqueness enforced by TOKENIZING the module and asserting
  the `0.75` number token appears once (prose about it isn't a false positive).
  Target compared **as written**, so `[[concepts/alpah]]` is reported, not
  repaired — stripping the directory would let a wrong directory be silently
  retargeted, exactly what criterion 16 warns against.
  **⚠ REVIEW THIS:** registration order changed so `fix_broken_links` runs
  BEFORE `fix_index_drift`, so a typo'd index entry is repaired (keeping its
  prose) rather than deleted and re-added bare. General rule now in the module
  docstring: edit-passes precede remove-passes.

## Task 16: Fix-mode plumbing — log.md, read-only default, --dry-run

- Files: `tools/wiki_health/fixes.py` (extend), `tools/wiki_health/cli.py`
  (extend), `tools/tests/test_fix_mode.py`
- Test first: `tools/tests/test_fix_mode.py` — `"a run without --fix writes
  nothing at all"` (snapshot every file mtime and content hash before and
  after), `"--fix appends exactly one line to log.md"`, `"--fix never rewrites
  existing log lines"`, `"--fix --dry-run writes nothing but reports intended
  changes"`.
- Context: spec criteria 17, 18, 19; `wiki/SCHEMA.md` rule 5 (append-only log).
- Details: log line format follows the existing convention in
  `skills/finish/SKILL.md:24` — `YYYY-MM-DD | wiki-health | fixed: N | errors: N
  | warns: N`. Read-only is the default and must be provable, hence the
  snapshot test.
- Done when: tests pass. The no-write test is the single most important test in
  this plan — CI and pre-commit safety rest on it.
- [x] completed — every safety property **mutation-tested**, not merely green:
  `if args.fix:`→`if True:`, double log append, log rewrite, dry-run calling
  `apply_plan`, `exit_code_for` not skipping `fixed`, stray stdout print — each
  mutation killed its test. Append-only asserted at BYTE level
  (`after.startswith(before)`); `splitlines()` would let a CRLF rewrite pass.
  No-write test also asserts exit 1, since a crash-on-startup writes nothing
  too. **Missing `log.md` → warn on stderr, never create**: no check reports a
  missing log, so stderr is the only channel that keeps a modified wiki from
  going unrecorded. `--dry-run` without `--fix` is an argument error (exit 2),
  not a no-op — the flag alone requests a mode that doesn't exist.

## Task 17: Rewire the framework — remove wiki-lint

- Files: delete `skills/wiki-lint/` (directory); edit `CLAUDE.md` (line 30),
  `skills/INDEX.md` (line 13, the `wiki-lint` table row), `README.md` (line 23)
- Test first: `tools/tests/test_no_wiki_lint_references.py` — `"no file in the
  repo references wiki-lint"`. Walk the repo from the root, skipping `.git/`,
  `artifacts/` (specs and plans legitimately discuss the removal) and this test
  file itself; assert no remaining match for `wiki-lint` or `wiki_lint`.
- Context: spec criteria 20, 21, 22, 24, 25.
- Details: `CLAUDE.md:30` currently reads "**Model-invoked skills**: finish,
  wiki-lint." — leave `finish` as the sole model-invoked skill. `README.md:23`
  reads "`wiki-lint` keeps the graph healthy." — replace with a sentence naming
  the CLI and its invocation. `.claude/skills` is a symlink to `skills/`, so
  deleting the source directory is sufficient; do not edit through the symlink.
- Done when: the test passes and `grep -rn "wiki-lint" .` returns hits only
  under `artifacts/`.
- [ ] completed

## Task 18: Rewire finish/SKILL.md to invoke the CLI

- Files: `skills/finish/SKILL.md` (step 6, currently line 26)
- Test first: `tools/tests/test_finish_wiring.py` — `"finish invokes the CLI by
  its exact command string"` (assert `skills/finish/SKILL.md` contains
  `python3 tools/wiki-health.py`), `"finish no longer references the skill"`.
- Context: spec criterion 23. Read `skills/finish/SKILL.md` in full first —
  match its numbered-step voice.
- Details: replace step 6 with an instruction to run
  `python3 tools/wiki-health.py --json`, parse the result, fix what it reports,
  and re-run to confirm zero errors. State that a non-zero `error` count blocks
  the finish skill's EXIT condition. Keep it to 2–3 lines; SKILL.md files in
  this repo are terse by design.
- Done when: both tests pass.
- [ ] completed


## Task 19: PostToolUse hook for automatic wiki checking

- Files: `.claude/hooks/wiki-health-check.sh`, `.claude/settings.json`,
  `README.md` (document the hook under Setup)
- Test first: `tools/tests/test_hook.py` — `"hook script is executable"`,
  `"settings.json declares a PostToolUse hook matching Write and Edit"`
  (parse the JSON, assert structure — do not regex it), `"hook script runs the
  CLI in read-only mode"` (assert the script contains no `--fix`).
- Context: spec open question 4, resolved yes. Read `.claude/hooks/session-start.sh`
  first and match its shell style and shebang.
- Details: **`PostToolUse`, not `PreToolUse`** — the check must run *after* a
  write lands, or it inspects stale state. Matcher `Write|Edit`. The script
  exits 0 when the edited path is outside `wiki/`, so non-wiki work is
  unaffected. It runs the CLI **read-only** (never `--fix`) and emits findings
  for the agent to act on. It must not block on `warn`.
- Done when: tests pass and editing a file under `wiki/` in a live session
  surfaces the CLI's findings.
- [ ] completed

## Task 20: End-to-end verification

- Files: `tools/tests/test_end_to_end.py`, `README.md` (usage section)
- Test first: `tools/tests/test_end_to_end.py` — `"clean fixture end to end
  exits 0 with empty findings"`, `"kitchen-sink fixture surfaces one finding per
  check"` (a fixture violating all ten checks at once; assert every check id
  appears exactly once — this is what proves no check silently stopped firing).
- Context: spec criteria 26, 27.
- Details: also document usage in `README.md`: the four flags, the three exit
  codes, and the test command. Confirm the full suite passes from the repo root:
  `python3 -m unittest discover -s tools/tests -t tools`.
- Done when: entire suite green, and the kitchen-sink fixture exercises all ten
  checks in the Orientation severity table.
- [x] completed — **the severity table's "ten checks" is stale; the registry
  closed at 13.** Kitchen sink is generated in a tempfile (same reasoning as
  Task 8) and derives its page count from `MAX_DIR_PAGES`.
  "Exactly once" is unsatisfiable — three intrinsic overlaps, one of them
  previously unrecorded: **an orphan page is necessarily also index-drift**,
  since a page nothing links to can't be BFS-reached from INDEX.md. So the
  assertion is the exact SET of `(check id, path)` pairs — 16 findings over 13
  ids — plus a guard that the expected keys equal
  `{c.check_id for c in checks.ALL_CHECKS}`, so a 14th check fails until
  represented. Verified by 5 mutations (dead check, added check, over-reporting
  check, flipped severity, emptied exemptions) — all killed.
  README documents **five** flags; the plan said four.

## Task 21: git pre-commit gate for wiki health

Added 2026-08-16 after Task 20. Ships **alongside** Task 19, not instead of it:
`PostToolUse` catches agent damage mid-session; this catches anyone's damage —
including manual edits — at the commit boundary. Full rationale in
`~/.claude/plans/translate-the-explanation-to-recursive-dove.md`.

- Files: `githooks/pre-commit` (extend — it exists and `core.hooksPath=githooks`,
  so it is live), `tools/tests/test_pre_commit_hook.py`, `README.md`
- Test first: `tools/tests/test_pre_commit_hook.py` — static: `"hook is
  executable"`, `"hook never passes --fix"`, `"hook uses checkout-index"`.
  Integration (throwaway git repo in `tempfile`, `core.hooksPath` set):
  `"clean staged wiki commits"`, `"staged error is rejected"`,
  `"ALLOW_WIKI_UNHEALTHY=1 overrides"`, `"non-wiki commit passes while wiki is
  broken"`, `"breakage staged but fixed in worktree is still rejected"`,
  `"breakage in worktree but not staged is allowed"`, `"warning-only wiki
  commits"`.
- Context: spec criterion 3 (exit codes) and open question 4; `githooks/pre-commit`;
  `.claude/hooks/session-start.sh` for shell style.
- Details:
  - **Checks STAGED content, not the working tree.** Materialize the whole
    `wiki/` from the index — `git ls-files wiki/ | git checkout-index
    --prefix="$tmp/" --stdin` — then `--path "$tmp/wiki"`. Whole graph, not just
    the diff: orphans and 2-hop reachability are whole-graph properties.
    `trap 'rm -rf "$tmp"' EXIT` for cleanup.
  - Skip entirely when the commit touches no `wiki/` path.
  - Branch on the CLI's exit code, never on parsed output: 0 allow, 1 block
    unless `ALLOW_WIKI_UNHEALTHY=1`, 2 block with a distinct "checker itself
    failed" message.
  - **Never `--fix`** — a commit hook that edits files would stage changes the
    user never reviewed.
  - Restructure the existing governance branch so `ALLOW_GOVERNANCE=1` FALLS
    THROUGH to the wiki gate instead of `exit 0`; otherwise a commit touching
    both governance files and `wiki/` skips the wiki check entirely. Also make
    its control flow explicit — line 16's `[[ ... ]] && exit 0` + `exit 1` only
    works because `set -e` catches the failed `&&` list.
- Done when: tests pass; live check rejects a staged `[[nonexistent-page]]` and
  allows it under `ALLOW_WIKI_UNHEALTHY=1`.
- [ ] completed — **RED phase done; implementation BLOCKED on
  `Edit/Write(./githooks/**)` deny.** `tools/tests/test_pre_commit_hook.py`
  (14 tests) is written and validated against a scratchpad reference hook:
  14/14 green when implemented to spec, and 5 mutations each killed by the
  intended test. 5 of the 14 are currently RED for the right reason; the other
  9 pass vacuously today and become load-bearing once the gate lands.
  Landing also needs `ALLOW_GOVERNANCE=1 git commit ...`.

  Notes for whoever writes the hook:
  1. Use `cd "$(git rev-parse --show-toplevel)"`, NOT `$(dirname "$0")` — with
     `core.hooksPath` set, `$0`'s directory is the hooks dir, not the worktree
     being committed.
  2. **Unresolved:** is exit 2 overridable by `ALLOW_WIKI_UNHEALTHY=1`? Task 21
     didn't say. The tests pin "no" — exit 2 means *unverified*, not
     *unhealthy*. Argue with that test explicitly if you disagree; don't
     quietly weaken it.
  3. `--prefix="$tmp/"` needs the trailing slash, and the `wiki/`-scope skip
     must come BEFORE the pipeline so an empty `git ls-files` is never piped
     under `pipefail`.
  4. Untested edge: repo with unborn HEAD. Existing hook has the same gap.
  5. `README.md` is still owed by this task.

---

## BLOCKER — Tasks 17, 18, 19 gated on permissions (2026-08-16)

`.claude/settings.json` gained a `permissions.deny` list mid-implementation:

```
Edit/Write(./CLAUDE.md), Edit/Write(./.claude/**),
Edit/Write(./skills/**), Edit/Write(./githooks/**)
```

That denies every file the rewiring phase must change:

| Task | Blocked file | Status |
|---|---|---|
| 17 | `CLAUDE.md`, `skills/INDEX.md`, delete `skills/wiki-lint/` | blocked (README.md is writable) |
| 18 | `skills/finish/SKILL.md` | blocked — tests written and RED |
| 19 | `.claude/hooks/wiki-health-check.sh`, `.claude/settings.json` | blocked |

Not routed around with Bash `rm`/`sed`: a deny entry is the user's decision.
The suite is RED by exactly 3 tests in `tools/tests/test_finish_wiring.py`
until Task 18's edit lands. Those failures are EXPECTED, not a regression.

Task 18's replacement text for `skills/finish/SKILL.md` line 26, ready to apply
verbatim:

```
6. Run `python3 tools/wiki-health.py --json` and parse the report. Repair every
   finding (`--fix` handles index drift and unambiguous broken links), then
   re-run. A non-zero `summary.error` blocks EXIT — this step is not done
   until that count is zero.
```

Resolution needs one of: the user lifts the deny for these paths, or applies
the edits by hand.

## Deferred to `finish`

Three ADRs should be written when this task closes (spec Constraints notes they
are ADR-worthy):

1. Replacing a model-invoked skill with deterministic code — and the general
   rule it implies about which checks belong in code vs. inference.
2. Dropping contradiction-aging and speculation-drift, leaving them unowned.
3. Fuzzy link repair: the 0.75 threshold and the report-over-guess principle.
