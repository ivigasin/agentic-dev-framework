"""Tests for the kebab-case filename check (spec criterion 14).

`wiki/SCHEMA.md` writes the concept path as `wiki/concepts/<kebab-name>.md` and
the ADR path as `wiki/decisions/adr-NNN-<slug>.md`. Both spell the same
convention: a page's file name is lower-case, digits allowed, words joined by
single hyphens. It is worth enforcing because the file name is not decoration —
it is the link target. `[[some-page]]` is what an author types, and a wiki that
mixes `Some_Page.md` with `some-page.md` makes the author guess which.

A `warn`, not an error, per the plan's severity table: nothing in the graph is
broken by the name — the links to it resolve, since resolution is by exact
string — so the defect is a convention violation, not a lie.

Three scoping decisions are pinned by the tests below:

- **The exemption is the shared `is_framework_page`**, so `INDEX.md`,
  `SCHEMA.md` and `log.md` are exempt in *any* directory. They are not
  instances of a page template at all, and SCHEMA rule 2 asks for a directory
  `INDEX.md` by that exact upper-case name.
- **`decisions/` is left to `adr-bad-filename`.** Every non-kebab name is also
  a non-conformant ADR name, so every page this check would report there is
  already an error with the same repair — one rename should not look like two
  problems. `TestDecisionsAreLeftToTheAdrCheck` proves the coverage claim
  rather than assuming it.
- **Only the file name is examined, never the directories above it.** SCHEMA
  fixes the three directory names itself, and a finding whose `path` is a
  directory is `directory-scale`'s shape, not a page check's.

`fixtures/bad-filename/` is `fixtures/clean/` plus one page named
`Some_Page.md`, conformant in every other respect and linked from `INDEX.md`
so that the rename is not tangled with an orphan or a reachability problem.
Everything about *matching* is asserted in temporary directories, where the
input sits next to the expectation — the same split the ADR tests use.
"""

import collections
import pathlib
import tempfile
import unittest

from wiki_health import checks
from wiki_health.checks import schema
from wiki_health.model import Finding, Severity
from wiki_health.pages import discover

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
CLEAN = FIXTURES / "clean"
BAD_FILENAME = FIXTURES / "bad-filename"

# The one defect in the bad-filename fixture, pinned here so a fixture edit
# fails loudly instead of quietly weakening the test.
BAD_NAME_PAGE = "concepts/Some_Page.md"

# A page that satisfies every other check, so a temporary wiki built from it
# isolates the file name as the only variable.
CONCEPT = """# Placeholder
> One-line definition.

## What it is
Body.

## How we use it (project-specific!)
Body.

## Related:

## Sources: raw/notes.md
"""

# A conformant ADR body, for the pages that exercise the `decisions/` handover.
ADR = """# ADR-001: A decision that follows the template
Status: accepted
Date: 2026-08-16

## Context
Body.

## Decision
Body.

## Consequences (including what we gave up)
Body.
"""


def write_page(directory, name, text=CONCEPT):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_filenames(root):
    return schema.check_filename_case(discover(root), root)


def run_adr_filenames(root):
    return schema.check_adr_filename(discover(root), root)


def in_temp_wiki(runner, names, text=CONCEPT):
    """Run one check over a wiki built from `names`."""
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            write_page(tmp, name, text)
        return runner(tmp)


def reported(names, text=CONCEPT):
    return [finding.path for finding in in_temp_wiki(run_filenames, names, text)]


class TestNonKebabFilename(unittest.TestCase):
    def test_non_kebab_case_filename_is_a_warn(self):
        (finding,) = run_filenames(BAD_FILENAME)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, schema.FILENAME_CASE)
        self.assertEqual(finding.severity, Severity.WARN)
        self.assertEqual(finding.path, BAD_NAME_PAGE)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)

    def test_the_message_names_the_page_and_the_convention(self):
        (finding,) = run_filenames(BAD_FILENAME)

        self.assertIn(BAD_NAME_PAGE, finding.message)
        self.assertIn("kebab", finding.message)

    def test_every_shape_that_is_not_kebab_case_is_reported(self):
        for name in (
            "concepts/Some_Page.md",  # the fixture's case
            "concepts/some_page.md",  # underscore
            "concepts/SomePage.md",  # camel case
            "concepts/Some-Page.md",  # capitals with hyphens
            "concepts/some page.md",  # space
            "concepts/some--page.md",  # doubled separator
            "concepts/-leading.md",  # leading hyphen
            "concepts/trailing-.md",  # trailing hyphen
            "concepts/some.page.md",  # dot as a separator
            "concepts/café.md",  # non-ascii
        ):
            with self.subTest(name=name):
                self.assertEqual(reported([name]), [name])

    def test_each_badly_named_page_is_reported_once(self):
        names = ["concepts/One_Page.md", "concepts/Two_Page.md", "concepts/ok.md"]

        self.assertEqual(
            reported(names), ["concepts/One_Page.md", "concepts/Two_Page.md"]
        )

    def test_a_page_at_the_wiki_root_is_checked_too(self):
        self.assertEqual(reported(["Notes_Page.md"]), ["Notes_Page.md"])

    def test_a_nested_page_is_checked_too(self):
        # `concepts/` may grow subdirectories; a subtree is not a place where
        # the naming convention stops applying.
        self.assertEqual(
            reported(["concepts/sub/Some_Page.md"]), ["concepts/sub/Some_Page.md"]
        )


