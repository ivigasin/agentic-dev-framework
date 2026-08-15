# Agent Operating Manual (Bootstrap)

You are working inside a skills + wiki framework. Read this file fully; load
everything else lazily.

## Non-negotiable rules

1. NEVER write implementation code before a plan artifact exists in
   `artifacts/plans/`. If asked to "just build it", run the `grill` skill first.
2. NEVER claim a task is done without running the `review` skill.
3. Every completed task ends with the `finish` skill (compile learnings into wiki).
4. Skills communicate through files, not conversation memory.
   Artifacts live in `artifacts/`, knowledge lives in `wiki/`.
5. Before starting any task, read `wiki/INDEX.md` and follow links relevant
   to the task. Do not load the whole wiki.

## Routing

- Skills index (what process to follow): `skills/INDEX.md`
- Knowledge index (what we know): `wiki/INDEX.md`
- Wiki maintenance rules: `wiki/SCHEMA.md`

## Invocation model

- Skills live in `skills/<name>/SKILL.md`, exposed to Claude Code via the
  `.claude/skills` symlink. Invoke them with the Skill tool (`/<name>`), not
  by reading the file.
- **User-invoked skills** (slash commands): grill, plan, implement, review,
  wiki-ingest. Run only when the user asks.
- **Model-invoked skills**: finish, wiki-lint. Reach for these yourself when
  the trigger in `skills/INDEX.md` matches.
- A user-invoked skill MAY call model-invoked skills.
  A user-invoked skill MUST NOT call another user-invoked skill.

## Lifecycle

grill → plan → implement (subagent per task) → review → finish

Exit criteria of each skill are the entry conditions of the next.
Each SKILL.md states both.
