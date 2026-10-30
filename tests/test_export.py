"""export_dataset: one registry-driven path to Parquet, CSV, DuckDB and PostgreSQL, verified."""

import datetime as dt
import json
import uuid
from pathlib import Path

import dlt
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy import export as export_module
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec
from baseballpy.core.stores import ProcessedStore
from baseballpy.export import (
    ExportError,
    NoCachedDataError,
    available_seasons,
    export_dataset,
)
from baseballpy.sinks.csv import read_csv_typed
from baseballpy.sinks.dlt import DltSink

SCHEMA = pa.schema(
    [
        pa.field("key", pa.string()),
        pa.field("name", pa.string()),
        pa.field("n", pa.int16()),
        pa.field("score", pa.float64()),
        pa.field("day", pa.date32()),
        pa.field("at", pa.timestamp("us", "UTC")),
        pa.field("flag", pa.bool_()),
        pa.field("kind", pa.dictionary(pa.int8(), pa.string())),
    ]
)


def _spec(name: str, partition: str) -> DatasetSpec:
    return DatasetSpec(
        source="demo",
        name=name,
        view=f"demo_{name}",
        schema=SCHEMA,
        partition=partition,  # type: ignore[arg-type]
        keys=("key",),
        description="test dataset",
        endpoint_doc="",
    )


PEOPLE = _spec("people", "none")
GAMES = _spec("games", "season")


def _table(keys: list[str], n: int = 7) -> pa.Table:
    count = len(keys)
    return pa.table(
        {
            "key": keys,
            "name": ['ünï, "q"' if i == 0 else None for i in range(count)],
            "n": pa.array([n] * count, pa.int16()),
            "score": pa.array([0.1 * i for i in range(count)], pa.float64()),
            "day": pa.array([dt.date(2024, 4, 1)] * count, pa.date32()),
            "at": pa.array(
                [dt.datetime(2024, 4, 1, 12, tzinfo=dt.UTC)] * count, SCHEMA.field("at").type
            ),
            "flag": pa.array([i % 2 == 0 for i in range(count)], pa.bool_()),
            "kind": pa.array(["a", "b", "a"][:count] + ["a"] * max(0, count - 3))
            .dictionary_encode()
            .cast(SCHEMA.field("kind").type),
        },
        schema=SCHEMA,
    )


@pytest.fixture
def lake(tmp_path: Path) -> LakeConfig:
    config = LakeConfig(home=tmp_path / "lake")
    store = ProcessedStore(config)
    store.put(PEOPLE, _table(["p1", "p2", "p3"]))
    store.put(GAMES, _table(["g1", "g2"]), season=2023)
    store.put(GAMES, _table(["g3", "g4", "g5"]), season=2024)
    return config


@pytest.mark.parametrize("target", ["parquet", "csv"])
def test_files_land_in_the_exports_folder_with_the_registry_layout(
    lake: LakeConfig, target: str
) -> None:
    result = export_dataset(PEOPLE, target, config=lake)
    path = lake.exports_root / "demo" / "people" / f"people.{target}"
    assert path.exists() and result.rows == 3 and result.verified
    assert result.destination == str(lake.exports_root / "demo" / "people")
    expected = ProcessedStore(lake).read(PEOPLE)
    back = pq.read_table(path) if target == "parquet" else read_csv_typed(path)
    assert back.schema.equals(SCHEMA) and back.equals(expected)
    if target == "csv":
        assert (path.parent / "people.schema.json").exists()


def test_out_overrides_the_folder_and_seasons_get_season_folders(
    lake: LakeConfig, tmp_path: Path
) -> None:
    out = tmp_path / "elsewhere"
    result = export_dataset(GAMES, "parquet", config=lake, out=out)
    assert result.seasons == (2023, 2024) and result.rows == 5
    assert (out / "demo" / "games" / "season=2023" / "games.parquet").exists()
    assert (out / "demo" / "games" / "season=2024" / "games.parquet").exists()
    assert not lake.exports_root.exists()
    only = export_dataset(GAMES, "csv", config=lake, seasons=[2024])
    assert only.seasons == (2024,) and only.rows == 3
    assert not (lake.exports_root / "demo" / "games" / "season=2023").exists()


