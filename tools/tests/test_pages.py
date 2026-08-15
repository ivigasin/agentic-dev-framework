"""Tests for page discovery and wikilink parsing.

Two kinds of test live here. Discovery and link-shape tests read the clean
fixture, because that fixture is the negative control every later check task
asserts against — if it stops parsing the way these tests say, ten downstream
tasks break. Line-number tests write a throwaway file instead, so the expected
numbers are visible in the test rather than tied to a fixture's whitespace.

Nothing here touches the repo's real `wiki/`.
"""

import pathlib
import tempfile
import unittest

from wiki_health.pages import Page, discover, load

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
CLEAN = FIXTURES / "clean"

# The clean fixture's full inventory. Spelled out rather than globbed so that a
# page silently appearing or vanishing fails a test instead of passing one.
CLEAN_PAGES = {
    "INDEX.md",
    "SCHEMA.md",
    "log.md",
    "concepts/alpha.md",
    "decisions/adr-001-example.md",
    "projects/demo.md",
}


def page_by_rel_path(pages, rel_path):
    (match,) = [p for p in pages if p.rel_path == rel_path]
    return match


def write_page(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestDiscovery(unittest.TestCase):
    def test_discovers_every_markdown_page(self):
        pages = discover(CLEAN)

        self.assertEqual({p.rel_path for p in pages}, CLEAN_PAGES)

    def test_discovery_recurses_into_subdirectories(self):
        pages = discover(CLEAN)
        nested = page_by_rel_path(pages, "concepts/alpha.md")

        self.assertEqual(nested.path, CLEAN / "concepts" / "alpha.md")

    def test_rel_path_uses_forward_slashes(self):
        for page in discover(CLEAN):
            self.assertNotIn("\\", page.rel_path)

    def test_name_is_the_filename_stem(self):
        pages = discover(CLEAN)

        self.assertEqual(page_by_rel_path(pages, "concepts/alpha.md").name, "alpha")
        self.assertEqual(
            page_by_rel_path(pages, "decisions/adr-001-example.md").name,
            "adr-001-example",
        )

    def test_discovery_order_is_stable(self):
        first = [p.rel_path for p in discover(CLEAN)]
        second = [p.rel_path for p in discover(CLEAN)]

        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first))

    def test_non_markdown_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "kept.md", "# Kept\n")
            write_page(tmp, "notes.txt", "not a page\n")
            write_page(tmp, "data.json", "{}\n")

            self.assertEqual([p.rel_path for p in discover(tmp)], ["kept.md"])


class TestWikilinkParsing(unittest.TestCase):
    def test_parses_bare_wikilink(self):
        pages = discover(CLEAN)
        demo = page_by_rel_path(pages, "projects/demo.md")

        self.assertIn("alpha", [target for target, _ in demo.links])

    def test_parses_directory_qualified_wikilink(self):
        pages = discover(CLEAN)
        demo = page_by_rel_path(pages, "projects/demo.md")

        self.assertIn(
            "decisions/adr-001-example", [target for target, _ in demo.links]
        )

    def test_index_links_to_every_non_root_page(self):
        # The fixture's link graph is load-bearing for the reachability and
        # orphan checks; pin it here so a fixture edit cannot quietly break it.
        pages = discover(CLEAN)
        index = page_by_rel_path(pages, "INDEX.md")

        self.assertEqual(
            [target for target, _ in index.links],
            [
                "concepts/alpha",
                "decisions/adr-001-example",
                "projects/demo",
                "SCHEMA",
                "log",
            ],
        )

    def test_several_links_on_one_line_are_all_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "p.md", "# P\n\n## Related: [[a]], [[decisions/b]]\n")

            page = load(pathlib.Path(tmp) / "p.md", tmp)

        self.assertEqual(page.links, [("a", 3), ("decisions/b", 3)])

    def test_records_link_line_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(
                tmp,
                "p.md",
                "# P\n"           # 1
                "\n"              # 2
                "See [[alpha]].\n"  # 3
                "\n"              # 4
                "Also [[decisions/adr-001-example]] and [[demo]].\n",  # 5
            )

            page = load(pathlib.Path(tmp) / "p.md", tmp)

        self.assertEqual(
            page.links,
            [("alpha", 3), ("decisions/adr-001-example", 5), ("demo", 5)],
        )

    def test_link_line_numbers_are_one_based_and_point_at_the_link(self):
        for page in discover(CLEAN):
            for target, line_no in page.links:
                self.assertGreaterEqual(line_no, 1)
                self.assertIn(f"[[{target}]]", page.lines[line_no - 1])

    def test_page_without_links_has_an_empty_link_list(self):
        pages = discover(CLEAN)

        self.assertEqual(page_by_rel_path(pages, "log.md").links, [])


