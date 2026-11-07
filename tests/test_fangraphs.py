"""FanGraphs files you supply: typed from the inbox, never downloaded, nothing lost."""

import decimal
import gzip
import hashlib
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.ingest.types import JobStatus, Selection
from baseballpy.sources import catalog
from baseballpy.sources.fangraphs.adapter import FangraphsAdapter
from baseballpy.sources.fangraphs.files import BY_DATASET, DATASET_KEYS, FILES
from baseballpy.sources.fangraphs.ingest import IngestOutcome, ingest
from baseballpy.sources.fangraphs.schema import FANGRAPHS_SCHEMAS
from baseballpy.sources.fangraphs.tables import FANGRAPHS_COLUMNS

SCRIPTS = Path(__file__).parent.parent / "scripts"


def guts_csv(rows: list[dict[str, str]], extra_header: str = "") -> bytes:
    """A ``guts`` file with the real header; cells not given are empty."""
    header = [name for name, _ in FANGRAPHS_COLUMNS["guts"]]
    lines = [",".join(header) + extra_header]
    for row in rows:
        lines.append(",".join(row.get(name, "") for name in header) + ("," if extra_header else ""))
    return ("\n".join(lines) + "\n").encode("utf-8")


GUTS = [
    {"season": "2024", "woba": ".310", "wobascale": "1.242", "cfip": "3.166",
     "_loaded_at": "2026-10-06 12:00:00.123+00"},
    {"season": "1871", "woba": ".316", "wobascale": ".996", "cfip": "3.1",
     "_loaded_at": "2026-10-06 12:00:00.123+00"},
]  # fmt: skip


def lake(tmp_path: Path, *, gz: bool = False, body: bytes | None = None) -> LakeConfig:
    """A lake whose inbox holds a guts file."""
    config = LakeConfig(home=tmp_path)
    inbox = config.inbox_dir("fangraphs")
    inbox.mkdir(parents=True)
    data = body if body is not None else guts_csv(GUTS)
    if gz:
        (inbox / "guts.csv.gz").write_bytes(gzip.compress(data))
    else:
        (inbox / "guts.csv").write_bytes(data)
    return config


def test_ten_files_are_registered_as_on_demand_datasets_with_keys_in_the_schema() -> None:
    registry = catalog.register_all()
    names = {spec.name for key, spec in registry.items() if key.startswith("fangraphs.")}
    assert names == {f.dataset for f in FILES} and len(names) == 10
    for name in names:
        spec = registry[f"fangraphs.{name}"]
        assert spec.ingest == "on_demand" and spec.partition == "none"
        assert set(spec.keys) == set(DATASET_KEYS[name]) <= set(spec.schema.names)
        assert spec.schema.names[-1] == "_extras"
        assert "private" in spec.description


def test_values_are_typed_exactly_and_nothing_is_set_aside(tmp_path: Path) -> None:
    config = lake(tmp_path)
    outcome = ingest(["guts"], config=config)
    assert outcome.rows == {"guts": 2}
    rows = {
        r["season"]: r
        for r in ProcessedStore(config).read(get_dataset("fangraphs", "guts")).to_pylist()
    }
    assert rows[2024]["woba"] == decimal.Decimal("0.310") and rows[1871][
        "wobascale"
    ] == decimal.Decimal("0.996")
    assert rows[2024]["_loaded_at"].year == 2026
    assert all(r["_extras"] is None for r in rows.values())
    assert not (tmp_path / "quarantine").exists()


def test_the_file_may_be_gzipped_and_the_raw_bytes_are_kept_with_their_checksum(
    tmp_path: Path,
) -> None:
    body = guts_csv(GUTS)
    config = lake(tmp_path, gz=True, body=body)
    ingest(["guts"], config=config)
    store = RawStore(config)
    assert (
        store.verify("fangraphs", "guts", "guts.csv")
        and store.get("fangraphs", "guts", "guts.csv") == body
    )
    entry = config.dataset_manifest("fangraphs", "guts", "raw").get_chunk("guts.csv")
    assert entry is not None and entry["sha256"] == hashlib.sha256(body).hexdigest()


def test_an_unchanged_file_is_left_alone_and_refresh_types_it_again(tmp_path: Path) -> None:
    config = lake(tmp_path)
    assert ingest(["guts"], config=config).unchanged == []
    again = ingest(["guts"], config=config)
    assert again.unchanged == ["guts"] and again.rows == {"guts": 2}
    assert ingest(["guts"], refresh=True, config=config).unchanged == []
    (config.inbox_dir("fangraphs") / "guts.csv").write_bytes(guts_csv(GUTS[:1]))
    changed = ingest(["guts"], config=config)
    assert changed.unchanged == [] and changed.rows == {"guts": 1}


