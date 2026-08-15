"""Argument parsing and entrypoint for wiki-health.

The pipeline is four steps and lives entirely in `main`: discover pages, run
every registered check over them, wrap the findings in a `Report`, render it.
Nothing here knows what a check does — adding one changes `checks/`, never this
file.

Two invariants this module owns:

- **stdout is the report, stderr is everything else.** Under `--json` an agent
  parses stdout whole, so a stray progress line would corrupt the payload. Path
  errors, warnings about unimplemented flags, and tracebacks all go to stderr,
  and on a tool error stdout stays empty rather than emitting half a report.
- **Exit 2 is a tool error, exit 1 is an unhealthy wiki** (criterion 3). An
  unreadable file must not masquerade as a finding, so discovery and checks run
  inside a guard that maps `OSError`/decode failures onto 2.
"""

import argparse
import pathlib
import sys

from . import checks, pages, report as report_text
from .model import Report, Severity

# tools/wiki_health/cli.py -> tools/wiki_health -> tools -> repo root
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_WIKI = REPO_ROOT / "wiki"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_TOOL_ERROR = 2

PROG = "wiki-health"


def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Check a wiki against the contract in wiki/SCHEMA.md.",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="wiki directory to check (default: the repo's wiki/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable report on stdout and nothing else",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as failures for the purpose of the exit code",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="repair what can be repaired safely (default is read-only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --fix, report intended changes without writing",
    )
    return parser


def resolve_wiki_path(raw):
    """Resolve --path against the cwd; the default hangs off the repo root."""
    if raw is None:
        return DEFAULT_WIKI
    return pathlib.Path(raw).expanduser()


def exit_code_for(report, strict):
    """`EXIT_FINDINGS` when the report clears the failure threshold.

    Fixed findings are excluded (criterion 15): they are reported *as fixed*,
    and a `--fix` run that repaired everything leaves a healthy wiki behind, so
    it must exit 0. Warnings only count under `--strict` (criterion 4).
    """
    for entry in report.entries():
        if entry["fixed"]:
            continue
        if entry["severity"] == Severity.ERROR.value:
            return EXIT_FINDINGS
        if strict and entry["severity"] == Severity.WARN.value:
            return EXIT_FINDINGS
    return EXIT_OK


def build_report(wiki_path):
    """Discover, check, and collect — the whole read-only pipeline."""
    discovered = pages.discover(wiki_path)
    findings = checks.run_all(discovered, wiki_path)
    return Report(findings=findings, root=wiki_path)


def main(argv=None):
    """Return a process exit code. Never raises SystemExit."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # --help/--version exit 0; every other argparse bail is a tool error.
        return EXIT_OK if exc.code in (0, None) else EXIT_TOOL_ERROR

    wiki_path = resolve_wiki_path(args.path)
    if not wiki_path.is_dir():
        print(
            f"{PROG}: error: wiki path does not exist: {wiki_path}",
            file=sys.stderr,
        )
        return EXIT_TOOL_ERROR

    if args.fix or args.dry_run:
        # Accepted by the parser since Task 1; the repair passes land in Tasks
        # 14-16. Say so rather than silently running read-only, which would
        # look like "nothing was fixable".
        print(
            f"{PROG}: warning: --fix/--dry-run are not implemented yet; "
            "running read-only",
            file=sys.stderr,
        )

    try:
        report = build_report(wiki_path)
    except (OSError, UnicodeDecodeError) as exc:
        # An unreadable wiki is a tool error, not a finding — exit 2 so CI can
        # tell "the tool broke" from "the wiki is unhealthy".
        print(f"{PROG}: error: cannot read wiki: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR

    print(report.to_json() if args.json else report_text.render(report))
    return exit_code_for(report, args.strict)
