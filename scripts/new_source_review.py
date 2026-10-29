"""Create the OpenSpec change, the task-card file and the backlog rows for a source review.

Usage::

    uv run python scripts/new_source_review.py lahman [--dry-run]

Every source is reviewed with the same seven stages (``docs/agents/WORK_BREAKDOWN.md``) and the same
standing standards (shared currency check, export checklist, full access, cited descriptions). The
standard tasks live in one table (:data:`CARDS`); this script renders them for a source, so the
reviews cannot drift apart. Afterwards an agent fills in the "Starting facts" of ``design.md`` and the
"Suspected findings" of the track file, and adds the findings as tasks ``5.n`` with cards.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
CHANGES = ROOT / "openspec" / "changes"
TRACKS = ROOT / "docs" / "agents" / "tracks"
BACKLOG = ROOT / "docs" / "agents" / "BACKLOG.md"

#: source -> (track number, card prefix, display name, spec name, data-workflow-standard task)
SOURCES: dict[str, tuple[str, str, str, str, str]] = {
    "chadwick": ("01", "C", "Chadwick", "chadwick-register", "done"),
    "lahman": ("02", "L", "Lahman", "lahman-database", "2.5"),
    "retrosheet": ("03", "R", "Retrosheet", "retrosheet-ingestion", "2.6"),
    "statcast": ("04", "S", "Statcast", "statcast-ingestion", "2.7"),
    "mlb_api": ("05", "M", "MLB API", "mlb-api-ingestion", "2.8"),
}


@dataclass(frozen=True)
class Card:
    """One standard review task (section.number), rendered for a source."""

    num: str
    stage: str
    title: str
    executor: str
    files: str
    tools: str
    inputs: str
    steps: tuple[str, ...]
    done: str
    record: str


CARDS: tuple[Card, ...] = (
    Card(
        "1.1",
        "S1",
        "Inventory the provider against the registry",
        "Claude",
        "docs/sources/$source.md (hand-written part), the change's design.md",
        "git tree listing (core/github_tree.py) or the provider's own listing, HttpClient; docs/references/",
        "the pinned version (core/sources_lock.json) or the provider docs; `uv run baseballpy catalog list`",
        (
            "list every file, endpoint, parameter and documentation file the provider offers",
            "map each to a registered dataset, or mark it a gap with the reason (README, licence and data-dictionary files count: nothing is left behind)",
            "read the provider's licence and data dictionary and write down which licence applies and what attribution it asks for",
            "if the source has a second way in (user-supplied files, an alternative mirror), inventory a real sample of that too",
            "compare the latest upstream version with the pin; record the inventory table in design.md",
        ),
        "every upstream item is mapped or listed as a gap with a reason; the licence is named; `uv run baseballpy catalog status --gaps` for the source is pasted in design.md",
        "tick 1.1; design.md section S1",
    ),
    Card(
        "1.2",
        "S2",
        "Check registry and adapter conformance",
        "Claude",
        "src/baseballpy/sources/$source/adapter.py, tests/test_ingest_adapters.py (read only; fixes are tasks 5.n)",
        "the dataset registry (core/datasets.py) is the only list of dataset names",
        "`uv run baseballpy ingest $source -d <name> --dry-run` for every registered dataset",
        (
            "reproduce: is every registered dataset accepted by --datasets, and unknown names rejected with the registry list?",
            "find every hard-coded list of dataset or table names in the source (adapter, extractor, api) and whether it agrees with the registry",
            "record the result; a disagreement becomes a task 5.n",
        ),
        "the result for every registered dataset is in design.md; every disagreement has a task 5.n",
        "tick 1.2; design.md S2",
    ),
    Card(
        "1.3",
        "S3",
        "Compare the generated schema with real data",
        "Claude",
        "design.md; regenerate with the source's generator in scripts/ only if a mismatch is proven (never hand-edit generated files)",
        "Polars or pyarrow to profile the cached Parquet and the raw files, never a Python row loop",
        "the source's tables.py (types), one clean ingest, docs/sources/$source.md",
        (
            "profile every column: type, null rate, distinct values, ranges, sentinel-looking values (blank vs 0 vs a text marker), empty strings",
            "check uniqueness of every registry key and which key columns contain NULLs (a key with NULLs cannot be merged on export; changing a key is a generator change and an OWNER decision)",
            "check every id column that points into another table or another source: orphan rows inside the source, and the match rate against the Chadwick register for player ids",
            "check _extras is empty and that drift is logged once; list era or provider quirks to document",
        ),
        "a table in design.md with a verdict per column group and the measured match rates; every mismatch has a follow-up task 5.n or a regeneration commit",
        "tick 1.3; design.md S3",
    ),
    Card(
        "1.4",
        "S4",
        "Review the code against the designated tools and decoupling rules",
        "Claude (review only; no code change in this task)",
        "read all of src/baseballpy/sources/$source/",
        "docs/agents/TOOLING.md rows: HTTP, parsing, dataframe code, concurrency, config",
        "AGENTS.md sections 2, 4, 7, 8 and 14; tests/test_architecture.py",
        (
            "per module: what it does and which designated tool covers it",
            "flag Python loops over bulk data, hard-coded names, custom retry/hash/cache code, per-source special cases, swallowed errors, non-atomic writes",
            "list every cache shortcut (raw tier and processed tier) and say whether upstream is ever asked before it serves data",
            "check validation and quality code: does its result depend on load order, is it shown to users or only logged?",
            "measure load, first lookup and 1000 repeated calls of each public function on a real lake; look for registry, catalog or config work done on every call",
            "for each flag choose migrate (new task 5.n) or tool-cannot (one sentence of evidence)",
        ),
        "design.md has the per-module table, the cache-tier list and the timings; every migrate has a numbered follow-up task in tasks.md and a BACKLOG row",
        "tick 1.4; add tasks 5.n",
    ),
    Card(
        "5.1",
        "S4",
        "Record upstream fingerprints for every raw file",
        "Claude designs, agy codes (review the full diff)",
        "the source's extractor, tests/test_$source*.py",
        "core/upstream.py (Fingerprint), RawStore.put(upstream=...), core/github_tree.py for git blob SHAs; the Chadwick extractor as the model",
        "ADR 43; docs/DATA_WORKFLOW.md; `uv run baseballpy cache check --upstream --source $source`",
        (
            "record the provider's fingerprint of every raw file: git blob SHA from the tree, else ETag or Last-Modified, else the content sha256",
            "files the user supplied keep their own origin marker; decide and document what `cache check --upstream` reports for them",
            "tests with respx that the fingerprints are stored",
            "run `cache check --upstream --source $source` on a real lake",
        ),
        "every remote raw file reports current or changed (not `no_fingerprint` or `not_checked`); local imports report a documented verdict; the tests pass",
        "tick 5.1; design.md S4",
    ),
    Card(
        "5.2",
        "S4",
        "Decide currency with is_current() at every cache tier",
        "Claude designs, agy codes (review the full diff)",
        "the source's extractor and api modules, tests/test_$source*.py; tick data-workflow-standard $dws in that change",
        "core/upstream.py (is_current), the cache-tier list from task 1.4",
        "ADR 43; the Chadwick extractor and register as the model",
        (
            "route every cache shortcut found in 1.4 (raw tier AND processed tier) through is_current(); fixing only the extractor leaves the processed tier serving stale data",
            "use the pinned fingerprint as `expected=` (reproducible mode) unless the owner decides the source should float with a time-to-live: OWNER decision, ask once, then continue",
            "tests with respx: fresh copy costs no request, changed fingerprint refetches, unreachable upstream serves the copy with a warning",
            "correct any documentation that claims behavior the code does not have",
        ),
        "no cache shortcut bypasses is_current(); the old decision code is gone; the tests above pass; the docs state what is checked at each tier",
        "tick 5.2 and data-workflow-standard $dws; design.md S4",
    ),
    Card(
        "5.3",
        "S1",
        "Keep the provider's documentation files",
        "Claude designs, agy codes (review the full diff)",
        "a shared helper in src/baseballpy/core/ (move Chadwick's DOCUMENT_FILES logic there), the source's extractor, docs/DATA_LICENSES.md, tests",
        "RawStore.put with fingerprints; core/github_tree.py; AGENTS.md 14.2.4 (a helper used twice moves to core/)",
        "the documentation files found in task 1.1 (README, licence, data dictionary)",
        (
            "keep each documentation file in raw/ with its sha256 and fingerprint through one shared helper that Chadwick and this source both use",
            "state the licence and the attribution text in docs/DATA_LICENSES.md from the kept text",
            "tests: the files are stored once, not downloaded again on a cached run, a failed download is logged and does not block the data",
        ),
        "the files are in raw/ with hashes; Chadwick uses the same helper and its tests still pass; DATA_LICENSES names the licence",
        "tick 5.3; design.md S1",
    ),
    Card(
        "5.4",
        "S4",
        "Review the second way in (user-supplied files); N/A if the source has none",
        "Claude designs, agy codes (review the full diff)",
        "the source's import code, tests, docs/sources/$source.md",
        "the source's own safety checks stay; the registry decides which files are datasets",
        "the sample inventoried in task 1.1",
        (
            "keep the non-data files (README, licence, data dictionary) of a supplied release, not only the data files",
            "detect a mixed release: a partial supplied set completed from the remote mirror must warn or refuse",
            "decide what unknown files in a supplied set become (reject, or keep raw only), never silent unregistered tables",
            "document how currency applies to supplied data",
        ),
        "tests cover the partial import, the unknown file and the kept documents; or the card is marked N/A with one sentence",
        "tick 5.4; design.md S4",
    ),
    Card(
        "5.5",
        "S7",
        "Make every dataset and column reachable from Python",
        "Claude designs, agy codes (review the full diff)",
        "src/baseballpy/sources/$source/__init__.py and api module, tests, docs/sources/$source.md, docs/QUICKSTART.md",
        "pyarrow tables from ProcessedStore; Polars/narwhals for lookups; a process-wide cache when lookups repeat (as ChadwickRegister.load does)",
        "the registry (every dataset), the schema (every column); the access that already exists (do not rebuild it)",
        (
            "list datasets with no documented Python access; reuse the generic accessor if one exists, else add one driven by the registry and validated against it (OWNER decision if named functions per dataset are wanted instead)",
            "if the source has record classes, add a schema-sync test that fails when a column is missing from them; otherwise mark this step N/A (tables only)",
            "run every code block of docs/sources/$source.md and the source's quickstart lines against a real lake and fix wrong examples",
        ),
        "every registered dataset is readable with one documented call; every documented example ran; the new tests pass",
        "tick 5.5; docs updated",
    ),
    Card(
        "2.1",
        "S5",
        "Close the spec and test gaps",
        "agy writes tests from the findings, Claude reviews",
        "openspec/changes/$source-source-review/specs/$spec/spec.md (delta), tests/test_$source*.py",
        "respx for HTTP, hypothesis for parsing and lookups, fixtures under tests/fixtures/",
        "the current spec requirements and every finding that changed behavior; start only when every task 5.n is done",
        (
            "one scenario per finding and per requirement without one; each ends with a `Verified by` line",
            "property tests where parsing or lookups are lossy",
            "confirm unit tests make no network call",
        ),
        "`uv run pytest tests/test_spec_scenarios.py tests/test_$source*.py -q` and `openspec validate --specs` pass",
        "tick 2.1; the delta stays in the change until the close task",
    ),
    Card(
        "3.1",
        "S6",
        "Live verification on a clean scratch home",
        "Claude",
        "none in the repo; evidence goes into design.md",
        "the CLI (ingest, cache check, catalog status, audit tail); no ad hoc scripts committed",
        "about 120 GB free on this PC; set BASEBALLPY_HOME to a scratch folder and delete it afterwards",
        (
            "ingest the source from an empty home; note rows, bytes and seconds from audit.jsonl",
            "run again: nothing downloaded, audit shows cache_hit true",
            "`baseballpy cache check` and `cache check --upstream --source $source`",
            "raw rows (minus any header line) against processed rows; spot-check known facts against the provider",
        ),
        "counts, timings, the second-run result and the cache-check output are pasted in design.md",
        "tick 3.1; design.md S6",
    ),
    Card(
        "3.2",
        "S7",
        "Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source)",
        "Claude",
        "design.md; docs/sources/$source.md (exceptions that apply)",
        "baseballpy export (export.py): pyarrow files, native DuckDB, dlt PostgreSQL; embedded pgserver for PostgreSQL",
        "the cached datasets from the live run; `uv run --with pgserver` or the dev dependency",
        (
            "export every dataset to parquet and csv, then duckdb and postgres, with verification on",
            "check that column names survive every target (mixed case, names that start with a digit, reserved words) and compare the names read back",
            "try --mode merge and note which datasets are refused (key with NULLs)",
            "record rows, seconds and sizes; list the exceptions (nested columns, season partitions, size)",
        ),
        "every dataset verifies for every target or has a stated exception in the source page; numbers pasted in design.md",
        "tick 3.2; design.md S7",
    ),
    Card(
        "3.3",
        "S7",
        "Cited column descriptions",
        "Claude",
        "scripts/build_column_descriptions.py (the source's builder), docs/columns/$source.json (generated), docs/sources/$source.md",
        "the provider's own documentation (never invented text); `uv run baseballpy docs generate`",
        "ADR 34; the description coverage in docs/agents/PROJECT_MAP.md (it counts _extras columns too: state which denominator you mean)",
        (
            "list undescribed columns",
            "add cited text for each column the provider defines, citing the pinned version of the document (not a moving branch)",
            "list the columns the provider does not define in the source page",
        ),
        "`uv run python scripts/build_column_descriptions.py $source` run, `docs generate --check` clean, coverage not lower than before",
        "tick 3.3; design.md S7",
    ),
    Card(
        "4.1",
        "S7",
        "Docs, decisions, spec merge, archive",
        "Claude",
        "docs/sources/$source.md, docs/DECISIONS.md, openspec/specs/$spec/spec.md, this change directory (moved to archive/), BACKLOG.md, EXECUTION_ORDER.md",
        "uv run baseballpy docs generate (never hand-type counts)",
        "design.md of this change",
        (
            "update the hand-written parts of the source page (keys, quirks, access, export, currency)",
            "one ADR per decision",
            "merge the spec delta into openspec/specs",
            "run all gates; move the change to openspec/changes/archive/<date>-$source-source-review; update BACKLOG, EXECUTION_ORDER, PROJECT_MAP",
        ),
        "gates green, `openspec validate --specs` passes, change archived, scorecard row complete",
        "tick 4.1 and archive the change",
    ),
)

#: section number -> heading; sections render in this order (fixes come before tests and verification)
SECTIONS = {
    "1": "Review (look and report; no code changes)",
    "5": "Fixes (the standard ones first, then one task per finding of the review)",
    "2": "Tests",
    "3": "Verify",
    "4": "Close",
}


def _subs(source: str) -> dict[str, str]:
    number, prefix, name, spec, dws = SOURCES[source]
    return {
        "source": source,
        "Source": name,
        "spec": spec,
        "dws": f"{dws}" if dws != "done" else "(done)",
    }


def _card_id(prefix: str, index: int) -> str:
    return f"{prefix}-{index:02d}"


def render_tasks(source: str) -> str:
    """tasks.md of the source's review."""
    number, prefix, name, spec, _ = SOURCES[source]
    s = _subs(source)
    lines = [
        f"# Tasks: {source}-source-review",
        "",
        f"Cards with steps and files: `docs/agents/tracks/{number}-{source}.md` (card {prefix}-0N is the Nth task below).",
        "Findings of the review become tasks `5.n` (with cards) before the tests and verification tasks run.",
        "",
    ]
    section = ""
    for index, card in enumerate(CARDS, start=1):
        head = card.num.split(".")[0]
        if head != section:
            section = head
            lines.append(f"- [ ] {head}. {SECTIONS[head]}")
        lines.append(
            f"  - [ ] {card.num} {Template(card.title).substitute(s)} ({_card_id(prefix, index)})"
        )
    return "\n".join(lines) + "\n"


