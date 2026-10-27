"""Lahman coverage: 27 strict generated schemas, drift, quality checks, permitted sources only."""

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx

from baseballpy.core import schema_tools, sources_lock
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import HttpClient
from baseballpy.sources.lahman import quality
from baseballpy.sources.lahman.api import LahmanSource
from baseballpy.sources.lahman.extractor import (
    LOCAL_IMPORT,
    LahmanExtractor,
    LahmanSourceError,
)
from baseballpy.sources.lahman.normalizer import LahmanNormalizer
from baseballpy.sources.lahman.schema import (
    LAHMAN_PRIMARY_KEYS,
    LAHMAN_SCHEMAS,
    LahmanTable,
)

FIXTURES = Path(__file__).parent / "fixtures" / "lahman"
TABLES = sorted(t.value for t in LahmanTable)


def _rates() -> RateLimitConfig:
    return RateLimitConfig(
        default_requests_per_second=1000,
        host_rates={"raw.githubusercontent.com": 1000},
        max_retries=0,
    )


def test_every_one_of_the_27_tables_has_a_strict_schema_and_key() -> None:
    assert len(TABLES) == 27
    assert set(LAHMAN_SCHEMAS) == set(TABLES) == set(LAHMAN_PRIMARY_KEYS)
    for name, schema in LAHMAN_SCHEMAS.items():
        assert schema.names[-1] == "_extras" and schema.field("_extras").type == pa.string()
        assert set(LAHMAN_PRIMARY_KEYS[name]) <= set(schema.names), name
        assert len(schema.names) >= 4, name


