"""Tests for ADR-page conformance (spec criterion 11).

`wiki/SCHEMA.md` gives the ADR template as a file name (`adr-NNN-<slug>.md`), a
`Status:` line, a `Date:` line, and three sections. All four are errors, not
warns: ADRs are this framework's audit trail, and an ADR that cannot be dated,
numbered, or read for its decision has already failed at the only job it has.

Each of the four is its own check id, so this module has four independent
entry points. That is deliberate — see the module docstring in
`wiki_health/checks/schema.py` — and it is what lets each test below assert a
count rather than a presence: `fixtures/bad-adr/` is `fixtures/clean/` plus
exactly one page per defect, each page conformant in every other respect.

Everything about *matching* — how many digits the number needs, which `Status:`
values are legal, what `Date:` will parse — is asserted in temp directories,
where the input sits next to the expectation rather than in a fixture file.
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
BAD_ADR = FIXTURES / "bad-adr"

# The four defects in the bad-adr fixture, pinned here so a fixture edit fails
# loudly instead of quietly weakening the test.
BAD_FILENAME_PAGE = "decisions/adr-2-bad-number.md"
MISSING_STATUS_PAGE = "decisions/adr-002-missing-status.md"
BAD_DATE_PAGE = "decisions/adr-003-bad-date.md"
MISSING_HEADING_PAGE = "decisions/adr-004-missing-sections.md"

CONFORMANT = """# ADR-007: A decision that follows the template
Status: accepted
Date: 2026-08-16

## Context
Body.

## Decision
Body.

