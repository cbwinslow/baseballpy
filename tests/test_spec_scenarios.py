"""Every spec scenario that cites a test names a test that exists."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _citations() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for spec in sorted((ROOT / "openspec" / "specs").glob("*/spec.md")):
        for line in spec.read_text(encoding="utf-8").splitlines():
            if not line.startswith("- Verified by "):
                continue
            current = ""
            for match in re.finditer(r"(tests/\w+\.py)|::(\w+)", line):
                if match.group(1):
                    current = match.group(1)
                else:
                    found.append((spec.parent.name, current, match.group(2)))
    return found


def test_specs_cite_tests() -> None:
    assert len(_citations()) >= 45


def test_every_cited_test_exists() -> None:
    missing = []
    for spec, file, name in _citations():
        path = ROOT / file
        if not path.is_file() or not re.search(
            rf"(?m)^(async )?def {re.escape(name)}\(", path.read_text(encoding="utf-8")
        ):
            missing.append(f"{spec}: {file}::{name}")
    assert not missing, missing


def test_every_scenario_cites_a_test() -> None:
    uncited = []
    for spec in sorted((ROOT / "openspec" / "specs").glob("*/spec.md")):
        text = spec.read_text(encoding="utf-8")
        for block in re.split(r"(?m)^(?=####\s+Scenario:)", text)[1:]:
            body = re.split(r"(?m)^(?=#{1,3}\s)", block)[0]
            if not re.search(r"^- Verified by .*tests/\w+\.py::\w+", body, re.M):
                uncited.append(f"{spec.parent.name}: {body.splitlines()[0]}")
    assert not uncited, f"scenarios without a `- Verified by` line naming a test: {uncited}"
