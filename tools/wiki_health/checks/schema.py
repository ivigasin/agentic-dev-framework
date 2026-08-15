"""Checks on page *shape*: does each page look like the template it claims?

`wiki/SCHEMA.md` gives one template per page type, and the type is declared by
where the file lives — `concepts/`, `decisions/`, `projects/`. So every check
here starts the same way: select the pages of one type, then compare each
against its template. `typed_pages()` and `missing_headings()` exist so that
selection and comparison are written once rather than once per page type.

Two rules the whole module follows:

- **Headings are matched by prefix.** SCHEMA writes `## How we use it
  (project-specific!)` and `## Consequences (including what we gave up)`; the
  parenthetical is commentary, not part of the requirement. `Page.headings`
  keeps the `#` markers verbatim precisely so a prefix match can be made
  level-sensitive: `### What it is` does not satisfy `## What it is`.
- **One finding per page per check.** A page missing three sections is one
  problem to fix, and the message names all three. Findings carry `line=None`:
  the defect is the *absence* of a line, so there is nowhere to point.

Severities come from the plan's table and are not negotiable per-check: a
concept with no H1 is an `error` (nothing can name the page), a concept missing
a section is a `warn` (a gap in a page, not a lie in the graph). Every ADR
defect is an `error`: ADRs are this framework's audit trail, and one that cannot
be numbered, dated, or read for its decision has failed at its only job.

**One check id per distinct defect, not one per page type.** The concept
template yields two ids and the ADR template four, because a shared id hides a
dead check: if `Status:` and `Date:` both reported `adr-nonconformant`, a bug
that stopped the date validation from firing would leave the id present in the
report and the end-to-end "every check id appears exactly once" assertion still
green. Separate ids also separate remedies — a bad file name is fixed by a
rename, a missing section by an edit. `adr-bad-filename` deliberately does not
cover ADR *numbering*: duplicate numbers and unresolved supersede pointers are
graph-level facts about the whole `decisions/` directory and carry their own ids.

Those last two enforce the one sentence in `wiki/SCHEMA.md` that no single page
can satisfy alone — "ADRs are append-only. To change a decision, write a new ADR
that supersedes." An append-only record needs the number to be an identity (so
two ADRs may not share one) and needs every retirement to name a decision that
exists (so `superseded by` may not dangle). Two things they deliberately do not
do: they do not report *gaps*, since a number is an identifier and not a census
and closing a gap would mean renumbering an existing ADR — the one edit
append-only forbids; and they resolve a pointer by **number**, not by wikilink
resolution, because `superseded by [[adr-002]]` asks whether ADR 002 exists,
which is a different question from whether that link finds a page. The usual
case answers both at once, which is why a dangling pointer is also reported as
`broken-link`; that overlap is accepted, on the same grounds as Task 7's, and
the two messages carry different repairs.

`check_filename_case` is the exception to the module's opening sentence: file
names are not a page template, so it walks *every* page rather than one
directory's. It hands `decisions/` to `check_adr_filename` — the opposite call
from the supersede overlap above, and for the opposite reason. There the two
checks answer different questions and diverge in both directions; here one
answer strictly contains the other, since a name that is not kebab-case cannot
match `adr-NNN-<slug>.md` either. Nothing goes unreported, the reader is handed
the stricter of two identical repairs, and one rename does not look like two
problems. Both regexes are built from `ADR_SLUG_PATTERN` so the containment is
a fact about one pattern rather than a coincidence between two.
"""

import datetime
import re

from . import check
from ..model import Finding, Severity
from ..pages import iter_content_lines

CONCEPT_MISSING_H1 = "concept-missing-h1"
CONCEPT_MISSING_HEADING = "concept-missing-heading"
ADR_BAD_FILENAME = "adr-bad-filename"
ADR_BAD_STATUS = "adr-bad-status"
ADR_BAD_DATE = "adr-bad-date"
ADR_MISSING_HEADING = "adr-missing-heading"
ADR_DUPLICATE_NUMBER = "adr-duplicate-number"
ADR_SUPERSEDED_MISSING = "adr-superseded-missing"
FILENAME_CASE = "filename-case"

# Page-type directories, as named in `wiki/SCHEMA.md` "Page types".
CONCEPTS_DIR = "concepts"
DECISIONS_DIR = "decisions"

