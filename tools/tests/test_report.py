"""Tests for the human-readable renderer.

Like the model tests these are pure data-structure tests: no fixture wiki is
read and nothing is written. The renderer's contract is that a human reading a
terminal — or a CI log, which is why there are no color codes — can find the
offending line from the output alone.
"""

import unittest

from wiki_health.model import Finding, Report, Severity
from wiki_health.report import render


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
            check="kebab-case",
            severity=Severity.WARN,
            path="concepts/Some_Page.md",
            line=None,
            message="filename is not kebab-case",
        ),
        Finding(
            check="broken-link",
            severity=Severity.ERROR,
            path="concepts/alpha.md",
            line=4,
            message="[[gone]] does not resolve",
        ),
    ]


class TestGrouping(unittest.TestCase):
    def test_findings_grouped_by_severity(self):
        text = render(Report(make_findings()))
        lines = text.splitlines()

        error_lines = [i for i, ln in enumerate(lines) if "[broken-link]" in ln]
        warn_lines = [
            i for i, ln in enumerate(lines)
            if "[orphan-page]" in ln or "[kebab-case]" in ln
        ]

        self.assertEqual(len(error_lines), 2)
        self.assertEqual(len(warn_lines), 2)
        # Every error is printed before every warning.
        self.assertLess(max(error_lines), min(warn_lines))

    def test_severity_headings_label_each_group(self):
        lines = render(Report(make_findings())).splitlines()

        self.assertIn("Errors (2):", lines)
        self.assertIn("Warnings (2):", lines)
        self.assertLess(lines.index("Errors (2):"), lines.index("Warnings (2):"))

    def test_group_is_omitted_when_that_severity_is_empty(self):
        findings = [
            Finding(
                check="orphan-page",
                severity=Severity.WARN,
                path="concepts/zeta.md",
                line=None,
                message="no inbound links",
            )
        ]
        text = render(Report(findings))

        self.assertNotIn("Errors", text)
        self.assertIn("Warnings (1):", text)

    def test_findings_follow_the_model_canonical_order(self):
        # model.Report.entries() is the single source of ordering truth; the
        # renderer must not impose its own or text and JSON could disagree.
        text = render(Report(make_findings()))

        self.assertLess(
            text.index("concepts/alpha.md:4"),
            text.index("concepts/alpha.md:12"),
        )
        self.assertLess(
            text.index("concepts/Some_Page.md"),
            text.index("concepts/zeta.md"),
        )


class TestFindingLine(unittest.TestCase):
    def test_line_reference_rendered_as_path_colon_line(self):
        finding = Finding(
            check="broken-link",
            severity=Severity.ERROR,
            path="concepts/alpha.md",
            line=12,
            message="[[nope]] does not resolve",
        )
        lines = render(Report([finding])).splitlines()
        (entry,) = [ln for ln in lines if "broken-link" in ln]

        self.assertEqual(
            entry.strip(),
            "concepts/alpha.md:12  [broken-link]  [[nope]] does not resolve",
        )

    def test_finding_without_line_omits_colon(self):
        finding = Finding(
            check="orphan-page",
            severity=Severity.WARN,
            path="concepts/zeta.md",
            line=None,
            message="no inbound links",
        )
        lines = render(Report([finding])).splitlines()
        (entry,) = [ln for ln in lines if "orphan-page" in ln]

        self.assertEqual(
            entry.strip(),
            "concepts/zeta.md  [orphan-page]  no inbound links",
        )
        self.assertNotIn("concepts/zeta.md:", entry)
        self.assertNotIn("None", entry)

    def test_fixed_finding_is_marked_as_fixed(self):
        finding = Finding(
            check="index-drift",
            severity=Severity.ERROR,
            path="INDEX.md",
            line=None,
            message="concepts/alpha.md not listed",
            fixed=True,
        )
        lines = render(Report([finding])).splitlines()
        (entry,) = [ln for ln in lines if "index-drift" in ln]

        self.assertIn("(fixed)", entry)

    def test_paths_are_rendered_relative_to_the_wiki_root(self):
        import pathlib

        root = pathlib.Path("/somewhere/repo/wiki")
        finding = Finding(
            check="broken-link",
            severity=Severity.ERROR,
            path=root / "concepts" / "alpha.md",
            line=1,
            message="[[nope]] does not resolve",
        )
        text = render(Report([finding], root=root))

        self.assertIn("concepts/alpha.md:1", text)
        self.assertNotIn("/somewhere/repo", text)


class TestSummary(unittest.TestCase):
    def test_report_ends_with_a_one_line_summary_count(self):
        lines = render(Report(make_findings())).splitlines()

        self.assertEqual(lines[-1], "2 errors, 2 warnings")

    def test_summary_is_singular_for_one(self):
        findings = [
            Finding(
                check="broken-link",
                severity=Severity.ERROR,
                path="concepts/alpha.md",
                line=4,
                message="[[gone]] does not resolve",
            ),
            Finding(
                check="orphan-page",
                severity=Severity.WARN,
                path="concepts/zeta.md",
                line=None,
                message="no inbound links",
            ),
        ]
        lines = render(Report(findings)).splitlines()

        self.assertEqual(lines[-1], "1 error, 1 warning")

    def test_summary_reports_fixed_count_when_nonzero(self):
        findings = [
            Finding(
                check="index-drift",
                severity=Severity.ERROR,
                path="INDEX.md",
                line=None,
                message="concepts/alpha.md not listed",
                fixed=True,
            )
        ]
        lines = render(Report(findings)).splitlines()

        self.assertEqual(lines[-1], "1 error, 0 warnings, 1 fixed")

    def test_clean_report_says_no_findings(self):
        text = render(Report([]))

        self.assertEqual(text, "No findings.")


class TestPlainText(unittest.TestCase):
    def test_output_contains_no_ansi_color_codes(self):
        text = render(Report(make_findings()))

        self.assertNotIn("\x1b", text)

    def test_render_returns_a_string_without_a_trailing_newline(self):
        text = render(Report(make_findings()))

        self.assertIsInstance(text, str)
        self.assertFalse(text.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
