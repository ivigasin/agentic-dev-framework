"""Tests for the broken-link auto-fix (spec criterion 16).

This is the riskiest behaviour in the tool: a wrong rewrite silently changes
what a page says, and nothing downstream will ever notice. So the tests are
weighted towards the *refusals* rather than the repairs — most of what follows
asserts that a file came back byte-identical.

Three rules shape them:

- **Exactly one candidate at or above the threshold.** Not the best candidate,
  not the closest one: one. `TestSeveralCandidatesAreLeftUnfixed` pins the
  argmax reading shut with two candidates of *different* scores, because
  "closest wins" is the natural thing to write and is wrong here.
- **The boundary is tested from both sides.** `SequenceMatcher` ratios are
  arithmetic — `2 * matches / total_length` — so a pair scoring exactly
  `LINK_FIX_MIN_RATIO` and a pair scoring just under it can both be constructed
  by hand rather than hunted for. `abcd`/`abcx` is 6/8; `abcdxy`/`abcde` is
  8/11.
- **Never touch the committed fixture.** Criterion 27. Every test that needs a
  wiki on disk copies one, and `TestFixtureIsUntouched` proves the copy really
  was rewritten so the assertion cannot pass vacuously.

`fixtures/broken-link-fix/` is the clean fixture with one character changed —
`[[demo]]` became `[[demoo]]` — so it carries exactly one finding and the tests
can assert on counts. Every other shape is built inline in a temp wiki, where
the expected outcome sits next to the assertion.
"""

import hashlib
import io
import inspect
import pathlib
import shutil
import tempfile
import tokenize
import unittest

from wiki_health import checks, fixes
from wiki_health.checks import structural
from wiki_health.pages import discover

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
BROKEN = FIXTURES / "broken-link-fix"

TYPO_PAGE = "concepts/alpha.md"
TYPO_LINE = 12  # 1-based, the `## Related:` line
TYPO_LINK = "[[demoo]]"
REPAIRED_LINK = "[[projects/demo]]"


def write_page(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def copy_fixture(tmp, source=BROKEN):
    """The fixture, copied somewhere writable. The original is never opened."""
    destination = pathlib.Path(tmp) / "wiki"
    shutil.copytree(source, destination)
    return destination


def digest(root):
    """A content hash of a whole directory tree — path names included."""
    hasher = hashlib.sha256()
    for path in sorted(pathlib.Path(root).rglob("*")):
        hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
        if path.is_file():
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


def run_fix(root, dry_run=False):
    pages = discover(root)
    findings = checks.run_all(pages, root)
    return fixes.run_fixes(pages, root, findings, dry_run=dry_run)


def read(root, rel_path):
    return (pathlib.Path(root) / rel_path).read_text(encoding="utf-8")


def lines_of(root, rel_path):
    return read(root, rel_path).splitlines()


def link_findings(findings):
    return [f for f in findings if f.check == structural.BROKEN_LINK]


def keys(findings):
    return sorted((f.check, f.path, f.line) for f in findings)


def one_source_wiki(tmp, link, stems, source="concepts/source.md"):
    """A minimal wiki: one page carrying `link`, plus a page per stem.

    `INDEX.md` links the source page so the link under test is the only thing
    that varies between cases. The other checks still fire on these wikis —
    they are not schema-conformant — which is deliberate: the fix must behave
    the same in a wiki that has other problems.
    """
    write_page(tmp, "INDEX.md", f"# I\n\n## Concepts\n- [[{source[:-3]}]]\n")
    write_page(tmp, source, f"# Source\n\nSee [[{link}]] for details.\n")
    for stem in stems:
        write_page(tmp, f"concepts/{stem}.md", f"# {stem}\n")
    return tmp


class TestSingleCloseMatchIsRewritten(unittest.TestCase):
    def test_single_close_match_above_threshold_is_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            run_fix(root)
            line = lines_of(root, TYPO_PAGE)[TYPO_LINE - 1]

        self.assertIn(REPAIRED_LINK, line)
        self.assertNotIn(TYPO_LINK, line)

    def test_the_rest_of_the_line_is_preserved_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)
            before = lines_of(root, TYPO_PAGE)[TYPO_LINE - 1]

            run_fix(root)
            after = lines_of(root, TYPO_PAGE)[TYPO_LINE - 1]

        self.assertEqual(before.replace(TYPO_LINK, REPAIRED_LINK), after)

    def test_no_other_line_in_the_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)
            before = lines_of(root, TYPO_PAGE)

            run_fix(root)
            after = lines_of(root, TYPO_PAGE)

        self.assertEqual(len(before), len(after))
        differing = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(differing, [TYPO_LINE - 1])

    def test_no_other_page_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            plan = run_fix(root)

        self.assertEqual(plan.written, (TYPO_PAGE,))

    def test_the_repair_is_reported_as_fixed_not_as_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            plan = run_fix(root)

        self.assertEqual(plan.remaining, ())
        self.assertEqual(keys(plan.fixed), [(structural.BROKEN_LINK, TYPO_PAGE, TYPO_LINE)])
        self.assertTrue(all(finding.fixed for finding in plan.fixed))

    def test_the_repaired_wiki_is_actually_clean(self):
        # The `fixed` marker is only honest if the defect is gone from disk.
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            run_fix(root)

            self.assertEqual(checks.run_all(discover(root), root), [])

    def test_the_rewrite_is_directory_qualified(self):
        # Bare `[[demo]]` would resolve today and break the day a second page
        # takes the stem — the same call Task 14 makes for new index entries.
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            run_fix(root)

            self.assertIn(REPAIRED_LINK, read(root, TYPO_PAGE))

    def test_a_match_at_exactly_the_threshold_is_rewritten(self):
        # `abcd` vs `abcx`: 2 * 3 / 8 == 0.75. The boundary is inclusive.
        with tempfile.TemporaryDirectory() as tmp:
            one_source_wiki(tmp, "abcd", ["abcx"])

            run_fix(tmp)

            self.assertIn("[[concepts/abcx]]", read(tmp, "concepts/source.md"))


