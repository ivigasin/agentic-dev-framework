"""Tests for the directory-scale check (spec criterion 9, severity `warn`).

`wiki/SCHEMA.md` rule 2: "Beyond ~40 pages per directory → add a directory
INDEX.md." The check is a counting rule, so the only interesting cases sit on
the boundary — 40, 41, and 41-with-an-index — and on what "a directory" means:
siblings and subdirectories are counted apart, and the wiki root is a directory
like any other.

Every wiki here is generated in a temp directory rather than committed under
`fixtures/`, which is a deliberate departure from the two-fixture shape the
other structural tests use. Three reasons:

- 41 near-identical stubs are unreadable as a fixture. Every other fixture in
  this suite is a small wiki whose defect you can see by reading it; a committed
  scale fixture would be 41 files whose defect is only visible by counting them.
- Keeping it honest costs more than the defect is worth. To stop the orphan and
  index-drift checks firing on it, all 41 stubs would need entries in the
  fixture's root `INDEX.md`, and every check added after this one — kebab-case
  filenames, page-template conformance — would have to be kept happy across all
  41 files forever.
- The threshold is the thing under test, and one committed directory can only
  ever express one side of it. Generating from `MAX_DIR_PAGES` lets the tests
  straddle the boundary and stay correct if the constant ever moves.

`TestNoIncidentalFindings` is what pays for the choice: it asserts the generated
wiki trips this check and nothing else, which is the guarantee a committed
fixture would have been giving.
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

# `projects/` on purpose: SCHEMA gives project pages no template, so a stub is
# a conformant project page and the schema checks stay quiet on the generated
# wiki. Stubs under `concepts/` would each trip the concept-template check and
# bury the one finding these tests are about.
BULK_DIR = "projects"

# SCHEMA rule 2, quoted verbatim from `wiki/SCHEMA.md`. The check's message has
# to carry this text, so a drift in either copy fails here.
SCHEMA_RULE_2_TEXT = "Beyond ~40 pages per directory → add a directory INDEX.md"


def write_page(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def stub_names(count):
    return [f"stub-{n:03d}" for n in range(count)]


def build_wiki(tmp, counts, directory_index=()):
    """A wiki with `counts` = {directory: page count}, fully linked from INDEX.md.

    Every generated page gets an entry in the root index, so the wiki's *only*
    possible defect is how many pages sit in one directory. `directory_index`
    names the directories that also get an `INDEX.md`.
    """
    root = pathlib.Path(tmp)
    entries = []
    for directory, count in counts.items():
        for stub in stub_names(count):
            rel = stub if directory == "." else f"{directory}/{stub}"
            write_page(root, f"{rel}.md", f"# {stub}\n\nA stub page.\n")
            entries.append(f"- [[{rel}]]")
    for directory in directory_index:
        write_page(root, f"{directory}/INDEX.md", f"# {directory}\n")
        entries.append(f"- [[{directory}/INDEX]]")
    write_page(root, "INDEX.md", "# Index\n\n## Projects\n" + "\n".join(entries) + "\n")
    return root


def run_check(root):
    return structural.check_directory_scale(discover(root), root)


class TestThreshold(unittest.TestCase):
    def test_directory_over_forty_pages_without_index_is_a_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, {BULK_DIR: structural.MAX_DIR_PAGES + 1})

            (finding,) = run_check(tmp)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, structural.DIRECTORY_SCALE)
        self.assertEqual(finding.severity, Severity.WARN)
        self.assertEqual(finding.path, BULK_DIR)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)

    def test_same_directory_with_an_index_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(
                tmp,
                {BULK_DIR: structural.MAX_DIR_PAGES + 1},
                directory_index=[BULK_DIR],
            )

            self.assertEqual(run_check(tmp), [])

    def test_exactly_forty_pages_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, {BULK_DIR: structural.MAX_DIR_PAGES})

            self.assertEqual(run_check(tmp), [])

    def test_threshold_is_the_named_constant(self):
        self.assertEqual(structural.MAX_DIR_PAGES, 40)


class TestMessage(unittest.TestCase):
    def message(self, tmp):
        build_wiki(tmp, {BULK_DIR: structural.MAX_DIR_PAGES + 1})
        (finding,) = run_check(tmp)
        return finding.message

    def test_message_quotes_schema_rule_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            message = self.message(tmp)

        self.assertIn(SCHEMA_RULE_2_TEXT, message)

    def test_message_names_the_directory_its_count_and_the_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            message = self.message(tmp)

        self.assertIn(BULK_DIR, message)
        self.assertIn(str(structural.MAX_DIR_PAGES + 1), message)
        self.assertIn(f"{BULK_DIR}/INDEX.md", message)


class TestDirectoryScope(unittest.TestCase):
    def test_sibling_directories_are_counted_apart(self):
        # 25 + 25 is 50 pages and no finding: the budget is per directory, and
        # summing siblings would punish a wiki for being well organised.
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, {"projects": 25, "concepts-ish": 25})

            self.assertEqual(run_check(tmp), [])

    def test_subdirectory_pages_do_not_count_toward_the_parent(self):
        # The repair SCHEMA rule 2 asks for is a *directory* INDEX.md, so the
        # count has to be per directory, not per subtree — otherwise splitting
        # an oversized directory into subdirectories would never clear it.
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, {"projects": 21, "projects/sub": 21})

            self.assertEqual(run_check(tmp), [])

    def test_each_oversized_directory_is_reported_once(self):
        over = structural.MAX_DIR_PAGES + 1
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, {"projects": over, "notes": over})

            findings = run_check(tmp)

        self.assertEqual(sorted(f.path for f in findings), ["notes", "projects"])


class TestWikiRoot(unittest.TestCase):
    def test_the_wiki_root_is_a_directory_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for stub in stub_names(structural.MAX_DIR_PAGES + 1):
                write_page(root, f"{stub}.md", f"# {stub}\n")

            (finding,) = run_check(tmp)

        self.assertEqual(finding.path, structural.WIKI_ROOT_DIR)
        self.assertEqual(finding.severity, Severity.WARN)

    def test_the_root_index_exempts_the_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, {".": structural.MAX_DIR_PAGES + 1})

            self.assertEqual(run_check(tmp), [])

    def test_root_finding_message_says_wiki_root_not_a_dot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for stub in stub_names(structural.MAX_DIR_PAGES + 1):
                write_page(root, f"{stub}.md", f"# {stub}\n")

            (finding,) = run_check(tmp)

        self.assertIn("wiki root", finding.message)
        self.assertIn("INDEX.md", finding.message)


class TestIndexRecognition(unittest.TestCase):
    def test_index_is_matched_by_exact_filename(self):
        # `index.md` is not the file SCHEMA rule 2 names, and treating it as one
        # would let a directory look indexed to this tool while the kebab-case
        # and link checks disagree about which file the index actually is.
        with tempfile.TemporaryDirectory() as tmp:
            root = build_wiki(tmp, {BULK_DIR: structural.MAX_DIR_PAGES + 1})
            write_page(root, f"{BULK_DIR}/index.md", "# lowercase\n")

            (finding,) = run_check(tmp)

        self.assertEqual(finding.path, BULK_DIR)

    def test_an_index_elsewhere_does_not_exempt_this_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(
                tmp,
                {BULK_DIR: structural.MAX_DIR_PAGES + 1, "notes": 1},
                directory_index=["notes"],
            )

            (finding,) = run_check(tmp)

        self.assertEqual(finding.path, BULK_DIR)


class TestNoIncidentalFindings(unittest.TestCase):
    """The guarantee a committed fixture would have carried, asserted instead."""

    def test_the_generated_wiki_trips_this_check_and_no_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, {BULK_DIR: structural.MAX_DIR_PAGES + 1})

            findings = checks.run_all(discover(tmp), tmp)

        self.assertEqual([f.check for f in findings], [structural.DIRECTORY_SCALE])

    def test_the_indexed_variant_trips_nothing_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(
                tmp,
                {BULK_DIR: structural.MAX_DIR_PAGES + 1},
                directory_index=[BULK_DIR],
            )

            self.assertEqual(checks.run_all(discover(tmp), tmp), [])


class TestCleanFixture(unittest.TestCase):
    def test_clean_fixture_yields_no_scale_findings(self):
        self.assertEqual(run_check(CLEAN), [])

    def test_an_empty_wiki_yields_no_scale_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_check(tmp), [])


class TestRegistration(unittest.TestCase):
    def test_scale_check_is_registered(self):
        self.assertIn(structural.check_directory_scale, checks.ALL_CHECKS)

    def test_scale_check_id_is_stable_and_unique(self):
        self.assertEqual(
            structural.check_directory_scale.check_id, structural.DIRECTORY_SCALE
        )

        ids = [check.check_id for check in checks.ALL_CHECKS]
        self.assertEqual(ids.count(structural.DIRECTORY_SCALE), 1)


if __name__ == "__main__":
    unittest.main()
