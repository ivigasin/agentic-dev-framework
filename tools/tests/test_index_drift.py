"""Tests for the index-drift check (spec criterion 8, severity `error`).

`wiki/SCHEMA.md` rule 2 — "every page reachable from `wiki/INDEX.md` within 2
link hops" — has two failure modes, and this check owns both:

- a page the index can no longer reach in two hops (or at all), and
- an index entry naming a page that is gone.

They are the same defect seen from either end of the edge, which is why they
share a check id. The second overlaps deliberately with the broken-link check:
a dead link in INDEX.md is both a broken link and index drift, and a reader
fixing it needs to know it was the *index* that went stale.

`fixtures/index-drift/` is the clean fixture plus exactly those two defects, so
tests assert counts rather than mere presence. Everything else is built in temp
directories, where the expected graph sits next to the assertion.
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
DRIFT = FIXTURES / "index-drift"

# The two defects in the index-drift fixture, pinned here so a fixture edit
# fails loudly instead of quietly weakening the test.
DRIFTED_PAGE = "concepts/gamma.md"  # three hops: INDEX -> alpha -> beta -> here
TWO_HOP_PAGE = "concepts/beta.md"  # exactly at the limit, must stay silent
STALE_TARGET = "concepts/deleted"  # an INDEX.md entry whose page was deleted


def write_page(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_check(root):
    return structural.check_index_drift(discover(root), root)


def paths(findings):
    return [finding.path for finding in findings]


class TestHopDepth(unittest.TestCase):
    def test_page_beyond_two_hops_is_an_error(self):
        (finding,) = [f for f in run_check(DRIFT) if f.path == DRIFTED_PAGE]

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, structural.INDEX_DRIFT)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)
        self.assertIn(DRIFTED_PAGE, finding.message)

    def test_page_at_exactly_two_hops_passes(self):
        self.assertNotIn(TWO_HOP_PAGE, paths(run_check(DRIFT)))

    def test_two_hop_chain_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n\n- [[beta]]\n")
            write_page(tmp, "concepts/beta.md", "# Beta\n")

            self.assertEqual(run_check(tmp), [])

    def test_three_hop_chain_reports_only_the_far_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n\n- [[beta]]\n")
            write_page(tmp, "concepts/beta.md", "# Beta\n\n- [[gamma]]\n")
            write_page(tmp, "concepts/gamma.md", "# Gamma\n")

            findings = run_check(tmp)

        self.assertEqual(paths(findings), ["concepts/gamma.md"])

    def test_unreachable_page_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            (finding,) = run_check(tmp)

        self.assertEqual(finding.path, "concepts/alpha.md")
        self.assertEqual(finding.severity, Severity.ERROR)

    def test_shortest_path_wins(self):
        # gamma is three hops down one chain and one hop from the index. BFS
        # takes the short route, so it is not drift.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[alpha]]\n- [[gamma]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n\n- [[beta]]\n")
            write_page(tmp, "concepts/beta.md", "# Beta\n\n- [[gamma]]\n")
            write_page(tmp, "concepts/gamma.md", "# Gamma\n")

            self.assertEqual(run_check(tmp), [])

    def test_directory_index_is_an_ordinary_hop_node(self):
        # A `concepts/INDEX.md` does not reset the hop counter: it costs a hop
        # like any other page, so a page under it is two hops, not one.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[concepts/INDEX]]\n")
            write_page(tmp, "concepts/INDEX.md", "# Concepts\n\n- [[alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n\n- [[beta]]\n")
            write_page(tmp, "concepts/beta.md", "# Beta\n")

            findings = run_check(tmp)

        self.assertEqual(paths(findings), ["concepts/beta.md"])

    def test_unresolved_link_does_not_extend_the_graph(self):
        # `[[Alpha]]` matches no page, so it carries no reachability: the page
        # it was meant to reach is drifted, not indexed.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[Alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            self.assertIn("concepts/alpha.md", paths(run_check(tmp)))

    def test_link_inside_a_fenced_block_does_not_reach(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n```md\n- [[alpha]]\n```\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            self.assertIn("concepts/alpha.md", paths(run_check(tmp)))

    def test_cycle_does_not_hang(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n\n- [[beta]]\n")
            write_page(tmp, "concepts/beta.md", "# Beta\n\n- [[alpha]]\n")

            self.assertEqual(run_check(tmp), [])


class TestExemptRoots(unittest.TestCase):
    def test_index_schema_and_log_are_exempt(self):
        # The three framework files are addressed by name, not reached by link
        # (`wiki/SCHEMA.md` rules 2 and 5), so an index that does not link them
        # has not drifted. INDEX.md is the BFS root and cannot drift from itself.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n")
            write_page(tmp, "SCHEMA.md", "# Schema\n")
            write_page(tmp, "log.md", "# Log\n")

            self.assertEqual(run_check(tmp), [])

    def test_exemption_applies_only_at_the_wiki_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n")
            write_page(tmp, "concepts/INDEX.md", "# Concepts\n")

            (finding,) = run_check(tmp)

        self.assertEqual(finding.path, "concepts/INDEX.md")


class TestStaleIndexEntry(unittest.TestCase):
    def test_index_entry_pointing_at_missing_file_is_an_error(self):
        (finding,) = [f for f in run_check(DRIFT) if f.path == "INDEX.md"]

        self.assertEqual(finding.check, structural.INDEX_DRIFT)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertIn(STALE_TARGET, finding.message)

    def test_stale_entry_finding_points_at_its_line(self):
        (finding,) = [f for f in run_check(DRIFT) if f.path == "INDEX.md"]
        lines = (DRIFT / "INDEX.md").read_text(encoding="utf-8").splitlines()

        self.assertIsNotNone(finding.line)
        self.assertIn(STALE_TARGET, lines[finding.line - 1])

    def test_message_is_distinct_from_the_broken_link_finding(self):
        pages = discover(DRIFT)
        (drift,) = [
            f for f in structural.check_index_drift(pages, DRIFT) if f.path == "INDEX.md"
        ]
        (broken,) = structural.check_broken_links(pages, DRIFT)

        # The overlap is intended, but the two findings must stay legible as
        # two: different check ids, and messages a reader can tell apart.
        self.assertNotEqual(drift.check, broken.check)
        self.assertNotEqual(drift.message, broken.message)
        self.assertIn("INDEX.md", drift.message)

    def test_a_dead_link_outside_the_root_index_is_not_index_drift(self):
        # An ordinary page's dead link is the broken-link check's business.
        # Reporting it here too would make every broken link index drift.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n\n- [[nowhere]]\n")

            self.assertEqual(run_check(tmp), [])

    def test_ambiguous_index_entry_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n- [[alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")
            write_page(tmp, "projects/alpha.md", "# Alpha\n")

            findings = [f for f in run_check(tmp) if f.path == "INDEX.md"]

        self.assertEqual(len(findings), 1)


class TestMissingRootIndex(unittest.TestCase):
    def test_missing_index_is_reported_once_not_per_page(self):
        # Without a root index nothing is reachable. One finding naming the
        # missing file is actionable; one per page is a wall of noise.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")
            write_page(tmp, "concepts/beta.md", "# Beta\n")

            findings = run_check(tmp)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "INDEX.md")
        self.assertEqual(findings[0].severity, Severity.ERROR)

    def test_empty_wiki_yields_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_check(tmp), [])


class TestFixtures(unittest.TestCase):
    def test_clean_fixture_yields_no_drift(self):
        self.assertEqual(run_check(CLEAN), [])

    def test_drift_fixture_has_exactly_the_two_pinned_defects(self):
        self.assertEqual(sorted(paths(run_check(DRIFT))), ["INDEX.md", DRIFTED_PAGE])

    def test_drift_fixture_adds_two_pages_to_clean(self):
        clean = {page.rel_path for page in discover(CLEAN)}
        drift = {page.rel_path for page in discover(DRIFT)}

        self.assertEqual(drift - clean, {TWO_HOP_PAGE, DRIFTED_PAGE})
        self.assertEqual(clean - drift, set())


class TestRegistration(unittest.TestCase):
    def test_index_drift_check_is_registered(self):
        self.assertIn(structural.check_index_drift, checks.ALL_CHECKS)

    def test_index_drift_check_id_is_stable_and_unique(self):
        self.assertEqual(structural.check_index_drift.check_id, structural.INDEX_DRIFT)

        ids = [check.check_id for check in checks.ALL_CHECKS]
        self.assertEqual(ids.count(structural.INDEX_DRIFT), 1)


if __name__ == "__main__":
    unittest.main()
