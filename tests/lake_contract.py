"""The lake contract: what a fresh download MUST leave on disk, for every source (AGENTS.md section 15).

One helper, driven by the dataset registry (no dataset names here), used by the per-source download
tests. After a download into an empty home the lake must have exactly this shape, so every user who runs
the same workflow finds the same folders, names, types and views:

1. ``processed/<source>/<dataset>/[season=YYYY/]`` holds only ``part-*``, ``compact-NNNN`` or ``seg-NNNN``
   Parquet files, in a season folder exactly when the dataset is partitioned by season;
2. every Parquet file has the registered column names and types, in the registered order;
3. no folder belongs to an unregistered dataset, no file is a half-written ``.part``;
4. the raw files recorded in the manifests exist and match their sha256;
5. no value of the provider's text is lost or changed (``baseballpy.core.roundtrip``);
6. ``baseballpy db sync`` makes one view per dataset that has data, named by the registry, and counting
   exactly the rows in the files.
"""

import re
from collections.abc import Sequence
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.cache_check import OK, check_raw, check_segments
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, LINEAGE_COLUMN
from baseballpy.core.roundtrip import roundtrip_dataset
from baseballpy.core.sql import quote_ident
from baseballpy.database import BaseballDatabase
from baseballpy.layout_audit import audit_layout
from baseballpy.sources import catalog
from baseballpy.sources.adapters import register_all_adapters

FILE_NAME = re.compile(r"^(part-.+|compact-\d{4}|seg-\d{4})\.parquet$")
SEASON_DIR = re.compile(r"^season=\d{4}$")


def processed_files(config: LakeConfig, source: str) -> list[Path]:
    """Every Parquet file under ``processed/<source>``."""
    return sorted((config.processed_root / source).rglob("*.parquet"))


def assert_lake_contract(config: LakeConfig, sources: Sequence[str]) -> dict[str, int]:
    """Assert the contract for ``sources``; returns ``view -> row count`` for the datasets found."""
    catalog.register_all()
    specs = {(s.source, s.name): s for s in DATASETS.values()}

    for finding in audit_layout(config, tuple(sources)):
        assert not finding.fails, (
            f"layout: {finding.kind} {finding.source}/{finding.item}: {finding.evidence}"
        )

    rows_by_dataset: dict[tuple[str, str], int] = {}
    for source in sources:
        for path in processed_files(config, source):
            rel = path.relative_to(config.processed_root / source)
            dataset = rel.parts[0]
            spec = specs[(source, dataset)]  # an unregistered folder is a KeyError, i.e. a failure
            by_season = spec.partition == "season"
            expected_depth = 3 if by_season else 2
            assert len(rel.parts) == expected_depth, f"{path}: wrong depth for {spec.key}"
            if by_season:
                assert SEASON_DIR.match(rel.parts[1]), f"{path}: not in a season=YYYY folder"
            assert FILE_NAME.match(path.name), f"{path}: unexpected file name"
            schema = pq.read_schema(path)
            expected = list(spec.schema)
            if path.name.startswith(
                "seg-"
            ):  # a segment names the response each row came from (ADR 95)
                expected.append(pa.field(LINEAGE_COLUMN, pa.string()))
            assert [f.name for f in schema] == [f.name for f in expected], f"{path}: columns"
            assert [f.type for f in schema] == [f.type for f in expected], f"{path}: types"
            rows = pq.read_metadata(path).num_rows
            rows_by_dataset[(source, dataset)] = rows_by_dataset.get((source, dataset), 0) + rows
        leftovers = [
            p
            for p in (config.processed_root / source).rglob("*")
            if p.is_file() and (p.suffix == ".part" or "_open" in p.parts)
        ]
        assert not leftovers, f"half-written files: {leftovers}"

    for check in [
        *check_raw(config, sources=tuple(sources)),
        *check_segments(config, sources=tuple(sources)),
    ]:
        assert check.integrity == OK, (
            f"raw {check.source}/{check.dataset}/{check.name}: {check.integrity}"
        )

    # 4b. no value of the provider's text was lost or changed on its way into the typed tables
    register_all_adapters()
    for (source, dataset), spec in sorted(specs.items()):
        if source in sources and (source, dataset) in rows_by_dataset:
            verdict = roundtrip_dataset(config, spec)
            assert verdict.status != "loss", f"round trip {spec.key}: " + "; ".join(
                f"{x.kind} {x.column} x{x.count} ({x.example})" for x in verdict.losses[:4]
            )

    BaseballDatabase(cache_config=config).sync_views()
    counted: dict[str, int] = {}
    con = duckdb.connect(str(config.database_path), read_only=True)
    try:
        for (source, dataset), rows in rows_by_dataset.items():
            view = specs[(source, dataset)].view
            query = f"SELECT count(*) FROM {quote_ident(view)}"  # noqa: S608 - quoted by core/sql.py
            (count,) = con.execute(query).fetchone() or (None,)
            assert count == rows, f"view {view} counts {count}, the files hold {rows}"
            counted[view] = rows
    finally:
        con.close()
    return counted