def render_cards(source: str) -> str:
    """The track file: header plus one card per standard task."""
    number, prefix, name, spec, _ = SOURCES[source]
    s = _subs(source)
    out = [
        f"# Track {int(number)}: {name}",
        "",
        f"OpenSpec change: `openspec/changes/{source}-source-review/`. Spec: `openspec/specs/{spec}/`.",
        f"Docs: `docs/sources/{source}.md`. Code: `src/baseballpy/sources/{source}/`. Method: `docs/agents/WORK_BREAKDOWN.md`;",
        "standing standards: `docs/DATA_WORKFLOW.md` (currency, export, onboarding checklist), `docs/agents/TOOLING.md`.",
        "",
        "How to read a card: a step that does not apply is marked N/A with one sentence of reason; a step that",
        "needs a decision from the owner is marked OWNER, the agent asks once (one short list) and moves on to",
        "the next card. Tasks 1.x only look and report; every fix is a task 5.n.",
        "",
        "Suspected findings to verify (not yet confirmed; the cards decide):",
        "- (fill in from the survey in design.md)",
        "",
    ]
    for index, card in enumerate(CARDS, start=1):
        sub = lambda text: Template(text).substitute(s)  # noqa: E731
        out += [
            f"### {_card_id(prefix, index)} {sub(card.title)}",
            f"- **Change task:** `{source}-source-review {card.num}`",
            f"- **Stage:** {card.stage}",
            f"- **Executor:** {card.executor}",
            f"- **Files:** {sub(card.files)}",
            f"- **Tools (reuse check):** {sub(card.tools)}",
            f"- **Inputs:** {sub(card.inputs)}",
            "- **Steps:** "
            + "; ".join(f"{i}. {sub(step)}" for i, step in enumerate(card.steps, 1))
            + ".",
            f"- **Done when:** {sub(card.done)}.",
            f"- **Record:** {sub(card.record)}.",
            "",
        ]
    return "\n".join(out)