# The three framework files are not instances of any page template: INDEX.md is
# navigation, SCHEMA.md is the contract, log.md is a ledger. Matched by file
# name rather than by `rel_path`, so a directory `concepts/INDEX.md` — which
# SCHEMA rule 2 asks for once a directory grows — is exempt too.
FRAMEWORK_FILENAMES = frozenset({"INDEX.md", "SCHEMA.md", "log.md"})

# The concept template, `wiki/SCHEMA.md` "Concept page", in document order. The
# order is what the finding message lists, so it reads as the template does.
CONCEPT_HEADINGS = (
    "## What it is",
    "## How we use it",
    "## Related:",
    "## Sources:",
)

# The ADR template, `wiki/SCHEMA.md` "Decision (ADR)", in document order.
ADR_HEADINGS = (
    "## Context",
    "## Decision",
    "## Consequences",
)

# `wiki/SCHEMA.md`: `wiki/decisions/adr-NNN-<slug>.md`. Exactly three digits, so
# ADRs sort lexically in the order they were written, and a lower-case kebab
# slug, so the file name doubles as a link target. Group 1 is the number, left
# capturing for the numbering checks that read it.
ADR_SLUG_PATTERN = r"[a-z0-9]+(?:-[a-z0-9]+)*"
ADR_FILENAME_RE = re.compile(rf"^adr-(\d{{3}})-{ADR_SLUG_PATTERN}\.md$")
ADR_FILENAME_SHAPE = "adr-NNN-<slug>.md"

# `wiki/SCHEMA.md`: `wiki/concepts/<kebab-name>.md`. The same alphabet the ADR
# slug uses, deliberately built from the same pattern — SCHEMA states the
# convention twice and means it once, so the two must not drift apart. Anchored
# whole-name, which is what rejects `some.page.md`: a second dot is neither a
# word separator nor an extension.
KEBAB_FILENAME_RE = re.compile(rf"^{ADR_SLUG_PATTERN}\.md$")
KEBAB_FILENAME_SHAPE = "<kebab-name>.md"

# The two header lines. Matched as `Label:` at the start of a line rather than
# by position, because SCHEMA fixes the labels but nothing fixes how much prose
# an author puts above them.
ADR_STATUS_LABEL = "Status:"
ADR_DATE_LABEL = "Date:"

# `Status: accepted | superseded by [[adr-MMM]]`. Case-sensitive and exact:
# these two strings are a machine-readable state, and the supersede pointer is
# parsed back out of this line, so accepting `Accepted` or `Superseded By`
# would turn that parse into guesswork. The link may carry a slug or a
# `decisions/` prefix, since both forms resolve — whether it resolves to a real
# ADR is a separate check. Group 1 is the superseding ADR's number: the same
# string validates the status and yields the pointer, so the two can never drift.
ADR_STATUS_ACCEPTED = "accepted"
ADR_SUPERSEDED_RE = re.compile(
    rf"^superseded by \[\[(?:{DECISIONS_DIR}/)?adr-(\d{{3}})"
    rf"(?:-{ADR_SLUG_PATTERN})?\]\]$"
)
ADR_STATUS_FORMS = "`accepted` or `superseded by [[adr-MMM]]`"

# `wiki/SCHEMA.md`, under the ADR template. Quoted so the duplicate-number
# finding hands the reader the sentence it is enforcing rather than a rule the
# reader has to go looking for.
SCHEMA_APPEND_ONLY = (
    "ADRs are append-only. To change a decision, write a new ADR that supersedes."
)

# `Date: YYYY-MM-DD`. Parsed, not pattern-matched, so `2026-02-30` is rejected.
ADR_DATE_FORMAT = "%Y-%m-%d"
ADR_DATE_SHAPE = "YYYY-MM-DD"


def basename(page):
    """The page's file name, with no directories: `concepts/a.md` → `a.md`.

    Split off `rel_path` rather than read from `page.path`, so the answer is the
    same POSIX string on every platform, and kept with its `.md` suffix, since
    the file name — extension and all — is what the naming conventions describe.
    """
    return page.rel_path.rsplit("/", 1)[-1]


def is_framework_page(page):
    """True for INDEX.md / SCHEMA.md / log.md, in any directory."""
    return basename(page) in FRAMEWORK_FILENAMES


def is_decision_page(page):
    """True for a page under `decisions/` — an ADR, or a claim to be one.

    The same scope `typed_pages(pages, DECISIONS_DIR)` selects, phrased for one
    page at a time so `check_filename_case` can hand that directory over to
    `check_adr_filename` without rebuilding the selection.
    """
    return page.rel_path.startswith(f"{DECISIONS_DIR}/") and not is_framework_page(page)


