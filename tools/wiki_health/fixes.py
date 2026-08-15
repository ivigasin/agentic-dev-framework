"""Repairs — the only code in this package that writes to a wiki.

Everything else here reads. That asymmetry is the safety property the tool rests
on (spec criterion 18): the CLI runs read-only by default, in CI and in a
PostToolUse hook, so a write must be impossible to reach by accident. Hence the
shape below.

## The seam

    plan = plan_fixes(pages, root, findings)   # pure: computes, never writes
    apply_plan(plan)                           # the ONLY writer in the package

`run_fixes(..., dry_run=True)` is the first half alone. A dry run and a real run
therefore execute *identical* logic and produce an identical `FixPlan`; the only
difference is whether `apply_plan` is called. There is no second code path to
keep in sync, and no way for a pass to sneak a write in — a pass never receives
a path or a file handle, only the `FixPlan` it stages text into.

## Writing a fix pass (Task 16)

    @fix(SOME_CHECK)
    def fix_something(plan):
        lines = plan.lines_for("concepts/alpha.md")
        ...
        plan.stage_lines("concepts/alpha.md", lines, ["what changed"])

- Register with `@fix(<check id>)`, mirroring `checks.check`. Passes run in
  registration order, and each sees the previous pass's staged text through
  `plan.lines_for` / `plan.current_pages()`, so two passes editing the same file
  compose instead of clobbering.
- New passes go **above** the `ALL_FIXES = tuple(_REGISTRY)` line at the bottom
  of this file, or they never run.
- Registration order is load-bearing where two passes disagree about the same
  line. `fix_broken_links` runs before `fix_index_drift` because a repair
  preserves more than a deletion: a typo'd index entry gets its target corrected
  rather than dropped and re-added without its description. A pass that *edits*
  should generally precede one that *removes*.
- `stage_lines` takes the file's complete intended contents. An append (Task
  16's `log.md` line) is expressed as the original lines plus the new one, which
  is what keeps the append-only guarantee checkable: the prefix is carried over
  verbatim rather than regenerated.

## What counts as fixed

A pass does not declare what it repaired. After every pass has staged its edits,
`FixPlan` re-parses the staged text in memory, re-runs the full check suite over
that hypothetical wiki, and diffs: findings that survive are `remaining`,
findings that vanished come back marked `fixed=True` (criterion 15). Two reasons
to settle it this way rather than have each pass report its own successes:

- A repair that does not actually clear the check cannot be reported as a fix.
- Side effects are caught for free. Adding a page to `INDEX.md` also clears the
  orphan finding for it, and no pass has to know that.

The diff matches on `(check, path, message)` and deliberately ignores `line`:
deleting a stale index entry shifts every line below it, and matching on line
numbers would report the survivors as both fixed and unfixed. `remaining` holds
the *post-fix* findings, so the line numbers a reader sees are the ones in the
file they will open.
"""

import dataclasses
import difflib
import pathlib

from . import checks, pages as pages_module
from .checks import structural
from .checks.structural import (
    BROKEN_LINK,
    EXEMPT_ROOTS,
    INDEX_DRIFT,
    LinkIndex,
    MAX_HOPS,
    ROOT_INDEX,
    hop_depths,
)
from .pages import LINK_RE, MARKDOWN_SUFFIX

# How close a broken `[[target]]` must be to a page's filename stem before the
# link fix will rewrite it, as a `difflib.SequenceMatcher` ratio. The one place
# the number lives; a test tokenizes this module and fails on a second copy.
#
# The value is a judgement, not a measurement, and it is set where it is because
# of what it costs to be wrong in each direction. Too low and the tool rewrites
# a link to a page the author never meant — a silent change of meaning that no
# later check can detect, because the result is a perfectly valid link. Too high
# and the tool reports a typo it could have fixed, which costs a human thirty
# seconds. Those are not symmetric, so the threshold sits high enough that only
# a near-miss qualifies: one or two characters in a short name.
LINK_FIX_MIN_RATIO = 0.75