def test_export_holds_one_season_at_a_time(
    lake: LakeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    real_read = ProcessedStore.read
    real_write = export_module.atomic_write_parquet

    def read(self: ProcessedStore, spec: DatasetSpec, season: int | None = None, columns=None):  # type: ignore[no-untyped-def]
        events.append(f"read {season}" if columns is None else f"keys {season}")
        return real_read(self, spec, season, columns)

    def write(table: pa.Table, path: Path, **kwargs: object) -> None:
        events.append("write")
        real_write(table, path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ProcessedStore, "read", read)
    monkeypatch.setattr(export_module, "atomic_write_parquet", write)
    export_dataset(GAMES, "parquet", config=lake)
    # each season is read and written before the next one is read
    assert events == ["read 2023", "write", "read 2024", "write"]


def test_the_exports_folder_can_be_moved_by_environment(
    lake: LakeConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_EXPORTS_ROOT_OVERRIDE", str(tmp_path / "moved"))
    config = LakeConfig(home=lake.home)
    export_dataset(PEOPLE, "parquet", config=config)
    assert (tmp_path / "moved" / "demo" / "people" / "people.parquet").exists()


def test_seasons_listing_reads_the_processed_folders(lake: LakeConfig) -> None:
    assert available_seasons(lake, GAMES) == [2023, 2024]
    assert available_seasons(lake, PEOPLE) == []


def _duckdb_rows(path: Path, table: str) -> list[tuple[object, ...]]:
    con = duckdb.connect(str(path), read_only=True)
    try:
        return con.execute(f'SELECT key, n FROM "{table}" ORDER BY key').fetchall()  # noqa: S608
    finally:
        con.close()


def test_duckdb_modes_with_seasons(lake: LakeConfig, tmp_path: Path) -> None:
    out = tmp_path / "x.duckdb"
    first = export_dataset(GAMES, "duckdb", config=lake, out=out)
    assert first.rows == 5 and first.destination.endswith(":demo_games") and first.verified
    export_dataset(GAMES, "duckdb", config=lake, out=out)  # replace again: still 5, not 10
    assert [k for k, _ in _duckdb_rows(out, "demo_games")] == ["g1", "g2", "g3", "g4", "g5"]
    export_dataset(GAMES, "duckdb", config=lake, out=out, mode="append")
    assert len(_duckdb_rows(out, "demo_games")) == 10
    ProcessedStore(lake).put(GAMES, _table(["g3", "g9"], n=99), season=2024)
    export_dataset(GAMES, "duckdb", config=lake, out=out, mode="replace")
    export_dataset(GAMES, "duckdb", config=lake, out=out, mode="merge")  # same keys: no growth
    rows = dict(_duckdb_rows(out, "demo_games"))
    assert sorted(rows) == ["g1", "g2", "g3", "g9"] and rows["g3"] == 99


def test_default_duckdb_file_is_in_the_exports_folder(lake: LakeConfig) -> None:
    export_dataset(PEOPLE, "duckdb", config=lake)
    assert _duckdb_rows(lake.exports_root / "baseballpy.duckdb", "demo_people")[0][0] == "p1"


def test_postgres_replace_append_merge_with_registry_names(
    lake: LakeConfig, postgres_url: str
) -> None:
    schema = f"t_{uuid.uuid4().hex[:8]}"
    sink = DltSink(
        destination="postgres",
        dataset_name=schema,
        credentials=postgres_url,
        pipelines_dir=str(lake.home / "cache" / "dlt"),
        pipeline_name="baseballpy_export_direct",
    )
    result = export_dataset(GAMES, "postgres", config=lake, url=postgres_url, schema=schema)
    assert result.rows == 5 and result.destination == f"postgres:{schema}.demo_games"
    assert sink.table_info("demo_games").rows == 5
    export_dataset(GAMES, "postgres", config=lake, url=postgres_url, schema=schema)  # replace
    assert sink.table_info("demo_games").rows == 5
    export_dataset(GAMES, "postgres", config=lake, url=postgres_url, schema=schema, mode="merge")
    assert sink.table_info("demo_games").rows == 5  # merge on the registry key: no duplicates
    export_dataset(GAMES, "postgres", config=lake, url=postgres_url, schema=schema, mode="append")
    assert sink.table_info("demo_games").rows == 10


def test_postgres_export_still_works_after_an_export_by_the_first_version(
    lake: LakeConfig, postgres_url: str
) -> None:
    schema = f"t_{uuid.uuid4().hex[:8]}"
    first_version = dlt.pipeline(  # the first version used dlt's default snake_case naming
        pipeline_name="baseballpy_export",
        destination=dlt.destinations.postgres(credentials=postgres_url),
        dataset_name=schema,
        pipelines_dir=str(lake.home / "cache" / "dlt"),
    )
    first_version.run(
        dlt.resource([pa.table({"gameID": ["g0"]})], name="demo_games", write_disposition="replace")
    )
    result = export_dataset(GAMES, "postgres", config=lake, url=postgres_url, schema=schema)
    assert result.rows == 5 and result.verified


def test_postgres_url_comes_from_the_environment_or_an_error_says_how(
    lake: LakeConfig, postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BASEBALLPY_POSTGRES_URL", raising=False)
    with pytest.raises(ExportError, match="BASEBALLPY_POSTGRES_URL"):
        export_dataset(PEOPLE, "postgres", config=lake)
    monkeypatch.setenv("BASEBALLPY_POSTGRES_URL", postgres_url)
    schema = f"t_{uuid.uuid4().hex[:8]}"
    assert export_dataset(PEOPLE, "postgres", config=lake, schema=schema).rows == 3


def test_missing_data_modes_targets_and_seasons_are_refused_clearly(lake: LakeConfig) -> None:
    other = _spec("nothing", "none")
    with pytest.raises(NoCachedDataError, match="ingest demo -d nothing"):
        export_dataset(other, "parquet", config=lake)
    with pytest.raises(NoCachedDataError, match=r"season\(s\) \[1999\]"):
        export_dataset(GAMES, "parquet", config=lake, seasons=[1999])
    with pytest.raises(ValueError, match="always replaced"):
        export_dataset(PEOPLE, "csv", config=lake, mode="merge")
    with pytest.raises(ValueError, match="unknown export target"):
        export_dataset(PEOPLE, "xlsx", config=lake)
    with pytest.raises(ValueError, match="unknown export mode"):
        export_dataset(PEOPLE, "duckdb", config=lake, mode="upsert")


def test_a_difference_found_on_read_back_fails_the_export(
    lake: LakeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = export_module.read_csv_typed

    def damaged(path: Path | str) -> pa.Table:
        return real(path).slice(1)  # one row lost

    monkeypatch.setattr(export_module, "read_csv_typed", damaged)
    with pytest.raises(ExportError, match="data read back differs"):
        export_dataset(PEOPLE, "csv", config=lake)
    assert export_dataset(PEOPLE, "csv", config=lake, verify=False).verified is False


def test_an_empty_cached_dataset_exports_an_empty_typed_file(lake: LakeConfig) -> None:
    empty = _spec("empty", "none")
    ProcessedStore(lake).put_stream(empty, [])  # recorded with zero rows
    result = export_dataset(empty, "csv", config=lake)
    assert result.rows == 0 and result.verified
    assert read_csv_typed(lake.exports_root / "demo" / "empty" / "empty.csv").schema.equals(SCHEMA)


def test_every_export_is_written_to_the_audit_log(lake: LakeConfig) -> None:
    from baseballpy.core.audit import default_audit_logger

    export_dataset(PEOPLE, "parquet", config=lake)
    events = [
        json.loads(line)
        for line in default_audit_logger.log_path.read_text(encoding="utf-8").splitlines()
    ]
    exported = [e for e in events if e["operation"] == "export"]
    assert exported and exported[-1]["records_count"] == 3
    assert exported[-1]["source"] == "demo" and exported[-1]["status"] == "SUCCESS"


# -- the command ----------------------------------------------------------------------------------


def _chadwick_lake() -> LakeConfig:
    """Cache two of the four Chadwick datasets (names and countries) from the test fixtures."""
    from baseballpy.core.datasets import get_dataset
    from baseballpy.sources import catalog
    from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer

    catalog.register_all()
    fixtures = Path(__file__).parent / "fixtures" / "chadwick"
    config = LakeConfig()
    store = ProcessedStore(config)
    normalizer = ChadwickNormalizer()
    store.put(
        get_dataset("chadwick", "register_countries"),
        normalizer.normalize_countries((fixtures / "countries_sample.csv").read_bytes()),
    )
    store.put(
        get_dataset("chadwick", "register_names"),
        normalizer.normalize_names((fixtures / "names_sample.csv").read_bytes()),
    )
    return config


def test_command_exports_named_datasets_and_skips_uncached_ones_of_a_source() -> None:
    from click.testing import CliRunner

    from baseballpy.cli import main

    config = _chadwick_lake()
    runner = CliRunner()
    one = runner.invoke(main, ["export", "chadwick:register_countries", "--to", "csv", "--json"])
    assert one.exit_code == 0 and json.loads(one.output)["dataset"] == "register_countries"
    assert (
        config.exports_root / "chadwick" / "register_countries" / "register_countries.csv"
    ).exists()
    whole = runner.invoke(main, ["export", "chadwick", "--to", "parquet", "--json"])
    assert whole.exit_code == 0
    done = {
        json.loads(line)["dataset"] for line in whole.output.splitlines() if line.startswith("{")
    }
    assert done == {"register_countries", "register_names"}  # links and register are not cached


def test_command_fails_for_an_explicit_dataset_with_nothing_cached_and_for_bad_input() -> None:
    from click.testing import CliRunner

    from baseballpy.cli import main

    _chadwick_lake()
    runner = CliRunner()
    missing = runner.invoke(main, ["export", "chadwick:register", "--to", "csv"])
    assert missing.exit_code == 1 and "ingest chadwick -d register" in missing.output.replace(
        "\n", ""
    )
    assert runner.invoke(main, ["export", "nosuch", "--to", "csv"]).exit_code == 2
    assert runner.invoke(main, ["export", "chadwick:nosuch", "--to", "csv"]).exit_code == 2
    assert (
        runner.invoke(main, ["export", "chadwick", "--to", "csv", "--seasons", "x"]).exit_code == 2
    )
    nothing = runner.invoke(main, ["export", "lahman", "--to", "csv"])
    assert nothing.exit_code == 1 and "Nothing was exported" in nothing.output


def test_command_reaches_postgres_through_the_environment(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from baseballpy.cli import main

    _chadwick_lake()
    monkeypatch.setenv("BASEBALLPY_POSTGRES_URL", postgres_url)
    schema = f"t_{uuid.uuid4().hex[:8]}"
    result = CliRunner().invoke(
        main,
        ["export", "chadwick:register_countries", "--to", "postgres", "--schema", schema, "--json"],
    )
    assert result.exit_code == 0
    assert (
        json.loads(result.output)["destination"] == f"postgres:{schema}.chadwick_register_countries"
    )


def test_merge_is_refused_when_a_key_column_has_empty_values(
    lake: LakeConfig, tmp_path: Path
) -> None:
    keyed = _spec("keyed", "none")
    table = _table(["k1", "k2"])
    table = table.set_column(0, "key", pa.array(["k1", None], pa.string()))
    ProcessedStore(lake).put(keyed, table)
    with pytest.raises(ExportError, match="cannot be merged.*'key'.*replace"):
        export_dataset(keyed, "duckdb", config=lake, out=tmp_path / "k.duckdb", mode="merge")
    assert not (tmp_path / "k.duckdb").exists()  # refused before anything was written
    assert export_dataset(keyed, "duckdb", config=lake, out=tmp_path / "k.duckdb").rows == 2


def test_a_list_column_exports_to_duckdb_and_verifies(tmp_path: Path) -> None:
    # retrosheet.box_records.fields is list<string>: DuckDB stores it as varchar[]
    spec = DatasetSpec(
        source="demo",
        name="lists",
        view="demo_lists",
        schema=pa.schema([("key", pa.string()), ("fields", pa.list_(pa.string()))]),
        partition="none",
        keys=("key",),
        description="list column",
        endpoint_doc="",
    )
    config = LakeConfig(home=tmp_path / "lake")
    ProcessedStore(config).put(
        spec, pa.table({"key": ["a", "b"], "fields": [["x", "y"], []]}, schema=spec.schema)
    )
    result = export_dataset(spec, "duckdb", config=config, out=tmp_path / "l.duckdb")
    assert result.rows == 2 and not result.problems
