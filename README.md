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

## Setup

1. Open this folder in Claude Code — the SessionStart hook injects the bootstrap.
2. Open `wiki/` (or the whole repo) as an Obsidian vault for the graph view.
3. Optional: point Graphify at `raw/` for batch ingestion.

## Extending

Use Anthropic's skill-creator to build each new skill with test prompts and
trigger-rate evals before adding it to `skills/INDEX.md`.
