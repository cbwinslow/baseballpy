"""Phase 2 of the Retrosheet site datasets (change retrosheet-site-logs): player, manager and umpire logs as tables."""

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import RawStore
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet import site

LOGS = (
    "player_batting_logs",
    "player_fielding_logs",
    "player_pitching_logs",
    "manager_logs",
    "umpire_logs",
)

BATTING_HEAD = "gid,id,team,b_lp,b_seq,stattype,b_pa,b_ab,b_h,date,number,site,vishome,opp,eject"
BAT_A = BATTING_HEAD + "\nSLN200904060,aardd001,SLN,1,1,value,4,3,2,20090406,0,STL10,v,CHN,\n"
BAT_B = (
    BATTING_HEAD
    + ",surprise\nSLN200904070,aaroh101,SLN,2,1,value,5,5,1,20090407,0,STL10,h,CHN,,x\n"
)
FIELD_A = "gid,id,team,d_seq,d_pos,stattype,d_po,d_a,d_e,date\nSLN200904060,aardd001,SLN,1,1,value,3,1,0,20090406\n"
PITCH_A = "gid,id,team,p_seq,stattype,p_ipouts,p_h,p_er,date\nSLN200904060,aardd001,SLN,1,value,27,5,2,20090406\n"
MGR_A = "gid,team,mgr,stattype,b_pa,b_h,date\nWAS200704020,WAS,actam801,value,38,9,20070402\n"
UMP_A = "gid,visteam,hometeam,site,date,number,umphome\nCHN200904060,CHN,SLN,STL10,20090406,0,abbec101\n"
UMP_B = "gid,visteam,hometeam,site,date,number,umphome\nCHN200904070,CHN,SLN,STL10,20090407,0,abbed901\n"


