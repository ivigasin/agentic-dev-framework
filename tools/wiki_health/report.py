"""Human-readable rendering of a `model.Report`.

Plain text only — no color codes, no terminal detection. The same bytes are
read by a person at a prompt and by whoever scrolls a CI log a week later, and
escape sequences help neither.

Ordering is never decided here: `Report.entries()` is the one canonical-order
accessor, so the text report and the JSON report can never disagree about which
finding comes first.
"""

from .model import Severity

# Two spaces between columns: enough to scan, cheap enough that a long path
# never pushes the message off the line the way padded columns would.
GAP = "  "
INDENT = "  "

# Errors first — criterion 1 groups by severity, and the group a reader must
# act on comes first.
GROUPS = (
    (Severity.ERROR.value, "Errors"),
    (Severity.WARN.value, "Warnings"),
)

NO_FINDINGS = "No findings."


def format_location(entry):
    """`path:line`, or bare `path` when the finding is about the whole file."""
    if entry["line"] is None:
        return entry["path"]
    return f"{entry['path']}:{entry['line']}"


def format_entry(entry):
    """One finding as `path:line  [check]  message`."""
    parts = [format_location(entry), f"[{entry['check']}]", entry["message"]]
    if entry["fixed"]:
        parts.append("(fixed)")
    return GAP.join(parts)


def _plural(count, noun):
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def format_summary(counts):
    """The closing one-liner: counts per severity, plus fixes when any exist."""
    parts = [_plural(counts["error"], "error"), _plural(counts["warn"], "warning")]
    if counts["fixed"]:
        parts.append(f"{counts['fixed']} fixed")
    return ", ".join(parts)


def render(report):
    """Render `report` as plain text with no trailing newline."""
    entries = report.entries()
    if not entries:
        return NO_FINDINGS

    lines = []
    for severity, heading in GROUPS:
        group = [e for e in entries if e["severity"] == severity]
        if not group:
            continue
        if lines:
            lines.append("")
        lines.append(f"{heading} ({len(group)}):")
        lines.extend(INDENT + format_entry(entry) for entry in group)

    lines.append("")
    lines.append(format_summary(report.summary(entries)))
    return "\n".join(lines)
