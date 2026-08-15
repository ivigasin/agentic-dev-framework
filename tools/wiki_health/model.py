"""Findings and the report they aggregate into.

Every check produces `Finding` objects; the CLI collects them into a `Report`
and renders it either as human text (see `report.py`) or as the versioned JSON
below. The JSON is a contract with agents and CI, so it is deterministic: same
findings in, byte-identical bytes out, whatever order the checks ran in.
"""

import dataclasses
import enum
import json
import pathlib

SCHEMA_VERSION = 1


class Severity(str, enum.Enum):
    """The only two severities a finding may carry (spec criterion 4)."""

    ERROR = "error"
    WARN = "warn"

    def __str__(self):
        return self.value


@dataclasses.dataclass(frozen=True)
class Finding:
    check: str
    severity: Severity
    path: object
    line: int | None
    message: str
    fixed: bool = False

    def to_dict(self, root=None):
        """Serializable form; `path` is rendered relative to the wiki root."""
        return {
            "check": self.check,
            "severity": Severity(self.severity).value,
            "path": _relative_path(self.path, root),
            "line": self.line,
            "message": self.message,
            "fixed": bool(self.fixed),
        }


def _relative_path(path, root):
    """Render a path as a POSIX string relative to `root` where possible.

    Absolute paths would leak the checkout location into the report and break
    byte-for-byte comparison between machines, so they are trimmed to the wiki
    root. A path outside the root is left as-is rather than turned into `..`
    noise.
    """
    pure = pathlib.PurePath(path)
    if root is not None:
        try:
            pure = pure.relative_to(pathlib.PurePath(root))
        except ValueError:
            pass
    return pure.as_posix()


def _sort_key(entry):
    """Order by (path, line, check), with the rest as tiebreakers.

    `line` is None for whole-file findings; None does not compare against int,
    so it sorts as -1 — ahead of any real line. The trailing fields make the
    order total, so two reports built from the same findings in different
    orders still serialize identically.
    """
    return (
        entry["path"],
        -1 if entry["line"] is None else entry["line"],
        entry["check"],
        entry["severity"],
        entry["message"],
        entry["fixed"],
    )


@dataclasses.dataclass
class Report:
    findings: list
    root: object = None

    schemaVersion = SCHEMA_VERSION

    def entries(self):
        """Findings as sorted dicts — the canonical order for every renderer."""
        return sorted(
            (f.to_dict(self.root) for f in self.findings),
            key=_sort_key,
        )

    def summary(self, entries=None):
        if entries is None:
            entries = self.entries()
        counts = {"error": 0, "warn": 0, "fixed": 0}
        for entry in entries:
            counts[entry["severity"]] += 1
            if entry["fixed"]:
                counts["fixed"] += 1
        return counts

    def to_dict(self):
        entries = self.entries()
        return {
            "schemaVersion": self.schemaVersion,
            "findings": entries,
            "summary": self.summary(entries),
        }

    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), indent=indent)
