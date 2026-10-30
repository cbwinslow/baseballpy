"""Spike for the OpenSpec change ``dlt-processed-tier-spike``: current processed writer vs dlt.

Reads the typed Lahman tables from a lake built by the current path, then writes the same Arrow
tables twice into scratch lakes: with ``ProcessedStore`` (current) and with ``dlt`` (filesystem
destination, Parquet, ``replace``). Prints a comparison and probes behaviour. Not part of the
package; evidence for ADR 50.

    uv run python scripts/dlt_processed_spike.py LAHMAN_HOME SCRATCH_DIR
"""

import os
import shutil
import sys
import time
from pathlib import Path

import dlt
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from baseballpy.core.config import LakeConfig
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.lahman.api import lahman_spec


def read_inputs(home: Path) -> dict[str, pa.Table]:
    """The processed Lahman tables of an existing lake, by table name."""
    out: dict[str, pa.Table] = {}
    for part in sorted((home / "processed" / "lahman").glob("*/part-data.parquet")):
        out[part.parent.name] = pq.read_table(part)
    return out


def write_current(tables: dict[str, pa.Table], home: Path) -> float:
    """Current path: one atomic Parquet part and manifest entry per table."""
    store = ProcessedStore(LakeConfig(home=home))
    start = time.perf_counter()
    for name, table in tables.items():
        store.put(lahman_spec(name), table, chunk_id="data")
    return time.perf_counter() - start


def dlt_pipeline(root: Path, name: str, **destination: object) -> dlt.Pipeline:
    """A dlt pipeline writing Parquet files into ``root/lake``."""
    dest = dlt.destinations.filesystem(bucket_url=root.joinpath("lake").as_uri(), **destination)
    return dlt.pipeline(
        name, destination=dest, dataset_name="lahman", pipelines_dir=str(root / "_p")
    )


def resources(tables: dict[str, pa.Table]) -> list[object]:
    """One replace-resource per table (the table is the whole content of the dataset)."""

    def make(name: str, table: pa.Table) -> object:
        @dlt.resource(name=name, write_disposition="replace")
        def one() -> object:
            yield table

        return one()

    return [make(n, t) for n, t in tables.items()]


def write_dlt(tables: dict[str, pa.Table], root: Path) -> float:
    """dlt path: one load of all tables, Parquet files written by dlt."""
    start = time.perf_counter()
    dlt_pipeline(root, "lahman").run(resources(tables), loader_file_format="parquet")
    return time.perf_counter() - start


def dlt_files(root: Path, name: str) -> list[Path]:
    """The Parquet files dlt wrote for one table."""
    return sorted(root.joinpath("lake", "lahman", name).glob("*.parquet"))


def compare(tables: dict[str, pa.Table], cur: Path, dl: Path) -> None:
    """Same column names, types and rows in both lakes?"""
    store = ProcessedStore(LakeConfig(home=cur))
    same_rows = same_names = same_types = 0
    type_diffs: dict[str, str] = {}
    for name in tables:
        a = pq.read_table(store.part_path(lahman_spec(name), "data"))
        b = pa.concat_tables([pq.read_table(f) for f in dlt_files(dl, name)])
        b = b.select([c for c in b.column_names if not c.startswith("_dlt_")])
        same_names += a.column_names == b.column_names
        for field in a.schema:
            if field.name in b.column_names and b.schema.field(field.name).type != field.type:
                type_diffs[f"{name}.{field.name}"] = (
                    f"{field.type} -> {b.schema.field(field.name).type}"
                )
        same_types += a.schema.types == b.schema.types
        keys = [(c, "ascending") for c in a.column_names]
        if b.column_names == a.column_names:
            same_rows += a.sort_by(keys).equals(
                b.select(a.column_names).cast(a.schema, safe=False).sort_by(keys)
            )
    n = len(tables)
    print(
        f"tables {n}: same column names {same_names}, same types {same_types}, same rows {same_rows}"
    )
    print(f"type differences: {len(type_diffs)}; first: {list(type_diffs.items())[:6]}")
    extra = {
        c
        for name in tables
        for f in dlt_files(dl, name)
        for c in pq.read_schema(f).names
        if c.startswith("_dlt_")
    }
    print("dlt added columns:", sorted(extra))


def schema_change(tables: dict[str, pa.Table], dl: Path) -> None:
    """Add a column to one table and reload it through dlt (our path: ADR 49, tested in tests/test_lake.py)."""
    name = "Batting" if "Batting" in tables else next(iter(tables))
    wider = tables[name].append_column(
        "spike_new", pa.array([None] * tables[name].num_rows, pa.string())
    )
    dlt_pipeline(dl, "lahman").run(resources({name: wider}), loader_file_format="parquet")
    names = [pq.read_schema(f).names[-2:] for f in dlt_files(dl, name)]
    print(
        f"dlt after adding a column to {name}: {len(dlt_files(dl, name))} file(s), last columns {names}"
    )


