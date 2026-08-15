"""Argument parsing and entrypoint for wiki-health."""

import argparse
import pathlib
import sys

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

    return EXIT_OK