def render_proposal(source: str) -> str:
    """proposal.md of the source's review."""
    number, prefix, name, spec, _ = SOURCES[source]
    return f"""# Proposal: {source}-source-review

## Why
Track {int(number)} of the source-by-source review (owner request 2026-10-29). {name} is reviewed with the
same seven stages and standing standards as Chadwick: complete inventory, registry conformance, schema
against real data, code against the designated tools, the shared currency check (ADR 43), full Python
access, tests and spec, a clean live run, the export checklist (ADR 46), cited column descriptions and
documentation. Starting facts and suspected findings are in design.md.

## What changes
The standard tasks in tasks.md (cards in `docs/agents/tracks/{number}-{source}.md`): look-only review tasks 1.x, the
standard fixes 5.1 to 5.5, one more task `5.n` for each finding of the review, then tests, verification and close. Code changes happen only under a numbered task.

## Out of scope
Other sources; the export command itself (built, ADR 46); changes to how the provider is reached beyond
what a finding requires.

## Impact
`src/baseballpy/sources/{source}/`, `docs/sources/{source}.md`, the `{spec}` spec, `docs/columns/{source}.json`.
"""


def render_design(source: str) -> str:
    """design.md skeleton: the seven stages, to be filled in as tasks complete."""
    return f"""# Design: {source}-source-review

Method and card format: `docs/agents/WORK_BREAKDOWN.md`; cards: `docs/agents/tracks/{SOURCES[source][0]}-{source}.md`.
Evidence goes into the sections below as each task completes (command output, counts, dates).

## Starting facts (survey before the review)
(fill in: what exists, sizes, pins, tests, spec, docs, known gaps)

## S1 inventory
(not started)

## S2 conformance
(not started)

## S3 schema and types
(not started)

## S4 code review against the designated tools
(not started)

## S5 tests and spec gaps
(not started)

## S6 live verification
(not started)

## S7 access, export, descriptions, docs, close
(not started)
"""


