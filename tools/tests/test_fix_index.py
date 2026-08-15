"""Tests for the index-drift auto-fix (spec criteria 15, 27).

Two rules shape every test here:

- **Never touch the committed fixture.** Criterion 27. Each test copies
  `fixtures/index-drift/` into a temp directory with `shutil.copytree` and works
  on the copy; `TestFixtureIsUntouched` proves the original's content hash is
  unchanged *and* that the copy really was rewritten, so the assertion cannot
  pass by the fix having done nothing.
- **A fix is only a fix if the finding goes away.** The repaired items must come
  back marked `fixed`, and re-running the checks over the repaired wiki must
  return nothing. Asserting only on the marker would let a cosmetic edit that
  leaves the wiki broken look like a successful repair.

`fixtures/index-drift/` carries exactly the two defects this fix owns — a page
three hops from the index, and an index entry naming a deleted page — so the
tests can assert on counts. Everything else is built inline in a temp wiki,
where the expected shape sits next to the assertion.
"""

import hashlib
import pathlib
import shutil
import tempfile
import unittest

from wiki_health import checks, fixes
from wiki_health.pages import discover

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
DRIFT = FIXTURES / "index-drift"

ROOT_INDEX = "INDEX.md"

# The two defects in the fixture, pinned so a fixture edit fails loudly here
# rather than quietly weakening the tests.
DRIFTED_PAGE = "concepts/gamma.md"  # three hops: INDEX -> alpha -> beta -> here
DRIFTED_LINK = "[[concepts/gamma]]"
STALE_TARGET = "concepts/deleted"  # an INDEX.md entry whose page was deleted


def write_page(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def copy_fixture(tmp, source=DRIFT):
    """The fixture, copied somewhere writable. The original is never opened."""
    destination = pathlib.Path(tmp) / "wiki"
    shutil.copytree(source, destination)
    return destination


def digest(root):
    """A content hash of a whole directory tree — path names included.

    Names are hashed alongside bytes so a rename, an addition, or a deletion
    moves the digest even when the surviving bytes are identical.
    """
    hasher = hashlib.sha256()
    for path in sorted(pathlib.Path(root).rglob("*")):
        hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
        if path.is_file():
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


def run_fix(root, dry_run=False):
    """Discover, check, fix — what Task 16 will wire the CLI's `--fix` into."""
    pages = discover(root)
    findings = checks.run_all(pages, root)
    return fixes.run_fixes(pages, root, findings, dry_run=dry_run)


def remaining_findings(root):
    return checks.run_all(discover(root), root)


def index_lines(root):
    return (pathlib.Path(root) / ROOT_INDEX).read_text(encoding="utf-8").splitlines()


def section_body(lines, heading):
    """The lines under `## <heading>` up to the next `## ` heading."""
    body = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            inside = line.strip() == heading
            continue
        if inside:
            body.append(line)
    return body


def keys(findings):
    return sorted((f.check, f.path) for f in findings)


class TestMissingPageIsIndexed(unittest.TestCase):
    def test_missing_page_is_added_to_the_correct_index_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            run_fix(root)
            lines = index_lines(root)

        self.assertIn(
            DRIFTED_LINK,
            "\n".join(section_body(lines, fixes.INDEX_SECTIONS["concepts"])),
        )

    def test_the_entry_lands_in_no_other_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            run_fix(root)
            lines = index_lines(root)

        others = ["## Decisions (ADRs)", "## Projects", "## Maintenance"]
        for heading in others:
            self.assertNotIn("gamma", "\n".join(section_body(lines, heading)), heading)

    def test_the_section_keeps_the_entries_it_already_had(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            run_fix(root)
            lines = index_lines(root)

        concepts = "\n".join(section_body(lines, fixes.INDEX_SECTIONS["concepts"]))
        self.assertIn("[[concepts/alpha]]", concepts)

    def test_the_page_is_one_hop_from_the_index_afterwards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            run_fix(root)
            depths = fixes.structural.hop_depths(discover(root))

        self.assertEqual(depths[DRIFTED_PAGE], 1)

    def test_a_decision_page_goes_under_the_adr_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, ROOT_INDEX, "# I\n\n## Concepts\n\n## Decisions (ADRs)\n")
            write_page(tmp, "decisions/adr-002-thing.md", "# ADR-002\n")

            run_fix(tmp)
            lines = index_lines(tmp)

        self.assertIn(
            "[[decisions/adr-002-thing]]",
            "\n".join(section_body(lines, fixes.INDEX_SECTIONS["decisions"])),
        )

    def test_a_project_page_goes_under_the_projects_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, ROOT_INDEX, "# I\n\n## Projects\n")
            write_page(tmp, "projects/demo.md", "# Demo\n")

            run_fix(tmp)
            lines = index_lines(tmp)

        self.assertIn(
            "[[projects/demo]]",
            "\n".join(section_body(lines, fixes.INDEX_SECTIONS["projects"])),
        )


