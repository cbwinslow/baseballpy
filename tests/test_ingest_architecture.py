"""Architecture tests for baseballpy.ingest: decoupled core and clean boundaries."""

import ast
from pathlib import Path

INGEST_DIR = Path(__file__).parent.parent / "src" / "baseballpy" / "ingest"


def _py_files() -> list[Path]:
    return sorted(INGEST_DIR.glob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_ingest_does_not_import_sources() -> None:
    """Ingest core must never import anything from baseballpy.sources."""
    offenders: list[str] = []
    for p in _py_files():
        for mod in _imports(p):
            if mod == "baseballpy.sources" or mod.startswith("baseballpy.sources."):
                offenders.append(f"{p.name}: imports {mod}")
    assert offenders == []


def test_ingest_does_not_import_database_or_network_drivers() -> None:
    """Ingest core must not import database drivers or raw network libraries."""
    banned = {
        "duckdb",
        "httpx",
        "urllib",
        "requests",
        "aiohttp",
        "sqlite3",
        "psycopg2",
        "psycopg",
        "dlt",
    }
    offenders: list[str] = []
    for p in _py_files():
        for mod in _imports(p):
            top = mod.split(".")[0]
            if top in banned:
                offenders.append(f"{p.name}: imports {mod}")
    assert offenders == []


def _is_swallowing(handler: ast.ExceptHandler) -> bool:
    broad = handler.type is None or (
        isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}
    )
    if not broad:
        return False
    reraises = any(isinstance(n, ast.Raise) for n in ast.walk(handler))
    return not reraises


def test_no_broad_exception_swallowing_in_ingest() -> None:
    """Ingest modules must not swallow broad exceptions."""
    offenders: list[str] = []
    for p in _py_files():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _is_swallowing(node):
                offenders.append(f"{p.name}:{node.lineno}")
    assert offenders == []


def test_no_assert_statements_in_ingest() -> None:
    """Library code must use explicit exceptions, never assert statements."""
    offenders: list[str] = []
    for p in _py_files():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                offenders.append(f"{p.name}:{node.lineno}")
    assert offenders == []