class TestKebabCasePasses(unittest.TestCase):
    def test_kebab_case_passes(self):
        for name in (
            "concepts/alpha.md",
            "concepts/some-page.md",
            "concepts/a-longer-page-name.md",
            "concepts/page2.md",
            "concepts/2026-retrospective.md",
            "projects/demo.md",
            "notes.md",
        ):
            with self.subTest(name=name):
                self.assertEqual(reported([name]), [])

    def test_the_clean_fixture_yields_no_filename_findings(self):
        self.assertEqual(run_filenames(CLEAN), [])

    def test_only_the_file_name_is_examined(self):
        # Directory names are SCHEMA's business, not this check's: it reports a
        # page, and the repair it names is a file rename.
        self.assertEqual(reported(["concepts/Sub_Dir/some-page.md"]), [])


class TestFrameworkFilesAreExempt(unittest.TestCase):
    def test_index_schema_and_log_are_exempt(self):
        self.assertEqual(reported(["INDEX.md", "SCHEMA.md", "log.md"]), [])

    def test_the_exemption_holds_in_every_directory(self):
        # `is_framework_page` matches the basename, so the directory INDEX.md
        # SCHEMA rule 2 asks for is exempt exactly like the root one.
        for directory in ("", "concepts/", "projects/", "concepts/sub/"):
            for filename in sorted(schema.FRAMEWORK_FILENAMES):
                with self.subTest(name=directory + filename):
                    self.assertEqual(reported([directory + filename]), [])

    def test_the_exemption_is_by_exact_name_not_by_case(self):
        # `Index.md` is not the file SCHEMA names, so it is an ordinary page
        # carrying an ordinary badly-cased name.
        self.assertEqual(reported(["concepts/Index.md"]), ["concepts/Index.md"])


class TestDecisionsAreLeftToTheAdrCheck(unittest.TestCase):
    """`adr-bad-filename` already owns every name defect under `decisions/`.

    Task 10's precedent: a badly named ADR yields one finding, not several, so
    one rename does not look like several problems. The claim that makes the
    handover safe is a coverage claim — every name this check would report in
    `decisions/` is a name the ADR check already reports — and it is asserted
    below rather than assumed, because the day it stops holding is the day a
    badly named page under `decisions/` goes unreported entirely.
    """

    def test_a_badly_named_decisions_page_is_reported_only_as_an_adr_defect(self):
        names = ["decisions/Some_Page.md"]

        self.assertEqual(reported(names, ADR), [])
        self.assertEqual(
            [f.path for f in in_temp_wiki(run_adr_filenames, names, ADR)], names
        )

    def test_the_adr_check_covers_every_non_kebab_name_this_one_would(self):
        for name in (
            "Some_Page.md",
            "some_page.md",
            "SomePage.md",
            "adr-001-Bad_Slug.md",
            "ADR-001-example.md",
        ):
            with self.subTest(name=name):
                path = f"decisions/{name}"
                self.assertEqual(reported([path], ADR), [])
                self.assertEqual(
                    [f.path for f in in_temp_wiki(run_adr_filenames, [path], ADR)],
                    [path],
                )

    def test_a_conformant_adr_passes_both_checks(self):
        names = ["decisions/adr-001-example.md"]

        self.assertEqual(reported(names, ADR), [])
        self.assertEqual(in_temp_wiki(run_adr_filenames, names, ADR), [])

    def test_a_decisions_index_is_still_exempt_from_both(self):
        names = ["decisions/INDEX.md"]

        self.assertEqual(reported(names), [])
        self.assertEqual(in_temp_wiki(run_adr_filenames, names), [])


class TestFixtureShape(unittest.TestCase):
    def test_the_fixture_is_the_clean_one_plus_one_badly_named_page(self):
        clean = {page.rel_path for page in discover(CLEAN)}
        bad = {page.rel_path for page in discover(BAD_FILENAME)}

        self.assertEqual(bad - clean, {BAD_NAME_PAGE})
        self.assertEqual(clean - bad, set())

    def test_the_fixture_trips_exactly_the_expected_checks(self):
        # The whole registry over the whole fixture: one finding, no incidental
        # orphan, drift, or concept-shape noise.
        counts = collections.Counter(
            finding.check
            for finding in checks.run_all(discover(BAD_FILENAME), BAD_FILENAME)
        )

        self.assertEqual(counts, collections.Counter({schema.FILENAME_CASE: 1}))

    def test_the_clean_fixture_still_yields_nothing_at_all(self):
        self.assertEqual(checks.run_all(discover(CLEAN), CLEAN), [])


class TestRegistration(unittest.TestCase):
    def test_the_filename_check_is_registered(self):
        self.assertIn(schema.check_filename_case, checks.ALL_CHECKS)

    def test_the_check_id_is_stable_and_unique(self):
        ids = [function.check_id for function in checks.ALL_CHECKS]

        self.assertEqual(schema.check_filename_case.check_id, schema.FILENAME_CASE)
        self.assertEqual(ids.count(schema.FILENAME_CASE), 1)


if __name__ == "__main__":
    unittest.main()
