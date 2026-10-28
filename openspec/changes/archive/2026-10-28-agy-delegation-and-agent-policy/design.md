# Design: agy Delegation

- Transport: `agy -p <prompt> --model gemini-3.8-flash-medium --effort medium --mode accept-edits --output-format json --print-timeout 900s [--agent X]`. Chosen over ACP (`~/.gemini/antigravity-acp`) and MCP because print mode is one subprocess call with a machine-readable result and needs no server or plugin.
- Safety: the wrapper prefixes the repository contract, never commits or pushes, shows the diff stat; the caller reviews the full diff and runs the gates. Prompts and read files go to Google's service, so briefs must not contain secrets.
- Evidence (2026-10-27): `agy 1.2.14`; `agy models` lists `gemini-3.8-flash-{low,medium,high}`; a smoke test returned `AGY_OK` in 13 s; a delegated file-creation task succeeded in 18 s (about 21k tokens) with a typed, documented result.
