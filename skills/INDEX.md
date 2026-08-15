# Skills Index (router — keep each entry to 2 lines)

Load a SKILL.md only when its trigger matches. Never load all skills at once.

| Skill | Invocation | Trigger | Reads | Writes |
|---|---|---|---|---|
| grill | user (`/grill`) | New feature/idea, unclear requirements, "just build X" | wiki/INDEX.md | artifacts/specs/ |
| plan | user (`/plan`) | Approved spec exists, no plan yet | spec, wiki | artifacts/plans/ |
| implement | user (`/implement`) | Plan exists with unchecked tasks | plan, wiki | code, tests |
| review | user (`/review`) | Implementation claims completion | plan, diff | review notes in plan |
| finish | model | Review passed; task closing | plan, diff | wiki pages, wiki/log.md |
| wiki-ingest | user (`/wiki-ingest`) | New source dropped in raw/ or URL given | raw/, wiki | wiki pages, manifest |
| wiki-lint | model | After any wiki write touching 3+ pages | wiki/ | lint report |

Entry/exit contract: each SKILL.md declares ENTRY (preconditions) and EXIT
(artifacts that must exist before the skill may report success).
