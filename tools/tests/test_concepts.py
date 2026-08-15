"""Tests for concept-page conformance (spec criterion 10).

`wiki/SCHEMA.md` gives the concept template as an H1, a one-line definition, and
four sections. The plan's severity table splits enforcement in two, and so does
this module: a page with no H1 is an `error` (nothing can name it), a page
missing a section is a `warn` (it is a page with a gap, not a broken one). They
are two check ids because they are two rows in that table.

Fixture shape follows the broken-link and orphan tests: `fixtures/clean/` is the
negative control, and `fixtures/bad-concept/` is that wiki plus exactly one page
per defect, so a test can assert the count and not merely the presence of a
finding. Everything about *matching* — prefix tolerance for SCHEMA's
parentheticals, heading level, which directories are concept pages at all — is
asserted in temp directories, where the input sits next to the expectation.
"""

import pathlib
import tempfile
import unittest

from wiki_health import checks
from wiki_health.checks import schema
from wiki_health.model import Finding, Severity
from wiki_health.pages import discover

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
CLEAN = FIXTURES / "clean"
BAD_CONCEPT = FIXTURES / "bad-concept"

# The two defects in the bad-concept fixture, pinned here so a fixture edit
# fails loudly instead of quietly weakening the test.
NO_H1_PAGE = "concepts/no-h1.md"
MISSING_HEADING_PAGE = "concepts/missing-sources.md"

CONFORMANT = """# Alpha
> One-line definition.

## What it is
Body.

## How we use it (project-specific!)
Body.

## Related: [[alpha]]

## Sources: raw/notes.md
"""


def write_page(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_h1(root):
    return schema.check_concept_h1(discover(root), root)


def run_headings(root):
    return schema.check_concept_headings(discover(root), root)


class TestMissingH1(unittest.TestCase):
    def test_missing_h1_is_an_error(self):
        (finding,) = run_h1(BAD_CONCEPT)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, schema.CONCEPT_MISSING_H1)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(finding.path, NO_H1_PAGE)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)

    def test_message_names_the_page_and_says_what_to_add(self):
        (finding,) = run_h1(BAD_CONCEPT)

        self.assertIn(NO_H1_PAGE, finding.message)
        self.assertIn("#", finding.message)

    def test_a_blank_h1_does_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/alpha.md", "#\n\n## What it is\n")

            (finding,) = run_h1(tmp)

        self.assertEqual(finding.path, "concepts/alpha.md")

    def test_a_deeper_heading_is_not_an_h1(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/alpha.md", "## Alpha\n")

            (finding,) = run_h1(tmp)

        self.assertEqual(finding.path, "concepts/alpha.md")

    def test_an_h1_inside_a_fenced_block_is_not_an_h1(self):
        # SCHEMA.md shows the template inside a fence; a page that only quotes
        # one has still not named itself.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/alpha.md", "```md\n# Alpha\n```\n")

            (finding,) = run_h1(tmp)

        self.assertEqual(finding.path, "concepts/alpha.md")

    def test_each_page_is_reported_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/alpha.md", "no heading at all\n")
            write_page(tmp, "concepts/beta.md", "# Beta\n")

            findings = run_h1(tmp)

        self.assertEqual([f.path for f in findings], ["concepts/alpha.md"])


class TestMissingRequiredHeading(unittest.TestCase):
    def test_missing_required_heading_is_a_warn(self):
        (finding,) = run_headings(BAD_CONCEPT)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, schema.CONCEPT_MISSING_HEADING)
        self.assertEqual(finding.severity, Severity.WARN)
        self.assertEqual(finding.path, MISSING_HEADING_PAGE)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)

    def test_message_names_every_missing_heading(self):
        (finding,) = run_headings(BAD_CONCEPT)

        self.assertIn("## Sources:", finding.message)
        self.assertNotIn("## What it is", finding.message)

    def test_a_page_missing_several_headings_is_one_finding(self):
        # One finding per page, listing everything missing: a page with no
        # sections at all is one problem to fix, not four.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            (finding,) = run_headings(tmp)

        for required in schema.CONCEPT_HEADINGS:
            self.assertIn(required, finding.message)

    def test_parenthetical_suffix_still_satisfies_the_requirement(self):
        # SCHEMA's own template writes `## How we use it (project-specific!)`,
        # so the requirement is a prefix, not an equality.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/alpha.md", CONFORMANT)

            self.assertEqual(run_headings(tmp), [])

    def test_heading_level_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(
                tmp,
                "concepts/alpha.md",
                CONFORMANT.replace("## What it is", "### What it is"),
            )

            (finding,) = run_headings(tmp)

        self.assertIn("## What it is", finding.message)

    def test_required_headings_match_the_schema_template(self):
        self.assertEqual(
            list(schema.CONCEPT_HEADINGS),
            ["## What it is", "## How we use it", "## Related:", "## Sources:"],
        )


