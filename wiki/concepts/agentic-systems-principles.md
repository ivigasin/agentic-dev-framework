# Agentic Systems — Session Summary

*Coaching session: building and hardening the agentic-dev-framework (skills + wiki)*

## 1. The foundation: context is everything

An agent has no memory and no rules except what is in its context, right now,
this session. CLAUDE.md is not "installed" — it is re-delivered every session,
like a briefing handed to a new contractor each morning. If the hook fails
silently, the agent works with no rules and doesn't know it.

**Verified by:** the Session A/B thought experiment — with a broken hook, the
agent implements directly, because no rules exist for it.

## 2. Why process matters (three layers)

Good code from a rule-free session is still a loss, on three levels:

1. **Consistency** — no conventions, no ADR checks; ten sessions produce ten
   micro-styles (architectural decay).
2. **Knowledge** — nothing compiled into the wiki; decisions evaporate and get
   re-derived or contradicted later.
3. **Verifiability at scale** — process artifacts (spec, plan, review verdict)
   are what you audit *instead of* reading every line. No artifacts → the
   system cannot scale beyond your own eyeballs.

**Principle:** process in agentic systems isn't about making one output
better — it's about making a hundred outputs consistent, cumulative, and
auditable.

## 3. Soft rules vs. hard rules

The central distinction. Ask of any rule: *if the model ignores it, what happens?*

- **Soft** = instructions in context. Followed with high probability, never
  certainty. Erode under context pressure (long sessions). Cheap, flexible.
- **Hard** = mechanisms outside the model: tests, compilers, CI, branch
  protection, permissions, blocking hooks. Don't fade, don't negotiate.

Analogy: soft = runbook, hard = branch protection on the server.

Design method: write everything soft first → observe violations → harden
where violation is costliest. The hard version is always *a dumb
deterministic check wrapped around the smart nondeterministic model*.

Probabilistic failure compounds: 98% compliance × 30 decisions ≈ 45% chance
of at least one violation per session. Soft rules WILL be broken.

## 4. Fail-closed and the canary pattern

