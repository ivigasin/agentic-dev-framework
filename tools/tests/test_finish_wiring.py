"""Tests that `skills/finish/SKILL.md` calls the CLI, not the old skill.

Spec criterion 23. The wiki health check used to be `skills/wiki-lint/`, a
model-invoked skill: `finish` step 6 asked the model to go read the wiki and
judge it. That judgement is now deterministic Python, so step 6 has to name the
program instead — and naming it is the whole contract. A SKILL.md is prose read
by a model at runtime; nothing imports it, so a stale instruction there is
invisible to every other test in this suite. Hence these two assertions, which
are deliberately about text.

The command string is asserted verbatim (`python3 tools/wiki-health.py`)
because that exact invocation is what the spec fixes and what the entrypoint
supports; `python tools/wiki-health.py` or an import of `wiki_health.cli` would
be a different, unsupported contract.

The second test greps the file for `wiki-lint` in any form. Task 17 removes the
skill directory and the other references (CLAUDE.md, skills/INDEX.md,
README.md); this test guards only the one file this task owns, so that a
half-finished rewiring — CLI added, old call left behind — fails loudly rather
than leaving `finish` with two competing instructions.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FINISH_SKILL = REPO_ROOT / "skills" / "finish" / "SKILL.md"

CLI_COMMAND = "python3 tools/wiki-health.py"


class TestFinishInvokesTheCli(unittest.TestCase):
    def test_finish_skill_file_exists(self):
        self.assertTrue(
            FINISH_SKILL.is_file(),
            f"expected the finish skill at {FINISH_SKILL}",
        )

    def test_finish_invokes_the_cli_by_its_exact_command_string(self):
        text = FINISH_SKILL.read_text(encoding="utf-8")
        self.assertIn(
            CLI_COMMAND,
            text,
            "finish/SKILL.md must name the health check by its exact "
            f"invocation, {CLI_COMMAND!r}",
        )

    def test_finish_reads_the_json_output(self):
        text = FINISH_SKILL.read_text(encoding="utf-8")
        self.assertIn(
            "--json",
            text,
            "finish/SKILL.md must ask for machine-readable output (--json) "
            "so the result can be parsed rather than eyeballed",
        )


class TestFinishNoLongerReferencesTheSkill(unittest.TestCase):
    def test_finish_no_longer_references_the_skill(self):
        text = FINISH_SKILL.read_text(encoding="utf-8")
        self.assertNotIn(
            "wiki-lint",
            text,
            "finish/SKILL.md still references the retired wiki-lint skill",
        )


if __name__ == "__main__":
    unittest.main()