def repeat_run(tables: dict[str, pa.Table], dl: Path) -> None:
    """Load the same data again: does dlt notice that nothing changed?"""
    before = {n: [f.name for f in dlt_files(dl, n)] for n in tables}
    start = time.perf_counter()
    dlt_pipeline(dl, "lahman").run(resources(tables), loader_file_format="parquet")
    took = time.perf_counter() - start
    changed = sum(before[n] != [f.name for f in dlt_files(dl, n)] for n in tables)
    print(
        f"dlt repeat run: {took:.2f}s, {changed}/{len(tables)} tables got new files (no cache check)"
    )


def interrupt(tables: dict[str, pa.Table], root: Path) -> None:
    """A resource that fails midway: what is left in the destination?"""

    @dlt.resource(name="Batting", write_disposition="replace")
    def broken() -> object:
        yield tables["Batting"]
        raise RuntimeError("simulated crash after the first batch")

    dlt_pipeline(root, "lahman").run(
        resources({"Batting": tables["Batting"]}), loader_file_format="parquet"
    )
    good = [f.name for f in dlt_files(root, "Batting")]
    try:
        dlt_pipeline(root, "lahman").run([broken()], loader_file_format="parquet")
    except Exception as exc:  # noqa: BLE001
        print(f"dlt interrupted run raised {type(exc).__name__}")
    after = [f.name for f in dlt_files(root, "Batting")]
    print(
        f"Batting files before the crash {len(good)}, after {len(after)}; the good file survived: {good == after}"
    )


def season_folders(root: Path) -> None:
    """Rebuild one season of a season-partitioned dataset the way the lake needs it."""
    data = pa.table({"year": pa.array([2015, 2015, 2016], pa.int16()), "v": ["a", "b", "c"]})

    def load(season: int, disposition: str) -> None:
        dest = dlt.destinations.filesystem(
            bucket_url=root.joinpath("seasons").as_uri(),
            layout="{table_name}/season={season}/{load_id}.{file_id}.{ext}",
            extra_placeholders={"season": season},
        )
        pipe = dlt.pipeline(
            "seasons", destination=dest, dataset_name="lake", pipelines_dir=str(root / "_ps")
        )
        part = data.filter(pc.equal(data["year"], season))
        pipe.run(
            part, table_name="things", write_disposition=disposition, loader_file_format="parquet"
        )

    def listing() -> list[str]:
        return sorted(
            str(f.relative_to(root / "seasons" / "lake" / "things")).split("\\")[0].split("/")[0]
            for f in root.joinpath("seasons").rglob("*.parquet")
        )

    load(2015, "replace")
    load(2016, "replace")
    print("replace 2015 then 2016 leaves:", listing())
    load(2015, "append")
    load(2015, "append")
    print("append 2015 twice then adds:", listing())


def main() -> None:
    """Run every comparison and print the numbers."""
    home, scratch = Path(sys.argv[1]), Path(sys.argv[2])
    shutil.rmtree(scratch, ignore_errors=True)
    cur, dl = scratch / "current", scratch / "dlt"
    catalog.register_all()
    tables = read_inputs(home)
    rows = sum(t.num_rows for t in tables.values())
    print(f"input: {len(tables)} tables, {rows:,} rows")
    t_cur = write_current(tables, cur)
    renamed_tables = renamed_columns = 0
    default = scratch / "dlt_default_naming"
    write_dlt(tables, default)  # dlt's default naming convention (snake_case)
    for name in tables:
        found = sorted(p.name for p in default.joinpath("lake", "lahman").iterdir())
        renamed_tables += name not in found
    sample = sorted(default.joinpath("lake", "lahman", "allstar_full").glob("*.parquet"))
    if sample:
        renamed_columns = len(
            set(pq.read_schema(sample[0]).names) ^ set(tables["AllstarFull"].column_names)
        )
    print(
        f"default naming: {renamed_tables}/{len(tables)} table names changed; AllstarFull columns differing: {renamed_columns}"
    )
    os.environ["SCHEMA__NAMING"] = "direct"  # keep the provider's names, as our registry needs
    t_dlt = write_dlt(tables, dl)
    print(f"write seconds: current {t_cur:.2f}, dlt {t_dlt:.2f}")
    size = lambda p: sum(f.stat().st_size for f in p.rglob("*") if f.is_file())  # noqa: E731
    print(
        f"bytes: current {size(cur):,} (with manifests), dlt {size(dl / 'lake'):,} (data) + {size(dl / '_p'):,} (pipeline state)"
    )
    print(
        "current layout:",
        sorted(str(f.relative_to(cur)) for f in cur.rglob("*") if f.is_file())[:3],
    )
    print(
        "dlt layout:    ",
        sorted(str(f.relative_to(dl)) for f in dl.joinpath("lake").rglob("*") if f.is_file())[:3],
    )
    compare(tables, cur, dl)
    repeat_run(tables, dl)
    schema_change(tables, dl)
    interrupt(tables, scratch / "dlt_crash")
    season_folders(scratch / "dlt_seasons")


if __name__ == "__main__":
    main()
