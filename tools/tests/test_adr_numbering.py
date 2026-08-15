"""Tests for ADR numbering and supersede pointers (spec criteria 12, 13).

These are the two ADR facts no single page can establish about itself.
`wiki/SCHEMA.md` says "ADRs are append-only. To change a decision, write a new
ADR that supersedes." — which only holds while the number is an *identity* (so
no two ADRs may carry the same one) and while every retirement names a decision
that exists (so no `superseded by` may dangle). Both are properties of the
whole `decisions/` directory, so both are checked across pages rather than
within one, and both are errors: a duplicated number makes the record
unciteable, and a dangling pointer makes it unreadable.

Two deliberate non-behaviours are pinned below, because a linter's silence has
to be as intentional as its noise:

- **Gaps are not reported.** 001, 003, 007 is a fine sequence. ADR numbers are
  identifiers, not a census; a withdrawn draft or a number claimed in a branch
  that never landed leaves a hole, and demanding density would push authors to
  renumber existing ADRs — the one edit an append-only record forbids.
- **The pointer is matched by number, not by link resolution.** `[[adr-002]]`
  in a `Status:` line asks whether *ADR 002 exists*, which is not the same
  question as whether that wikilink resolves to a page. The two answers usually
  agree, and `TestOverlapWithBrokenLink` documents where they do not.

`fixtures/adr-numbering/` is `fixtures/clean/` plus one collision and one
dangling pointer, and it carries a valid supersede chain as its own negative
control. Everything about *matching* is asserted in temporary directories,
where the input sits next to the expectation — the same split `test_adr.py`
uses.
"""

import collections
import pathlib
import tempfile
import unittest

from wiki_health import checks
from wiki_health.checks import schema, structural
from wiki_health.model import Finding, Severity
from wiki_health.pages import discover

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
CLEAN = FIXTURES / "clean"
BAD_ADR = FIXTURES / "bad-adr"
NUMBERING = FIXTURES / "adr-numbering"

# The defects in the adr-numbering fixture, pinned here so a fixture edit fails
# loudly instead of quietly weakening the test.
NUMBER_HOLDER_PAGE = "decisions/adr-002-original.md"
DUPLICATE_NUMBER_PAGE = "decisions/adr-002-reused-number.md"
DANGLING_POINTER_PAGE = "decisions/adr-003-missing-supersede-target.md"
SUPERSEDED_PAGE = "decisions/adr-004-superseded-properly.md"
REPLACEMENT_PAGE = "decisions/adr-005-replacement.md"

# The ADR the fixture's dangling pointer names, and the line it sits on. The
# `Status:` line is line 2 of every ADR the templates produce.
MISSING_NUMBER = "999"
STATUS_LINE = 2

CONFORMANT = """# ADR-00X: A decision that follows the template
Status: accepted
Date: 2026-08-16

## Context
Body.

## Decision
Body.

## Consequences (including what we gave up)
Body.
"""


def write_page(directory, name, text=CONFORMANT):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def with_status(status):
    return CONFORMANT.replace("Status: accepted", f"Status: {status}")


def run_duplicates(root):
    return schema.check_adr_duplicate_number(discover(root), root)


def run_supersedes(root):
    return schema.check_adr_superseded_target(discover(root), root)


def run_broken_links(root):
    return structural.check_broken_links(discover(root), root)


NUMBERING_CHECKS = (run_duplicates, run_supersedes)