## Consequences (including what we gave up)
Body.
"""

CONFORMANT_NAME = "decisions/adr-007-conformant.md"


def write_page(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_filename(root):
    return schema.check_adr_filename(discover(root), root)


def run_status(root):
    return schema.check_adr_status(discover(root), root)


def run_date(root):
    return schema.check_adr_date(discover(root), root)


def run_headings(root):
    return schema.check_adr_headings(discover(root), root)


ALL_ADR_CHECKS = (run_filename, run_status, run_date, run_headings)


def only_finding(runner, name, text):
    """Run one ADR check over a one-page wiki and return its single finding."""
    with tempfile.TemporaryDirectory() as tmp:
        write_page(tmp, name, text)
        findings = runner(tmp)
    if len(findings) != 1:
        raise AssertionError(f"expected exactly one finding, got {findings}")
    return findings[0]


def findings_for(runner, name, text):
    with tempfile.TemporaryDirectory() as tmp:
        write_page(tmp, name, text)
        return runner(tmp)


class TestFilename(unittest.TestCase):
    def test_filename_not_matching_adr_nnn_slug_is_an_error(self):
        (finding,) = run_filename(BAD_ADR)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, schema.ADR_BAD_FILENAME)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(finding.path, BAD_FILENAME_PAGE)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)

    def test_message_names_the_page_and_the_expected_shape(self):
        (finding,) = run_filename(BAD_ADR)

        self.assertIn(BAD_FILENAME_PAGE, finding.message)
        self.assertIn("adr-NNN-", finding.message)

    def test_the_number_must_be_exactly_three_digits(self):
        for name in ("adr-1-x.md", "adr-01-x.md", "adr-0001-x.md"):
            with self.subTest(name=name):
                finding = only_finding(run_filename, f"decisions/{name}", CONFORMANT)
                self.assertEqual(finding.path, f"decisions/{name}")

    def test_a_missing_or_malformed_slug_is_an_error(self):
        for name in ("adr-001.md", "adr-001-.md", "adr-001--x.md", "notes.md"):
            with self.subTest(name=name):
                finding = only_finding(run_filename, f"decisions/{name}", CONFORMANT)
                self.assertEqual(finding.path, f"decisions/{name}")

    def test_the_slug_must_be_lower_case_kebab(self):
        for name in ("ADR-001-x.md", "adr-001-Mixed.md", "adr-001-two_words.md"):
            with self.subTest(name=name):
                finding = only_finding(run_filename, f"decisions/{name}", CONFORMANT)
                self.assertEqual(finding.path, f"decisions/{name}")

    def test_a_conformant_name_passes(self):
        for name in ("adr-001-x.md", "adr-012-multi-word-slug.md", "adr-999-a1.md"):
            with self.subTest(name=name):
                self.assertEqual(
                    findings_for(run_filename, f"decisions/{name}", CONFORMANT), []
                )

    def test_each_page_is_reported_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "decisions/adr-1-x.md", CONFORMANT)
            write_page(tmp, "decisions/adr-002-fine.md", CONFORMANT)

            findings = run_filename(tmp)

        self.assertEqual([f.path for f in findings], ["decisions/adr-1-x.md"])


class TestStatus(unittest.TestCase):
    def test_missing_status_line_is_an_error(self):
        (finding,) = run_status(BAD_ADR)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, schema.ADR_BAD_STATUS)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(finding.path, MISSING_STATUS_PAGE)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)

    def test_message_names_both_legal_forms(self):
        (finding,) = run_status(BAD_ADR)

        self.assertIn("accepted", finding.message)
        self.assertIn("superseded by", finding.message)

    def test_accepted_passes(self):
        self.assertEqual(findings_for(run_status, CONFORMANT_NAME, CONFORMANT), [])

    def test_superseded_by_a_wikilink_passes(self):
        for status in (
            "superseded by [[adr-002]]",
            "superseded by [[adr-002-later-decision]]",
            "superseded by [[decisions/adr-002]]",
        ):
            with self.subTest(status=status):
                text = CONFORMANT.replace("Status: accepted", f"Status: {status}")
                self.assertEqual(findings_for(run_status, CONFORMANT_NAME, text), [])

    def test_an_unrecognised_status_is_an_error_pointing_at_its_line(self):
        # The value is there but says nothing SCHEMA defines, so the line
        # exists and the finding can point at it.
        text = CONFORMANT.replace("Status: accepted", "Status: proposed")

        finding = only_finding(run_status, CONFORMANT_NAME, text)

        self.assertEqual(finding.line, 2)
        self.assertIn("proposed", finding.message)

    def test_status_matching_is_case_sensitive(self):
        # SCHEMA writes the values in lower case, and Task 11 parses the
        # supersede pointer out of this exact string; accepting variants here
        # would make that parse guesswork.
        text = CONFORMANT.replace("Status: accepted", "Status: Accepted")

        finding = only_finding(run_status, CONFORMANT_NAME, text)

        self.assertEqual(finding.line, 2)

    def test_a_superseded_status_with_no_target_is_an_error(self):
        text = CONFORMANT.replace("Status: accepted", "Status: superseded")

        finding = only_finding(run_status, CONFORMANT_NAME, text)

        self.assertEqual(finding.line, 2)

    def test_a_status_line_inside_a_fenced_block_does_not_count(self):
        text = CONFORMANT.replace("Status: accepted", "```\nStatus: accepted\n```")

        finding = only_finding(run_status, CONFORMANT_NAME, text)

        self.assertIsNone(finding.line)


class TestDate(unittest.TestCase):
    def test_unparseable_date_is_an_error(self):
        (finding,) = run_date(BAD_ADR)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, schema.ADR_BAD_DATE)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(finding.path, BAD_DATE_PAGE)
        self.assertEqual(finding.line, 3)
        self.assertFalse(finding.fixed)

    def test_message_names_the_expected_format(self):
        (finding,) = run_date(BAD_ADR)

        self.assertIn("YYYY-MM-DD", finding.message)

    def test_a_missing_date_line_is_an_error_with_no_line(self):
        text = CONFORMANT.replace("Date: 2026-08-16\n", "")

        finding = only_finding(run_date, CONFORMANT_NAME, text)

        self.assertIsNone(finding.line)

    def test_an_iso_date_passes(self):
        self.assertEqual(findings_for(run_date, CONFORMANT_NAME, CONFORMANT), [])

    def test_a_date_that_does_not_exist_is_an_error(self):
        for value in ("2026-02-30", "2026-13-01", "16-08-2026", "August 16, 2026"):
            with self.subTest(value=value):
                text = CONFORMANT.replace("Date: 2026-08-16", f"Date: {value}")
                finding = only_finding(run_date, CONFORMANT_NAME, text)
                self.assertEqual(finding.line, 3)

    def test_a_date_line_inside_a_fenced_block_does_not_count(self):
        text = CONFORMANT.replace("Date: 2026-08-16", "```\nDate: 2026-08-16\n```")

        finding = only_finding(run_date, CONFORMANT_NAME, text)

        self.assertIsNone(finding.line)


class TestHeadings(unittest.TestCase):
    def test_missing_context_decision_or_consequences_heading_is_an_error(self):
        (finding,) = run_headings(BAD_ADR)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, schema.ADR_MISSING_HEADING)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(finding.path, MISSING_HEADING_PAGE)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)

    def test_message_names_every_missing_section_and_no_others(self):
        (finding,) = run_headings(BAD_ADR)

        self.assertIn("## Decision", finding.message)
        self.assertIn("## Consequences", finding.message)
        self.assertNotIn("## Context", finding.message)

    def test_a_page_missing_all_three_is_one_finding(self):
        finding = only_finding(
            run_headings, CONFORMANT_NAME, "# ADR-007: Nothing\nStatus: accepted\n"
        )

        for required in schema.ADR_HEADINGS:
            self.assertIn(required, finding.message)

    def test_parenthetical_suffix_still_satisfies_the_requirement(self):
        # SCHEMA's own template writes `## Consequences (including what we gave
        # up)`, so the requirement is a prefix, not an equality.
        self.assertEqual(findings_for(run_headings, CONFORMANT_NAME, CONFORMANT), [])

    def test_heading_level_must_match(self):
        text = CONFORMANT.replace("## Context", "### Context")

        finding = only_finding(run_headings, CONFORMANT_NAME, text)

        self.assertIn("## Context", finding.message)

    def test_required_headings_match_the_schema_template(self):
        self.assertEqual(
            list(schema.ADR_HEADINGS),
            ["## Context", "## Decision", "## Consequences"],
        )


class TestScope(unittest.TestCase):
    def test_pages_outside_decisions_are_not_adr_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/Some_Page.md", "not an adr at all\n")
            write_page(tmp, "projects/demo.md", "not an adr at all\n")
            write_page(tmp, "log.md", "not an adr at all\n")

            for runner in ALL_ADR_CHECKS:
                with self.subTest(check=runner.__name__):
                    self.assertEqual(runner(tmp), [])

    def test_a_nested_page_is_still_an_adr_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "decisions/archive/notes.md", "not an adr at all\n")

            for runner in ALL_ADR_CHECKS:
                with self.subTest(check=runner.__name__):
                    (finding,) = runner(tmp)
                    self.assertEqual(finding.path, "decisions/archive/notes.md")

    def test_a_directory_index_is_not_an_adr_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "decisions/INDEX.md", "# Decisions\n\n- [[adr-001-x]]\n")

            for runner in ALL_ADR_CHECKS:
                with self.subTest(check=runner.__name__):
                    self.assertEqual(runner(tmp), [])


class TestCleanFixture(unittest.TestCase):
    def test_conformant_adr_passes(self):
        for runner in ALL_ADR_CHECKS:
            with self.subTest(check=runner.__name__):
                self.assertEqual(runner(CLEAN), [])

    def test_bad_adr_fixture_differs_from_clean_by_four_pages(self):
        clean = {p.rel_path for p in discover(CLEAN)}
        bad = {p.rel_path for p in discover(BAD_ADR)}

        self.assertEqual(
            bad - clean,
            {
                BAD_FILENAME_PAGE,
                MISSING_STATUS_PAGE,
                BAD_DATE_PAGE,
                MISSING_HEADING_PAGE,
            },
        )
        self.assertEqual(clean - bad, set())

    def test_each_defective_page_trips_exactly_one_of_the_four_checks(self):
        self.assertEqual([f.path for f in run_filename(BAD_ADR)], [BAD_FILENAME_PAGE])
        self.assertEqual([f.path for f in run_status(BAD_ADR)], [MISSING_STATUS_PAGE])
        self.assertEqual([f.path for f in run_date(BAD_ADR)], [BAD_DATE_PAGE])
        self.assertEqual([f.path for f in run_headings(BAD_ADR)], [MISSING_HEADING_PAGE])


class TestRegistration(unittest.TestCase):
    def test_adr_checks_are_registered(self):
        for function in (
            schema.check_adr_filename,
            schema.check_adr_status,
            schema.check_adr_date,
            schema.check_adr_headings,
        ):
            with self.subTest(check=function.__name__):
                self.assertIn(function, checks.ALL_CHECKS)

    def test_adr_check_ids_are_stable_and_unique(self):
        expected = {
            schema.check_adr_filename: schema.ADR_BAD_FILENAME,
            schema.check_adr_status: schema.ADR_BAD_STATUS,
            schema.check_adr_date: schema.ADR_BAD_DATE,
            schema.check_adr_headings: schema.ADR_MISSING_HEADING,
        }
        ids = [function.check_id for function in checks.ALL_CHECKS]

        for function, check_id in expected.items():
            with self.subTest(check=function.__name__):
                self.assertEqual(function.check_id, check_id)
                self.assertEqual(ids.count(check_id), 1)

        self.assertEqual(len(set(expected.values())), 4)


if __name__ == "__main__":
    unittest.main()
