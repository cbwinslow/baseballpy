# Delegating code writing to `agy` (Antigravity CLI, Gemini)

Claude is the brain: it reads the contract, finds the root cause, designs the interfaces and writes the brief. `agy` (default model `gemini-3.8-flash-medium`) writes the bulk of well-specified code quickly and cheaply. Claude then reviews every line and runs the gates. This is the only subagent mechanism the owner allows (Claude `Agent`/`Workflow` subagents stay off unless asked).

## How it is wired

No ACP, MCP or plugin is needed. `agy` has a headless print mode, so delegation is one Bash call to `scripts/agy_delegate.py`. **Print mode denies agy's shell commands, and a denied call ends its turn with an empty answer**, so the default `emit` mode runs agy read-only (plan mode) and has it answer with each file as `=== FILE: path ===` plus a code block; the wrapper writes only paths under `--allow` prefixes and retries (up to 3 attempts) when a run ends on a denied action. `--mode edit` lets agy edit directly but it cannot run tests. `--dangerously-skip-permissions` is never used. The wrapper wraps:

```bash
agy -p "<contract + brief>" --model gemini-3.8-flash-medium --effort medium \
    --mode accept-edits --output-format json --print-timeout 900s [--agent <name>]
```

- Binary: `~/AppData/Local/agy/bin/agy` (on PATH). `agy models` lists models; `agy agents` lists the agent definitions (`python-pro`, `code-reviewer`, `openspec-spec-writer`, `retrosheet-data-validator`, ... defined under `~/.gemini/antigravity*/` and `~/.agents/skills`).
- The wrapper prefixes the repository contract (decoupling, no hand-edits of generated files, only the listed files, no git commit/push, no network in tests), runs in the repo working directory, prints the result JSON fields and `git diff --stat`. It never commits.
- `--plan-only` runs read-only (`--mode plan`) for second opinions and research summaries.
- Verified 2026-10-27: three real slices (ingest core, five adapters, CLI commands; 6-7 minutes and about 100-150k tokens each) were written this way; each needed review fixes (see the change `agy-delegation-and-agent-policy`). agy cannot run tests, so Claude always runs the gates. Command: `uv run python scripts/agy_delegate.py brief.md --allow src/pkg/ --allow tests/test_x.py`.

## When to delegate

Delegate: a function or module whose interface Claude has already designed; mechanical edits across many files; test files for a stated behavior; fixtures and parsers once the format is known; boilerplate (registry entries, CLI commands) following an existing pattern.

Keep with Claude: root-cause analysis; anything needing live probes or judgement about upstream behavior; schema and `unsupported` decisions; OpenSpec/ADR writing; security- or data-loss-sensitive code; the final review.

## The brief (write it to a scratch file, never inline)

1. Goal in two sentences and the OpenSpec change it belongs to.
2. **Files it may touch** (explicit list) and files it must not.
3. Interfaces to honour (signatures, Protocols, registry hooks) and one existing file to imitate.
4. Facts it must not guess (formats, column names): paste them, with their source.
5. Acceptance: tests that must pass (named), gates, behavior on bad input (raise, never swallow).
6. What to report back.

## Review protocol (mandatory, every delegation)

1. `git diff` read in full; nothing outside the listed files changed; no generated file edited by hand.
2. Check against the design rules below (no hard-coded dataset names, no new coupling, no swallowed errors, no invented upstream facts).
3. Run the gates (`pytest`, `ruff check`, `ruff format --check`, `mypy --strict src`, `docs generate --check`) and a live check if an upstream is touched.
4. Fix or re-delegate with a sharper brief; two failed delegations of the same task means Claude writes it.
5. Mention in the commit body that `agy` wrote the first draft and Claude reviewed it.

## Cautions

- `agy` sends the prompt and any files it reads to Google's service: never put secrets, tokens or the contents of `.env` files in a brief.
- Its edits are real: run it only from the repository root on a clean or known tree so the diff is attributable; do not run two delegations at once on overlapping files.
- Treat its output as untrusted until reviewed; it does not know the owner rules beyond the prefixed contract.
