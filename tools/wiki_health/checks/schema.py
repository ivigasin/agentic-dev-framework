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
a section is a `warn` (a gap in a page, not a lie in the graph).
"""

from . import check
from ..model import Finding, Severity

CONCEPT_MISSING_H1 = "concept-missing-h1"
CONCEPT_MISSING_HEADING = "concept-missing-heading"

# Page-type directories, as named in `wiki/SCHEMA.md` "Page types".
CONCEPTS_DIR = "concepts"

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


def is_framework_page(page):
    """True for INDEX.md / SCHEMA.md / log.md, in any directory."""
    return page.rel_path.rsplit("/", 1)[-1] in FRAMEWORK_FILENAMES


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
