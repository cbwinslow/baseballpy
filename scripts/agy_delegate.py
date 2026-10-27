"""Delegate a fully specified coding task to the Antigravity CLI (``agy``) and report the result.

Claude designs and reviews; ``agy`` (default ``gemini-3.8-flash-medium``) writes the code.

    uv run python scripts/agy_delegate.py TASK.md --allow src/pkg/ --allow tests/test_x.py

``TASK.md`` is a complete brief: goal, files it may touch, interfaces to honour, tests that must
pass, and what NOT to change. Default mode is ``emit``: ``agy`` runs read-only (plan mode, no tool
approvals needed) and answers with every file as ``=== FILE: <path> ===`` plus a fenced code
block; this script writes only paths under an ``--allow`` prefix (everything else is refused and
listed). ``--mode edit`` lets ``agy`` edit files itself (print mode denies its shell commands).
Nothing is ever committed or pushed; the caller reviews the diff and runs the gates.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CONTRACT = """You are implementing one task in the baseballpy repository (working directory).
Rules (non-negotiable):
- Follow AGENTS.md and CLAUDE.md. Keep Extract / Parse / Sink decoupled behind typing.Protocol;
  no hard-coded dataset names (use the registry); no hand edits to generated files
  (tables.py, lb_tables.py, mlb_tables.py, stat_combos.py, docs between GENERATED markers).
- Touch ONLY the files the task lists. Never run git commit/push/checkout/reset/clean.
- No network access except through baseballpy.core.http.HttpClient; tests must not use the network.
- Never swallow exceptions. Strict typing (mypy --strict), docstrings on public items, ruff clean.
- Do not invent facts about upstream data; if the task lacks information, stop and say so.
- Shell commands are denied in this mode: read files with your file tools, do not run tests.
{output_rules}
TASK:
"""

EMIT_RULES = """- OUTPUT FORMAT: do not write or edit any file. Answer with every file in full, each as a line
  `=== FILE: <repo-relative path> ===` followed by one fenced code block with the complete file.
  Then a short summary of what you could not verify. Nothing else.
"""

_FILE = re.compile(
    r"^=== FILE: (?P<path>\S+) ===\s*\n```[\w+-]*\n(?P<body>.*?)\n```", re.DOTALL | re.MULTILINE
)


def write_files(response: str, allow: list[str], root: Path) -> tuple[list[str], list[str]]:
    """Write the files in ``response`` that fall under an allowed prefix; return (written, refused)."""
    written: list[str] = []
    refused: list[str] = []
    for m in _FILE.finditer(response):
        rel = m["path"].replace("\\", "/")
        target = (root / rel).resolve()
        inside = target.is_relative_to(root.resolve())
        if inside and any(rel.startswith(prefix) for prefix in allow):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(m["body"] + "\n", encoding="utf-8", newline="\n")
            written.append(rel)
        else:
            refused.append(rel)
    return written, refused


def main() -> int:
    """Run the delegated task and print the outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="markdown brief for the agent")
    parser.add_argument("--mode", default="emit", choices=["emit", "edit", "plan"])
    parser.add_argument("--allow", action="append", default=[], help="writable path prefix (emit)")
    parser.add_argument("--agent", help="agy agent definition (see `agy agents`)")
    parser.add_argument("--model", default="gemini-3.8-flash-medium")
    parser.add_argument("--effort", default="medium", choices=["low", "medium", "high", "max"])
    parser.add_argument("--timeout", default="900s", help="agy --print-timeout (0 = no limit)")
    args = parser.parse_args()
    if args.mode == "emit" and not args.allow:
        parser.error("emit mode needs at least one --allow prefix")
    rules = EMIT_RULES if args.mode == "emit" else ""
    prompt = CONTRACT.format(output_rules=rules) + args.task.read_text(encoding="utf-8")
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
        "accept-edits" if args.mode == "edit" else "plan",
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
    response = result.get("response", "")
    usage = result.get("usage", {})
    if args.mode == "emit":
        written, refused = write_files(response, args.allow, Path.cwd())
        print(f"wrote {len(written)} file(s): {', '.join(written) or '-'}")
        if refused:
            print(f"REFUSED (outside --allow): {', '.join(refused)}")
        tail = _FILE.sub("", response).strip()
        print(tail[-1500:])
    else:
        print(response.rstrip())
    print(
        f"\n[agy {result.get('status')} in {result.get('duration_seconds', 0):.0f}s, "
        f"{usage.get('total_tokens', '?')} tokens, conversation {result.get('conversation_id')}]"
    )
    print("\n[git status after the run]", flush=True)
    subprocess.run(["git", "status", "--short"], check=False)
    return 0 if result.get("status") == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
