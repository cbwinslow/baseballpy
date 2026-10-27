"""Lake layout versioning: detect v1 trees, stamp the ``VERSION`` file, hint about migration."""

import logging
import threading
from pathlib import Path

from baseballpy.core.atomic import atomic_write
from baseballpy.core.config import LAYOUT_VERSION, LakeConfig

logger = logging.getLogger(__name__)

#: Sub-directories of the pre-v2 ``cache/`` tree that held datasets.
V1_SOURCE_DIRS = ("statcast", "retrosheet", "lahman", "chadwick", "mlb_api")

_hinted: set[Path] = set()
_hint_lock = threading.Lock()


def v1_cache_root(config: LakeConfig) -> Path:
    """Where the v1 layout kept its data (``<home>/cache``)."""
    return config.home / "cache"


def has_v1_data(config: LakeConfig) -> bool:
    """True when any v1 per-source directory contains at least one file."""
    root = v1_cache_root(config)
    return any(
        (root / name).is_dir() and any(p.is_file() for p in (root / name).rglob("*"))
        for name in V1_SOURCE_DIRS
    )


def read_version(config: LakeConfig) -> int | None:
    """The integer in ``VERSION`` or ``None`` when the file is missing or unreadable."""
    try:
        return int(config.version_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def detect_layout(config: LakeConfig) -> int | None:
    """Layout version of the lake: stamped version, else 1 for a v1 tree, else ``None`` (empty)."""
    version = read_version(config)
    if version is not None:
        return version
    return 1 if has_v1_data(config) else None


def write_version(config: LakeConfig, version: int = LAYOUT_VERSION) -> None:
    """Atomically stamp the layout version."""
    with atomic_write(config.version_file, mode="w") as part:
        part.write_text(f"{version}\n", encoding="utf-8")


def ensure_version_file(config: LakeConfig) -> None:
    """Stamp a brand-new lake as v2 on first write; never stamp a lake that still has v1 data."""
    if config.version_file.exists() or has_v1_data(config):
        return
    write_version(config)


def hint_if_legacy(config: LakeConfig) -> bool:
    """Log (once per process and lake) a migration hint if a v1 tree is detected."""
    if detect_layout(config) != 1:
        return False
    with _hint_lock:
        if config.home in _hinted:
            return True
        _hinted.add(config.home)
    logger.warning(
        "legacy (v1) data layout detected under %s; nothing was moved. "
        "Run `baseballpy migrate-layout --dry-run` to review, then `baseballpy migrate-layout`.",
        v1_cache_root(config),
    )
    return True


def reset_hints() -> None:
    """Forget which lakes were already hinted (tests)."""
    with _hint_lock:
        _hinted.clear()