class TestAbsentSectionIsReportedNotInvented(unittest.TestCase):
    def test_missing_section_heading_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, ROOT_INDEX, "# I\n\n## Projects\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            run_fix(tmp)
            text = (pathlib.Path(tmp) / ROOT_INDEX).read_text(encoding="utf-8")

        self.assertNotIn("Concepts", text)
        self.assertNotIn("alpha", text)

    def test_unindexable_page_stays_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, ROOT_INDEX, "# I\n\n## Projects\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            plan = run_fix(tmp)

        self.assertIn(("index-drift", "concepts/alpha.md"), keys(plan.remaining))
        self.assertEqual(plan.fixed, ())

    def test_a_page_in_an_unmapped_directory_stays_a_finding(self):
        # `notes/` has no section in the real `wiki/INDEX.md`, so there is no
        # right answer to guess at.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, ROOT_INDEX, "# I\n\n## Concepts\n")
            write_page(tmp, "notes/scratch.md", "# Scratch\n")

            plan = run_fix(tmp)

        self.assertIn(("index-drift", "notes/scratch.md"), keys(plan.remaining))


class TestStaleEntryIsRemoved(unittest.TestCase):
    def test_entry_for_a_deleted_file_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            run_fix(root)
            text = (root / ROOT_INDEX).read_text(encoding="utf-8")

        self.assertNotIn(STALE_TARGET, text)

    def test_only_the_stale_line_goes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)
            before = index_lines(root)

            run_fix(root)
            after = index_lines(root)

        gone = [line for line in before if line not in after]
        self.assertEqual(len(gone), 1)
        self.assertIn(STALE_TARGET, gone[0])

    def test_an_ambiguous_entry_is_not_deleted(self):
        # Two pages match `[[alpha]]`. The repair is to qualify the entry with a
        # directory, not to drop it — deleting would destroy the one clue about
        # what the index meant.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, ROOT_INDEX, "# I\n\n## Concepts\n- [[alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")
            write_page(tmp, "projects/alpha.md", "# Alpha\n")

            plan = run_fix(tmp)
            text = (pathlib.Path(tmp) / ROOT_INDEX).read_text(encoding="utf-8")

        self.assertIn("- [[alpha]]", text)
        self.assertIn(("index-drift", ROOT_INDEX), keys(plan.remaining))

    def test_a_prose_line_is_reported_rather_than_rewritten(self):
        # Not a list entry: dropping the whole line would take real prose with
        # it, so the fix reports and leaves it.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(
                tmp,
                ROOT_INDEX,
                "# I\n\nStart at [[missing]] for context.\n\n## Concepts\n",
            )

            plan = run_fix(tmp)
            text = (pathlib.Path(tmp) / ROOT_INDEX).read_text(encoding="utf-8")

        self.assertIn("Start at [[missing]] for context.", text)
        self.assertIn(("index-drift", ROOT_INDEX), keys(plan.remaining))

    def test_a_line_with_one_live_link_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(
                tmp,
                ROOT_INDEX,
                "# I\n\n## Concepts\n- [[concepts/alpha]] and [[gone]]\n",
            )
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            run_fix(tmp)
            text = (pathlib.Path(tmp) / ROOT_INDEX).read_text(encoding="utf-8")

        self.assertIn("[[concepts/alpha]] and [[gone]]", text)

    def test_a_dead_link_outside_the_root_index_is_not_touched(self):
        # Ordinary pages are Task 15's business; this pass owns INDEX.md only.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, ROOT_INDEX, "# I\n\n## Concepts\n- [[concepts/alpha]]\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n\n- [[nowhere]]\n")

            run_fix(tmp)
            text = (pathlib.Path(tmp) / "concepts/alpha.md").read_text(encoding="utf-8")

        self.assertIn("[[nowhere]]", text)


