---
name: plan
description: Turn an approved spec into a task-level implementation plan.
  Use whenever an approved spec exists but no plan file does, or the user
  says "plan this" / "break this down".
---

# Plan

ENTRY: `artifacts/specs/<slug>.md` with Status: approved.
EXIT: `artifacts/plans/<slug>.md` where every task is executable by a fresh
subagent with zero conversation context.

## Process

1. Read the spec and every wiki page it links.
2. Break work into tasks of 2–5 minutes of agent work each. Every task lists:
   - Exact file paths to create/modify
   - The test that proves it (written BEFORE implementation)
   - Which wiki pages the implementing subagent must read
3. Order tasks so each leaves the repo green (compiling, tests passing).

## Plan format

```md
# Plan: <title>
Spec: artifacts/specs/<slug>.md
Status: ready | in-progress | done

## Task 1: <verb phrase>
- Files: path/to/file.ts
- Test first: path/to/file.spec.ts — "<test name>"
- Context: [[concepts/x]], [[decisions/adr-007]]
- Done when: <observable condition>
- [ ] completed
```

## Anti-patterns

- Tasks like "implement the feature" (too big — split it).
- Tasks that only make sense with conversation history (self-containment test:
  could a stranger execute this from the file alone?).