def typed_pages(pages, directory):
    """The pages under `directory/` that are instances of a page template.

    Recursive on purpose. SCHEMA puts concept pages flat in `concepts/`, but a
    nested one is still a concept page, and a scope rule that skipped it would
    let a whole subtree escape validation — the one failure mode a linter must
    not have, since it reports health it never measured.
    """
    prefix = f"{directory}/"
    return [
        page
        for page in pages
        if page.rel_path.startswith(prefix) and not is_framework_page(page)
    ]


def missing_headings(page, required):
    """Which of `required` no heading on `page` starts with, in template order."""
    return tuple(
        heading
        for heading in required
        if not any(present.startswith(heading) for present in page.headings)
    )


def labelled_line(page, label):
    """The first `Label: value` line outside a fence, as `(line_no, value)`.

    `(None, None)` when the page has no such line — which the callers turn into
    a finding with no line number, since the defect is the absence of the line.
    Fence-aware for the same reason the parser is: SCHEMA.md shows a
    `Status:` line inside a ``` block, and a page quoting the template has not
    thereby stated its own status.
    """
    for line_no, text in iter_content_lines(page.lines):
        stripped = text.strip()
        if stripped.startswith(label):
            return line_no, stripped[len(label) :].strip()
    return None, None


def adr_number(page):
    """The three-digit number in the page's file name, or None.

    None means the page is not part of the numbered record — either it is not
    named like an ADR at all, in which case `check_adr_filename` has already
    said so, or it lives outside `decisions/`. Either way it cannot collide with
    a number and cannot satisfy a supersede pointer, and reporting it again here
    would make one rename look like several problems.
    """
    match = ADR_FILENAME_RE.match(basename(page))
    return match.group(1) if match else None


def adr_numbers(pages):
    """number → the ADR pages carrying it, each list in `rel_path` order.

    The order is `discover()`'s, which is sorted, so which page of a colliding
    pair is treated as holding the number is the same on every platform and in
    every run — a linter whose finding moved between machines would be unusable.
    """
    numbered = {}
    for page in typed_pages(pages, DECISIONS_DIR):
        number = adr_number(page)
        if number is None:
            continue
        numbered.setdefault(number, []).append(page)
    return numbered


def superseded_number(page):
    """`(line_no, number)` for a `superseded by` status, else `(None, None)`.

    Read back out of the exact string `is_valid_status` accepts, so a status
    this returns a number for is by construction a well-formed one. A missing
    or malformed `Status:` yields no number: that is `check_adr_status`'s
    finding, and claiming the target is missing when what is missing is the
    syntax to name one would point the reader at the wrong repair.
    """
    line_no, value = labelled_line(page, ADR_STATUS_LABEL)
    if value is None:
        return None, None
    match = ADR_SUPERSEDED_RE.match(value)
    if match is None:
        return None, None
    return line_no, match.group(1)


def is_valid_status(value):
    """True for the two states `wiki/SCHEMA.md` defines, and nothing else."""
    return value == ADR_STATUS_ACCEPTED or bool(ADR_SUPERSEDED_RE.match(value))


def is_valid_date(value):
    """True when `value` is a real calendar date in `YYYY-MM-DD` form."""
    try:
        datetime.datetime.strptime(value, ADR_DATE_FORMAT)
    except ValueError:
        return False
    return True


def has_h1(page):
    """True when the page carries a non-empty level-1 heading.

    `Page.h1` is already fence-aware and already stripped of its marker, so a
    template quoted inside a ``` block does not count as naming the page.
    """
    return bool(page.h1 and page.h1.strip())


@check(CONCEPT_MISSING_H1)
def check_concept_h1(pages, root):
    """Every concept page names itself with an H1 (spec criterion 10)."""
    return [
        Finding(
            check=CONCEPT_MISSING_H1,
            severity=Severity.ERROR,
            path=page.rel_path,
            line=None,
            message=(
                f"concept page {page.rel_path} has no H1 — add "
                f"`# <Name>` as its first line (SCHEMA concept template)"
            ),
        )
        for page in typed_pages(pages, CONCEPTS_DIR)
        if not has_h1(page)
    ]