class TestFixedItemsAreReportedAsFixed(unittest.TestCase):
    def test_fixed_items_are_reported_as_fixed_not_as_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            plan = run_fix(root)

        self.assertEqual(plan.remaining, ())
        self.assertTrue(plan.fixed)
        self.assertTrue(all(finding.fixed for finding in plan.fixed))

    def test_every_original_finding_is_accounted_for(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)
            before = checks.run_all(discover(root), root)

            plan = run_fix(root)

        self.assertEqual(keys(plan.fixed), keys(before))

    def test_the_repaired_wiki_is_actually_clean(self):
        # The marker is only honest if the defect is gone from disk too.
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            run_fix(root)

            self.assertEqual(remaining_findings(root), [])

    def test_unrepaired_findings_are_not_marked_fixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, ROOT_INDEX, "# I\n\n## Projects\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            plan = run_fix(tmp)

        self.assertTrue(plan.remaining)
        self.assertFalse(any(finding.fixed for finding in plan.remaining))

    def test_the_report_findings_are_the_fixed_plus_the_remaining(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            plan = run_fix(root)

        self.assertEqual(list(plan.findings()), list(plan.fixed) + list(plan.remaining))


class TestDryRunWritesNothing(unittest.TestCase):
    def test_dry_run_leaves_the_copy_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)
            before = digest(root)

            run_fix(root, dry_run=True)

            self.assertEqual(digest(root), before)

    def test_dry_run_still_reports_the_intended_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            dry = run_fix(root, dry_run=True)
            wet = run_fix(root, dry_run=False)

        self.assertEqual([edit.rel_path for edit in dry.edits], [ROOT_INDEX])
        self.assertEqual(keys(dry.fixed), keys(wet.fixed))
        self.assertEqual(dry.written, ())
        self.assertEqual(wet.written, (ROOT_INDEX,))

    def test_planning_alone_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)
            before = digest(root)
            pages = discover(root)

            plan = fixes.plan_fixes(pages, root, checks.run_all(pages, root))

            self.assertTrue(plan.edits)
            self.assertEqual(digest(root), before)


class TestFixtureIsUntouched(unittest.TestCase):
    def test_original_fixture_is_untouched(self):
        before = digest(DRIFT)

        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)
            copy_before = digest(root)

            run_fix(root)

            # The guard that keeps this test honest: if the fix did nothing,
            # "the original is unchanged" would pass for the wrong reason.
            self.assertNotEqual(digest(root), copy_before)

        self.assertEqual(digest(DRIFT), before)


class TestPassRegistration(unittest.TestCase):
    def test_the_index_pass_is_registered_once(self):
        ids = [fix.check_id for fix in fixes.ALL_FIXES]

        self.assertIn(fixes.INDEX_DRIFT, ids)
        self.assertEqual(ids.count(fixes.INDEX_DRIFT), 1)

    def test_every_fix_targets_a_real_check_id(self):
        check_ids = {function.check_id for function in checks.ALL_CHECKS}

        for fix in fixes.ALL_FIXES:
            self.assertIn(fix.check_id, check_ids)


class TestNoIndexToFix(unittest.TestCase):
    def test_a_wiki_without_a_root_index_is_reported_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            plan = run_fix(tmp)

        self.assertEqual(plan.edits, ())
        self.assertEqual(plan.fixed, ())
        self.assertFalse((pathlib.Path(tmp) / ROOT_INDEX).exists())

    def test_an_empty_wiki_plans_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = run_fix(tmp)

        self.assertEqual(plan.edits, ())
        self.assertEqual(plan.findings(), [])

    def test_a_clean_wiki_plans_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp, source=FIXTURES / "clean")
            before = digest(root)

            plan = run_fix(root)

            self.assertEqual(plan.edits, ())
            self.assertEqual(digest(root), before)


if __name__ == "__main__":
    unittest.main()
