"""Raw Kalshi answers: the shared raw log, stored under ``raw/kalshi/``."""

from baseballpy.core.rawlog import RawLog
from baseballpy.core.rawlog import keep_raw as _keep_raw
from baseballpy.core.stores import RawStore


def keep_raw(store: RawStore, dataset: str, name: str, log: RawLog, **extra: str | int) -> None:
    """Write ``log`` as ``raw/kalshi/<dataset>/<name>`` with its sha256 in the manifest."""
    _keep_raw(store, "kalshi", dataset, name, log, **extra)


__all__ = ["RawLog", "keep_raw"]
