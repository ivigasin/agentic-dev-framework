"""Tests for the orphan-page check (spec criterion 7, severity `warn`).

Same two-fixture shape as the broken-link tests: `fixtures/clean/` is the
negative control, and `fixtures/orphan/` is that wiki plus exactly one page
nothing links to, so a test can assert the *count* and not merely the presence
of a finding.

The interesting cases are all about what does **not** count as an inbound link
— a self-link, a link that does not resolve — and about the three framework
files at the wiki root, which are entry points rather than linked-to pages.
Those are built in temp directories so the expected graph sits next to the
assertion.
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
ORPHAN = FIXTURES / "orphan"

# The one defect in the orphan fixture, pinned here so a fixture edit fails
# loudly instead of quietly weakening the test.
ORPHAN_PAGE = "concepts/gamma.md"


def write_page(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_check(root):
    return structural.check_orphans(discover(root), root)


class TestOrphanDetection(unittest.TestCase):
    def test_page_with_no_inbound_links_is_a_warn(self):
        (finding,) = run_check(ORPHAN)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, structural.ORPHAN_PAGE)
        self.assertEqual(finding.severity, Severity.WARN)
        self.assertEqual(finding.path, ORPHAN_PAGE)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)

    def test_orphan_fixture_differs_from_clean_by_one_page(self):
        clean = {p.rel_path for p in discover(CLEAN)}
        orphan = {p.rel_path for p in discover(ORPHAN)}

        self.assertEqual(orphan - clean, {ORPHAN_PAGE})
        self.assertEqual(clean - orphan, set())

    def test_a_single_inbound_link_is_enough(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            self.assertEqual(run_check(tmp), [])

    def test_directory_qualified_link_counts_as_inbound(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[concepts/alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            self.assertEqual(run_check(tmp), [])

    def test_self_link_does_not_rescue_a_page(self):
        # A page citing itself is still unreachable from the rest of the wiki,
        # which is the only thing an inbound link is evidence of.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n\nSee [[alpha]].\n")

            (finding,) = run_check(tmp)

        self.assertEqual(finding.path, "concepts/alpha.md")

    def test_unresolved_link_does_not_count_as_inbound(self):
        # `[[Alpha]]` matches no page; only resolved links build the graph, or
        # a typo would mask the orphan it created.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[Alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            (finding,) = run_check(tmp)

        self.assertEqual(finding.path, "concepts/alpha.md")

    def test_link_inside_a_fenced_block_does_not_count_as_inbound(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n```md\n- [[alpha]]\n```\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            (finding,) = run_check(tmp)

        self.assertEqual(finding.path, "concepts/alpha.md")

    def test_every_orphan_is_reported_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")
            write_page(tmp, "concepts/beta.md", "# Beta\n\nSee [[alpha]].\n")

            findings = run_check(tmp)

        self.assertEqual([f.path for f in findings], ["concepts/beta.md"])

    def test_message_names_the_page_and_says_what_to_do(self):
        (finding,) = run_check(ORPHAN)

        self.assertIn(ORPHAN_PAGE, finding.message)
        self.assertIn("link", finding.message)


class TestExemptRoots(unittest.TestCase):
    def test_index_schema_and_log_are_exempt(self):
        # The three framework files are entry points, not destinations: INDEX.md
        # is where a reader starts, and SCHEMA.md and log.md are addressed by
        # name. Nothing links to any of them here, and that is not a finding.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n")
            write_page(tmp, "SCHEMA.md", "# Schema\n")
            write_page(tmp, "log.md", "# Log\n")

            self.assertEqual(run_check(tmp), [])

    def test_exemption_applies_only_at_the_wiki_root(self):
        # A directory INDEX.md is an ordinary page in the graph: unlinked, it is
        # unreachable, and SCHEMA rule 2 expects it to hang off the root index.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n")
            write_page(tmp, "concepts/INDEX.md", "# Concepts\n")

            (finding,) = run_check(tmp)

        self.assertEqual(finding.path, "concepts/INDEX.md")
        self.assertEqual(finding.severity, Severity.WARN)


class TestCleanFixture(unittest.TestCase):
    def test_clean_fixture_yields_no_orphans(self):
        self.assertEqual(run_check(CLEAN), [])


class TestRegistration(unittest.TestCase):
    def test_orphan_check_is_registered(self):
        self.assertIn(structural.check_orphans, checks.ALL_CHECKS)

    def test_orphan_check_id_is_stable_and_unique(self):
        self.assertEqual(structural.check_orphans.check_id, structural.ORPHAN_PAGE)

        ids = [check.check_id for check in checks.ALL_CHECKS]
        self.assertEqual(ids.count(structural.ORPHAN_PAGE), 1)


if __name__ == "__main__":
    unittest.main()
