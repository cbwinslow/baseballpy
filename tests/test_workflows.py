"""One-command workflows: ``status``, ``update``, built-in plans, ``current`` seasons, fast scans."""

import json
import math
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.cli_ingest import scan_lake
from baseballpy.core.config import LakeConfig
from baseballpy.core.hostlock import busy_hosts, claim_host, release_all
from baseballpy.core.quarantine import Quarantine, safe_array
from baseballpy.ingest.backfill import BackfillError, builtin_plans, load_plan
from baseballpy.ingest.selection import parse_seasons


def test_current_means_this_calendar_year_alone_in_a_list_and_in_a_range() -> None:
    year = date.today().year
    assert parse_seasons("current") == (year,)
    assert parse_seasons("2024,current") == (2024, year)
    assert parse_seasons("2008-CURRENT")[0] == 2008
    assert parse_seasons("2008-current")[-1] == year


def test_the_built_in_plans_load_and_their_names_are_listed() -> None:
    assert {"daily", "full"} <= set(builtin_plans())
    daily = load_plan("daily")
    assert {s for stage in daily.stages for s in stage.sources} >= {"statcast", "mlb_api", "kalshi"}
    full = load_plan("full")
    assert [stage.name for stage in full.stages][0] == "reference"
    with pytest.raises(BackfillError, match="daily"):
        load_plan("no-such-plan")


def test_a_plan_file_still_wins_over_a_built_in_name(tmp_path: Path) -> None:
    plan = tmp_path / "daily"
    plan.write_text('[[stage]]\nname = "mine"\nsources = ["lahman"]\n', encoding="utf-8")
    assert [s.name for s in load_plan(plan).stages] == ["mine"]


def test_backfill_and_update_dry_runs_use_the_built_in_daily_plan() -> None:
    runner = CliRunner()
    named = runner.invoke(main, ["backfill", "daily", "--dry-run"])
    assert named.exit_code == 0, named.output
    assert "statcast-current" in named.output
    update = runner.invoke(main, ["update", "--dry-run"])
    assert update.exit_code == 0, update.output
    assert "statcast-current" in update.output and "mlb-current" in update.output


def _write_manifest(source: str, dataset: str, chunks: dict[str, tuple[int, int | None]]) -> None:
    tracker = LakeConfig().dataset_manifest(source, dataset)
    for chunk, (rows, season) in chunks.items():
        tracker.set_completed(chunk, records_count=rows, metadata={"season": season})


def test_the_scan_reads_manifests_and_never_opens_a_parquet_file_or_makes_a_folder() -> None:
    _write_manifest("statcast", "pitches", {"season=2023/a": (7, 2023), "season=2024/b": (5, 2024)})
    config = LakeConfig()
    before = {p for p in config.home.rglob("*")}
    statuses = {(s.source, s.dataset): s for s in scan_lake(config)}
    after = {p for p in config.home.rglob("*")}
    pitches = statuses[("statcast", "pitches")]
    assert (pitches.status, pitches.rows, pitches.files) == ("INGESTED", 12, 2)
    assert pitches.seasons == (2023, 2024)
    assert statuses[("lahman", "people")].status == "MISSING"
    assert after == before, "looking at the lake must not create folders"


def test_verify_counts_the_files_and_catches_a_manifest_that_is_wrong() -> None:
    config = LakeConfig()
    _write_manifest("statcast", "pitches", {"season=2023/a": (999, 2023)})
    folder = config.processed_dir("statcast", "pitches", season=2023)
    folder.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"x": [1, 2, 3]}), folder / "part-a.parquet")
    fast = next(s for s in scan_lake(config) if s.dataset == "pitches" and s.source == "statcast")
    slow = next(
        s
        for s in scan_lake(config, verify=True)
        if s.dataset == "pitches" and s.source == "statcast"
    )
    assert (fast.rows, slow.rows) == (999, 3)


def test_status_summarizes_each_source_and_says_nothing_runs() -> None:
    _write_manifest("statcast", "pitches", {"season=2023/a": (7, 2023), "season=2025/b": (5, 2025)})
    _write_manifest("lahman", "people", {"data": (100, None)})
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    sources = {s["source"]: s for s in report["sources"]}
    assert (sources["statcast"]["rows"], sources["statcast"]["first_season"]) == (12, 2023)
    assert sources["statcast"]["last_season"] == 2025
    assert sources["lahman"]["datasets_held"] == 1
    assert report["downloading_from"] == []
    text = runner.invoke(main, ["status"])
    assert text.exit_code == 0 and "statcast" in text.output and "nothing" in text.output


def test_busy_hosts_sees_a_claim_and_looking_does_not_take_the_lock(tmp_path: Path) -> None:
    folder = tmp_path / "locks"
    assert busy_hosts(folder) == []
    claim_host(folder, "example.test")
    try:
        assert busy_hosts(folder) == ["example.test"]
    finally:
        release_all(folder)
    assert busy_hosts(folder) == []
    claim_host(folder, "example.test")  # still claimable after being looked at
    release_all(folder)


class _Spy(Quarantine):
    """A quarantine that remembers what it was asked to write instead of writing it."""

    def __init__(self) -> None:
        super().__init__()
        self.written: list[object] = []

    def write(self, source, dataset, records, reason, context=None):  # type: ignore[no-untyped-def]
        self.written.extend(records)
        return None