class TestFencedCodeBlocks(unittest.TestCase):
    def test_ignores_wikilinks_inside_fenced_code_blocks(self):
        # The fixture's SCHEMA.md documents link syntax inside ``` fences and
        # names pages that do not exist. Treating those as links would make the
        # clean fixture report broken links.
        pages = discover(CLEAN)
        schema = page_by_rel_path(pages, "SCHEMA.md")

        self.assertEqual(schema.links, [])
        self.assertIn("[[adr-MMM]]", "\n".join(schema.lines))

    def test_links_after_a_closed_fence_are_parsed_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(
                tmp,
                "p.md",
                "# P\n"                 # 1
                "```md\n"               # 2
                "## Related: [[template-only]]\n"  # 3
                "```\n"                 # 4
                "Real link: [[alpha]]\n",  # 5
            )

            page = load(pathlib.Path(tmp) / "p.md", tmp)

        self.assertEqual(page.links, [("alpha", 5)])

    def test_headings_inside_fences_are_not_headings(self):
        pages = discover(CLEAN)
        schema = page_by_rel_path(pages, "SCHEMA.md")

        self.assertEqual(schema.h1, "Wiki Schema (maintainer contract)")
        self.assertNotIn("# <Name>", schema.headings)
        self.assertIn("## Page types", schema.headings)


class TestHeadings(unittest.TestCase):
    def test_headings_are_captured_with_their_markers(self):
        pages = discover(CLEAN)
        alpha = page_by_rel_path(pages, "concepts/alpha.md")

        self.assertEqual(
            alpha.headings,
            [
                "# Alpha",
                "## What it is",
                "## How we use it (project-specific!)",
                "## Related: [[decisions/adr-001-example]], [[demo]]",
                "## Sources: raw/clean-fixture-notes.md",
            ],
        )

    def test_h1_is_the_first_level_one_heading_without_its_marker(self):
        pages = discover(CLEAN)

        self.assertEqual(page_by_rel_path(pages, "concepts/alpha.md").h1, "Alpha")
        self.assertEqual(
            page_by_rel_path(pages, "decisions/adr-001-example.md").h1,
            "ADR-001: Keep one hand-written fixture that is correct by construction",
        )

    def test_h1_is_none_when_the_page_has_no_level_one_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "p.md", "## Only a subheading\n\ntext\n")

            page = load(pathlib.Path(tmp) / "p.md", tmp)

        self.assertIsNone(page.h1)

    def test_lines_preserve_the_file_without_trailing_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_page(tmp, "p.md", "# P\n\ntext\n")

            page = load(pathlib.Path(tmp) / "p.md", tmp)

        self.assertEqual(page.lines, ["# P", "", "text"])


class TestCleanFixtureShape(unittest.TestCase):
    """Guards on the fixture itself — later tasks assume all of this."""

    def test_every_link_in_the_fixture_resolves_to_a_fixture_page(self):
        pages = discover(CLEAN)
        stems = {p.name for p in pages}
        rel_no_ext = {p.rel_path[: -len(".md")] for p in pages}

        for page in pages:
            for target, line_no in page.links:
                self.assertTrue(
                    target in rel_no_ext or target in stems,
                    f"{page.rel_path}:{line_no} [[{target}]] does not resolve",
                )

    def test_every_page_but_the_exempt_roots_has_an_inbound_link(self):
        pages = discover(CLEAN)
        exempt = {"INDEX.md", "SCHEMA.md", "log.md"}
        linked = set()
        for page in pages:
            for target, _ in page.links:
                for other in pages:
                    if target in (other.name, other.rel_path[: -len(".md")]):
                        linked.add(other.rel_path)

        for page in pages:
            if page.rel_path in exempt:
                continue
            self.assertIn(page.rel_path, linked, f"{page.rel_path} is an orphan")

    def test_every_page_is_reachable_from_index_within_two_hops(self):
        pages = discover(CLEAN)
        by_rel = {p.rel_path: p for p in pages}

        def resolve(target):
            for page in pages:
                if target in (page.name, page.rel_path[: -len(".md")]):
                    return page.rel_path
            return None

        seen = {"INDEX.md"}
        frontier = ["INDEX.md"]
        for _ in range(2):
            nxt = []
            for rel in frontier:
                for target, _ in by_rel[rel].links:
                    hit = resolve(target)
                    if hit and hit not in seen:
                        seen.add(hit)
                        nxt.append(hit)
            frontier = nxt

        self.assertEqual(seen, CLEAN_PAGES)

    def test_fixture_is_a_page_dataclass(self):
        self.assertTrue(all(isinstance(p, Page) for p in discover(CLEAN)))


if __name__ == "__main__":
    unittest.main()