class TestScope(unittest.TestCase):
    def test_pages_outside_concepts_are_not_concept_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "projects/demo.md", "no h1, no sections\n")
            write_page(tmp, "decisions/adr-001-x.md", "no h1, no sections\n")

            self.assertEqual(run_h1(tmp), [])
            self.assertEqual(run_headings(tmp), [])

    def test_a_nested_page_is_still_a_concept_page(self):
        # SCHEMA puts concept pages flat in `concepts/`, but a nested one is
        # still a concept page. Skipping it would let a whole subtree escape
        # validation — the one failure mode a linter must not have.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/sub/alpha.md", "no h1, no sections\n")

            (h1_finding,) = run_h1(tmp)
            (heading_finding,) = run_headings(tmp)

        self.assertEqual(h1_finding.path, "concepts/sub/alpha.md")
        self.assertEqual(heading_finding.path, "concepts/sub/alpha.md")

    def test_a_directory_index_is_not_a_concept_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/INDEX.md", "# Concepts\n\n- [[alpha]]\n")

            self.assertEqual(run_h1(tmp), [])
            self.assertEqual(run_headings(tmp), [])


class TestCleanFixture(unittest.TestCase):
    def test_conformant_concept_page_passes(self):
        self.assertEqual(run_h1(CLEAN), [])
        self.assertEqual(run_headings(CLEAN), [])

    def test_bad_concept_fixture_differs_from_clean_by_two_pages(self):
        clean = {p.rel_path for p in discover(CLEAN)}
        bad = {p.rel_path for p in discover(BAD_CONCEPT)}

        self.assertEqual(bad - clean, {NO_H1_PAGE, MISSING_HEADING_PAGE})
        self.assertEqual(clean - bad, set())

    def test_each_defective_page_trips_exactly_one_of_the_two_checks(self):
        self.assertEqual([f.path for f in run_h1(BAD_CONCEPT)], [NO_H1_PAGE])
        self.assertEqual(
            [f.path for f in run_headings(BAD_CONCEPT)], [MISSING_HEADING_PAGE]
        )


class TestRegistration(unittest.TestCase):
    def test_concept_checks_are_registered(self):
        self.assertIn(schema.check_concept_h1, checks.ALL_CHECKS)
        self.assertIn(schema.check_concept_headings, checks.ALL_CHECKS)

    def test_concept_check_ids_are_stable_and_unique(self):
        self.assertEqual(
            schema.check_concept_h1.check_id, schema.CONCEPT_MISSING_H1
        )
        self.assertEqual(
            schema.check_concept_headings.check_id, schema.CONCEPT_MISSING_HEADING
        )

        ids = [check.check_id for check in checks.ALL_CHECKS]
        self.assertEqual(ids.count(schema.CONCEPT_MISSING_H1), 1)
        self.assertEqual(ids.count(schema.CONCEPT_MISSING_HEADING), 1)


if __name__ == "__main__":
    unittest.main()