def in_temp_wiki(runner, pages):
    """Run one numbering check over a wiki built from `{name: text}`."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in pages.items():
            write_page(tmp, name, text)
        return runner(tmp)


class TestDuplicateNumber(unittest.TestCase):
    def test_duplicate_adr_number_is_an_error(self):
        (finding,) = run_duplicates(NUMBERING)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, schema.ADR_DUPLICATE_NUMBER)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(finding.path, DUPLICATE_NUMBER_PAGE)
        self.assertIsNone(finding.line)
        self.assertFalse(finding.fixed)

    def test_message_names_the_number_and_the_page_holding_it(self):
        (finding,) = run_duplicates(NUMBERING)

        self.assertIn("002", finding.message)
        self.assertIn(NUMBER_HOLDER_PAGE, finding.message)

    def test_distinct_numbers_pass(self):
        pages = {
            "decisions/adr-001-a.md": CONFORMANT,
            "decisions/adr-002-b.md": CONFORMANT,
            "decisions/adr-003-c.md": CONFORMANT,
        }

        self.assertEqual(in_temp_wiki(run_duplicates, pages), [])

    def test_gaps_in_sequence_are_not_reported(self):
        # ADR numbers identify decisions; they do not have to be dense.
        pages = {
            "decisions/adr-001-a.md": CONFORMANT,
            "decisions/adr-003-c.md": CONFORMANT,
            "decisions/adr-007-g.md": CONFORMANT,
        }

        self.assertEqual(in_temp_wiki(run_duplicates, pages), [])

    def test_a_sequence_starting_above_one_is_not_reported(self):
        self.assertEqual(
            in_temp_wiki(run_duplicates, {"decisions/adr-042-only.md": CONFORMANT}), []
        )

    def test_the_first_page_in_path_order_keeps_the_number(self):
        # Deterministic by construction: `discover` sorts by rel_path, so the
        # same collision reports the same page on every platform.
        pages = {
            "decisions/adr-002-aaa.md": CONFORMANT,
            "decisions/adr-002-bbb.md": CONFORMANT,
        }

        (finding,) = in_temp_wiki(run_duplicates, pages)

        self.assertEqual(finding.path, "decisions/adr-002-bbb.md")
        self.assertIn("decisions/adr-002-aaa.md", finding.message)

    def test_a_third_page_with_the_same_number_is_reported_too(self):
        pages = {
            "decisions/adr-002-aaa.md": CONFORMANT,
            "decisions/adr-002-bbb.md": CONFORMANT,
            "decisions/adr-002-ccc.md": CONFORMANT,
        }

        findings = in_temp_wiki(run_duplicates, pages)

        self.assertEqual(
            [f.path for f in findings],
            ["decisions/adr-002-bbb.md", "decisions/adr-002-ccc.md"],
        )

    def test_a_badly_named_adr_has_no_number_to_collide_with(self):
        # `adr-2-x.md` is already an `adr-bad-filename` error; reporting it here
        # as well would make one rename look like two problems.
        pages = {
            "decisions/adr-2-x.md": CONFORMANT,
            "decisions/adr-002-x.md": CONFORMANT,
            "decisions/notes.md": CONFORMANT,
        }

        self.assertEqual(in_temp_wiki(run_duplicates, pages), [])

    def test_pages_outside_decisions_do_not_collide(self):
        pages = {
            "concepts/adr-002-lookalike.md": CONFORMANT,
            "decisions/adr-002-real.md": CONFORMANT,
        }

        self.assertEqual(in_temp_wiki(run_duplicates, pages), [])

    def test_a_nested_adr_still_collides(self):
        # `typed_pages` is recursive, so an archive subdirectory is not a place
        # to park a second ADR under a number already in use.
        pages = {
            "decisions/adr-002-real.md": CONFORMANT,
            "decisions/archive/adr-002-copy.md": CONFORMANT,
        }

        (finding,) = in_temp_wiki(run_duplicates, pages)

        self.assertEqual(finding.path, "decisions/archive/adr-002-copy.md")


class TestSupersededPointer(unittest.TestCase):
    def test_superseded_pointer_to_missing_adr_is_an_error(self):
        (finding,) = run_supersedes(NUMBERING)

        self.assertIsInstance(finding, Finding)
        self.assertEqual(finding.check, schema.ADR_SUPERSEDED_MISSING)
        self.assertEqual(finding.severity, Severity.ERROR)
        self.assertEqual(finding.path, DANGLING_POINTER_PAGE)
        self.assertEqual(finding.line, STATUS_LINE)
        self.assertFalse(finding.fixed)

    def test_message_names_the_missing_adr(self):
        (finding,) = run_supersedes(NUMBERING)

        self.assertIn(MISSING_NUMBER, finding.message)
        self.assertIn(DANGLING_POINTER_PAGE, finding.message)

    def test_valid_supersede_chain_passes(self):
        # The fixture's own chain: 004 is retired by 005, and 005 exists.
        reported = [f.path for f in run_supersedes(NUMBERING)]

        self.assertNotIn(SUPERSEDED_PAGE, reported)
        self.assertNotIn(REPLACEMENT_PAGE, reported)

    def test_accepted_status_is_not_a_pointer(self):
        self.assertEqual(
            in_temp_wiki(run_supersedes, {"decisions/adr-001-a.md": CONFORMANT}), []
        )

    def test_every_legal_pointer_form_resolves_by_number(self):
        for pointer in (
            "[[adr-002]]",
            "[[adr-002-the-replacement]]",
            "[[decisions/adr-002]]",
            "[[decisions/adr-002-the-replacement]]",
        ):
            with self.subTest(pointer=pointer):
                pages = {
                    "decisions/adr-001-a.md": with_status(f"superseded by {pointer}"),
                    "decisions/adr-002-the-replacement.md": CONFORMANT,
                }
                self.assertEqual(in_temp_wiki(run_supersedes, pages), [])

    def test_a_malformed_status_is_left_to_the_status_check(self):
        # These are `adr-bad-status` errors. Re-reporting them here would say
        # the target is missing when what is missing is the syntax to name one.
        for status in (
            "superseded",
            "superseded by adr-002",
            "Superseded by [[adr-002]]",
        ):
            with self.subTest(status=status):
                pages = {"decisions/adr-001-a.md": with_status(status)}
                self.assertEqual(in_temp_wiki(run_supersedes, pages), [])

    def test_a_missing_status_line_is_left_to_the_status_check(self):
        text = CONFORMANT.replace("Status: accepted\n", "")

        self.assertEqual(
            in_temp_wiki(run_supersedes, {"decisions/adr-001-a.md": text}), []
        )

    def test_a_status_line_inside_a_fenced_block_is_not_a_pointer(self):
        text = CONFORMANT.replace(
            "Status: accepted", "```\nStatus: superseded by [[adr-999]]\n```"
        )

        self.assertEqual(
            in_temp_wiki(run_supersedes, {"decisions/adr-001-a.md": text}), []
        )

    def test_the_target_is_matched_by_number_not_by_link_resolution(self):
        # `decisions/adr-777.md` resolves as a wikilink but is not an ADR: it
        # carries no three-digit number in a conformant name, so nothing in the
        # record is numbered 777 and the retirement still names nothing.
        pages = {
            "decisions/adr-001-a.md": with_status(
                "superseded by [[decisions/adr-777]]"
            ),
            "decisions/adr-777.md": CONFORMANT,
        }

        (finding,) = in_temp_wiki(run_supersedes, pages)

        self.assertEqual(finding.path, "decisions/adr-001-a.md")
        self.assertEqual(in_temp_wiki(run_broken_links, pages), [])

    def test_a_target_outside_decisions_does_not_satisfy_the_pointer(self):
        pages = {
            "decisions/adr-001-a.md": with_status(
                "superseded by [[adr-999-elsewhere]]"
            ),
            "concepts/adr-999-elsewhere.md": CONFORMANT,
        }

        (finding,) = in_temp_wiki(run_supersedes, pages)

        self.assertEqual(finding.path, "decisions/adr-001-a.md")

    def test_each_dangling_pointer_is_reported_once(self):
        pages = {
            "decisions/adr-001-a.md": with_status("superseded by [[adr-998]]"),
            "decisions/adr-002-b.md": with_status("superseded by [[adr-999]]"),
            "decisions/adr-003-c.md": CONFORMANT,
        }

        findings = in_temp_wiki(run_supersedes, pages)

        self.assertEqual(
            [f.path for f in findings],
            ["decisions/adr-001-a.md", "decisions/adr-002-b.md"],
        )


class TestOverlapWithBrokenLink(unittest.TestCase):
    """A dangling pointer is also a broken link — by construction, not by accident.

    Any `superseded by [[adr-999]]` naming an ADR that does not exist is also a
    wikilink that resolves to nothing, so both checks fire on the same line. The
    overlap is accepted rather than suppressed, on Task 7's precedent (a stale
    root-index entry is both `index-drift` and `broken-link`): the two checks
    answer different questions, they diverge in both directions — see
    `test_the_target_is_matched_by_number_not_by_link_resolution` — and a check
    that stayed quiet when another one had already spoken would be a check
    nobody could reason about in isolation. The messages carry different repairs.
    """

    def test_a_pointer_to_a_missing_adr_is_also_a_broken_link(self):
        pages = discover(NUMBERING)

        (link,) = [
            f
            for f in structural.check_broken_links(pages, NUMBERING)
            if f.path == DANGLING_POINTER_PAGE
        ]
        (pointer,) = run_supersedes(NUMBERING)

        self.assertEqual(link.line, pointer.line)
        self.assertNotEqual(link.message, pointer.message)

    def test_the_two_messages_name_different_repairs(self):
        (link,) = [
            f
            for f in structural.check_broken_links(discover(NUMBERING), NUMBERING)
            if f.path == DANGLING_POINTER_PAGE
        ]
        (pointer,) = run_supersedes(NUMBERING)

        self.assertIn("unresolved link", link.message)
        self.assertIn("supersed", pointer.message)

    def test_the_fixture_trips_exactly_the_expected_checks(self):
        # The whole registry over the whole fixture: three findings, no
        # incidental orphans, drift, or shape errors.
        counts = collections.Counter(
            f.check for f in checks.run_all(discover(NUMBERING), NUMBERING)
        )

        self.assertEqual(
            counts,
            collections.Counter(
                {
                    schema.ADR_DUPLICATE_NUMBER: 1,
                    schema.ADR_SUPERSEDED_MISSING: 1,
                    structural.BROKEN_LINK: 1,
                }
            ),
        )


class TestCleanFixture(unittest.TestCase):
    def test_the_clean_fixture_yields_no_numbering_findings(self):
        for runner in NUMBERING_CHECKS:
            with self.subTest(check=runner.__name__):
                self.assertEqual(runner(CLEAN), [])

    def test_the_bad_adr_fixture_yields_no_numbering_findings(self):
        # Its four defects are shape defects; none of them is a numbering one,
        # so a numbering check firing there would be reporting the wrong page.
        for runner in NUMBERING_CHECKS:
            with self.subTest(check=runner.__name__):
                self.assertEqual(runner(BAD_ADR), [])

    def test_the_numbering_fixture_is_the_clean_one_plus_five_pages(self):
        clean = {p.rel_path for p in discover(CLEAN)}
        numbering = {p.rel_path for p in discover(NUMBERING)}

        self.assertEqual(
            numbering - clean,
            {
                NUMBER_HOLDER_PAGE,
                DUPLICATE_NUMBER_PAGE,
                DANGLING_POINTER_PAGE,
                SUPERSEDED_PAGE,
                REPLACEMENT_PAGE,
            },
        )
        self.assertEqual(clean - numbering, set())


class TestRegistration(unittest.TestCase):
    def test_numbering_checks_are_registered(self):
        for function in (
            schema.check_adr_duplicate_number,
            schema.check_adr_superseded_target,
        ):
            with self.subTest(check=function.__name__):
                self.assertIn(function, checks.ALL_CHECKS)

    def test_numbering_check_ids_are_stable_and_unique(self):
        expected = {
            schema.check_adr_duplicate_number: schema.ADR_DUPLICATE_NUMBER,
            schema.check_adr_superseded_target: schema.ADR_SUPERSEDED_MISSING,
        }
        ids = [function.check_id for function in checks.ALL_CHECKS]

        for function, check_id in expected.items():
            with self.subTest(check=function.__name__):
                self.assertEqual(function.check_id, check_id)
                self.assertEqual(ids.count(check_id), 1)

        self.assertEqual(len(set(expected.values())), 2)


if __name__ == "__main__":
    unittest.main()