class TestSeveralCandidatesAreLeftUnfixed(unittest.TestCase):
    def test_two_candidates_above_threshold_are_left_unfixed(self):
        # `alph` scores 0.888 against both. Neither is more right than the other.
        with tempfile.TemporaryDirectory() as tmp:
            one_source_wiki(tmp, "alph", ["alpha", "alphx"])

            run_fix(tmp)

            self.assertIn("[[alph]]", read(tmp, "concepts/source.md"))

    def test_the_closest_of_two_candidates_is_not_chosen(self):
        # 0.909 vs 0.800 — both above the threshold. The rule is "exactly one
        # candidate qualifies", not "the best qualifying candidate wins", and
        # this is the test that keeps it that way.
        with tempfile.TemporaryDirectory() as tmp:
            one_source_wiki(tmp, "alpha", ["alphaa", "alphb"])

            run_fix(tmp)

            self.assertIn("[[alpha]]", read(tmp, "concepts/source.md"))

    def test_an_ambiguous_link_is_not_rewritten(self):
        # Two pages share the stem, so both score 1.0. An ambiguous link names
        # two pages, not none; the repair is to qualify it, which needs a human.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n## Concepts\n- [[concepts/source]]\n")
            write_page(tmp, "concepts/source.md", "# Source\n\nSee [[alpha]].\n")
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")
            write_page(tmp, "projects/alpha.md", "# Alpha\n")

            plan = run_fix(tmp)
            text = read(tmp, "concepts/source.md")

        self.assertIn("[[alpha]]", text)
        self.assertTrue(link_findings(plan.remaining))

    def test_three_candidates_are_left_unfixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            one_source_wiki(tmp, "alph", ["alpha", "alphx", "alphy"])

            run_fix(tmp)

            self.assertIn("[[alph]]", read(tmp, "concepts/source.md"))


