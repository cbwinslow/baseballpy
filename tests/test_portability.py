"""baseballpy behaves the same on Linux, macOS and Windows (ADR 89).

Most of the rules are checked by reading the source (a rule broken on one OS is broken in the code
for all of them); the rest by running the code. CI runs the whole suite on Ubuntu and Windows.
"""

import ast
import io
from pathlib import Path

import pytest

from baseballpy.cli import use_utf8_streams
from baseballpy.core.config import LakeConfig
from baseballpy.core.layout import ensure_version_file

SRC = Path(__file__).resolve().parents[1] / "src" / "baseballpy"
ROOT = SRC.parents[1]


def _calls(attribute: str) -> list[tuple[Path, ast.Call]]:
    found: list[tuple[Path, ast.Call]] = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == attribute
            ):
                found.append((path, node))
    return found


def _keywords(call: ast.Call) -> set[str | None]:
    return {k.arg for k in call.keywords}


def test_text_files_name_their_encoding() -> None:
    """Without ``encoding=`` Python uses the OS code page (cp1252 on Windows, UTF-8 on Linux)."""
    bad = [
        f"{p.relative_to(SRC)}:{c.lineno}"
        for attribute in ("read_text", "write_text")
        for p, c in _calls(attribute)
        if "encoding" not in _keywords(c)
    ]
    assert bad == []


def test_written_text_keeps_lf_line_endings() -> None:
    """Without ``newline="\\n"`` Windows turns every LF into CRLF: the same file differs by OS."""
    bad = [
        f"{p.relative_to(SRC)}:{c.lineno}"
        for p, c in _calls("write_text")
        if "newline" not in _keywords(c)
    ]
    assert bad == []


def test_text_mode_open_names_encoding_and_newline_when_writing() -> None:
    bad: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open"
            ):
                continue
            mode = (
                node.args[1]
                if len(node.args) > 1
                else next((k.value for k in node.keywords if k.arg == "mode"), None)
            )
            letters = str(mode.value) if isinstance(mode, ast.Constant) else "r"
            if "b" in letters:
                continue
            needed = {"encoding", "newline"} if set(letters) & set("wax+") else {"encoding"}
            if not needed <= _keywords(node):
                bad.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert bad == []


def test_worker_processes_use_spawn_on_every_os() -> None:
    """``fork`` is the Linux default before Python 3.14 and can deadlock a threaded parent."""
    bad = [
        f"{p.relative_to(SRC)}:{c.lineno}"
        for p, c in _calls("ProcessPoolExecutor")
        if "mp_context" not in _keywords(c)
    ]
    assert bad == []
    assert not [p for p, _ in _calls("fork")]


def test_the_repository_pins_lf_for_every_checkout() -> None:
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in text
    assert "*.parquet binary" in text


def test_a_file_the_library_writes_has_no_carriage_return(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    ensure_version_file(config)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert written
    assert all(b"\r" not in p.read_bytes() for p in written)


class _Stream(io.StringIO):
    def __init__(self, encoding: str) -> None:
        super().__init__()
        self._encoding = encoding
        self.reconfigured: dict[str, str] = {}

    @property
    def encoding(self) -> str:  # type: ignore[override]  # a StringIO has none; consoles do
        return self._encoding

    def reconfigure(self, **kwargs: str) -> None:
        self.reconfigured = kwargs


@pytest.mark.parametrize(
    ("encoding", "changed"), [("cp1252", True), ("utf-8", False), ("UTF8", False)]
)
def test_console_output_is_utf8(
    monkeypatch: pytest.MonkeyPatch, encoding: str, changed: bool
) -> None:
    out, err = _Stream(encoding), _Stream(encoding)
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    use_utf8_streams()
    assert bool(out.reconfigured) is changed and bool(err.reconfigured) is changed
    if changed:
        assert out.reconfigured == {"encoding": "utf-8", "errors": "replace"}