# Which `## ` heading of `wiki/INDEX.md` a page belongs under, keyed by its
# top-level directory. The headings are copied from the real `wiki/INDEX.md`
# verbatim, including the "(ADRs)" parenthetical, because the fix matches them
# literally: an index using different words is an index this tool does not
# understand, and guessing at the right section is how an auto-fix files a page
# where nobody will look for it. A directory absent from this mapping — or a
# heading absent from the file — is reported, never invented.
INDEX_SECTIONS = {
    "concepts": "## Concepts",
    "decisions": "## Decisions (ADRs)",
    "projects": "## Projects",
}

SECTION_PREFIX = "## "
LIST_MARKERS = ("- ", "* ", "+ ")

_REGISTRY = []


def fix(check_id):
    """Register a function as a fix pass for `check_id`."""

    def decorate(function):
        function.check_id = check_id
        _REGISTRY.append(function)
        return function

    return decorate


@dataclasses.dataclass(frozen=True)
class Edit:
    """One file's complete intended contents, plus why.

    `summaries` is what `--dry-run` prints (Task 16). It accumulates across
    passes, so a file two passes both touched explains both changes.
    """

    rel_path: str
    text: str
    summaries: tuple = ()


def _identity(finding):
    """What makes two findings the same defect across a fix.

    `line` is excluded on purpose — see the module docstring.
    """
    return (finding.check, finding.path, finding.message)


class FixPlan:
    """Staged edits and the findings they settle. Nothing here touches disk.

    Constructed by `plan_fixes`; written out only by `apply_plan`, which is the
    single place in this package that opens a file for writing.
    """

    def __init__(self, root, pages):
        self.root = pathlib.Path(root)
        self.fixed = ()
        self.remaining = ()
        self.written = ()
        self._pages = list(pages)
        self._by_path = {page.rel_path: page for page in self._pages}
        self._staged = {}
        self._summaries = {}

    # -- reading (passes) --------------------------------------------------

    def text_for(self, rel_path):
        """The file's current text — staged if a pass changed it, else on disk.

        None when the wiki has no such page. A pass must handle that rather than
        create the file: `INDEX.md` going missing is a finding for a human, not
        something an auto-fix should paper over by writing a new one.
        """
        if rel_path in self._staged:
            return self._staged[rel_path]
        page = self._by_path.get(rel_path)
        if page is None:
            return None
        return page.path.read_text(encoding="utf-8")

    def lines_for(self, rel_path):
        text = self.text_for(rel_path)
        return None if text is None else text.splitlines()

    def current_pages(self):
        """The page list as it would be after the edits staged so far.

        Re-parsed through `pages.parse`, so a pass sees exactly what the checks
        will see — same fence handling, same link extraction — without the
        staged text ever reaching the filesystem.
        """
        if not self._staged:
            return list(self._pages)
        return [self._reparse(page) for page in self._pages]

    def _reparse(self, page):
        text = self._staged.get(page.rel_path)
        if text is None:
            return page
        lines, headings, links, h1 = pages_module.parse(text)
        return dataclasses.replace(
            page, lines=lines, headings=headings, links=links, h1=h1
        )

    # -- staging (passes) --------------------------------------------------

    def stage(self, rel_path, text, summaries=()):
        self._staged[rel_path] = text
        self._summaries.setdefault(rel_path, []).extend(summaries)

    def stage_lines(self, rel_path, lines, summaries=()):
        """Stage `lines` as the file's contents, keeping its trailing newline.

        Whether a file ends with a newline is not this tool's business to
        change: a fix that flipped it would show up as a diff on every repaired
        file and make the real edit harder to review.
        """
        original = self.text_for(rel_path) or ""
        suffix = "\n" if original.endswith("\n") else ""
        self.stage(rel_path, "\n".join(lines) + suffix, summaries)

    # -- results -----------------------------------------------------------

    @property
    def edits(self):
        """Staged edits in `rel_path` order — stable across runs, like the report."""
        return tuple(
            Edit(
                rel_path=rel_path,
                text=self._staged[rel_path],
                summaries=tuple(self._summaries.get(rel_path, ())),
            )
            for rel_path in sorted(self._staged)
        )

    def findings(self):
        """Everything the report should show: the repairs, then what is left."""
        return list(self.fixed) + list(self.remaining)

    def settle(self, findings):
        """Split `findings` into fixed and remaining by re-checking the result."""
        if not self._staged:
            self.fixed = ()
            self.remaining = tuple(findings)
            return
        after = checks.run_all(self.current_pages(), self.root)
        survived = {_identity(finding) for finding in after}
        self.fixed = tuple(
            dataclasses.replace(finding, fixed=True)
            for finding in findings
            if _identity(finding) not in survived
        )
        self.remaining = tuple(after)


