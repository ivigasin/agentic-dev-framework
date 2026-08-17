"""Argument parsing and entrypoint for wiki-health.

The pipeline is four steps and lives entirely in `main`: discover pages, run
every registered check over them, wrap the findings in a `Report`, render it.
Nothing here knows what a check does — adding one changes `checks/`, never this
file.

Two invariants this module owns:

- **stdout is the report, stderr is everything else.** Under `--json` an agent
  parses stdout whole, so a stray progress line would corrupt the payload. Path
  errors, the `--dry-run` preview, and tracebacks all go to stderr, and on a
  tool error stdout stays empty rather than emitting half a report.
- **Exit 2 is a tool error, exit 1 is an unhealthy wiki** (criterion 3). An
  unreadable file must not masquerade as a finding, so discovery and checks run
  inside a guard that maps `OSError`/decode failures onto 2.

## Fix mode (criteria 17-19)

Writing is reached through exactly one branch — `if args.fix` — and nothing
else in this package opens a file for writing. That is the whole of criterion
18: a read-only run is not read-only by discipline, it is read-only because the
code path that writes is never entered.

- `--fix` repairs, appends one line to `wiki/log.md`, and reports the repairs
  as `fixed`. Fixed findings do not gate the exit code, so a run that repairs
  everything exits 0.
- `--fix --dry-run` builds the identical plan and applies none of it. The
  report on stdout then describes the wiki **as it still is on disk** — nothing
  was repaired, so nothing is marked `fixed`, and the exit code stays 1 for a
  wiki that is still broken. Telling an agent otherwise would be a lie it acts
  on. What *would* have changed goes to stderr as a preview, in both human and
  `--json` mode: it is a diagnostic, not the report, and routing it by mode
  would give stdout two possible meanings.
- `--dry-run` without `--fix` is refused with exit 2 — see `main`.
- A wiki with no `wiki/log.md` still gets repaired, but the run cannot record
  itself and says so on stderr — see `log_missing_line`. The fix never creates
  the file.
"""

import argparse
import pathlib
import sys

from . import checks, fixes, pages, report as report_text
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


def read_only_pass(wiki_path):
    """Discover, check, and collect — the whole read-only pipeline.

    Returns the pages alongside the report because fix mode needs both, and
    re-discovering would let the report and the repairs describe two different
    file trees.
    """
    discovered = pages.discover(wiki_path)
    findings = checks.run_all(discovered, wiki_path)
    return discovered, Report(findings=findings, root=wiki_path)


def build_report(wiki_path):
    """The read-only pipeline, for callers that only want the report."""
    return read_only_pass(wiki_path)[1]


def _count(number, noun):
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def preview_lines(plan, wiki_path):
    """The `--dry-run` report of intended changes, as stderr lines.

    Three parts, because they answer different questions: the staged edits say
    what would be written, the would-be-fixed findings say what that would
    accomplish, and the closing count says what a human would still be left
    with. Rendered with `report.format_entry`/`format_summary`, so a preview and
    the report it predicts cannot describe the same finding two different ways.

    The closing line summarizes `plan.remaining` — the findings that survive the
    repairs — and not `plan.findings()`. The latter counts a fixed finding in
    its severity bucket, which is right for a report of what happened and reads
    as "3 errors, 3 fixed" here, exactly the ambiguity a preview must not have.
    """
    edits = plan.edits
    if not edits:
        return [f"{PROG}: dry run: nothing to change; no files would be written"]

    summaries = [summary for edit in edits for summary in edit.summaries]
    lines = [
        f"{PROG}: dry run: nothing written. "
        f"{_count(len(summaries), 'change')} in {_count(len(edits), 'file')}:"
    ]
    lines.extend(report_text.INDENT + summary for summary in summaries)

    would_fix = Report(findings=list(plan.fixed), root=wiki_path).entries()
    if would_fix:
        lines.append(f"{PROG}: would fix:")
        lines.extend(
            report_text.INDENT + report_text.format_entry(entry) for entry in would_fix
        )
    left = Report(findings=list(plan.remaining), root=wiki_path)
    lines.append(
        f"{PROG}: would leave: {report_text.format_summary(left.summary())}"
    )
    return lines


def log_missing_line(wiki_path, dry_run):
    """Warn that a `--fix` run cannot record itself (SCHEMA rule 5).

    Emitted in both modes, and on stderr in both, because it is a diagnostic
    about the wiki's shape rather than part of the report. It matters more than
    it looks: no *check* reports a missing `log.md`, and the fix declines to
    create one, so this line is the only place the omission surfaces. Without
    it a `--fix` would repair a wiki and leave no trace anywhere that it ran.

    The dry-run wording is future tense for the same reason the preview is —
    nothing happened yet, and a warning phrased as though it did would send a
    reader looking for changes that are not on disk.
    """
    clause = "would not record" if dry_run else "did not record"
    return (
        f"{PROG}: warning: no {fixes.LOG_PATH} in {wiki_path}, so this run "
        f"{clause} itself. wiki/SCHEMA.md rule 5 expects one line per run; "
        f"create {fixes.LOG_PATH} by hand — a fix will not invent it."
    )


def main(argv=None):
    """Return a process exit code. Never raises SystemExit."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # --help/--version exit 0; every other argparse bail is a tool error.
        return EXIT_OK if exc.code in (0, None) else EXIT_TOOL_ERROR

    if args.dry_run and not args.fix:
        # Refused, not quietly accepted. A run without --fix is already
        # read-only (criterion 18), so on its own the flag asks for a mode that
        # does not exist — and the person who typed it almost certainly meant
        # `--fix --dry-run` and wants to see what would change. Printing an
        # ordinary report instead would answer a question they did not ask,
        # while looking like the preview they did. Exit 2 is criterion 3's code
        # for bad arguments, and refusing cannot write.
        print(
            f"{PROG}: error: --dry-run requires --fix; a run without --fix is "
            "already read-only",
            file=sys.stderr,
        )
        return EXIT_TOOL_ERROR

    wiki_path = resolve_wiki_path(args.path)
    if not wiki_path.is_dir():
        print(
            f"{PROG}: error: wiki path does not exist: {wiki_path}",
            file=sys.stderr,
        )
        return EXIT_TOOL_ERROR

    try:
        discovered, report = read_only_pass(wiki_path)
    except (OSError, UnicodeDecodeError) as exc:
        # An unreadable wiki is a tool error, not a finding — exit 2 so CI can
        # tell "the tool broke" from "the wiki is unhealthy".
        print(f"{PROG}: error: cannot read wiki: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR

    if args.fix:
        # The only branch in the tool that can reach a write.
        try:
            plan = fixes.run_fixes(
                discovered,
                wiki_path,
                report.findings,
                dry_run=args.dry_run,
                log=True,
            )
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{PROG}: error: cannot repair wiki: {exc}", file=sys.stderr)
            return EXIT_TOOL_ERROR

        if args.dry_run:
            for line in preview_lines(plan, wiki_path):
                print(line, file=sys.stderr)
        else:
            # Only now do the repairs enter the report, so the `fixed` markers
            # always describe writes that actually happened.
            report = Report(findings=plan.findings(), root=wiki_path)
            if plan.written:
                print(f"{PROG}: wrote {', '.join(plan.written)}", file=sys.stderr)

        if plan.log_missing:
            # After the preview or the write notice: it qualifies what just
            # happened, so it reads as a footnote to it rather than a headline.
            print(log_missing_line(wiki_path, args.dry_run), file=sys.stderr)

    print(report.to_json() if args.json else report_text.render(report))
    return exit_code_for(report, args.strict)