class TestMatchesBelowThresholdAreLeftUnfixed(unittest.TestCase):
    def test_match_below_threshold_is_left_unfixed(self):
        # `abcdxy` vs `abcde`: 2 * 4 / 11 == 0.727, just under the line.
        with tempfile.TemporaryDirectory() as tmp:
            one_source_wiki(tmp, "abcdxy", ["abcde"])

            run_fix(tmp)

            self.assertIn("[[abcdxy]]", read(tmp, "concepts/source.md"))

    def test_a_target_resembling_nothing_is_left_unfixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            one_source_wiki(tmp, "wibble", ["alpha"])

            run_fix(tmp)

            self.assertIn("[[wibble]]", read(tmp, "concepts/source.md"))

    def test_a_qualified_target_is_compared_as_written(self):
        # `concepts/alpah` vs the stem `alpha` scores far below the threshold,
        # so a typo inside a qualified link is reported rather than guessed at.
        # Comparing only the last segment would fix more links and would also
        # let a wrong *directory* be silently rewritten; criterion 16 says
        # prefer reporting.
        with tempfile.TemporaryDirectory() as tmp:
            one_source_wiki(tmp, "concepts/alpah", ["alpha"])

            plan = run_fix(tmp)

        self.assertIn("[[concepts/alpah]]", read(tmp, "concepts/source.md"))
        self.assertTrue(link_findings(plan.remaining))

    def test_an_empty_wiki_of_candidates_rewrites_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n## Concepts\n- [[concepts/source]]\n")
            write_page(tmp, "concepts/source.md", "# Source\n\nSee [[nowhere]].\n")

            run_fix(tmp)

            self.assertIn("[[nowhere]]", read(tmp, "concepts/source.md"))


class TestUnfixedCasesRemainFindings(unittest.TestCase):
    def test_unfixed_cases_remain_as_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            one_source_wiki(tmp, "alph", ["alpha", "alphx"])

            plan = run_fix(tmp)

        remaining = link_findings(plan.remaining)
        self.assertEqual([f.path for f in remaining], ["concepts/source.md"])
        self.assertFalse(any(f.fixed for f in remaining))
        self.assertEqual(link_findings(plan.fixed), [])

    def test_a_fixable_and_an_unfixable_link_are_reported_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n## Concepts\n- [[concepts/source]]\n")
            write_page(
                tmp,
                "concepts/source.md",
                "# Source\n\nSee [[alph]] and [[wibble]].\n",
            )
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")
            write_page(tmp, "concepts/alphx.md", "# Alphx\n")

            plan = run_fix(tmp)

        self.assertEqual(len(link_findings(plan.remaining)), 2)
        self.assertEqual(link_findings(plan.fixed), [])

    def test_only_the_broken_link_on_a_shared_line_is_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n## Concepts\n- [[concepts/source]]\n")
            write_page(
                tmp,
                "concepts/source.md",
                "# Source\n\nSee [[concepts/alpha]] and [[wibble]] and [[demoo]].\n",
            )
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")
            write_page(tmp, "projects/demo.md", "# Demo\n")

            run_fix(tmp)
            line = lines_of(tmp, "concepts/source.md")[2]

        self.assertEqual(
            line,
            "See [[concepts/alpha]] and [[wibble]] and [[projects/demo]].",
        )


class TestFencedBlocksAreInert(unittest.TestCase):
    def test_a_link_inside_a_fence_is_never_rewritten(self):
        # `pages.py` never reports fenced links, so they are not findings; the
        # fix must not reach them either, or documenting link syntax would
        # rewrite the documentation.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n## Concepts\n- [[concepts/source]]\n")
            write_page(
                tmp,
                "concepts/source.md",
                "# Source\n\n```md\nSee [[demoo]].\n```\n",
            )
            write_page(tmp, "projects/demo.md", "# Demo\n")

            run_fix(tmp)

            self.assertIn("[[demoo]]", read(tmp, "concepts/source.md"))

    def test_a_fenced_link_does_not_suppress_a_real_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "INDEX.md", "# I\n\n## Concepts\n- [[concepts/source]]\n")
            write_page(
                tmp,
                "concepts/source.md",
                "# Source\n\n```md\nSee [[demoo]].\n```\n\nSee [[demoo]].\n",
            )
            write_page(tmp, "projects/demo.md", "# Demo\n")

            run_fix(tmp)
            lines = lines_of(tmp, "concepts/source.md")

        self.assertEqual(lines[3], "See [[demoo]].")
        self.assertEqual(lines[6], "See [[projects/demo]].")