def _link_target(rel_path):
    """`concepts/gamma.md` → `concepts/gamma`, the text that goes in `[[ ]]`."""
    if rel_path.endswith(MARKDOWN_SUFFIX):
        return rel_path[: -len(MARKDOWN_SUFFIX)]
    return rel_path


def _similarity(target, stem):
    """How close a link target is to a filename stem, in `[0, 1]`."""
    return difflib.SequenceMatcher(None, target, stem).ratio()


def _sole_candidate(target, page, pages):
    """The one page `target` plausibly meant, or None — and None is the default.

    *Exactly one* page at or above `LINK_FIX_MIN_RATIO`. Not the closest page,
    not the best of several: one. The distinction is the whole safety property.
    A target that scores 0.91 against one page and 0.80 against another is not a
    typo the tool understands — it is a typo with two readings, and picking the
    higher score would be the tool inventing an intention the author did not
    express. Ambiguous links fall out of the same count for free: two pages
    sharing a stem both score 1.0, so there are two candidates and no fix.

    `page` itself is counted as a candidate but never returned as one. A page
    linking to itself is a link nobody writes on purpose, so whatever the author
    meant, it was not "here". Counting it and then refusing is deliberately more
    conservative than excluding it from the list, which would let a two-way tie
    collapse into a rewrite.

    Comparison is against the filename *stem*, and the target is compared as
    written — so a typo inside a directory-qualified `[[concepts/alpah]]` scores
    far below the threshold and is reported instead. Stripping the directory
    before comparing would repair more links, but it would also let a link whose
    *directory* is wrong be silently retargeted, which is the failure this
    threshold exists to prevent.
    """
    candidates = [
        candidate
        for candidate in pages
        if _similarity(target, candidate.name) >= LINK_FIX_MIN_RATIO
    ]
    if len(candidates) != 1:
        return None
    if candidates[0].rel_path == page.rel_path:
        return None
    return candidates[0]


def _replacement_for(target, page, pages, link_index):
    """The text to put inside `[[ ]]` instead of `target`, or None to leave it.

    Only *broken* links are candidates for repair — a link that resolves is a
    link the author got right, however unlike a filename it happens to look.

    The replacement is directory-qualified, the same call `fix_index_drift`
    makes for new entries: a bare stem resolves today and breaks the day a
    second page takes that name, and a fix that plants a future ambiguity is
    not much of a fix.
    """
    if link_index.resolve(target).is_resolved:
        return None
    candidate = _sole_candidate(target, page, pages)
    if candidate is None:
        return None
    replacement = _link_target(candidate.rel_path)
    return None if replacement == target else replacement


def _link_repairs(page, link_index, pages):
    """`line_no` → `{old target: new target}` for the links to rewrite on `page`.

    Keyed by line so the rewrite can touch exactly the lines carrying a repair
    and leave the rest of the file, including anything inside a fence,
    byte-identical: `page.links` never reports fenced links, so a fenced
    `[[demoo]]` can never appear here even when an identical link elsewhere in
    the file is being repaired.
    """
    repairs = {}
    replacements = {}
    for target, line_no in page.links:
        if target not in replacements:
            replacements[target] = _replacement_for(target, page, pages, link_index)
        replacement = replacements[target]
        if replacement is None:
            continue
        repairs.setdefault(line_no, {})[target] = replacement
    return repairs