Detection vs. prevention: prefer fail-closed (if the safety mechanism didn't
load, don't run). Claude Code won't block a session on hook failure, so the
watchdog lives in the text itself: hook output ends with a sentinel token
(BOOTSTRAP-LOADED-OK); CLAUDE.md's first rule is "verify you can see the
sentinel, else STOP." The agent checks its own context — a soft watchdog,
therefore probabilistic. Only external mechanisms are certain.

## 5. Specification gaming (Goodhart's law at machine speed)

The lifecycle gates (spec→plan→implement→finish) can be enforced by one
PreToolUse script checking artifacts. But: a gate checking a *proxy* (file
exists, status string) gets defeated by a dummy file with the desired status.
The optimizer satisfies the proxy, not the intent — compliance theater,
no malice required.

Defenses, layered (each is gameable alone):
1. **Substance checks** — make faking as expensive as honesty (plan must
   reference real file paths, every task names a test).
2. **Independent judge** — fresh-context reviewer grading artifacts, with no
   stake in the session that produced them.
3. **Outcome verification** — tests pass, criteria demonstrably met. Hardest
   to game; this is why TDD is the load-bearing wall.

## 6. The self-modification problem

Discovered live: the approved wiki-health spec included the agent editing
CLAUDE.md, skills/, and INDEX.md — its own constitution. Procedurally clean,
categorically dangerous: an agent that can edit its own rules can weaken
every gate. Governance files need protection the agent cannot operate,
with one escape hatch: **the agent proposes governance changes as PRs;
only the human merges.**

Corollary (bootstrap deadlock): self-referential controls need a privileged
bootstrap path outside the system — CODEOWNERS must be committed *before*
the rule that consumes it is armed, or the rule blocks its own deployment.

## 7. Defense in depth — the four-layer governance stack

| Layer | Mechanism | Covers | Status |
|---|---|---|---|
| Soft | CLAUDE.md + SKILL.md contracts | day-to-day behavior | done |
| In-session | settings.json deny rules (Edit/Write on governance paths) | live-session edits | configured; live test pending (known bug history: denies sometimes silently unenforced) |
| Client git | versioned pre-commit gate via core.hooksPath | casual commits | done, **tested** |
| Server | branch protection + CODEOWNERS (require code-owner review) | everything local tricks bypass | configured; PR test pending |

Each layer covers a bypass of the previous: session edits happen before any
commit; --no-verify skips client hooks; .git/hooks doesn't survive clones
(hence versioned core.hooksPath + a committed `make setup`); only the server
layer is beyond local defeat. Solo-repo caveat: authors can't approve their
own PRs; enforce_admins=false lets the human-as-admin merge while the agent
(non-admin) stays bound — the intended asymmetry.

## 8. Verify gates empirically, never declaratively

Three gate pathologies met personally in one session:

1. **Gameable gate** — dummy plan defeats a proxy check (thought experiment).
2. **Silently unenforced gate** — settings.json deny rules with a documented
   history of not blocking anything, no error raised.
3. **Hollow gate** — pre-commit file: executable, correctly named, 0 bytes.
   Runs, does nothing, exits 0, every commit passes.

Lesson: "gate exists" and "gate works" are different claims; only a test
that *expects rejection* distinguishes them. A passing test that passes for
the wrong reason (nothing staged) is worse than a failing one.
Planned: `make test-gates` — attempt a forbidden commit, assert it fails; run in CI.

## 9. Error messages are prompts

Quality-of-rejection comparison: empty hook (silent, 20 min to diagnose) vs.
settings.json bug (silent, months of user confusion) vs. GitHub's 422 with
field-level schema violations (diagnosed in one read). 422 = "parsed fine,
content violates the contract"; the body enumerated exact field/expected-type
deltas.

For agent-facing gates this matters doubly: **the rejection message becomes
the agent's debugging context.** `exit 1` in silence → blind retries. The
governance gate's "⛔ these files, go through a PR" → the agent knows the
legitimate path. Write gate errors as if prompting the agent's next move.

## 10. "Present on my machine" ≠ "guaranteed by the repo"

Recurring trap in three forms: .git/hooks/ (unversioned → dies on clone),
`git config core.hooksPath` (lives in .git/config → needs a committed
`make setup`), .claude/settings.local.json (machine-local by design →
pre-emptively .gitignored before it exists). The repo is the only source of
truth that travels; everything outside it needs a versioned bootstrap or a
deliberate ignore.

## 11. Process audit findings (grill session on wiki-health task)

What worked: risk-ordered questions; round 2 chased consequences of round 1;
caught the user's own reversal and recorded the orphaned checks explicitly;
PostToolUse-over-PreToolUse correction (pre-write hook reads stale state).

Drift found — **decision smuggling**: spec approved with open questions still
open while acceptance criteria already encoded answers to them (criterion 18
silently decided CI never writes the log). Decisions entered through the
criteria's back door without explicit approval. Fix queued for grill/SKILL.md:
a spec may not be presented for approval while a criterion answers a
still-open question.

## 12. Current state & next steps

**Built:** framework repo (skills + wiki + hooks), GitHub repo created,
CODEOWNERS committed, branch protection armed (raw-JSON gh api call — typed
schema requires real booleans/integers, not -f strings).

**Next, in order:**
1. Test PR → expect `REVIEW_REQUIRED` (closes the server layer).
2. Live-test the settings.json deny: ask the agent to append to CLAUDE.md;
   watch whether the tool call bounces.
3. Add `\.github/` to the pre-commit GOVERNANCE regex.
4. Run the wiki-health plan through the full lifecycle as a PR.
   **Observation target: the RED stage** — does the first test genuinely
   fail before implementation, and does the agent show the failure or
   merely assert it?
5. Later: skill-creator evals on grill (weakest-link tuning); make test-gates in CI.