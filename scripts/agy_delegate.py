"""Delegate a fully specified coding task to the Antigravity CLI (``agy``) and report the result.

Claude designs and reviews; ``agy`` (default ``gemini-3.8-flash-medium``) writes the code.

    uv run python scripts/agy_delegate.py TASK.md [--agent python-pro] [--model M] [--effort E]

``TASK.md`` is a complete brief: goal, files it may touch, interfaces to honour, tests that must
pass, and what NOT to change. The script prefixes the repository contract, runs ``agy`` headless
in edit-accepting mode, prints the JSON result and the resulting ``git diff --stat``. It never
commits and never pushes; the caller reviews the diff and runs the gates.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

CONTRACT = """You are implementing one task in the baseballpy repository (working directory).
Rules (non-negotiable):
- Follow AGENTS.md and CLAUDE.md. Keep Extract / Parse / Sink decoupled behind typing.Protocol;
  no hard-coded dataset names (use the registry); no hand edits to generated files
  (tables.py, lb_tables.py, mlb_tables.py, stat_combos.py, docs between GENERATED markers).
- Touch ONLY the files the task lists. Do not run git commit/push/checkout/reset.
- No network access except through baseballpy.core.http.HttpClient; tests must not use the network.
- Never swallow exceptions. Strict typing (mypy --strict), docstrings on public items, ruff clean.
- Do not invent facts about upstream data; if the task lacks information, stop and say so.
- Finish by printing a short summary: files changed, what you verified, anything unresolved.

TASK:
"""


def main() -> int:
    """Run the delegated task and print the outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="markdown brief for the agent")
    parser.add_argument("--agent", help="agy agent definition (see `agy agents`)")
    parser.add_argument("--model", default="gemini-3.8-flash-medium")
    parser.add_argument("--effort", default="medium", choices=["low", "medium", "high", "max"])
    parser.add_argument("--timeout", default="900s", help="agy --print-timeout (0 = no limit)")
    parser.add_argument("--plan-only", action="store_true", help="read-only: no edits")
    args = parser.parse_args()
    prompt = CONTRACT + args.task.read_text(encoding="utf-8")
    cmd = [
        "agy",
        "-p",
        prompt,
        "--model",
        args.model,
        "--effort",
        args.effort,
        "--output-format",
        "json",
        "--mode",
        "plan" if args.plan_only else "accept-edits",
        "--print-timeout",
        args.timeout,
    ]
    if args.agent:
        cmd += ["--agent", args.agent]
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    try:
        result = json.loads(done.stdout)
    except json.JSONDecodeError:
        print(done.stdout, done.stderr, sep="\n", file=sys.stderr)
        return 2
    print(result.get("response", "").rstrip())
    usage = result.get("usage", {})
    print(
        f"\n[agy {result.get('status')} in {result.get('duration_seconds', 0):.0f}s, "
        f"{usage.get('total_tokens', '?')} tokens, conversation {result.get('conversation_id')}]"
    )
    subprocess.run(["git", "diff", "--stat"], check=False)
    return 0 if result.get("status") == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