def _rewrite_line(line, repairs):
    """Replace only the text inside `[[ ]]`; the rest of the line is untouched.

    Substituting on the match rather than rebuilding the line is what keeps the
    surrounding prose — the em-dash description on an index entry, the other
    links in a `## Related:` list — exactly as it was.
    """

    def substitute(match):
        replacement = repairs.get(match.group(1).strip())
        if replacement is None:
            return match.group(0)
        return f"[[{replacement}]]"

    return LINK_RE.sub(substitute, line)


@fix(BROKEN_LINK)
def fix_broken_links(plan):
    """Repair unambiguous link typos (spec criterion 16).

    Registered *before* the index-drift pass, and the order is load-bearing.
    That pass deletes a root-index list entry whose links all name nothing —
    which a typo does. Repairing first means `- [[alpah]] — the founding
    concept.` keeps its sentence instead of being deleted and re-added bare.
    Every case the link fix declines still reaches the index pass unchanged, so
    running first only ever preserves information.
    """
    pages = plan.current_pages()
    link_index = LinkIndex(pages)
    for page in pages:
        repairs = _link_repairs(page, link_index, pages)
        if not repairs:
            continue
        lines = plan.lines_for(page.rel_path)
        if lines is None:
            continue
        summaries = []
        for line_no in sorted(repairs):
            lines[line_no - 1] = _rewrite_line(lines[line_no - 1], repairs[line_no])
            summaries.extend(
                f"{page.rel_path}:{line_no}: [[{old}]] → [[{new}]]"
                for old, new in sorted(repairs[line_no].items())
            )
        plan.stage_lines(page.rel_path, lines, summaries)


def _section_heading(rel_path):
    """The `## ` heading a page belongs under, or None if there is no rule."""
    parts = pathlib.PurePosixPath(rel_path).parts
    if len(parts) < 2:
        return None
    return INDEX_SECTIONS.get(parts[0])


def _sections(lines):
    """`## heading` → `(heading index, body end)`, both 0-based, end exclusive.

    Fence-aware via `pages.iter_content_lines`, so a heading quoted inside a
    code block is not mistaken for a real section. `body end` is one past the
    last non-blank line of the section, which is where a new entry goes: after
    the existing list, before the blank line separating the next heading.
    """
    headings = [
        (text.strip(), line_no - 1)
        for line_no, text in pages_module.iter_content_lines(lines)
        if text.startswith(SECTION_PREFIX)
    ]
    sections = {}
    for position, (heading, index) in enumerate(headings):
        if position + 1 < len(headings):
            end = headings[position + 1][1]
        else:
            end = len(lines)
        while end > index + 1 and not lines[end - 1].strip():
            end -= 1
        sections[heading] = (index, end)
    return sections


def _is_list_entry(line):
    return line.lstrip().startswith(LIST_MARKERS)


def _stale_entry_lines(index_page, link_index):
    """0-based indices of index lines whose every link names nothing at all.

    Three guards, each of them a case where deleting would destroy information:

    - Only list entries. A stale link inside a sentence takes real prose with it
      if the line goes, so that is reported instead.
    - Only when *no* link on the line resolves. `- [[alpha]] and [[gone]]` is
      still a live entry.
    - Never an *ambiguous* link. It names two pages, not none; the repair is to
      qualify it with a directory, and dropping the line would delete the only
      evidence of what the index meant.
    """
    by_line = {}
    for target, line_no in index_page.links:
        by_line.setdefault(line_no, []).append(target)

    removals = {}
    for line_no, targets in sorted(by_line.items()):
        line = index_page.lines[line_no - 1]
        if not _is_list_entry(line):
            continue
        resolutions = [link_index.resolve(target) for target in targets]
        if any(r.is_resolved or r.is_ambiguous for r in resolutions):
            continue
        removals[line_no - 1] = tuple(targets)
    return removals


