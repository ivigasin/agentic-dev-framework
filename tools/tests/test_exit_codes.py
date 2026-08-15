"""Exit-code and output-channel tests for the wired-up CLI.

These shell out to the real entrypoint, like `test_cli.py`, because the exit
code *is* the contract: CI and the pre-commit hook read the process status, not
a return value. A test that called `main()` in-process would not prove that the
shim propagates it.

Every run points `--path` at a fixture. The repo's own `wiki/` is never read
here — a wiki that grows a real finding must not turn this suite red.
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
ENTRYPOINT = "tools/wiki-health.py"

EXIT_OK = 0
EXIT_FINDINGS = 1

# Fixture roles, pinned here so a fixture edit that changes a severity mix
# fails with a readable name rather than an unexplained exit code.
CLEAN = "clean"          # zero findings
ERRORS = "broken-links"  # one error, no warnings
WARNS = "bad-filename"   # one warning, no errors


def run_cli(*args):
    """Run the entrypoint from the repo root and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, ENTRYPOINT, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def run_fixture(name, *args):
    return run_cli("--path", str(FIXTURES / name), *args)


class TestExitCodes(unittest.TestCase):
    def test_clean_fixture_exits_0(self):
        result = run_fixture(CLEAN)
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
        self.assertIn("No findings", result.stdout)

    def test_fixture_with_errors_exits_1(self):
        result = run_fixture(ERRORS)
        self.assertEqual(result.returncode, EXIT_FINDINGS, result.stdout + result.stderr)
        # Pin the cause: exit 1 must come from the finding, not from a crash.
        self.assertIn("broken-link", result.stdout)

    def test_fixture_with_only_warns_exits_0(self):
        result = run_fixture(WARNS)
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
        # The warning is still reported; only the exit code is unaffected.
        self.assertIn("filename-case", result.stdout)

    def test_fixture_with_only_warns_and_strict_exits_1(self):
        result = run_fixture(WARNS, "--strict")
        self.assertEqual(result.returncode, EXIT_FINDINGS, result.stdout + result.stderr)
        self.assertIn("filename-case", result.stdout)

    def test_strict_on_a_clean_fixture_still_exits_0(self):
        # Guards against --strict being read as "fail on anything".
        result = run_fixture(CLEAN, "--strict")
        self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)

    def test_json_emits_parseable_json_and_nothing_else(self):
        result = run_fixture(ERRORS, "--json")
        # Parse the WHOLE stream: any human-readable preamble would break this.
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["summary"]["error"], 1)
        checks = {finding["check"] for finding in payload["findings"]}
        self.assertIn("broken-link", checks)
        # And re-serializing must round-trip, i.e. stdout is exactly one object.
        self.assertEqual(result.stdout.strip(), json.dumps(payload, indent=2))

    def test_json_on_a_dirty_fixture_still_exits_1(self):
        result = run_fixture(ERRORS, "--json")
        self.assertEqual(result.returncode, EXIT_FINDINGS, result.stderr)

    def test_unreadable_wiki_exits_2_not_1(self):
        """Criterion 3: a tool error must stay distinguishable from findings.

        A directory named `*.md` is picked up by discovery and then fails to
        read — the same class of failure as a permission error, but reproducible
        for any user, including root.
        """
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "not-a-file.md").mkdir()
            result = run_cli("--path", tmp)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not-a-file.md", result.stderr)

    def test_json_path_error_keeps_stdout_empty(self):
        # Diagnostics belong on stderr so `--json` output stays machine-safe.
        missing = FIXTURES / "no-such-fixture"
        result = run_cli("--path", str(missing), "--json")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn("does not exist", result.stderr)


if __name__ == "__main__":
    unittest.main()
