"""The agent operating rules, the designated-tools table and the task cards stay enforceable."""

import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "AGENTS.md"
CLAUDE = ROOT / "CLAUDE.md"
TOOLING = ROOT / "docs" / "agents" / "TOOLING.md"
TRACKS = ROOT / "docs" / "agents" / "tracks"
CHANGES = ROOT / "openspec" / "changes"
SRC = ROOT / "src" / "baseballpy"

CARD_FIELDS = (
    "Change task",
    "Stage",
    "Executor",
    "Files",
    "Tools (reuse check)",
    "Inputs",
    "Steps",
    "Done when",
    "Record",
)


def test_agents_md_has_the_operating_rules() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "## 14. AI Agent Operating Rules" in text
    for heading in ("14.1 Preflight", "14.2 Hard rules", "14.3 Banned patterns"):
        assert f"### {heading}" in text, heading
    assert "### 14.4 Definition of done" in text
    assert "### 14.5 When blocked" in text


def test_claude_md_states_the_hard_rules_and_points_to_the_tools_table() -> None:
    text = CLAUDE.read_text(encoding="utf-8")
    assert "## Hard rules" in text
    assert "AGENTS.md" in text and "section 14" in text
    assert "docs/agents/TOOLING.md" in text
    assert "docs/agents/WORK_BREAKDOWN.md" in text


def _runtime_dependencies() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = []
    for spec in data["project"]["dependencies"]:
        match = re.match(r"[A-Za-z0-9_.-]+", spec)
        assert match
        names.append(match.group(0).lower())
    return names


def test_every_runtime_dependency_is_in_the_tooling_table() -> None:
    text = TOOLING.read_text(encoding="utf-8").lower()
    missing = [name for name in _runtime_dependencies() if name not in text]
    assert not missing, f"add these dependencies to docs/agents/TOOLING.md: {missing}"


def _cards() -> list[tuple[Path, str, str]]:
    cards = []
    for path in sorted(TRACKS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        parts = re.split(r"^### (?=[A-Z]-\d+ )", text, flags=re.M)[1:]
        for part in parts:
            title, _, body = part.partition("\n")
            cards.append((path, title.strip(), body))
    return cards


def test_task_cards_exist_and_have_every_field() -> None:
    cards = _cards()
    assert cards, "docs/agents/tracks/ has no task cards"
    problems = [
        f"{path.name} {title}: missing {field}"
        for path, title, body in cards
        for field in CARD_FIELDS
        if f"**{field}:**" not in body
    ]
    assert not problems, problems


def _task_numbers(change: str) -> set[str]:
    for base in (CHANGES, CHANGES / "archive"):
        for candidate in [base / change, *base.glob(f"*-{change}")]:
            tasks = candidate / "tasks.md"
            if tasks.exists():
                found = re.findall(r"- \[[ xX]\] (\d+(?:\.\d+)?)", tasks.read_text("utf-8"))
                return set(found)
    return set()


def test_every_card_names_a_real_change_task() -> None:
    problems = []
    for path, title, body in _cards():
        match = re.search(r"\*\*Change task:\*\* `([a-z][a-z0-9_-]+) (\d+(?:\.\d+)?)`", body)
        if not match:
            problems.append(f"{path.name} {title}: Change task is not `<change> <number>`")
        elif match.group(2) not in _task_numbers(match.group(1)):
            problems.append(f"{path.name} {title}: no task {match.group(2)} in {match.group(1)}")
    assert not problems, problems


def test_source_code_uses_no_banned_libraries() -> None:
    banned = ("requests", "aiohttp", "urllib.request", "pandas")
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                if any(name == b or name.startswith(f"{b}.") for b in banned):
                    offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno} {name}")
    assert offenders == []
