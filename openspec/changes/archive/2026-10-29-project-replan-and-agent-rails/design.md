# Design: project-replan-and-agent-rails

## Decisions
1. **One binding section, short pointers elsewhere.** The rules agents break live in `AGENTS.md`
   section 14 (preflight, reuse check, banned patterns, definition of done). `CLAUDE.md` repeats only
   the five hard rules and points to it; `GOAL_SEEK_PROMPT.md` points to it. One place to edit.
2. **Tool-first is a table, not a sentence.** `docs/agents/TOOLING.md` maps a need to a designated
   tool and the thing not to do. The test requires every runtime dependency to appear in it.
3. **Enforce what a machine can check.** `tests/test_agent_rails.py` checks: required headings in
   `AGENTS.md`; `CLAUDE.md` links to them; every runtime dependency is in `TOOLING.md`; every task
   card has all fields and names an existing change task; no new module imports a banned library
   (`requests`, `aiohttp`, `pandas` at module level in `src/`). Rules about judgement (is this a
   reuse of the right tool?) stay in the reuse check that the commit body must answer.
4. **Same seven stages for every source** so reviews are comparable and an agent never invents a
   method; the source order follows `EXECUTION_ORDER.md`.
5. **Cards mirror OpenSpec tasks one to one.** No second task system: the card number is the task
   number, the backlog row carries the status.

## Alternatives considered
- A lint plugin that flags `import csv`: rejected, many uses are legitimate (writing small CSVs);
  the review stage decides per module.
- Putting all rules in `CLAUDE.md`: rejected, other agents (`agy`, Codex) read `AGENTS.md`.

## Risks
Prose rules are only followed if read: the preflight in section 14 is short and `CLAUDE.md` opens
with it. Test wording must not make unrelated edits fail: tests check for headings and fields, not prose.