class TestIndexEntriesAreRepairedNotDeleted(unittest.TestCase):
    def test_a_typo_in_an_index_entry_is_repaired_not_deleted(self):
        # The index-drift pass deletes a list entry whose links all name
        # nothing. A typo *does* name nothing, so ordering decides whether the
        # entry — and the prose beside it — survives. Repair before delete.
        with tempfile.TemporaryDirectory() as tmp:
            write_page(
                tmp,
                "INDEX.md",
                "# I\n\n## Concepts\n- [[alpah]] — the founding concept.\n",
            )
            write_page(tmp, "concepts/alpha.md", "# Alpha\n")

            plan = run_fix(tmp)

        self.assertIn(
            "- [[concepts/alpha]] — the founding concept.",
            read(tmp, "INDEX.md"),
        )
        self.assertEqual(plan.remaining, ())


class TestNothingToFix(unittest.TestCase):
    def test_the_clean_fixture_plans_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp, source=FIXTURES / "clean")
            before = digest(root)

            plan = run_fix(root)

            self.assertEqual(plan.edits, ())
            self.assertEqual(digest(root), before)

    def test_an_empty_wiki_plans_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = run_fix(tmp)

        self.assertEqual(plan.edits, ())


class TestDryRunWritesNothing(unittest.TestCase):
    def test_dry_run_leaves_the_copy_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)
            before = digest(root)

            plan = run_fix(root, dry_run=True)

            self.assertEqual(digest(root), before)
            self.assertEqual([edit.rel_path for edit in plan.edits], [TYPO_PAGE])
            self.assertEqual(plan.written, ())

    def test_dry_run_reports_the_same_repairs_as_a_real_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            dry = run_fix(root, dry_run=True)
            wet = run_fix(root, dry_run=False)

        self.assertEqual(keys(dry.fixed), keys(wet.fixed))
        self.assertEqual(dry.edits, wet.edits)

    def test_the_summary_names_the_old_and_the_new_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)

            plan = run_fix(root, dry_run=True)

        summaries = "\n".join(plan.edits[0].summaries)
        self.assertIn(TYPO_LINK, summaries)
        self.assertIn(REPAIRED_LINK, summaries)


class TestFixtureIsUntouched(unittest.TestCase):
    def test_original_fixture_is_untouched(self):
        before = digest(BROKEN)

        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp)
            copy_before = digest(root)

            run_fix(root)

            # The guard that keeps this test honest: if the fix did nothing,
            # "the original is unchanged" would pass for the wrong reason.
            self.assertNotEqual(digest(root), copy_before)

        self.assertEqual(digest(BROKEN), before)

    def test_the_fixture_carries_exactly_one_defect(self):
        findings = checks.run_all(discover(BROKEN), BROKEN)

        self.assertEqual(keys(findings), [(structural.BROKEN_LINK, TYPO_PAGE, TYPO_LINE)])


class TestThreshold(unittest.TestCase):
    def test_the_threshold_is_a_named_constant(self):
        self.assertEqual(fixes.LINK_FIX_MIN_RATIO, 0.75)

    def test_the_threshold_literal_appears_exactly_once(self):
        # Tokenized rather than grepped, so prose in a docstring explaining the
        # number is not mistaken for a second copy of it.
        source = inspect.getsource(fixes)
        numbers = [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type == tokenize.NUMBER
        ]

        self.assertEqual(numbers.count("0.75"), 1)


class TestPassRegistration(unittest.TestCase):
    def test_the_broken_link_pass_is_registered_once(self):
        ids = [function.check_id for function in fixes.ALL_FIXES]

        self.assertEqual(ids.count(structural.BROKEN_LINK), 1)

    def test_link_repair_runs_before_index_entry_deletion(self):
        ids = [function.check_id for function in fixes.ALL_FIXES]

        self.assertLess(ids.index(structural.BROKEN_LINK), ids.index(fixes.INDEX_DRIFT))


if __name__ == "__main__":
    unittest.main()