@pytest.mark.parametrize("table", TABLES)
def test_fixture_normalizes_to_the_exact_schema_without_loss(
    table: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    schema_tools.reset_drift_warnings()
    from baseballpy.core.config import QuarantineConfig
    from baseballpy.core.quarantine import Quarantine

    q = Quarantine(QuarantineConfig(base_dir=tmp_path))
    raw = (FIXTURES / f"{table}.csv").read_bytes()
    with caplog.at_level("WARNING"):
        out = LahmanNormalizer(quarantine=q).normalize(raw, table_name=table)
    assert out.schema.equals(LAHMAN_SCHEMAS[table])
    assert out.num_rows == 5
    assert out["_extras"].null_count == 5
    assert not any("schema_drift" in r.getMessage() for r in caplog.records)
    assert not list((tmp_path / "quarantine").rglob("*.jsonl"))
    # keys are populated in the fixture rows
    for column in LAHMAN_PRIMARY_KEYS[table][:1]:
        assert out[column].null_count < 5


def test_people_fixture_handles_bom_and_surrogate_id() -> None:
    raw = (FIXTURES / "People.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    table = LahmanNormalizer().normalize(raw, table_name="People")
    assert table.schema.field("ID").type == pa.int32()
    assert table["ID"].to_pylist()[:2] == [1, 2]
    assert table.schema.field("debut").type == pa.date32()


def test_extra_and_missing_columns_never_drop_data() -> None:
    schema_tools.reset_drift_warnings()
    raw = "yearID,teamID,lgID,franchID,brandNew\n2024,BOS,AL,BOS,x\n"
    table = LahmanNormalizer().normalize(raw, table_name="Teams")
    row = {k: v[0] for k, v in table.to_pydict().items()}
    assert row["yearID"] == 2024 and row["Rank"] is None  # missing column -> NULL
    assert json.loads(str(row["_extras"])) == {"brandNew": "x"}


def test_reordered_headers_are_mapped_by_name() -> None:
    raw = "G,playerID,stint,yearID\n10,a01,1,2020\n"
    table = LahmanNormalizer().normalize(raw, table_name="Batting")
    assert table["playerID"].to_pylist() == ["a01"] and table["G"].to_pylist() == [10]


def test_unknown_table_keeps_every_column_as_strings() -> None:
    table = LahmanNormalizer().normalize("a,b\n1,x\n", table_name="NewTable")
    assert table.column_names == ["a", "b"] and table["a"].to_pylist() == ["1"]


def test_quality_checks_report_duplicates_orphans_and_stale_data() -> None:
    batting = pa.table(
        {
            "playerID": ["a", "a", "ghost"],
            "yearID": [2000, 2000, 2000],
            "stint": [1, 1, 1],
        }
    )
    report = quality.quality_report(
        "Batting", batting, people_ids=pa.array(["a", "b"]), today=date(2026, 6, 1)
    )
    assert report["duplicate_key_rows"] == 1
    assert report["orphan_player_rows"] == 1
    assert "stale" in report and "2000" in str(report["stale"])
    current = pa.table({"playerID": ["a"], "yearID": [2025], "stint": [1]})
    assert quality.quality_report("Batting", current, people_ids=None, today=date(2026, 6, 1)) == {}


def test_last_completed_season_rolls_over_in_november() -> None:
    assert quality.last_completed_season(date(2026, 10, 27)) == 2025
    assert quality.last_completed_season(date(2026, 11, 1)) == 2026


def _zip_of(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_import_archive_imports_all_27_as_local_import_and_never_hits_the_network(
    tmp_path: Path,
) -> None:
    cfg = LakeConfig(home=tmp_path / "lake")
    archive = tmp_path / "lahman.zip"
    archive.write_bytes(
        _zip_of({f"nested/{t}.csv": (FIXTURES / f"{t}.csv").read_bytes() for t in TABLES})
    )
    source = LahmanSource(cfg)
    assert source.import_archive(archive) == 27
    entry = source.extractor.manifest_for("Batting").get_chunk("Batting")
    assert entry is not None and entry["origin"] == LOCAL_IMPORT
    # served from the imported data: pytest-socket would fail any network attempt
    assert len(source.get_table("Batting")) == 5
    assert source.extractor.extract_table("Batting").startswith(b"playerID")
    raw = cfg.raw_dir("lahman", "People") / "People.csv"
    assert raw.read_bytes().startswith(b"\xef\xbb\xbf")  # raw bytes stored untouched
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize("member", ["../evil.csv", "a/../../evil.csv"])
def test_import_archive_rejects_path_traversal(tmp_path: Path, member: str) -> None:
    archive = tmp_path / "bad.zip"
    archive.write_bytes(_zip_of({member: b"a,b\n1,2\n"}))
    with pytest.raises(ValueError, match="unsafe path"):
        LahmanSource(LakeConfig(home=tmp_path / "lake")).import_archive(archive)
    assert not (tmp_path / "evil.csv").exists()


def test_import_archive_rejects_oversized_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baseballpy.sources.lahman import api

    monkeypatch.setattr(api, "MAX_MEMBER_BYTES", 10)
    archive = tmp_path / "big.zip"
    archive.write_bytes(_zip_of({"Batting.csv": b"playerID\n" + b"a\n" * 50}))
    with pytest.raises(ValueError, match="too large"):
        LahmanSource(LakeConfig(home=tmp_path / "lake")).import_archive(archive)


def test_import_archive_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LahmanSource(LakeConfig(home=tmp_path)).import_archive(tmp_path / "nope.zip")


def test_import_flags_stale_data_in_the_manifest(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = LakeConfig(home=tmp_path / "lake", today=date(2026, 6, 1))
    source = LahmanSource(cfg)
    stale = b"playerID,yearID,stint\na01,2010,1\n"
    with caplog.at_level("WARNING"):
        source._import_csv("Batting.csv", stale)
    assert any("looks stale" in r.getMessage() for r in caplog.records)
    from baseballpy.core.datasets import get_dataset

    entry = cfg.dataset_manifest("lahman", "Batting").get_chunk("data")
    assert entry is not None and "stale" in entry["quality"]
    assert get_dataset("lahman", "Batting")


@respx.mock
def test_remote_failure_names_import_archive_and_contacts_no_other_repo(tmp_path: Path) -> None:
    ref = sources_lock.get_source_ref("lahman")
    route = respx.get(f"{ref.raw_base()}/data/Parks.csv").mock(return_value=httpx.Response(404))
    http = HttpClient(_rates(), http2=False)
    ext = LahmanExtractor(
        cache_config=LakeConfig(home=tmp_path), rate_limit_config=_rates(), http=http
    )
    try:
        with pytest.raises(LahmanSourceError, match="import_archive"):
            ext.extract_table("Parks")
    finally:
        http.close()
    assert route.call_count == 1
    assert [str(c.request.url.host) for c in respx.calls] == ["raw.githubusercontent.com"]
    assert all("cbwinslow/lahman-database-csv" in str(c.request.url) for c in respx.calls)


def test_repo_override_is_honoured_and_baseballdatabank_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASEBALLPY_LAHMAN_REPO", "someone/lahman-fork")
    assert sources_lock.get_source_ref("lahman").repo == "someone/lahman-fork"
    monkeypatch.setenv("BASEBALLPY_LAHMAN_REPO", "chadwickbureau/baseballdatabank")
    with pytest.raises(ValueError, match="import_archive"):
        sources_lock.get_source_ref("lahman")


def test_lahman_registry_has_all_27_datasets() -> None:
    from baseballpy.core.datasets import datasets_for
    from baseballpy.sources import catalog

    catalog.register_all()
    assert {d.name for d in datasets_for("lahman")} == set(TABLES)
