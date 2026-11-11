# Design: quickstart-start-here

## 1. Evidence (2026-11-11)

- `docs/QUICKSTART.md` section 0 is "Load data from the lake (two doors)"; the install and configuration follow
  in sections 1 and 2; there is no end-to-end path or first command per source.
- Dry runs on an empty home (`BASEBALLPY_HOME` set to an empty folder): `ingest statcast -s 2024 -d pitches`
  (about 81.5 MB), `ingest retrosheet -s 2024`, `ingest chadwick`, `ingest lahman`, `ingest mlb_api -s 2024`
  all print a plan and an Estimate.

## 2. Reuse check

No code. The existing page gets a section; `click`'s command registry (`main.commands`) and the adapter
registry (`ADAPTERS`) are what the test reads.

## 3. Decision

Section placed first, short, command lines in fenced `bash` blocks; the test parses only that section.

## 4. As built

- `docs/QUICKSTART.md`: "## Start here" is now the first section (five numbered steps and a first-command table for
  Statcast, Retrosheet, Chadwick, Lahman and the MLB API); no new document.
- `tests/test_quickstart.py` (2 tests; failed first): the section is first and has five steps and a table; every
  `baseballpy <command>` is a CLI command and every `ingest <source>` a registered adapter.

## 5. Gate evidence (2026-11-11)

See the commit: pytest, ruff check, ruff format, mypy --strict, docs generate --check and openspec validate --specs.