def _missing_entries(pages, link_index, sections):
    """`heading` → new entry lines for pages the index cannot reach in time.

    Driven by `hop_depths`, the same BFS the index-drift check reports from, so
    the fix repairs exactly the pages that check names — including unreachable
    ones, which have no depth at all. Pages whose section is unknown or absent
    are skipped and stay findings.
    """
    depths = hop_depths(pages, link_index)
    additions = {}
    for page in pages:
        if page.rel_path in EXEMPT_ROOTS:
            continue
        depth = depths.get(page.rel_path)
        if depth is not None and depth <= MAX_HOPS:
            continue
        heading = _section_heading(page.rel_path)
        if heading is None or heading not in sections:
            continue
        additions.setdefault(heading, []).append(_link_target(page.rel_path))
    return additions


def _rewrite(lines, removals, additions, sections):
    """Apply removals and additions to `lines` in one pass, in file order."""
    inserts = {}
    for heading, targets in additions.items():
        _index, end = sections[heading]
        inserts.setdefault(end, []).extend(f"- [[{target}]]" for target in targets)

    rewritten = []
    for index, line in enumerate(lines):
        rewritten.extend(inserts.pop(index, ()))
        if index in removals:
            continue
        rewritten.append(line)
    for index in sorted(inserts):
        rewritten.extend(inserts[index])
    return rewritten


@fix(INDEX_DRIFT)
def fix_index_drift(plan):
    """Bring `INDEX.md` back in line with the wiki (spec criterion 15).

    Two edits, both to the root index and nothing else: add an entry for every
    page the index no longer reaches within `MAX_HOPS`, and drop every entry
    whose page is gone. A dead link on an *ordinary* page is Task 15's problem —
    the index-drift check scopes its stale-entry arm to the root index for the
    same reason, and widening it here would let this pass delete content it was
    never asked about.

    Entries are written bare — `- [[concepts/gamma]]` — with no description.
    The real index annotates its entries with a human sentence, and an auto-fix
    has nothing true to put there; a generated summary would read like an
    editorial decision nobody made. Directory-qualified, so the new entry cannot
    become ambiguous later when a second page takes the same stem.
    """
    lines = plan.lines_for(ROOT_INDEX)
    if lines is None:
        return

    pages = plan.current_pages()
    index_page = {page.rel_path: page for page in pages}.get(ROOT_INDEX)
    if index_page is None:
        return

    link_index = LinkIndex(pages)
    sections = _sections(lines)
    removals = _stale_entry_lines(index_page, link_index)
    additions = _missing_entries(pages, link_index, sections)
    if not removals and not additions:
        return

    summaries = [
        f"{ROOT_INDEX}: add [[{target}]] under {heading}"
        for heading, targets in sorted(additions.items())
        for target in targets
    ]
    summaries += [
        f"{ROOT_INDEX}: remove stale entry [[{target}]]"
        for targets in removals.values()
        for target in targets
    ]
    plan.stage_lines(
        ROOT_INDEX, _rewrite(lines, removals, additions, sections), summaries
    )


# New fix passes go ABOVE this line: the tuple is frozen here, and a pass
# registered after it would never run.
ALL_FIXES = tuple(_REGISTRY)


def plan_fixes(pages, root, findings=None):
    """Compute every repair without performing any of them.

    Pure with respect to the filesystem: it reads, it never writes. `findings`
    is the read-only report the CLI already built; passing it in keeps the
    fix run and the plain run describing the same wiki.
    """
    if findings is None:
        findings = checks.run_all(pages, root)
    plan = FixPlan(root, pages)
    for fix_pass in ALL_FIXES:
        fix_pass(plan)
    plan.settle(findings)
    return plan


def apply_plan(plan):
    """Write a plan out. **The only function in this package that writes.**

    Returns the `rel_path`s written, in the order they were written, and records
    them on the plan so a caller can report what happened.
    """
    written = []
    for edit in plan.edits:
        path = plan.root / edit.rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(edit.text, encoding="utf-8")
        written.append(edit.rel_path)
    plan.written = tuple(written)
    return plan.written


def run_fixes(pages, root, findings=None, dry_run=False):
    """Plan the repairs, and unless `dry_run`, carry them out."""
    plan = plan_fixes(pages, root, findings)
    if not dry_run:
        apply_plan(plan)
    return plan
