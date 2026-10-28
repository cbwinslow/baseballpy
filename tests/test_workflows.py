"""The GitHub workflows are parsed, and the weekly audit reports its findings as one issue."""

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _load(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_every_workflow_parses_and_has_jobs(path: Path) -> None:
    assert _load(path.name)["jobs"]


def test_weekly_audit_opens_or_updates_one_issue_on_findings() -> None:
    workflow = _load("live.yml")
    assert workflow["permissions"]["issues"] == "write"
    steps = workflow["jobs"]["audit"]["steps"]
    audit = next(s for s in steps if s.get("id") == "audit")
    assert audit["continue-on-error"] is True
    report = next(s for s in steps if "issue" in s.get("name", "").lower())
    assert report["if"] == "steps.audit.outcome == 'failure'"
    assert "gh issue create" in report["run"]
    assert "gh issue comment" in report["run"]
    assert workflow["env"]["AUDIT_ISSUE_TITLE"]
    assert "AUDIT_ISSUE_TITLE" in report["run"]


def test_weekly_audit_still_fails_the_job_after_reporting() -> None:
    steps = _load("live.yml")["jobs"]["audit"]["steps"]
    names = [s.get("name", "") for s in steps]
    final = steps[-1]
    assert final["if"] == "always() && steps.audit.outcome == 'failure'"
    assert names.index("Report audit findings as an issue") < len(steps) - 1
