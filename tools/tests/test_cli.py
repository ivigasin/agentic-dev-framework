"""CLI-level tests for wiki-health.

Every test shells out to the real entrypoint from the repo root, so the
hyphenated `tools/wiki-health.py` shim is exercised alongside the package.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ENTRYPOINT = "tools/wiki-health.py"

EXPECTED_FLAGS = ("--path", "--json", "--strict", "--fix", "--dry-run")


def run_cli(*args):
    """Run the entrypoint from the repo root and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, ENTRYPOINT, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


class TestCliArguments(unittest.TestCase):
    def test_unknown_flag_exits_2(self):
        result = run_cli("--definitely-not-a-flag")
        self.assertEqual(result.returncode, 2, result.stderr)
        # A nonexistent entrypoint also exits 2, so pin the argparse message.
        self.assertIn("unrecognized arguments", result.stderr)

    def test_help_exits_0(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in EXPECTED_FLAGS:
            self.assertIn(flag, result.stdout)

    def test_missing_path_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = pathlib.Path(tmp) / "no-such-wiki"
            result = run_cli("--path", str(missing))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        # Distinguish "the tool rejected the path" from "the tool is missing".
        self.assertIn(str(missing), result.stderr)
        self.assertIn("does not exist", result.stderr)


if __name__ == "__main__":
    unittest.main()