def test_a_blank_cell_is_missing_and_nan_text_is_a_float_and_neither_is_quarantined() -> None:
    spy = _Spy()
    ints = safe_array(
        [7, "", "  ", None], pa.int8(), source="s", dataset="d", column="c", quarantine=spy
    )
    assert ints.to_pylist() == [7, None, None, None]
    floats = safe_array(
        [1.5, "NaN", "-Infinity"], pa.float64(), source="s", dataset="d", column="c", quarantine=spy
    )
    values = floats.to_pylist()
    assert values[0] == 1.5 and math.isnan(values[1]) and values[2] == -math.inf
    assert spy.written == []


def test_number_text_from_json_is_kept_in_a_number_column_not_quarantined() -> None:
    """MLB sends ``".286"`` for an average: valid text for a float64 column must not become NULL."""
    spy = _Spy()
    floats = safe_array(
        [".286", "0.328", " 1e3 ", 0.5, "-.--"],
        pa.float64(),
        source="s",
        dataset="d",
        column="c",
        quarantine=spy,
    )
    assert floats.to_pylist() == [0.286, 0.328, 1000.0, 0.5, None]
    assert [row["value"] for row in spy.written] == ["-.--"]  # only the placeholder is quarantined
    ints = safe_array(["5", 6], pa.int32(), source="s", dataset="d", column="c", quarantine=spy)
    assert ints.to_pylist() == [5, 6]


def test_a_value_that_is_really_wrong_is_still_quarantined() -> None:
    spy = _Spy()
    out = safe_array(["abc", 5], pa.int8(), source="s", dataset="d", column="c", quarantine=spy)
    assert out.to_pylist() == [None, 5]
    assert len(spy.written) == 1


def test_coverage_expects_only_the_datasets_a_plain_ingest_fills() -> None:
    from baseballpy.core.datasets import datasets_for
    from baseballpy.coverage import check_dataset_tables
    from baseballpy.sources.catalog import register_all

    register_all()
    seasonal = [s for s in datasets_for("mlb_api") if s.partition == "season"]
    defaults = [s for s in seasonal if s.ingest == "default"]
    assert 0 < len(defaults) < len(seasonal), "the test needs both kinds of dataset"
    item = check_dataset_tables("mlb_api", 2025, LakeConfig())
    assert item.expected_count == len(defaults)
    assert str(len(seasonal) - len(defaults)) in item.note


def _newer_duckdb_error() -> Exception:
    import duckdb

    return duckdb.IOException(
        "IO Error: Trying to read a database file with version number 69, but we can only read "
        "versions between 64 and 68.\nThe database file was created with a newer version of DuckDB."
    )


def test_a_catalog_from_a_newer_duckdb_is_moved_aside_and_rebuilt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import duckdb

    from baseballpy.database import BaseballDatabase

    config = LakeConfig()
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    config.database_path.write_bytes(b"placeholder written by another duckdb")
    real = duckdb.connect
    calls: list[str] = []

    def connect(database: str, read_only: bool = False):  # type: ignore[no-untyped-def]
        calls.append(database)
        if len(calls) == 1:
            raise _newer_duckdb_error()
        return real(database, read_only=read_only)

    monkeypatch.setattr(duckdb, "connect", connect)
    with BaseballDatabase().session() as con:
        assert con.sql("select 1").fetchall() == [(1,)]
    aside = config.database_path.with_name(config.database_path.name + ".newer-duckdb")
    assert aside.read_bytes() == b"placeholder written by another duckdb"


def test_a_read_only_query_of_a_newer_catalog_says_what_to_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import duckdb

    from baseballpy import sql
    from baseballpy.database import DatabaseTooNewError

    config = LakeConfig()
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    config.database_path.write_bytes(b"x")

    def connect(*args: object, **kwargs: object) -> None:
        raise _newer_duckdb_error()

    monkeypatch.setattr(duckdb, "connect", connect)
    with pytest.raises(DatabaseTooNewError, match="db sync"):
        sql("select 1")


def test_arrow_is_another_name_for_pyarrow() -> None:
    from baseballpy.frames import to_dataframe

    table = pa.table({"x": [1, 2]})
    assert to_dataframe(table, "arrow").equals(table)
    with pytest.raises(ValueError, match="arrow"):
        to_dataframe(table, "nope")  # type: ignore[arg-type]


def test_a_missing_optional_dataframe_library_says_what_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import narwhals as nw

    from baseballpy.frames import to_dataframe

    def missing(*args: object, **kwargs: object) -> None:
        raise ModuleNotFoundError("No module named 'pandas'", name="pandas")

    monkeypatch.setattr(nw, "from_arrow", missing)
    with pytest.raises(ImportError, match="pip install pandas"):
        to_dataframe(pa.table({"x": [1]}), "pandas")


def test_an_unknown_dataset_error_explains_that_some_names_belong_to_a_group() -> None:
    result = CliRunner().invoke(
        main,
        ["ingest", "statcast", "-d", "leaderboard_sprint_speed", "--seasons", "2024", "--dry-run"],
    )
    assert result.exit_code == 2
    assert "leaderboards" in result.output and "group" in result.output
