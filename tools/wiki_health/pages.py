"""Reading a wiki off disk: page discovery, headings, and wikilinks.

Every check downstream of here works on `Page` objects, never on raw text, so
this module is the single place that decides what counts as a page, a heading,
or a link. Two consequences worth stating up front:

- Fenced code blocks are inert. `wiki/SCHEMA.md` documents the page templates
  by showing them, fences and all, and those templates contain both headings
  (`## What it is`) and wikilinks (`[[adr-MMM]]`) that name nothing real. A
  parser that read them would report a schema document as a broken wiki.
- Nothing here resolves a link. `links` holds the literal text between the
  brackets; turning `decisions/adr-003` into a file is the broken-link check's
  job, and keeping the two apart is what lets that check report an *unresolved*
  target rather than silently dropping it.
"""

import dataclasses
import pathlib
import re

# Both link forms in SCHEMA.md: bare `[[concept-a]]` and directory-qualified
# `[[decisions/adr-003]]`. Brackets are excluded from the target so an
# unterminated `[[` cannot swallow the rest of the line.
LINK_RE = re.compile(r"\[\[([^\[\]\n]+)\]\]")

# ATX headings only. Setext (`===` underlines) is not used anywhere in this
# wiki's templates, and supporting it would make `h1` depend on lookahead.
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

FENCE = "```"

MARKDOWN_SUFFIX = ".md"


@dataclasses.dataclass(frozen=True)
class Page:
    """One markdown file, parsed once and read many times.

    - `path` — absolute (or as-given) path on disk.
    - `rel_path` — POSIX path relative to the wiki root, e.g.
      `concepts/alpha.md`. This is the identity used in findings and in the
      link graph; it is what gets printed, so it never contains a backslash.
    - `name` — the filename stem, `alpha`. Bare links resolve against this.
    - `lines` — the file split on newlines, with no trailing newline retained.
      Indexing is 0-based here while `links` reports 1-based line numbers, the
      way an editor counts them.
    - `headings` — heading lines *with* their `#` markers, in document order,
      fenced blocks excluded. Kept verbatim so the schema checks can prefix-
      match `## How we use it` against SCHEMA's
      `## How we use it (project-specific!)`.
    - `links` — `(target, line_no)` in document order, duplicates included: two
      broken links on one line are two findings.
    - `h1` — text of the first level-1 heading without its marker, or None.
    """

    path: pathlib.Path
    rel_path: str
    name: str
    lines: list
    headings: list
    links: list
    h1: object = None


def iter_content_lines(lines):
    """Yield `(line_no, text)` for lines outside fenced code blocks.

    A line whose first non-space character starts a ``` run toggles the fence,
    and the fence markers themselves are never yielded. An unclosed fence
    therefore swallows the rest of the file — the same thing a markdown renderer
    does, and the safe direction to err: it under-reports links rather than
    inventing them.
    """
    in_fence = False
    for index, text in enumerate(lines):
        if text.lstrip().startswith(FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield index + 1, text


def parse(text):
    """Parse markdown source into `(lines, headings, links, h1)`."""
    lines = text.splitlines()
    headings = []
    links = []
    h1 = None

    for line_no, line in iter_content_lines(lines):
        heading = HEADING_RE.match(line)
        if heading:
            headings.append(line.rstrip())
            if h1 is None and len(heading.group(1)) == 1:
                h1 = heading.group(2)
        for match in LINK_RE.finditer(line):
            links.append((match.group(1).strip(), line_no))

    return lines, headings, links, h1


def load(path, root):
    """Read and parse a single page. `root` is the wiki root `rel_path` is against."""
    path = pathlib.Path(path)
    lines, headings, links, h1 = parse(path.read_text(encoding="utf-8"))
    return Page(
        path=path,
        rel_path=path.relative_to(root).as_posix(),
        name=path.stem,
        lines=lines,
        headings=headings,
        links=links,
        h1=h1,
    )


def discover(root):
    """Every `*.md` file under `root`, recursively, in stable `rel_path` order.

    The sort is not cosmetic: findings are reported in the order pages are
    walked before `Report` re-sorts them, and a fixture whose page order shifts
    between runs would make failures hard to diff. Sorting the `rel_path`
    strings rather than the `Path` objects keeps that order identical on every
    platform, since path comparison folds case on some of them.
    """
    root = pathlib.Path(root)
    pages = [load(path, root) for path in root.rglob(f"*{MARKDOWN_SUFFIX}")]
    pages.sort(key=lambda page: page.rel_path)
    return pages