@check(CONCEPT_MISSING_HEADING)
def check_concept_headings(pages, root):
    """Every concept page carries the four template sections (criterion 10)."""
    findings = []
    for page in typed_pages(pages, CONCEPTS_DIR):
        missing = missing_headings(page, CONCEPT_HEADINGS)
        if not missing:
            continue
        findings.append(
            Finding(
                check=CONCEPT_MISSING_HEADING,
                severity=Severity.WARN,
                path=page.rel_path,
                line=None,
                message=(
                    f"concept page {page.rel_path} is missing "
                    f"{', '.join(f'`{h}`' for h in missing)} — "
                    f"see the concept template in SCHEMA.md"
                ),
            )
        )
    return findings


@check(ADR_BAD_FILENAME)
def check_adr_filename(pages, root):
    """Every ADR is named `adr-NNN-<slug>.md` (spec criterion 11).

    Checked on every page under `decisions/`, not only on the ones that look
    close to the pattern: a file put there is a claim to be an ADR, and an
    unrecognisable name is exactly how one drops out of the numbered record.
    """
    return [
        Finding(
            check=ADR_BAD_FILENAME,
            severity=Severity.ERROR,
            path=page.rel_path,
            line=None,
            message=(
                f"ADR {page.rel_path} is not named `{ADR_FILENAME_SHAPE}` — "
                f"the number is exactly three digits and the slug is "
                f"lower-case kebab (SCHEMA ADR template)"
            ),
        )
        for page in typed_pages(pages, DECISIONS_DIR)
        if not ADR_FILENAME_RE.match(basename(page))
    ]


@check(ADR_BAD_STATUS)
def check_adr_status(pages, root):
    """Every ADR declares one of SCHEMA's two statuses (spec criterion 11)."""
    findings = []
    for page in typed_pages(pages, DECISIONS_DIR):
        line_no, value = labelled_line(page, ADR_STATUS_LABEL)
        if value is not None and is_valid_status(value):
            continue
        if line_no is None:
            message = (
                f"ADR {page.rel_path} has no `{ADR_STATUS_LABEL}` line — "
                f"add one reading {ADR_STATUS_FORMS} (SCHEMA ADR template)"
            )
        else:
            message = (
                f"ADR {page.rel_path} has `{ADR_STATUS_LABEL} {value}`, which "
                f"is neither {ADR_STATUS_FORMS} (SCHEMA ADR template)"
            )
        findings.append(
            Finding(
                check=ADR_BAD_STATUS,
                severity=Severity.ERROR,
                path=page.rel_path,
                line=line_no,
                message=message,
            )
        )
    return findings


@check(ADR_BAD_DATE)
def check_adr_date(pages, root):
    """Every ADR carries a parseable `Date:` (spec criterion 11).

    An ADR's date is what orders the decision record when the numbers cannot —
    so a date that does not parse is worth an error even though the wiki reads
    fine without it.
    """
    findings = []
    for page in typed_pages(pages, DECISIONS_DIR):
        line_no, value = labelled_line(page, ADR_DATE_LABEL)
        if value is not None and is_valid_date(value):
            continue
        if line_no is None:
            message = (
                f"ADR {page.rel_path} has no `{ADR_DATE_LABEL}` line — add one "
                f"reading `{ADR_DATE_LABEL} {ADR_DATE_SHAPE}` "
                f"(SCHEMA ADR template)"
            )
        else:
            message = (
                f"ADR {page.rel_path} has `{ADR_DATE_LABEL} {value}`, which is "
                f"not a date in `{ADR_DATE_SHAPE}` form (SCHEMA ADR template)"
            )
        findings.append(
            Finding(
                check=ADR_BAD_DATE,
                severity=Severity.ERROR,
                path=page.rel_path,
                line=line_no,
                message=message,
            )
        )
    return findings


@check(ADR_MISSING_HEADING)
def check_adr_headings(pages, root):
    """Every ADR carries Context, Decision, and Consequences (criterion 11).

    An error rather than the concept template's warn: a concept page missing a
    section is incomplete, but an ADR missing `## Decision` records a situation
    and never records what was decided about it.
    """
    findings = []
    for page in typed_pages(pages, DECISIONS_DIR):
        missing = missing_headings(page, ADR_HEADINGS)
        if not missing:
            continue
        findings.append(
            Finding(
                check=ADR_MISSING_HEADING,
                severity=Severity.ERROR,
                path=page.rel_path,
                line=None,
                message=(
                    f"ADR {page.rel_path} is missing "
                    f"{', '.join(f'`{h}`' for h in missing)} — "
                    f"see the ADR template in SCHEMA.md"
                ),
            )
        )
    return findings


