"""The check registry, and the one shape every check in this package follows.

A check is a plain function, decorated with `@check(<id>)`:

    @check("broken-link")
    def check_broken_links(pages, root):
        return [Finding(...), ...]

- `pages` — the already-parsed `pages.Page` list from `pages.discover(root)`.
  A check never opens a file itself. Parsing once and passing the result means
  every check sees the same wiki, and fenced code blocks are inert everywhere
  rather than in whichever checks remembered to skip them.
- `root` — the wiki root as a path. Take it even when the check ignores it
  (most link-graph checks do, since `Page.rel_path` is already root-relative),
  because the CLI calls every check through the same two-argument signature.
- Returns a `list` of `model.Finding`, empty when the wiki is fine. A check
  never raises on wiki content it dislikes and never prints: a problem in the
  wiki is a finding, and a traceback would take the other checks down with it.
- `Finding.path` is the offending page's `rel_path`, `Finding.line` the 1-based
  line, or None for a whole-file finding.

The decorator stamps `fn.check_id` and appends the function to `ALL_CHECKS` in
import order. The id is a contract, not a label: it is what `Finding.check`
carries into the JSON report, so it must be stable across releases and unique
across checks. Two findings may share an id with different messages — an
unresolved link and an ambiguous one are both `broken-link`.

Adding a check: write it in `structural.py` (link graph) or `schema.py` (page
shape), decorate it, and — if it lives in a new module — import that module at
the bottom of this file, or it will never run.
"""

_REGISTRY = []


def check(check_id):
    """Register a function as a check under `check_id`."""

    def decorate(function):
        function.check_id = check_id
        _REGISTRY.append(function)
        return function

    return decorate


# Imported for their side effect: decorating a check registers it. Kept at the
# bottom so `check` exists by the time a submodule imports it.
from . import structural  # noqa: E402
from . import schema  # noqa: E402

# New check modules go ABOVE this line: the tuple is frozen here, and a check
# registered after it would never run.
ALL_CHECKS = tuple(_REGISTRY)


def run_all(pages, root):
    """Every registered check, in registration order, findings concatenated."""
    findings = []
    for function in ALL_CHECKS:
        findings.extend(function(pages, root))
    return findings
