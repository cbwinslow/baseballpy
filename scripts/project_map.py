"""Map the whole project from its own sources: specs, requirements, scenarios, ADRs, changes, tasks.

``uv run python scripts/project_map.py`` rewrites ``docs/agents/PROJECT_MAP.md``; ``--check`` fails
when the file is stale. ``open_tasks`` is also what ``tests/test_agent_runbooks.py`` uses to prove
that every open task of every active change appears in ``docs/agents/BACKLOG.md``.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "openspec" / "specs"
CHANGES = ROOT / "openspec" / "changes"
ADRS = ROOT / "docs" / "DECISIONS.md"
OUTPUT = ROOT / "docs" / "agents" / "PROJECT_MAP.md"

_TASK = re.compile(r"^(?P<indent>\s*)- \[(?P<mark>[ xX])\] (?P<num>\d+(?:\.\d+)?[a-z]?)\.?(?:\s|$)")


def active_changes() -> list[Path]:
    """Active change directories (everything but the archive), sorted by name."""
    return sorted(p for p in CHANGES.iterdir() if p.is_dir() and p.name != "archive")


def tasks_of(change: Path) -> list[tuple[str, bool]]:
    """``(task number, done)`` for each numbered checkbox of the change's ``tasks.md``."""
    path = change / "tasks.md"
    if not path.exists():
        return []
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _TASK.match(line)
        if match:
            found.append((match["num"], match["mark"] != " "))
    return found


def open_tasks() -> list[tuple[str, str]]:
    """``(change, task number)`` of every open *leaf* task: an open task with no open subtask."""
    leaves = []
    for change in active_changes():
        open_numbers = [n for n, done in tasks_of(change) if not done]
        for num in open_numbers:
            if not any(other.startswith(f"{num}.") for other in open_numbers):
                leaves.append((change.name, num))
    return leaves


def spec_rows() -> list[str]:
    """One table row per spec: requirements, scenarios and the tests the scenarios cite."""
    rows = []
    for spec in sorted(SPECS.iterdir()):
        text = (spec / "spec.md").read_text(encoding="utf-8")
        reqs = len(re.findall(r"^###\s+Requirement:", text, re.M))
        scenarios = len(re.findall(r"^####\s+Scenario:", text, re.M))
        tests = len(set(re.findall(r"tests/[\w/.]+\.py::\w+", text)))
        rows.append(f"| `{spec.name}` | {reqs} | {scenarios} | {tests} |")
    return rows


def adr_rows() -> list[str]:
    """One bullet per ADR heading of ``docs/DECISIONS.md``."""
    text = ADRS.read_text(encoding="utf-8")
    return [f"- {m['title']}" for m in re.finditer(r"^## (?P<title>ADR \d+:.*)$", text, re.M)]


def change_rows() -> list[str]:
    """One table row per active change: task counts and the open leaf tasks."""
    rows = []
    for change in active_changes():
        tasks = tasks_of(change)
        open_ = [n for c, n in open_tasks() if c == change.name]
        done = sum(1 for _, d in tasks if d)
        rows.append(
            f"| `{change.name}` | {done} | {len(tasks) - done} | {', '.join(open_) or 'none'} |"
        )
    return rows


SOURCE_SPECS = {
    "chadwick": "chadwick-register",
    "lahman": "lahman-database",
    "retrosheet": "retrosheet-ingestion",
    "statcast": "statcast-ingestion",
    "mlb_api": "mlb-api-ingestion",
}
TRACKS = ROOT / "docs" / "agents" / "tracks"


def source_rows() -> list[str]:
    """One scorecard row per source: where it stands against the standing standards.

    Everything is read from files and the registry, so the table is deterministic: review state
    (archived, in progress with its task counts, not started), whether a track card file exists,
    whether the source code uses the shared currency check and stores upstream fingerprints,
    cited column-description coverage, and spec size.
    """
    from baseballpy.core.datasets import datasets_for
    from baseballpy.docsgen import description_coverage
    from baseballpy.sources import catalog

    catalog.register_all()
    coverage = description_coverage(ROOT / "docs")
    rows = []
    for source in SOURCE_SPECS:  # the planned review order
        if any((CHANGES / "archive").glob(f"*-{source}-source-review")):
            review = "archived"
        elif (CHANGES / f"{source}-source-review").is_dir():
            tasks = [(n, d) for n, d in tasks_of(CHANGES / f"{source}-source-review") if "." in n]
            review = f"in progress ({sum(1 for _, d in tasks if d)}/{len(tasks)} tasks)"
        else:
            review = "not started"
        track = "yes" if any(TRACKS.glob(f"*-{source}.md")) else "no"
        code = "\n".join(
            f.read_text(encoding="utf-8")
            for f in sorted((ROOT / "src" / "baseballpy" / "sources" / source).glob("*.py"))
        )
        currency = "yes" if "core.upstream import" in code else "no"
        fingerprints = "yes" if "upstream=" in code else "no"
        described, total = coverage.get(source, (0, 0))
        percent = f"{described}/{total} ({100 * described // total}%)" if total else "n/a"
        spec_file = SPECS / SOURCE_SPECS[source] / "spec.md"
        requirements = len(re.findall(r"^###\s+Requirement:", spec_file.read_text("utf-8"), re.M))
        rows.append(
            f"| `{source}` | {len(datasets_for(source))} | {review} | {track} | {currency} | "
            f"{fingerprints} | {percent} | {requirements} |"
        )
    return rows


def render() -> str:
    """The full text of ``PROJECT_MAP.md``."""
    archived = sum(1 for p in (CHANGES / "archive").iterdir() if p.is_dir())
    docs = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs").glob("**/*.md"))
    parts = [
        "# Project map",
        "",
        "Generated by `scripts/project_map.py` (do not edit; `--check` fails when stale). Work comes",
        "from `docs/agents/BACKLOG.md`; this file shows where everything lives.",
        "",
        "## Specs (`openspec/specs/`)",
        "",
        "| Spec | Requirements | Scenarios | Tests cited |",
        "|---|---|---|---|",
        *spec_rows(),
        "",
        "## Source review scorecard (where each source stands)",
        "",
        "Review = the `<source>-source-review` change (seven stages, `docs/agents/WORK_BREAKDOWN.md`);",
        "currency = uses the shared `is_current()` check; fingerprints = stores upstream fingerprints",
        "(ADR 43); descriptions = columns with cited text. A new source review is created with",
        "`uv run python scripts/new_source_review.py <source>`.",
        "",
        "| Source | Datasets | Review | Track cards | Shared currency | Fingerprints | Column descriptions | Spec requirements |",
        "|---|---|---|---|---|---|---|---|",
        *source_rows(),
        "",
        "## Active changes (`openspec/changes/`)",
        "",
        f"{archived} changes are archived under `openspec/changes/archive/`.",
        "",
        "| Change | Tasks done | Tasks open | Open leaf tasks |",
        "|---|---|---|---|",
        *change_rows(),
        "",
        "## Decisions (`docs/DECISIONS.md`)",
        "",
        *adr_rows(),
        "",
        "## Documentation pages (`docs/`)",
        "",
        *(f"- `{d}`" for d in docs),
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args()
    text = render()
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if args.check:
        if current != text:
            print(f"{OUTPUT.relative_to(ROOT)} is stale: run scripts/project_map.py")
            return 1
        print("project map is up to date")
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
