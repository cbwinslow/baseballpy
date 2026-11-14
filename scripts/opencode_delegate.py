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
import re
import subprocess
import sys
import tempfile
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
    """Send the prompt through ``opencode run`` (the supported CLI path) and return its text answer.

    The experimental HTTP endpoint (``opencode api POST /api/experimental/generate/text``) is metered apart from the
    free models and answers "Free usage limit reached" while ``opencode run`` still works (2026-11-14).
    """
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        handle.write(prompt)
        brief = Path(handle.name)
    cmd = [
        "opencode",
        "run",
        "-m",
        f"{provider_id}/{model_id}",
        "-f",
        str(brief),
        "Follow the attached task file exactly. Do not edit any file yourself: answer only in the format it asks for.",
    ]
    try:
        res = subprocess.run(  # noqa: S603 - fixed argv
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
        )
    finally:
        brief.unlink(missing_ok=True)
    text = re.sub(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))", "", res.stdout)
    # the quota message only counts as the answer when the answer is that short: a real answer may quote it
    if res.returncode != 0 or ("Free usage limit reached" in text and len(text) < 3000):
        print(f"[OpenCode Error {res.returncode}] {res.stderr.strip()}", file=sys.stderr)
        if text.strip():
            print(f"[OpenCode Body] {text.strip()[-1500:]}", file=sys.stderr)
        sys.exit(1)
    return text


def main() -> int:
    """Execute OpenCode delegation and print results."""
    for stream in (
        sys.stdout,
        sys.stderr,
    ):  # a Windows console is cp1252: the model may answer with any character
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="Path to markdown brief for OpenCode")
    parser.add_argument("--allow", action="append", default=[], help="Allowed writable path prefix")
    parser.add_argument(
        "--model",
        default="opencode/glm-5.3-flash-free",
        help="OpenCode model identifier; the only model to use is opencode/glm-5.3-flash-free (DeepSeek was removed from OpenCode)",
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

    if not written:
        print(
            "[!] OpenCode answered without any '=== FILE: <path> ===' block: nothing was written. Its answer:"
        )
        print(response.strip()[-2500:])
        return 2

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
