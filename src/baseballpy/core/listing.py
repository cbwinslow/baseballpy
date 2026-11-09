"""Which Parquet files of a dataset folder are data (ADR 96, design section 2).

A dataset folder holds ``part-*``, ``compact-*`` and ``seg-*`` Parquet files, directly in it
(a dataset that is not split) or one folder level down in ``season=YYYY/`` (a split one). Folders
whose name starts with an underscore (``_open`` while a segment is written, ``_legacy`` while a
season is replaced) and files that end in ``.part`` or start with an underscore are never data:
a reader that took them would count rows twice or read half a file.
"""

from collections.abc import Iterator
from pathlib import Path


def is_hidden(path: Path, root: Path) -> bool:
    """True for a file below ``root`` that is not data: in an underscore folder, ``_*`` or ``*.part``."""
    parts = path.relative_to(root).parts
    return any(part.startswith("_") for part in parts) or path.name.endswith(".part")


def dataset_files(root: Path, *, by_season: bool) -> list[Path]:
    """The data files of a dataset folder, sorted: ``season=*/*.parquet`` or ``*.parquet``."""
    if not root.is_dir():
        return []
    pattern = "season=*/*.parquet" if by_season else "*.parquet"
    return sorted(p for p in root.glob(pattern) if not is_hidden(p, root))


def dataset_glob(root: Path, *, by_season: bool) -> Path:
    """The same files as one glob for DuckDB or Polars (hidden ones cannot match it)."""
    return root / "season=*" / "*.parquet" if by_season else root / "*.parquet"


def visible_parquet(root: Path) -> Iterator[Path]:
    """Every data file below ``root`` when the layout is not known (unregistered datasets)."""
    if root.is_dir():
        yield from (p for p in root.rglob("*.parquet") if not is_hidden(p, root))