@check(ADR_DUPLICATE_NUMBER)
def check_adr_duplicate_number(pages, root):
    """No two ADRs carry the same number (spec criterion 12).

    Gaps are not a defect and are not reported: 001, 003, 007 is a fine
    sequence, and the only way to close a gap is to renumber an ADR that has
    already been cited — the edit `wiki/SCHEMA.md` forbids. Reuse is the
    defect, because it is what makes a citation ambiguous.

    The finding lands on the later-sorting page of a collision rather than on
    both, so a two-ADR clash is one problem with one repair — renumber this one
    — and the message names the page that holds the number, so the reader never
    has to guess which of the two to leave alone.
    """
    findings = []
    for number, group in sorted(adr_numbers(pages).items()):
        holder = group[0]
        for page in group[1:]:
            findings.append(
                Finding(
                    check=ADR_DUPLICATE_NUMBER,
                    severity=Severity.ERROR,
                    path=page.rel_path,
                    line=None,
                    message=(
                        f"ADR {page.rel_path} reuses number {number}, already "
                        f"held by {holder.rel_path} — SCHEMA: "
                        f'"{SCHEMA_APPEND_ONLY}"; give this ADR the next '
                        f"unused number"
                    ),
                )
            )
    return findings


@check(ADR_SUPERSEDED_MISSING)
def check_adr_superseded_target(pages, root):
    """Every `superseded by` pointer names an ADR that exists (criterion 13).

    Matched by number against the ADRs in `decisions/`, not by resolving the
    wikilink: the question is whether the decision that replaced this one was
    ever written, and a page elsewhere in the wiki that happens to share the
    name does not answer it. An unresolvable pointer is therefore usually
    reported twice — here and as `broken-link` — which is deliberate; the
    checks diverge in both directions and their messages carry different
    repairs.
    """
    numbers = adr_numbers(pages)
    findings = []
    for page in typed_pages(pages, DECISIONS_DIR):
        line_no, number = superseded_number(page)
        if number is None or number in numbers:
            continue
        findings.append(
            Finding(
                check=ADR_SUPERSEDED_MISSING,
                severity=Severity.ERROR,
                path=page.rel_path,
                line=line_no,
                message=(
                    f"ADR {page.rel_path} says it is superseded by ADR {number}, "
                    f"which no page in {DECISIONS_DIR}/ carries — write the "
                    f"superseding ADR or correct the pointer"
                ),
            )
        )
    return findings


@check(FILENAME_CASE)
def check_filename_case(pages, root):
    """Every page file name is kebab-case (spec criterion 14).

    The only check in the package that walks *all* pages rather than one
    directory's, because the convention is not a property of a page template:
    `wiki/SCHEMA.md` writes `wiki/concepts/<kebab-name>.md` and
    `wiki/decisions/adr-NNN-<slug>.md`, and a page anywhere else in the wiki is
    still linked by typing its name.

    A `warn`: the links to `Some_Page.md` resolve, because resolution is by
    exact string, so nothing in the graph is broken — what is broken is the
    author's ability to guess a link target without opening a file browser.

    Two exclusions. Framework files are exempt through the shared
    `is_framework_page`, so `INDEX.md`, `SCHEMA.md` and `log.md` are exempt in
    every directory — SCHEMA rule 2 asks for a directory `INDEX.md` by that
    exact upper-case name. And `decisions/` is left to `check_adr_filename`,
    which already reports every name in that directory that is not
    `adr-NNN-<slug>.md`: since no non-kebab name can match that pattern, the
    handover reports strictly fewer findings without losing one, and Task 10's
    rule holds — one rename should not look like several problems. Nothing is
    excluded on the grounds of *directory* naming: this check reports a page and
    names a file rename as the repair.
    """
    return [
        Finding(
            check=FILENAME_CASE,
            severity=Severity.WARN,
            path=page.rel_path,
            line=None,
            message=(
                f"page {page.rel_path} is not named in kebab-case — rename it "
                f"to lower-case words joined by single hyphens (SCHEMA: "
                f"`{KEBAB_FILENAME_SHAPE}`), so the file name can be typed as "
                f"a link target"
            ),
        )
        for page in pages
        if not is_framework_page(page)
        and not is_decision_page(page)
        and not KEBAB_FILENAME_RE.match(basename(page))
    ]
