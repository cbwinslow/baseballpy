"""Dataset registry: the single source of truth for every dataset the lake can hold.

Path derivation, DuckDB views, docs and tests iterate :data:`DATASETS`; nothing else
hardcodes a dataset name. Sources register their datasets in ``baseballpy.sources.catalog``.
"""

from dataclasses import dataclass
from typing import Literal

import pyarrow as pa

SOURCES = ("statcast", "mlb_api", "lahman", "chadwick", "retrosheet")

#: how a dataset gets into the lake: ``default`` (the default ``ingest`` selection), ``opt_in``
#: (needs an explicit option because it is large), ``on_demand`` (needs an input such as a query
#: or a since-timestamp) or ``api_only`` (filled only by the Python API; a declarative twin is
#: ingested by default)
IngestMode = Literal["default", "opt_in", "on_demand", "api_only"]


@dataclass(frozen=True)
class DatasetSpec:
    """Static description of one dataset (one ``processed/<source>/<name>/`` directory)."""

    source: str
    name: str
    view: str
    schema: pa.Schema
    partition: Literal["season", "none"]
    keys: tuple[str, ...]
    description: str
    endpoint_doc: str
    ingest: IngestMode = "default"
    #: what to do for ``opt_in``/``on_demand``, or why a ``default`` dataset can be empty
    ingest_note: str = ""
    #: bump when the parser's output changes without a schema change (a value fix): stored chunks of
    #: an older revision are rebuilt (0, the default, leaves the stored digest equal to the schema's)
    revision: int = 0

    @property
    def key(self) -> str:
        """Registry key ``<source>.<name>``."""
        return f"{self.source}.{self.name}"


DATASETS: dict[str, DatasetSpec] = {}


def register(spec: DatasetSpec) -> DatasetSpec:
    """Add ``spec`` to the registry; re-registering an identical spec is a no-op."""
    if spec.source not in SOURCES:
        raise ValueError(f"unknown source {spec.source!r}; expected one of {SOURCES}")
    existing = DATASETS.get(spec.key)
    if existing is not None:
        if existing == spec:
            return existing
        raise ValueError(f"dataset {spec.key} already registered with a different spec")
    clash = next((d for d in DATASETS.values() if d.view == spec.view), None)
    if clash is not None:
        raise ValueError(f"view {spec.view!r} already used by {clash.key}")
    DATASETS[spec.key] = spec
    return spec


def get_dataset(source: str, name: str) -> DatasetSpec:
    """Look up a registered dataset, raising ``KeyError`` with the known names on a miss."""
    try:
        return DATASETS[f"{source}.{name}"]
    except KeyError:
        known = ", ".join(sorted(DATASETS)) or "(none registered)"
        raise KeyError(f"unknown dataset {source}.{name}; known: {known}") from None


def datasets_for(source: str) -> list[DatasetSpec]:
    """All registered datasets of one source, ordered by name."""
    return sorted((d for d in DATASETS.values() if d.source == source), key=lambda d: d.name)
