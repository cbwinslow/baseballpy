"""Architecture and policy tests: import boundaries and no-silent-failure rules (AGENTS.md)."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "baseballpy"
ROOT = SRC.parent.parent


def _py_files(sub: str = "") -> list[Path]:
    return sorted((SRC / sub).rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_only_core_http_imports_httpx() -> None:
    offenders = [
        str(p.relative_to(SRC))
        for p in _py_files()
        if "httpx" in _imports(p) and p.name != "http.py"
    ]
    assert offenders == []


def test_sinks_do_not_import_network_libraries() -> None:
    banned = {"httpx", "urllib", "requests", "aiohttp"}
    offenders = [str(p.name) for p in _py_files("sinks") if _imports(p) & banned]
    assert offenders == []


def test_sources_do_not_import_database_drivers() -> None:
    banned = {"duckdb", "psycopg2", "psycopg", "sqlite3", "dlt"}
    offenders = [str(p.relative_to(SRC)) for p in _py_files("sources") if _imports(p) & banned]
    assert offenders == []


def _is_swallowing(handler: ast.ExceptHandler) -> bool:
    """True for ``except Exception/BaseException/bare`` whose body hides the error."""
    broad = handler.type is None or (
        isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}
    )
    if not broad:
        return False
    reraises = any(isinstance(n, ast.Raise) for n in ast.walk(handler))
    return not reraises


def test_no_broad_exception_swallowing() -> None:
    offenders: list[str] = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _is_swallowing(node):
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert offenders == []


def test_no_unsafe_arrow_casts() -> None:
    offenders: list[str] = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.keyword)
                and node.arg == "safe"
                and isinstance(node.value, ast.Constant)
                and node.value.value is False
            ):
                offenders.append(f"{path.relative_to(SRC)}:{node.value.lineno}")
    assert offenders == []


def test_no_assert_statements_in_library_code() -> None:
    offenders = [
        f"{p.relative_to(SRC)}:{n.lineno}"
        for p in _py_files()
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
        if isinstance(n, ast.Assert)
    ]
    assert offenders == []


@pytest.mark.parametrize("folder", ["src", "docs"])
def test_baseballdatabank_is_never_fetched(folder: str) -> None:
    """Lahman data must only come from the owner's repo or user-supplied data."""
    banned = (
        "githubusercontent.com/chadwickbureau/baseballdatabank",
        "github.com/chadwickbureau/baseballdatabank",
    )
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / folder).rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".md", ".yaml", ".yml", ".toml", ".json"}
        and any(b in path.read_text(encoding="utf-8", errors="ignore").lower() for b in banned)
    ]
    assert offenders == []
