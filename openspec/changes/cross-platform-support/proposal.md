# Proposal: cross-platform-support

## Why
The owner wants baseballpy to behave the same on Linux, macOS and Windows, with nothing that depends on a Windows tool. The code was written and run on Windows, so the audit looked for behavior that differs by operating system. The lake layout is already portable (ADR 63, `tests/test_portable_layout.py`) and CI already runs the whole suite on Ubuntu and Windows (3.11 to 3.13).

## What changes (found by the audit)
- Text files written with `Path.write_text` or `open(..., "w")` turned every LF into CRLF on Windows only, so the same file (docs, board, version file, JSON caches, quarantine, JSONL events) differed by OS. All writers now pass `newline="\n"`.
- No `.gitattributes`: line endings depended on each developer's git settings. Added `* text=auto eol=lf`.
- The Retrosheet parse pool used the platform default start method: `fork` on Linux (before Python 3.14) copies a process that has HTTP and DuckDB threads and can deadlock. It now uses `spawn` everywhere.
- A Windows console or a pipe prints with a legacy code page (table borders became `?`). The CLI switches stdout and stderr to UTF-8.
- `tests/test_portability.py` enforces these rules by reading the source, so a new `write_text` without `newline`, an `open` without `encoding`, or a process pool without `mp_context` fails the gates on every OS.
- Docs: a "Platforms" section in the README and ADR 89.

## Not changed (already portable, checked)
`core/hostlock.py` uses `fcntl.flock` on Linux and macOS and `msvcrt.locking` on Windows. `atomic_write` uses `os.replace` with a retry that only matters on Windows. Names that clash on case-insensitive disks are refused. Every `read_text` and `write_text` names its encoding.

## Impact
Spec: new `portability`. ADR 89. Tests: `tests/test_portability.py`. Code: `cli.py`, `cli_agent.py`, `cli_stream.py`, `core/{github_tree,layout,quarantine,sources_lock}.py`, `docsgen.py`, `sinks/csv.py`, `sources/statcast/extractor.py`, `sources/retrosheet/pool.py`, `.gitattributes`.
