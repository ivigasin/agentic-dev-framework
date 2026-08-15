"""Checks on the link graph: does every `[[target]]` name a real page, and does
every page have something naming it?

`pages.py` deliberately stops at the literal text between the brackets, so this
module owns resolution — and owning it is what lets the check say *why* a link
failed. A target that matches nothing and a target that matches two pages are
different problems with different repairs, and both are errors (plan severity
table, criterion 6).

The orphan check reads the same graph from the other end. It is a `warn`, not
an error: an unlinked page is a gap in the index, not a lie in it.

The index-drift check reads it from the root: `wiki/SCHEMA.md` rule 2 makes
`INDEX.md` the entry point every page must sit within two hops of, so drift is
measured as distance from that one node rather than as a property of any page.
"""

import collections
import dataclasses

from . import check
from ..model import Finding, Severity
from ..pages import MARKDOWN_SUFFIX

BROKEN_LINK = "broken-link"
ORPHAN_PAGE = "orphan-page"
INDEX_DRIFT = "index-drift"

# `wiki/SCHEMA.md` rule 2: "Every page reachable from `wiki/INDEX.md` within 2
# link hops."
MAX_HOPS = 2
ROOT_INDEX = "INDEX.md"

# The framework files at the wiki root are entry points, not destinations:
# INDEX.md is where a reader starts, and SCHEMA.md and log.md are addressed by
# name (by `wiki/SCHEMA.md` rules 2 and 5) rather than reached by link. Nothing
# is obliged to link them. The exemption is by exact `rel_path`, so a directory
# `concepts/INDEX.md` stays an ordinary page in the graph.
EXEMPT_ROOTS = frozenset({"INDEX.md", "SCHEMA.md", "log.md"})


@dataclasses.dataclass(frozen=True)
class Resolution:
    """What a wikilink target turned out to name.

    `rel_path` is set when exactly one page matched. When it is None the link
    is broken, and `candidates` tells the two cases apart: empty means nothing
    matched, two or more means the bare name was ambiguous.
    """

    target: str
    rel_path: object = None
    candidates: tuple = ()

    @property
    def is_resolved(self):
        return self.rel_path is not None

    @property
    def is_ambiguous(self):
        return self.rel_path is None and len(self.candidates) > 1


def _drop_suffix(rel_path):
    if rel_path.endswith(MARKDOWN_SUFFIX):
        return rel_path[: -len(MARKDOWN_SUFFIX)]
    return rel_path


class LinkIndex:
    """Resolves the two link forms in `wiki/SCHEMA.md` against a set of pages.

    Path match first, stem match second. The order is the whole point: a
    directory-qualified `[[projects/alpha]]` names one page and must fail when
    that page is gone, rather than quietly retargeting `concepts/alpha.md` and
    hiding the stale link this check exists to surface.
    """

    def __init__(self, pages):
        self._by_path = {}
        self._by_stem = {}
        for page in pages:
            self._by_path[_drop_suffix(page.rel_path)] = page.rel_path
            self._by_stem.setdefault(page.name, []).append(page.rel_path)

    def resolve(self, target):
        key = target.strip()

        exact = self._by_path.get(key)
        if exact is not None:
            return Resolution(target, rel_path=exact)

        matches = tuple(self._by_stem.get(key, ()))
        if len(matches) == 1:
            return Resolution(target, rel_path=matches[0])
        return Resolution(target, candidates=matches)


def describe(resolution):
    """The finding message for an unresolved link — distinct per failure mode."""
    if resolution.is_ambiguous:
        return (
            f"ambiguous link [[{resolution.target}]] — matches "
            f"{', '.join(resolution.candidates)}; qualify it with a directory"
        )
    return (
        f"unresolved link [[{resolution.target}]] — no page matches; "
        f"fix the target or create the page"
    )


@check(BROKEN_LINK)
def check_broken_links(pages, root):
    """Every `[[target]]` resolves to exactly one page (spec criterion 6)."""
    index = LinkIndex(pages)
    findings = []
    for page in pages:
        for target, line_no in page.links:
            resolution = index.resolve(target)
            if resolution.is_resolved:
                continue
            findings.append(
                Finding(
                    check=BROKEN_LINK,
                    severity=Severity.ERROR,
                    path=page.rel_path,
                    line=line_no,
                    message=describe(resolution),
                )
            )
    return findings


def inbound_counts(pages):
    """`rel_path` → how many other pages link to it.

    Only *resolved* links count, or a typo would mask the orphan it created:
    renaming `alpha.md` and leaving `[[alpha]]` behind must surface as one
    broken link *and* one orphan, not as neither. Self-links are excluded for
    the same reason — a page citing itself is still unreachable from the rest
    of the wiki, which is the only thing an inbound link is evidence of.
    """
    index = LinkIndex(pages)
    counts = {page.rel_path: 0 for page in pages}
    for page in pages:
        for target, _line_no in page.links:
            resolution = index.resolve(target)
            if not resolution.is_resolved:
                continue
            if resolution.rel_path == page.rel_path:
                continue
            counts[resolution.rel_path] += 1
    return counts


