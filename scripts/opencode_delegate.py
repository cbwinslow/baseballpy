"""Delegate a task brief to OpenCode (DeepSeek, etc.) and apply changes safely.

Claude and Gemini act as the Chief of Staff; OpenCode runs lightweight or free
models (like DeepSeek v4.1 Flash) to write boilerplate, fixtures, and draft code.

Usage:
    uv run python scripts/opencode_delegate.py BRIEF.md --allow src/baseballpy/sources/ --allow tests/

The brief is a markdown file specifying the goal, allowed files, interfaces to
honour, and tests that must pass. The script safely writes only files matching an
`--allow` prefix. The Chief of Staff reviews the diff and runs the gates.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CONTRACT = """You are implementing one task in the baseballpy repository.
Rules (non-negotiable):
- Follow AGENTS.md, CLAUDE.md and docs/agents/AGENT_BOARD.md. Keep Extract / Parse / Sink decoupled
  behind typing.Protocol; no hard-coded dataset names (use the registry); no hand edits to generated files
  (tables.py, lb_tables.py, mlb_tables.py, stat_combos.py, docs between GENERATED markers).
- Touch ONLY the files the task lists. Never touch files checked out by another agent. Never run git commit/push/checkout/reset/clean.
- No network access except through baseballpy.core.http.HttpClient; tests must not use the network.
- Never swallow exceptions. Strict typing (mypy --strict), docstrings on public items, ruff clean.
- Do not invent facts about upstream data; if the task lacks information, stop and say so.
- OUTPUT FORMAT: do not write or edit files directly. Answer with every file in full, each as a line:
  === FILE: <repo-relative path> ===
  followed by one fenced code block with the complete file contents.
  Then a short summary of what you did. Nothing else.

TASK:
"""

_FILE_BLOCK = re.compile(
    r"^=== FILE: (?P<path>\S+) ===\s*\n```[\w+-]*\n(?P<body>.*?)\n```",
    re.DOTALL | re.MULTILINE,
)


def parse_model(model_str: str) -> tuple[str, str]:
    """Parse 'provider/model_id' into (providerID, model_id)."""
    if "/" in model_str:
        provider, model_id = model_str.split("/", 1)
        return provider, model_id
    return "opencode", model_str


def write_allowed_files(
    response: str, allow_prefixes: list[str], root: Path
) -> tuple[list[str], list[str]]:
    """Write files from the response that match an allowed prefix."""
    written: list[str] = []
    refused: list[str] = []
    for match in _FILE_BLOCK.finditer(response):
        rel = match["path"].replace("\\", "/")
        target = (root / rel).resolve()
        inside = target.is_relative_to(root.resolve())
        if inside and any(rel.startswith(prefix) for prefix in allow_prefixes):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(match["body"] + "\n", encoding="utf-8", newline="\n")
            written.append(rel)
        else:
            refused.append(rel)
    return written, refused


def call_opencode_api(prompt: str, provider_id: str, model_id: str) -> str:
    """Send generation prompt to the local OpenCode HTTP API."""
    payload = json.dumps(
        {
            "prompt": prompt,
            "model": {
                "providerID": provider_id,
                "id": model_id,
            },
        }
    )
    cmd = ["opencode", "api", "POST", "/api/experimental/generate/text", "-d", payload]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)  # noqa: S603 - fixed argv
    if res.returncode != 0:
        print(f"[OpenCode Error {res.returncode}] {res.stderr.strip()}", file=sys.stderr)
        if res.stdout.strip():
            print(f"[OpenCode Body] {res.stdout.strip()}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(res.stdout)
        return str(data.get("text", res.stdout))
    except json.JSONDecodeError:
        return res.stdout


def main() -> int:
    """Execute OpenCode delegation and print results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="Path to markdown brief for OpenCode")
    parser.add_argument("--allow", action="append", default=[], help="Allowed writable path prefix")
    parser.add_argument(
        "--model",
        default="opencode/deepseek-v4.1-flash-free",
        help="OpenCode model identifier (e.g. opencode/deepseek-v4.1-flash-free or opencode-go/deepseek-v4.1-flash)",
    )
    parser.add_argument(
        "--plan-only", action="store_true", help="Print model response without writing files"
    )
    args = parser.parse_args()

    if not args.plan_only and not args.allow:
        parser.error(
            "Must provide at least one --allow prefix to write files safely (or use --plan-only)"
        )

    brief = args.task.read_text(encoding="utf-8")
    full_prompt = CONTRACT + brief
    provider_id, model_id = parse_model(args.model)

    print(f"[*] Tasking OpenCode ({provider_id}/{model_id})...")
    response = call_opencode_api(full_prompt, provider_id, model_id)

    if args.plan_only:
        print("\n--- Plan Response ---")
        print(response)
        return 0

    written, refused = write_allowed_files(response, args.allow, Path.cwd())
    print(f"\n[*] Files written ({len(written)}): {', '.join(written) or 'None'}")
    if refused:
        print(f"[!] REFUSED (outside --allow): {', '.join(refused)}")

    # Print any commentary after the code blocks
    commentary = _FILE_BLOCK.sub("", response).strip()
    if commentary:
        print("\n--- Summary from OpenCode ---")
        print(commentary[:1200])

    print("\n[*] Git status after delegation:")
    subprocess.run(["git", "status", "--short"], check=False)  # noqa: S607 - git on PATH
    print("\n[!] Chief of Staff: Please review the git diff and run test gates before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
