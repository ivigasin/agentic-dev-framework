"""Tests for the finding/report model and its JSON serialization.

These are pure data-structure tests: no fixture wiki is read, and nothing is
written. Paths are strings that never have to exist on disk.
"""

import json
import pathlib
import unittest

from wiki_health.model import Finding, Report, Severity

REQUIRED_FINDING_KEYS = {"check", "severity", "path", "line", "message", "fixed"}


def make_findings():
    """A deliberately unsorted set of findings covering both severities."""
    return [
        Finding(
            check="orphan-page",
            severity=Severity.WARN,
            path="concepts/zeta.md",
            line=None,
            message="no inbound links",
        ),
        Finding(
            check="broken-link",
            severity=Severity.ERROR,
            path="concepts/alpha.md",
            line=12,
            message="[[nope]] does not resolve",
        ),
        Finding(
            check="adr-shape",
            severity=Severity.ERROR,
            path="decisions/adr-001-example.md",
            line=3,
            message="missing Status line",
            fixed=True,
        ),
        Finding(
            check="broken-link",
            severity=Severity.ERROR,
            path="concepts/alpha.md",
            line=4,
            message="[[gone]] does not resolve",
        ),
    ]


class TestSeverity(unittest.TestCase):
    def test_severity_values_are_the_two_spec_strings(self):
        self.assertEqual(Severity.ERROR.value, "error")
        self.assertEqual(Severity.WARN.value, "warn")
        self.assertEqual({s.value for s in Severity}, {"error", "warn"})

    def test_severity_is_a_str_enum(self):
        # Checks compare and format severities as plain strings.
        self.assertIsInstance(Severity.ERROR, str)
        self.assertEqual(Severity("warn"), Severity.WARN)


class TestFindingSerialization(unittest.TestCase):
    def test_finding_serializes_to_json_with_required_keys(self):
        finding = Finding(
            check="broken-link",
            severity=Severity.ERROR,
            path="concepts/alpha.md",
            line=12,
            message="[[nope]] does not resolve",
        )
        payload = json.loads(Report([finding]).to_json())
        (entry,) = payload["findings"]

        self.assertEqual(set(entry), REQUIRED_FINDING_KEYS)
        self.assertEqual(entry["check"], "broken-link")
        self.assertEqual(entry["severity"], "error")
        self.assertEqual(entry["path"], "concepts/alpha.md")
        self.assertEqual(entry["line"], 12)
        self.assertEqual(entry["message"], "[[nope]] does not resolve")
        self.assertIs(entry["fixed"], False)

    def test_finding_without_line_serializes_line_as_null(self):
        finding = Finding(
            check="orphan-page",
            severity=Severity.WARN,
            path="concepts/zeta.md",
            line=None,
            message="no inbound links",
        )
        payload = json.loads(Report([finding]).to_json())
        (entry,) = payload["findings"]

        self.assertEqual(set(entry), REQUIRED_FINDING_KEYS)
        self.assertIsNone(entry["line"])
        self.assertEqual(entry["severity"], "warn")

    def test_paths_are_emitted_relative_to_the_wiki_root(self):
        root = pathlib.Path("/somewhere/repo/wiki")
        finding = Finding(
            check="broken-link",
            severity=Severity.ERROR,
            path=root / "concepts" / "alpha.md",
            line=1,
            message="[[nope]] does not resolve",
        )
        payload = json.loads(Report([finding], root=root).to_json())

        self.assertEqual(payload["findings"][0]["path"], "concepts/alpha.md")


class TestReport(unittest.TestCase):
    def test_report_carries_schema_version(self):
        payload = json.loads(Report([]).to_json())

        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(Report.schemaVersion, 1)
        self.assertEqual(set(payload), {"schemaVersion", "findings", "summary"})

    def test_summary_counts_severities_and_fixes(self):
        payload = json.loads(Report(make_findings()).to_json())

        self.assertEqual(payload["summary"], {"error": 3, "warn": 1, "fixed": 1})

    def test_empty_report_has_zeroed_summary(self):
        payload = json.loads(Report([]).to_json())

        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["summary"], {"error": 0, "warn": 0, "fixed": 0})

    def test_findings_are_ordered_by_path_line_check(self):
        payload = json.loads(Report(make_findings()).to_json())
        order = [(f["path"], f["line"], f["check"]) for f in payload["findings"]]

        self.assertEqual(
            order,
            [
                ("concepts/alpha.md", 4, "broken-link"),
                ("concepts/alpha.md", 12, "broken-link"),
                ("concepts/zeta.md", None, "orphan-page"),
                ("decisions/adr-001-example.md", 3, "adr-shape"),
            ],
        )


class TestDeterminism(unittest.TestCase):
    def test_json_is_stable_across_runs(self):
        first = Report(make_findings()).to_json()
        second = Report(list(reversed(make_findings()))).to_json()

        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))

    def test_json_is_stable_regardless_of_root_form(self):
        root = pathlib.Path("/somewhere/repo/wiki")
        findings = [
            Finding(
                check="broken-link",
                severity=Severity.ERROR,
                path=root / "concepts" / "alpha.md",
                line=1,
                message="[[nope]] does not resolve",
            )
        ]
        with_root = Report(findings, root=root).to_json()
        already_relative = Report(
            [
                Finding(
                    check="broken-link",
                    severity=Severity.ERROR,
                    path="concepts/alpha.md",
                    line=1,
                    message="[[nope]] does not resolve",
                )
            ]
        ).to_json()

        self.assertEqual(with_root, already_relative)


if __name__ == "__main__":
    unittest.main()
