"""Tests for the broken-link check and the check-function convention itself.

Two fixtures are in play. `fixtures/clean/` is the negative control — a check
that fires on it has a bug — and `fixtures/broken-links/` is the same wiki plus
exactly one page carrying one unresolved target, so a test can assert the count
and not merely the presence of a finding.

Ambiguity cases are built in a temp directory rather than committed as a
fixture: two same-named pages are a defect nothing else in the suite wants to
inherit, and writing them inline keeps the expected resolution visible next to
the assertion.
"""

import pathlib
import tempfile
import unittest

from wiki_health import checks
from wiki_health.checks import structural
from wiki_health.model import Finding, Severity
from wiki_health.pages import discover

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
CLEAN = FIXTURES / "clean"
BROKEN = FIXTURES / "broken-links"

# The one defect in the broken-links fixture, pinned here so a fixture edit
# fails loudly instead of quietly weakening the test.
BROKEN_PAGE = "concepts/beta.md"
BROKEN_TARGET = "does-not-exist"
BROKEN_LINE = 12


def write_page(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_check(root):
    return structural.check_broken_links(discover(root), root)


class TestUnresolvedTargets(unittest.TestCase):
    def test_unresolved_target_is_an_error(self):
        (finding,) = run_check(BROKEN)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, structural.BROKEN_LINK)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(finding.path, BROKEN_PAGE)
        self.assertEqual(finding.line, BROKEN_LINE)
        self.assertIn(BROKEN_TARGET, finding.message)
        self.assertFalse(finding.fixed)

    def test_finding_line_points_at_the_link(self):
        (finding,) = run_check(BROKEN)
        page = [p for p in discover(BROKEN) if p.rel_path == BROKEN_PAGE][0]

        self.assertIn(f"[[{BROKEN_TARGET}]]", page.lines[finding.line - 1])

    def test_two_broken_links_on_one_line_are_two_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "p.md", "# P\n\n## Related: [[nope-a]], [[nope-b]]\n")

            findings = run_check(tmp)

        self.assertEqual(len(findings), 2)
        self.assertEqual({f.line for f in findings}, {3})

    def test_links_inside_fenced_blocks_are_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "p.md", "# P\n\n```md\n[[not-a-real-page]]\n```\n")

            self.assertEqual(run_check(tmp), [])


class TestResolution(unittest.TestCase):
    def test_bare_name_resolves_against_any_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[alpha]]\n- [[adr-001-example]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")
            write_page(tmp, "decisions/adr-001-example.md", "# ADR-001\n")

            self.assertEqual(run_check(tmp), [])

    def test_directory_qualified_name_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[concepts/alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            self.assertEqual(run_check(tmp), [])

    def test_root_level_page_resolves_by_its_bare_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[SCHEMA]]\n")
            write_page(tmp, "SCHEMA.md", "# Schema\n")

            self.assertEqual(run_check(tmp), [])

    def test_wrong_directory_qualifier_does_not_resolve(self):
        # `[[projects/alpha]]` must not fall back to `concepts/alpha.md`: a
        # qualified target names one page, and silently retargeting it would
        # hide exactly the kind of stale link this check exists to catch.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[projects/alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            (finding,) = run_check(tmp)

        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertIn("projects/alpha", finding.message)


class TestAmbiguousStems(unittest.TestCase):
    def ambiguous_wiki(self, tmp, target):
        write_page(tmp, "INDEX.md", f"# I\n\n- [[{target}]]\n")
        write_page(tmp, "concepts/dup.md", "# Dup\n")
        write_page(tmp, "projects/dup.md", "# Dup\n")
        return run_check(tmp)

    def test_ambiguous_stem_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            (finding,) = self.ambiguous_wiki(tmp, "dup")

        self.assertEqual(finding.check, structural.BROKEN_LINK)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(finding.path, "INDEX.md")
        self.assertEqual(finding.line, 3)
        self.assertIn("concepts/dup.md", finding.message)
        self.assertIn("projects/dup.md", finding.message)

    def test_ambiguous_message_differs_from_unresolved_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            (ambiguous,) = self.ambiguous_wiki(tmp, "dup")
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[dup]]\n")
            (unresolved,) = run_check(tmp)

        self.assertNotEqual(ambiguous.message, unresolved.message)

    def test_exact_path_match_beats_an_ambiguous_stem(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.ambiguous_wiki(tmp, "concepts/dup"), [])


class TestCleanFixture(unittest.TestCase):
    def test_clean_fixture_yields_no_broken_link_findings(self):
        self.assertEqual(run_check(CLEAN), [])

    def test_broken_links_fixture_differs_from_clean_by_one_page(self):
        clean = {p.rel_path for p in discover(CLEAN)}
        broken = {p.rel_path for p in discover(BROKEN)}

        self.assertEqual(broken - clean, {BROKEN_PAGE})
        self.assertEqual(clean - broken, set())


class TestCheckConvention(unittest.TestCase):
    """The shape Tasks 6-12 must follow, asserted rather than only documented."""

    def test_broken_link_check_is_registered(self):
        self.assertIn(structural.check_broken_links, checks.ALL_CHECKS)

    def test_check_ids_are_unique(self):
        ids = [check.check_id for check in checks.ALL_CHECKS]

        self.assertEqual(len(ids), len(set(ids)))

    def test_every_registered_check_takes_pages_and_root_and_returns_findings(self):
        for check in checks.ALL_CHECKS:
            findings = check(discover(CLEAN), CLEAN)

            self.assertIsInstance(findings, list, check.check_id)
            self.assertTrue(
                all(isinstance(f, Finding) for f in findings), check.check_id
            )

    def test_run_all_collects_findings_from_every_check(self):
        findings = checks.run_all(discover(BROKEN), BROKEN)

        self.assertIn(structural.BROKEN_LINK, {f.check for f in findings})

    def test_run_all_on_the_clean_fixture_finds_nothing(self):
        self.assertEqual(checks.run_all(discover(CLEAN), CLEAN), [])


if __name__ == "__main__":
    unittest.main()
