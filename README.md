# Agentic Dev Framework

Skills (process) + Karpathy-style wiki (memory) for Claude Code and other agents.

## Architecture

    hooks (entry) -> skills (process) -> wiki (memory) -> subagents (execution)

- `CLAUDE.md` — bootstrap: hard rules, routing, invocation model (~1 page)
- `skills/` — one SKILL.md per process unit; `INDEX.md` is the lazy router.
  Claude Code only scans `.claude/skills/`, so that path is a symlink to this
  directory — keep it if you clone or copy the repo.
- `wiki/` — compiled knowledge (concepts, ADRs, projects); `SCHEMA.md` is the
  maintainer contract; open the folder as an Obsidian vault for graph view
- `raw/` — immutable source inbox for wiki-ingest
- `artifacts/` — inter-skill communication (specs, plans)

## Lifecycle

grill -> plan -> implement (fresh subagent per task, TDD) -> review -> finish

`finish` compiles learnings back into the wiki, so every task makes the next
one smarter. `wiki-lint` keeps the graph healthy.

## Wiki health

`tools/wiki-health.py` checks a wiki against the contract in `wiki/SCHEMA.md` —
broken links, orphan pages, index drift, oversized directories, and the concept
and ADR page templates. It is deterministic Python (stdlib only, no install
step), and it is the replacement for the model-invoked lint skill this
framework used to lean on: the same graph health, decided by code rather than
by inference.

    python3 tools/wiki-health.py                    # check the repo's wiki/
    python3 tools/wiki-health.py --json             # machine-readable report
    python3 tools/wiki-health.py --fix --dry-run    # what --fix would change

Flags:

| Flag | Effect |
|---|---|
| `--path DIR` | wiki directory to check (default: this repo's `wiki/`) |
| `--json` | emit the report as JSON on stdout, and nothing else |
| `--strict` | count warnings toward failure, not just errors |
| `--fix` | repair what can be repaired safely — index drift and unambiguous broken links — and append one line to `wiki/log.md`. Without it the run never writes |
| `--dry-run` | with `--fix`, print the intended changes to stderr and write nothing. On its own it is an argument error |

Exit codes:

| Code | Meaning |
|---|---|
| 0 | healthy — no findings above the threshold |
| 1 | findings: any `error`, or any `warn` under `--strict` |
| 2 | tool error — bad arguments, or a wiki that cannot be read |

Errors and warnings are separated so a wiki with only warnings still passes CI;
exit 2 is kept distinct from exit 1 so "the tool broke" never reads as "the
wiki is unhealthy". Run the tests from the repo root:

    python3 -m unittest discover -s tools/tests -t tools

## Setup

1. Open this folder in Claude Code — the SessionStart hook injects the bootstrap.
2. Open `wiki/` (or the whole repo) as an Obsidian vault for the graph view.
3. Optional: point Graphify at `raw/` for batch ingestion.

## Extending

Use Anthropic's skill-creator to build each new skill with test prompts and
trigger-rate evals before adding it to `skills/INDEX.md`.