def _zip(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return buffer.getvalue()


def _store(home: Path) -> LakeConfig:
    config = LakeConfig(home=home)
    raw = RawStore(config)
    zips = {
        "playerlogs.zip": {
            "aardd001_b.csv": BAT_A,
            "aaroh101_b.csv": BAT_B,
            "aardd001_f.csv": FIELD_A,
            "aardd001_p.csv": PITCH_A,
        },
        "mgrlogs.zip": {"actam801_mlog.csv": MGR_A},
        "umplogs.zip": {"abbec101_ulog.csv": UMP_A, "abbed901_ulog.csv": UMP_B},
    }
    for name, members in zips.items():
        data = _zip(members)
        staging = raw.path_for("retrosheet", site.RAW_DATASET, name).with_name(name + ".download")
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.write_bytes(data)
        raw.adopt(
            "retrosheet",
            site.RAW_DATASET,
            name,
            staging,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
        )
    return config


def test_the_log_datasets_are_registered_opt_in_and_strict() -> None:
    catalog.register_all()
    for name in LOGS:
        spec = get_dataset("retrosheet", name)
        assert spec.ingest == "opt_in", name
        assert spec.keys and all(k in spec.schema.names for k in spec.keys), name
        assert "_extras" in spec.schema.names, f"{name} keeps unknown columns"
    assert set(LOGS) <= set(site.SITE_DATASETS)
    assert [f.name for f in site.files_for(LOGS)] == [
        "playerlogs.zip",
        "mgrlogs.zip",
        "umplogs.zip",
    ]


def test_members_become_one_typed_table_per_kind(tmp_path: Path) -> None:
    config = _store(tmp_path)
    tables = site.read_site_datasets(config, LOGS)
    batting = tables["player_batting_logs"]
    assert batting.num_rows == 2, "both member files, one row each"
    assert batting.column("id").to_pylist() == ["aardd001", "aaroh101"]
    assert batting.schema.field("b_h").type in (pa.int16(), pa.int32())
    assert str(batting.schema.field("date").type) == "date32[day]"
    assert "surprise" in batting.column("_extras").to_pylist()[1], (
        "an unknown column is kept, not dropped"
    )
    assert tables["player_fielding_logs"].num_rows == 1
    assert tables["player_pitching_logs"].num_rows == 1
    assert tables["manager_logs"].column("mgr").to_pylist() == ["actam801"]
    umpires = tables["umpire_logs"]
    assert umpires.column("umpire_id").to_pylist() == ["abbec101", "abbed901"], (
        "the id comes from the file name"
    )


def test_batches_add_up_to_the_same_rows(tmp_path: Path) -> None:
    config = _store(tmp_path)
    batches = list(site.site_batches(config, "umpire_logs", batch_members=1))
    assert len(batches) == 2
    assert sum(b.num_rows for b in batches) == 2
    whole = site.read_site_datasets(config, ("umpire_logs",))["umpire_logs"]
    assert pa.concat_tables(batches).equals(whole)


def test_logs_ingest_end_to_end_then_skip(tmp_path: Path) -> None:
    """Zips already stored, network blocked: written once with the registered schema, then current."""
    from baseballpy.sources.retrosheet.api import RetrosheetSource

    config = _store(tmp_path)
    source = RetrosheetSource(config)
    first = source.ingest_site(LOGS)
    assert first == {
        "player_batting_logs": 2,
        "player_fielding_logs": 1,
        "player_pitching_logs": 1,
        "manager_logs": 1,
        "umpire_logs": 2,
    }
    stored = source.store.read_part(get_dataset("retrosheet", "umpire_logs"), "data", None)
    assert stored.schema == get_dataset("retrosheet", "umpire_logs").schema
    assert source.ingest_site(LOGS) == dict.fromkeys(first)


def test_the_generator_types_a_batch_from_its_values() -> None:
    path = Path(__file__).resolve().parent.parent / "scripts" / "gen_retrosheet_site_schemas.py"
    spec = importlib.util.spec_from_file_location("gen_retrosheet_site_schemas", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    infer = module.infer_arrow_type
    assert infer(pa.array(["1", "-7", None, ""])) == "int16"
    assert infer(pa.array(["1", "70000"])) == "int32"
    assert infer(pa.array(["1.5", "2", ""])) == "float64"
    assert infer(pa.array(["a", "1"])) == "string"
    assert infer(pa.array(["", None])) is None, "no value, no evidence"
    assert module.widen_types("int16", "float64") == "float64"
    assert module.widen_types("int16", None) == "int16"
    assert module.widen_types(None, "string") == "string"


def test_a_log_kind_with_no_member_is_reported(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    raw = RawStore(config)
    data = _zip({"other.txt": "x"})
    staging = raw.path_for("retrosheet", site.RAW_DATASET, "umplogs.zip").with_name(
        "umplogs.zip.download"
    )
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_bytes(data)
    raw.adopt(
        "retrosheet",
        site.RAW_DATASET,
        "umplogs.zip",
        staging,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )
    with pytest.raises(ValueError, match="no member"):
        site.read_site_datasets(config, ("umpire_logs",))


def test_a_declared_numeric_column_stays_a_number_when_one_cell_is_not(tmp_path: Path) -> None:
    """Upstream has a stray '?' or a manager id in a number column: the cell is quarantined, the column stays numeric."""
    path = Path(__file__).resolve().parent.parent / "scripts" / "gen_retrosheet_site_schemas.py"
    spec = importlib.util.spec_from_file_location("gen_retrosheet_site_schemas", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    column = pa.array(["3", "?", "10", "", None])
    assert module.infer_arrow_type(column) == "string", "undeclared: any stray value makes it text"
    assert module.infer_arrow_type(column, numeric=True) == "int16", (
        "declared numeric: typed from the numbers"
    )
    assert module.infer_arrow_type(pa.array(["1.5", "x"]), numeric=True) == "float64"
    assert site.SITE_DATASETS["manager_logs"].numeric == ("b_k", "p_k")
    assert site.SITE_DATASETS["umpire_logs"].numeric == ("temp",)
    assert site.SITE_DATASETS["player_fielding_logs"].numeric == ("d_pos",)
    assert len(site.SITE_DATASETS["manager_logs"].text) == 28, "line scores stay text"


def test_parallel_parsing_gives_the_same_rows_in_the_same_order(tmp_path: Path) -> None:
    """Parsing members on worker threads must not change the rows or their order."""
    config = _store(tmp_path)
    one = site.read_site_datasets(config, ("umpire_logs", "player_batting_logs"))
    threaded = LakeConfig(home=tmp_path, parse_workers=4)
    many = site.read_site_datasets(threaded, ("umpire_logs", "player_batting_logs"))
    assert one["umpire_logs"].equals(many["umpire_logs"])
    assert one["player_batting_logs"].equals(many["player_batting_logs"])


def test_the_negro_leagues_bundle_is_seven_opt_in_tables() -> None:
    """Its games are in neither our events (0 of 8,215) nor fully in the box scores: it must be tables."""
    catalog.register_all()
    names = (
        "negro_players",
        "negro_games",
        "negro_team_stats",
        "negro_batting",
        "negro_pitching",
        "negro_fielding",
        "negro_plays",
    )
    for name in names:
        spec = get_dataset("retrosheet", name)
        assert spec.ingest == "opt_in" and spec.keys and "_extras" in spec.schema.names, name
    assert [f.name for f in site.files_for(names)] == ["negroleagues.zip"]