@check(ORPHAN_PAGE)
def check_orphans(pages, root):
    """Every page is linked from somewhere (spec criterion 7)."""
    counts = inbound_counts(pages)
    findings = []
    for page in pages:
        if page.rel_path in EXEMPT_ROOTS:
            continue
        if counts[page.rel_path]:
            continue
        findings.append(
            Finding(
                check=ORPHAN_PAGE,
                severity=Severity.WARN,
                path=page.rel_path,
                line=None,
                message=(
                    f"orphan page {page.rel_path} — no page links to it; "
                    f"link it from INDEX.md or a related page"
                ),
            )
        )
    return findings


def hop_depths(pages, index=None):
    """`rel_path` → shortest number of resolved links from the root `INDEX.md`.

    Breadth-first, so the first depth recorded for a page is its shortest: a
    page the index reaches directly is one hop even when some long chain also
    ends there. Pages the index cannot reach at all are simply absent from the
    mapping — an unreachable page has no finite depth, and callers need to say
    something different about it than "too deep".

    A directory `concepts/INDEX.md` is an ordinary node here. It costs a hop
    like any other page, which is what makes SCHEMA rule 2's "beyond ~40 pages
    per directory → add a directory INDEX.md" a real budget rather than a way
    to hide depth. An empty mapping means there is no root index to walk from.
    """
    if index is None:
        index = LinkIndex(pages)
    by_path = {page.rel_path: page for page in pages}
    if ROOT_INDEX not in by_path:
        return {}

    depths = {ROOT_INDEX: 0}
    queue = collections.deque([ROOT_INDEX])
    while queue:
        rel_path = queue.popleft()
        depth = depths[rel_path] + 1
        for target, _line_no in by_path[rel_path].links:
            resolution = index.resolve(target)
            if not resolution.is_resolved:
                continue
            if resolution.rel_path in depths:
                continue
            depths[resolution.rel_path] = depth
            queue.append(resolution.rel_path)
    return depths


def describe_index_entry(resolution):
    """The finding message for a root-index entry that names no single page."""
    if resolution.is_ambiguous:
        return (
            f"ambiguous index entry [[{resolution.target}]] in INDEX.md — "
            f"matches {', '.join(resolution.candidates)}; qualify it with a "
            f"directory"
        )
    return (
        f"stale index entry [[{resolution.target}]] in INDEX.md — the page it "
        f"named is gone; remove the entry or restore the page"
    )


def _describe_depth(rel_path, depth):
    if depth is None:
        return (
            f"{rel_path} is unreachable from INDEX.md — SCHEMA rule 2 requires "
            f"every page within {MAX_HOPS} link hops; link it from the index "
            f"or from a page the index reaches"
        )
    return (
        f"{rel_path} is {depth} hops from INDEX.md — SCHEMA rule 2 allows at "
        f"most {MAX_HOPS}; link it from the index or from a page the index "
        f"reaches directly"
    )


@check(INDEX_DRIFT)
def check_index_drift(pages, root):
    """The index and the wiki still describe each other (spec criterion 8).

    Two arms, one defect seen from either end of an index entry: a page the
    index no longer reaches within `MAX_HOPS`, and an entry naming a page that
    is gone. They share a check id because they share a repair — editing
    `INDEX.md` — and because Task 14's auto-fix handles both by rewriting it.

    The stale-entry arm is scoped to the root index. A dead link on an ordinary
    page is the broken-link check's business; reporting it here as well would
    make every broken link index drift and drown the signal. The overlap that
    remains — a dead entry in `INDEX.md` is both a broken link and drift — is
    deliberate, and the messages are worded to stay distinguishable.
    """
    if not pages:
        return []

    index = LinkIndex(pages)
    by_path = {page.rel_path: page for page in pages}

    root_index = by_path.get(ROOT_INDEX)
    if root_index is None:
        # Without an entry point nothing is reachable, and reporting every page
        # would bury the one fact that matters under the wiki's page count.
        return [
            Finding(
                check=INDEX_DRIFT,
                severity=Severity.ERROR,
                path=ROOT_INDEX,
                line=None,
                message=(
                    "missing INDEX.md at the wiki root — SCHEMA rule 2 makes it "
                    "the entry point every page hangs off; create it"
                ),
            )
        ]

    findings = []
    for target, line_no in root_index.links:
        resolution = index.resolve(target)
        if resolution.is_resolved:
            continue
        findings.append(
            Finding(
                check=INDEX_DRIFT,
                severity=Severity.ERROR,
                path=ROOT_INDEX,
                line=line_no,
                message=describe_index_entry(resolution),
            )
        )

    depths = hop_depths(pages, index)
    for page in pages:
        if page.rel_path in EXEMPT_ROOTS:
            continue
        depth = depths.get(page.rel_path)
        if depth is not None and depth <= MAX_HOPS:
            continue
        findings.append(
            Finding(
                check=INDEX_DRIFT,
                severity=Severity.ERROR,
                path=page.rel_path,
                line=None,
                message=_describe_depth(page.rel_path, depth),
            )
        )
    return findings