def test_a_new_column_lands_in_extras_and_nothing_is_dropped(tmp_path: Path) -> None:
    header = [name for name, _ in FANGRAPHS_COLUMNS["guts"]]
    body = (
        ",".join(header) + ",brand_new\n" + ",".join(["2024"] + [""] * (len(header) - 1)) + ",7\n"
    ).encode()
    config = lake(tmp_path, body=body)
    ingest(["guts"], config=config)
    row = ProcessedStore(config).read(get_dataset("fangraphs", "guts")).to_pylist()[0]
    assert row["_extras"] == '{"brand_new": "7"}'


def test_whole_numbers_written_as_floats_load_as_integers(tmp_path: Path) -> None:
    kinds = dict(FANGRAPHS_COLUMNS["batting"])
    assert kinds["ab"] == "int32" and kinds["xmlbamid"] == "int32"
    header = [name for name, _ in FANGRAPHS_COLUMNS["batting"]]
    cells = dict.fromkeys(header, "")
    cells.update(
        {
            "playerid": "15640",
            "season": "2024.0",
            "ab": "157.0",
            "xmlbamid": "592450.0",
            "pa": "700",
        }
    )
    body = (",".join(header) + "\n" + ",".join(cells[h] for h in header) + "\n").encode()
    config = LakeConfig(home=tmp_path)
    inbox = config.inbox_dir("fangraphs")
    inbox.mkdir(parents=True)
    (inbox / "batting.csv").write_bytes(body)
    ingest(["batting"], config=config)
    row = ProcessedStore(config).read(get_dataset("fangraphs", "batting")).to_pylist()[0]
    assert (row["season"], row["ab"], row["xmlbamid"], row["pa"]) == (2024, 157, 592450, 700)
    assert not (tmp_path / "quarantine").exists()


def test_a_missing_file_is_named_or_listed_and_nothing_is_ever_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_network(*_: Any, **__: Any) -> None:
        raise AssertionError("the FanGraphs source must not make a request")

    monkeypatch.setattr("baseballpy.core.http.get_http_client", no_network)
    config = lake(tmp_path)
    with pytest.raises(FileNotFoundError, match=r"batting\.csv"):
        ingest(["batting"], config=config)
    outcome = ingest(config=config)
    assert outcome.rows.keys() == {"guts"} and "batting" in outcome.missing
    with pytest.raises(ValueError, match="unknown dataset"):
        ingest(["nope"], config=config)


def test_adapter_plans_one_job_and_reports_missing_files() -> None:
    adapter = FangraphsAdapter(
        loader=lambda datasets, refresh: IngestOutcome(
            rows={"guts": 2}, unchanged=["guts"], missing=["batting"]
        )
    )
    assert len(adapter.plan(Selection())) == 1
    subset = adapter.plan(Selection(datasets=("guts", "batting")))
    assert subset[0].param("datasets") == "batting,guts"
    result = adapter.run(subset[0])
    assert result.status is JobStatus.COMPLETED and result.rows == 2 and result.cache_hit
    assert "no file for batting" in result.detail
    with pytest.raises(ValueError, match="unknown dataset"):
        adapter.plan(Selection(datasets=("nope",)))
    assert adapter.all_seasons()[0] == 1871, "download mode can ask for every season"


def test_the_export_script_refuses_odd_names_and_builds_one_read_only_copy_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spec = importlib.util.spec_from_file_location(
        "export_homelab_fangraphs", SCRIPTS / "export_homelab_fangraphs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls: list[list[str]] = []

    class Done:
        returncode = 0

    monkeypatch.setattr(module.subprocess, "run", lambda args, **_: (calls.append(args), Done())[1])
    target = tmp_path / "out.csv.gz"
    module.export("host", "mlb", "raw", BY_DATASET["guts"].homelab_table, str(target))
    assert calls[0][:4] == ["ssh", "-o", "BatchMode=yes", "host"]
    assert "copy (select * from raw.fangraphs_guts) to stdout with csv header" in calls[0][4]
    for bad in ("raw; drop table x", "a b", ""):
        with pytest.raises(ValueError, match="plain database name"):
            module.export("host", "mlb", bad, "t", str(target))
    assert FANGRAPHS_SCHEMAS["guts"].names[0] == "season"