def next_backlog_number(text: str) -> int:
    """The next free ``B-nn`` id of the backlog."""
    found = [int(n) for n in re.findall(r"\| B-(\d+) \|", text)]
    return max(found, default=0) + 1


def render_backlog(source: str, text: str) -> str:
    """Backlog rows (one per standard task) continuing the numbering of ``text``."""
    number, prefix, name, spec, _ = SOURCES[source]
    s = _subs(source)
    start = next_backlog_number(text)
    rows = [
        "",
        f"## Source review: {name} (`{source}-source-review`, track {int(number)})",
        "",
        "| ID | Task | Status | Done when |",
        "|---|---|---|---|",
    ]
    for offset, card in enumerate(CARDS):
        status = "READY" if offset == 0 else f"after B-{start + offset - 1}"
        if card.num == "2.1":
            status += " and after every task 5.n found by the review (add its rows below)"
        title = Template(card.title).substitute(s)
        rows.append(
            f"| B-{start + offset} | `{source}-source-review {card.num}`: {title} "
            f"(card {_card_id(prefix, offset + 1)}) | {status} | see the card |"
        )
    return "\n".join(rows) + "\n"


def render(source: str, backlog_text: str) -> dict[Path, str]:
    """Every file to create (path -> text); the backlog entry is the rows to append."""
    number = SOURCES[source][0]
    base = CHANGES / f"{source}-source-review"
    return {
        base / "proposal.md": render_proposal(source),
        base / "design.md": render_design(source),
        base / "tasks.md": render_tasks(source),
        TRACKS / f"{number}-{source}.md": render_cards(source),
    }


def _show(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def main(argv: list[str] | None = None) -> int:
    """Create the review files for a source (refuses to overwrite)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--dry-run", action="store_true", help="print the paths only")
    args = parser.parse_args(argv)
    backlog_text = BACKLOG.read_text(encoding="utf-8")
    files = render(args.source, backlog_text)
    existing = [p for p in files if p.exists()]
    if existing:
        print(f"refusing to overwrite: {[_show(p) for p in existing]}")
        return 1
    for path in files:
        print(("would create " if args.dry_run else "creating ") + _show(path))
    if args.dry_run:
        return 0
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    BACKLOG.write_text(
        backlog_text.rstrip("\n") + "\n" + render_backlog(args.source, backlog_text),
        encoding="utf-8",
    )
    print("appended backlog rows; now fill in the survey in design.md and the suspected findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
