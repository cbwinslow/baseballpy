"""Retrosheet coverage: tree discovery, honest completion, every dataset, resume, streaming."""

import json
import os
import time
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import respx
from conftest import RetroRepo

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for, get_dataset
from baseballpy.core.github_tree import TreeEntry
from baseballpy.core.schema_tools import reset_drift_warnings
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet import api as retro_api
from baseballpy.sources.retrosheet.api import RetrosheetSource
from baseballpy.sources.retrosheet.downloader import FetchOutcome, RetrosheetDownloader
from baseballpy.sources.retrosheet.parser import RetrosheetFlatParser
from baseballpy.sources.retrosheet.tree import classify


def _game(game_id: str, home: str = "BOS", away: str = "BAL") -> bytes:
    year = game_id[3:7]
    return (
        f"id,{game_id}\n"
        f"info,date,{year}/04/01\n"
        f"info,hometeam,{home}\n"
        f"info,visteam,{away}\n"
        "start,play01,Batter One,0,1,4\n"
        "start,pitch01,Pitcher One,1,1,1\n"
        "play,1,0,play01,00,,S\n"
        "data,er,pitch01,0\n"
    ).encode()


SCHEDULE = (
    b"Date,Num,Day,Visitor,League,Game,Home,League,Game,Day/Night,Postponed,Makeup\n"
    b'"20240328","0","Thu","BAL","AL",1,"BOS","AL",1,"d","",""\n'
)
UMPIRES = b"ID,last,first\nbarkj901,Barker,Jim\n"
DISCS = (
    b"ID,Player,Year,Team,Type,Pos,Cat,Game,Retro,Official,Cross,Code,,Notes,Accepted\n"
    b"2024A0001,play01,2024,BOS,D,2B,DP,BOS202404010,2,1,,SWAP,,note,\n"
    b"2024A0002,play01,2024,BOS,D,2B,DP,BOS202404010,2,1,,SWAP,\n"  # short row (14 fields)
)
GAMELOG = b"20240401,0,Mon,BAL,AL,1,BOS,AL,1,5,3,54,D,0,0,0,BOS07,37000,180\n"


def full_season(repo: RetroRepo, year: int = 2024) -> RetroRepo:
    """One of every file kind Retrosheet publishes for a season."""
    s = f"seasons/{year}"
    repo.add(f"{s}/TEAM{year}", b"BOS,A\nBAL,A\n")
    repo.add(f"{s}/{year}BOS.EVA", _game(f"BOS{year}04010"))
    repo.add(f"{s}/{year}BAL.EVN", _game(f"BAL{year}04020", "BAL", "BOS"))
    repo.add(f"{s}/{year}ALCS.EVE", _game(f"BOS{year}10150"))
    repo.add(f"{s}/{year}.EDA", _game(f"BOS{year}05010"))
    repo.add(
        f"{s}/{year}.EBA",
        b"id,BOS%d04010\nversion,3\nstat,bline,play01,0,1,1,4,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n"
        % year,
    )
    repo.add(f"{s}/BOS{year}.ROS", b"play01,One,Batter,R,R,BOS,OF\n")
    repo.add(f"{s}/GL{year}.TXT", GAMELOG)
    repo.add(f"{s}/{year}schedule.csv", SCHEDULE)
    repo.add(f"{s}/UMPIRES{year}.txt", UMPIRES)
    repo.add(f"{s}/{year}aldiscs.csv", DISCS)
    return repo


# --------------------------------------------------------------------------- tree classification
def test_classify_covers_every_published_file_kind() -> None:
    paths = [
        "seasons/1912/1912.EBA",
        "seasons/1912/1912aldiscs.csv",
        "seasons/1912/GL1912.TXT",
        "seasons/1912/TEAM1912",
        "seasons/1912/UMPIRES1912.txt",
        "seasons/1912/BS11871.ROS",
        "seasons/1950/1950.EDA",
        "seasons/1950/1950.EVR",
        "seasons/1950/1950AS.EVE",
        "seasons/1950/1950BOS.EVA",
        "seasons/1950/1950BOS.EVN",
        "seasons/2026/2026SCHEDULE.CSV",
        "seasons/2023/2023.EBN",
        "seasons/2020/2020sched-orig.csv",
        "seasons/2023/mystery.bin",
        "gamelog/GLWS.TXT",
        "gamelog/GLAS.TXT",
        "reference/ballparks.csv",
        "reference/biofile0.csv",
        "README.md",
    ]
    tree = classify(TreeEntry(p, 1, "x") for p in paths)
    kinds = {f.name: f.kind for files in tree.by_season.values() for f in files}
    assert kinds["1912.EBA"] == "box" and kinds["1912aldiscs.csv"] == "discrepancies"
    assert kinds["GL1912.TXT"] == "gamelog" and kinds["TEAM1912"] == "team"
    assert kinds["UMPIRES1912.txt"] == "umpires" and kinds["BS11871.ROS"] == "roster"
    assert kinds["1950.EDA"] == "event_deduced" and kinds["1950.EVR"] == "event_postseason"
    assert kinds["1950AS.EVE"] == "event_postseason" and kinds["1950BOS.EVA"] == "event_regular"
    assert kinds["1950BOS.EVN"] == "event_regular" and kinds["2023.EBN"] == "box"
    assert kinds["2026SCHEDULE.CSV"] == "schedule"
    assert kinds["2020sched-orig.csv"] == "schedule_original"
    assert tree.seasons() == [1912, 1950, 2020, 2023, 2026]
    assert tree.uncovered == ["seasons/2023/mystery.bin"]
    assert [f.name for f in tree.postseason_gamelogs] == ["GLWS.TXT", "GLAS.TXT"]
    assert tree.postseason_gamelog("world_series") is not None
    assert tree.reference_file("biofile0") is not None and tree.reference_file("nope") is None
    assert {f.raw_dataset for f in tree.reference} == {"reference_ballparks", "reference_biofile0"}


# --------------------------------------------------------------------------- downloader
@respx.mock
def test_download_season_fetches_all_kinds_records_sha256_and_resumes(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    cfg = LakeConfig(home=tmp_path)
    dl = RetrosheetDownloader(cache_config=cfg)
    first = dl.download_season(2024)
    assert first.complete and not first.absent and len(first.files) == 11
    assert dl.manifest.is_completed("season_2024")

    raw = cfg.raw_root / "retrosheet"
    assert (raw / "event_files" / "season=2024" / "2024BOS.EVA").exists()
    assert (raw / "event_files" / "season=2024" / "TEAM2024").exists()
    assert (raw / "box_files" / "season=2024" / "2024.EBA").exists()
    assert (raw / "rosters" / "season=2024" / "BOS2024.ROS").exists()
    assert (raw / "gamelogs" / "season=2024" / "GL2024.TXT").exists()
    assert (raw / "schedule" / "season=2024" / "2024schedule.csv").exists()
    assert (raw / "umpires" / "season=2024" / "UMPIRES2024.txt").exists()
    assert (raw / "discrepancies" / "season=2024" / "2024aldiscs.csv").exists()
    entry = cfg.dataset_manifest("retrosheet", "event_files", "raw", 2024).get_chunk("2024BOS.EVA")
    assert entry is not None and len(entry["sha256"]) == 64 and entry["source_ref"]

    calls = len(respx.calls)
    again = dl.download_season(2024)
    assert again.cache_hit and again.complete
    assert len(respx.calls) == calls  # no network at all on resume


@respx.mock
def test_listed_but_missing_file_is_absent_never_completed_and_retried(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    import baseballpy.core.sources_lock as lock

    full_season(retro_repo)
    retro_repo.mount(serve=False)
    ref = lock.get_source_ref("retrosheet")
    for path, content in retro_repo.files.items():
        status = 404 if path.endswith("BAL.EVN") else 200
        respx.get(f"{ref.raw_base()}/{path}").mock(
            return_value=httpx.Response(status, content=content)
        )
    cfg = LakeConfig(home=tmp_path)
    dl = RetrosheetDownloader(cache_config=cfg)
    result = dl.download_season(2024)
    assert result.absent == ["2024BAL.EVN"] and not result.complete
    assert not dl.manifest.is_completed("season_2024")
    chunk = dl.manifest.get_chunk("season_2024")
    assert chunk is not None and chunk["status"] == "ABSENT" and "2024BAL.EVN" in chunk["reason"]

    respx.get(f"{ref.raw_base()}/seasons/2024/2024BAL.EVN").mock(
        return_value=httpx.Response(200, content=_game("BAL202404020", "BAL", "BOS"))
    )
    retry = dl.download_season(2024)
    assert retry.complete and dl.manifest.is_completed("season_2024")


@respx.mock
def test_kind_restricted_download_never_marks_the_season_complete(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    dl = RetrosheetDownloader(cache_config=LakeConfig(home=tmp_path))
    partial = dl.download_season(2024, kinds=("team", "roster"))
    assert {f.kind for f in partial.files} == {"team", "roster"} and not partial.complete
    assert dl.manifest.get_chunk("season_2024") is None


@respx.mock
def test_season_missing_from_the_tree_is_recorded_absent(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    dl = RetrosheetDownloader(cache_config=LakeConfig(home=tmp_path))
    result = dl.download_season(1999)
    assert result.files == [] and not result.complete
    chunk = dl.manifest.get_chunk("season_1999")
    assert chunk is not None and chunk["status"] == "ABSENT"


@respx.mock
def test_tree_is_cached_and_seasons_come_from_it(tmp_path: Path, retro_repo: RetroRepo) -> None:
    full_season(retro_repo, 2023)
    full_season(retro_repo, 2024)
    retro_repo.mount()
    cfg = LakeConfig(home=tmp_path)
    assert RetrosheetDownloader(cache_config=cfg).seasons() == [2023, 2024]
    before = len(respx.calls)
    assert RetrosheetDownloader(cache_config=cfg).seasons() == [2023, 2024]
    assert len(respx.calls) == before  # served from cache/http (pinned ref)


@respx.mock
def test_stale_part_files_are_discarded_at_startup(tmp_path: Path, retro_repo: RetroRepo) -> None:
    full_season(retro_repo).mount()
    cfg = LakeConfig(home=tmp_path)
    leftover = (
        cfg.raw_dir("retrosheet", "event_files", 2024, create=True) / "2024BOS.EVA.1.abcd.part"
    )
    leftover.write_bytes(b"half a file")
    old = time.time() - 7200
    os.utime(leftover, (old, old))
    RetrosheetDownloader(cache_config=cfg)
    assert not leftover.exists()


# --------------------------------------------------------------------------- datasets
@respx.mock
def test_ingest_season_produces_every_dataset_and_keeps_box_files_raw_only(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    cfg = LakeConfig(home=tmp_path)
    source = RetrosheetSource(cache_config=cfg)
    report = source.ingest_season(2024)
    assert report.complete_download
    rows = report.datasets
    assert rows["events"] == 2 and rows["events_postseason"] == 1 and rows["events_deduced"] == 1
    for name in ("boxscores_batting", "boxscores_pitching", "daily_splits", "substitutions"):
        assert rows[name] is not None, name
    assert rows["rosters"] == 1 and rows["gamelogs"] == 1
    assert rows["schedule"] == 1 and rows["umpires"] == 1 and rows["discrepancies"] == 2

    events = source.store.read(get_dataset("retrosheet", "events"), 2024)
    assert sorted(events["GAME_ID"].to_pylist()) == ["BAL202404020", "BOS202404010"]
    post = source.store.read(get_dataset("retrosheet", "events_postseason"), 2024)
    assert post["GAME_ID"].to_pylist() == ["BOS202410150"]
    assert "BOS202404010" not in post["GAME_ID"].to_pylist()  # no duplicated regular-season games
    deduced = source.store.read(get_dataset("retrosheet", "events_deduced"), 2024)
    assert deduced["GAME_ID"].to_pylist() == ["BOS202405010"]

    sched = source.store.read(get_dataset("retrosheet", "schedule"), 2024)
    assert sched["game_date"].to_pylist()[0].isoformat() == "2024-03-28"
    assert sched["visitor_team"].to_pylist() == ["BAL"] and sched[
        "home_game_number"
    ].to_pylist() == [1]
    disc = source.store.read(get_dataset("retrosheet", "discrepancies"), 2024)
    assert disc["disc_id"].to_pylist() == ["2024A0001", "2024A0002"]
    assert disc["notes"].to_pylist()[0] == "note"
    ump = source.store.read(get_dataset("retrosheet", "umpires"), 2024)
    assert ump["umpire_id"].to_pylist() == ["barkj901"] and ump["last_name"].to_pylist() == [
        "Barker"
    ]

    # box files are stored raw only: no processed dataset exists for them
    assert (cfg.raw_dir("retrosheet", "box_files", 2024) / "2024.EBA").exists()
    assert not any("box_files" in d.name for d in datasets_for("retrosheet"))
    assert not (cfg.processed_root / "retrosheet" / "box_files").exists()

    again = source.ingest_season(2024)
    assert all(v is None for v in again.datasets.values())  # everything cached


@respx.mock
def test_future_season_with_only_a_schedule_is_ingestible(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    retro_repo.add("seasons/2026/2026SCHEDULE.CSV", SCHEDULE.replace(b"2024", b"2026"))
    retro_repo.mount()
    source = RetrosheetSource(cache_config=LakeConfig(home=tmp_path))
    report = source.ingest_season(2026)
    assert report.datasets["schedule"] == 1
    assert report.datasets["events"] == 0 and report.datasets["gamelogs"] == 0
    assert source.schedule(2026)["visitor_team"].to_pylist() == ["BAL"]
    # empty chunks are remembered, so nothing is re-parsed
    assert source.ingest_season(2026).datasets["events"] is None


@respx.mock
def test_unknown_reference_table_is_rejected_with_the_valid_names(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    retro_repo.add(
        "reference/teams.csv",
        b"TEAM,LEAGUE,CITY,NICKNAME,FIRST,LAST\nBOS,AL,Boston,Red Sox,1901,2024\n",
    )
    retro_repo.mount()
    source = RetrosheetSource(cache_config=LakeConfig(home=tmp_path))
    with pytest.raises(ValueError, match="Unknown reference table"):
        source.reference("nonsense")
    assert source.reference("teams")["team_id"].to_pylist() == ["BOS"]


@respx.mock
def test_missing_gamelog_raises_instead_of_returning_empty(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    retro_repo.add("seasons/1800/TEAM1800", b"BOS,A\n").mount()
    source = RetrosheetSource(cache_config=LakeConfig(home=tmp_path))
    with pytest.raises(FileNotFoundError, match="game log"):
        source.game_logs(1800)


# --------------------------------------------------------------------------- resume
@respx.mock
def test_ingest_all_resumes_after_an_interruption(
    tmp_path: Path, retro_repo: RetroRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    for year in (2000, 2001, 2002, 2003, 2004, 2005):
        full_season(retro_repo, year)
    retro_repo.add(
        "reference/teams.csv",
        b"TEAM,LEAGUE,CITY,NICKNAME,FIRST,LAST\nBOS,AL,Boston,Red Sox,1901,2024\n",
    )
    retro_repo.add("gamelog/GLWS.TXT", GAMELOG)
    retro_repo.mount()
    cfg = LakeConfig(home=tmp_path)
    source = RetrosheetSource(cache_config=cfg)

    real = RetrosheetSource.ingest_season
    state = {"crash": True}

    def flaky(self: RetrosheetSource, year: int, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if year == 2003 and state["crash"]:
            # a killed process leaves a half-written .part file behind
            part = (
                cfg.raw_dir("retrosheet", "event_files", 2003, create=True)
                / "2003BOS.EVA.9.dead.part"
            )
            part.write_bytes(b"partial")
            old = time.time() - 7200
            os.utime(part, (old, old))
            raise KeyboardInterrupt
        return real(self, year, *args, **kwargs)

    monkeypatch.setattr(RetrosheetSource, "ingest_season", flaky)
    with pytest.raises(KeyboardInterrupt):
        source.ingest_all(2000, 2005)
    done = [y for y in range(2000, 2006) if source.downloader.manifest.is_completed(f"season_{y}")]
    assert done == [2000, 2001, 2002]

    state["crash"] = False
    calls = len(respx.calls)
    resumed = RetrosheetSource(cache_config=cfg).ingest_all(2000, 2005)
    assert resumed.ok and [s.year for s in resumed.seasons] == [2000, 2001, 2002, 2003, 2004, 2005]
    for season in resumed.seasons[:3]:  # already finished: nothing re-parsed
        assert all(v is None for v in season.datasets.values())
    assert resumed.seasons[3].datasets["events"] == 2
    assert not list(tmp_path.rglob("*.part"))
    assert resumed.reference["reference_teams"] == 1
    assert resumed.reference["gamelogs_postseason:world_series"] == 1
    assert len(respx.calls) > calls


@respx.mock
def test_ingest_all_can_collect_failures_per_season(
    tmp_path: Path, retro_repo: RetroRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_season(retro_repo, 2001)
    full_season(retro_repo, 2002)
    retro_repo.mount()
    real = RetrosheetSource.ingest_season

    def broken(self: RetrosheetSource, year: int, *a: object, **k: object):  # type: ignore[no-untyped-def]
        if year == 2001:
            raise RuntimeError("boom")
        return real(self, year, *a, **k)

    monkeypatch.setattr(RetrosheetSource, "ingest_season", broken)
    source = RetrosheetSource(cache_config=LakeConfig(home=tmp_path))
    report = source.ingest_all(reference=False, continue_on_error=True)
    assert report.failures == {2001: "RuntimeError: boom"} and [s.year for s in report.seasons] == [
        2002
    ]
    with pytest.raises(RuntimeError, match="boom"):
        source.ingest_all(reference=False)


# --------------------------------------------------------------------------- flat parser
def test_reference_header_drift_goes_to_extras_and_dates_are_typed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reset_drift_warnings()
    raw = (
        "PARKID,NAME,AKA,CITY,STATE,START,END,LEAGUE,NOTES,CAPACITY\n"
        "BOS07,Fenway,,Boston,MA,4/20/1912,,AL,,37755\n"
    )
    with caplog.at_level("WARNING"):
        table = RetrosheetFlatParser().parse_bytes("reference_ballparks", raw)
    assert table["park_id"].to_pylist() == ["BOS07"]
    assert table["start_date"].to_pylist()[0].isoformat() == "1912-04-20"  # single-digit month/day
    assert json.loads(table["_extras"][0].as_py()) == {"CAPACITY": "37755"}
    assert any("schema_drift" in r.getMessage() for r in caplog.records)


def test_headerless_schedule_and_column_reordering() -> None:
    headerless = b'"19040414","0","Thu","NY1","NL",1,"BRO","NL",1,"D","",""\n'
    table = RetrosheetFlatParser().parse_bytes("schedule", headerless)
    assert table["visitor_team"].to_pylist() == ["NY1"] and table["home_team"].to_pylist() == [
        "BRO"
    ]
    assert table["game_date"].to_pylist()[0].isoformat() == "1904-04-14"
    reordered = RetrosheetFlatParser().parse_bytes(
        "reference_relatives", "id2,id1,relation\nb,a,Brother\n"
    )
    assert reordered["person_id_1"].to_pylist() == ["a"] and reordered[
        "person_id_2"
    ].to_pylist() == ["b"]


def test_both_biofile_flavours_are_typed() -> None:
    old = RetrosheetFlatParser().parse_bytes(
        "reference_biofile",
        'PLAYERID,LAST,FIRST,BIRTHDATE,PLAY.DEBUT,WEIGHT\n"aardd001","Aardsma","David","12/27/1981","04/06/2004",200\n',
    )
    new = RetrosheetFlatParser().parse_bytes(
        "reference_biofile0",
        "id,lastname,birthdate,debut_p,weight\naardd001,Aardsma,19811227,20040406,200.5\n",
    )
    assert old["play_debut"].to_pylist()[0].isoformat() == "2004-04-06"
    assert old["birthdate"].to_pylist() == [
        "12/27/1981"
    ]  # partial dates exist upstream: kept as text
    assert new["birthdate"].to_pylist() == ["19811227"]  # YYYYMMDD, 00 = unknown part
    assert new["debut_p"].to_pylist()[0].isoformat() == "2004-04-06"
    assert new["weight"].to_pylist() == [200.5]


def test_unparseable_dates_are_quarantined_not_silently_dropped(tmp_path: Path) -> None:
    from baseballpy.core.config import QuarantineConfig
    from baseballpy.core.quarantine import Quarantine

    q = Quarantine(QuarantineConfig(base_dir=tmp_path))
    table = RetrosheetFlatParser(quarantine=q).parse_bytes(
        "reference_coaches", "id,year,team,role,start,end\nabc,1979,ATL,C,not-a-date,09/30/1979\n"
    )
    assert table["start_date"].to_pylist() == [None]
    assert list((tmp_path / "quarantine" / "retrosheet").rglob("*.jsonl"))


def test_unknown_flat_dataset_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown flat Retrosheet dataset"):
        RetrosheetFlatParser().parse_bytes("nope", b"a\n1\n")


# --------------------------------------------------------------------------- registry & adapter
def test_registry_has_every_retrosheet_dataset() -> None:
    catalog.register_all()
    assert {d.name for d in datasets_for("retrosheet")} >= {
        "events",
        "events_postseason",
        "events_deduced",
        "boxscores_batting",
        "boxscores_pitching",
        "daily_splits",
        "substitutions",
        "rosters",
        "gamelogs",
        "gamelogs_postseason",
        "schedule",
        "umpires",
        "discrepancies",
        "reference_ballparks",
        "reference_biofile",
        "reference_biofile0",
        "reference_coaches",
        "reference_ejections",
        "reference_relatives",
        "reference_teams",
    }
    assert get_dataset("retrosheet", "schedule").partition == "season"


def test_only_the_adapter_imports_chadwickpy() -> None:
    src = Path(__file__).parent.parent / "src" / "baseballpy"
    offenders = [
        str(p.relative_to(src))
        for p in src.rglob("*.py")
        if p.name != "_chadwick_adapter.py"
        and "chadwickpy" in p.read_text(encoding="utf-8")
        and any(
            line.lstrip().startswith(("import chadwickpy", "from chadwickpy"))
            for line in p.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert offenders == []


def test_adapter_raises_a_helpful_error_when_chadwickpy_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins
    import importlib

    import baseballpy.sources.retrosheet._chadwick_adapter as adapter

    real_import = builtins.__import__

    def fake(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name.startswith("chadwickpy"):
            raise ImportError("no chadwickpy")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake)
    try:
        with pytest.raises(ImportError, match=r"baseballpy\[retrosheet\]"):
            importlib.reload(adapter)
    finally:
        monkeypatch.undo()
        importlib.reload(adapter)


# --------------------------------------------------------------------------- streaming & pool
@respx.mock
def test_events_are_streamed_into_one_part_with_a_row_group_per_file(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    retro_repo.add("seasons/2024/TEAM2024", b"BOS,A\nBAL,A\n")
    retro_repo.add("seasons/2024/2024BOS.EVA", _game("BOS202404010"))
    retro_repo.add("seasons/2024/2024NYA.EVA", _game("NYA202404020", "NYA", "BOS"))
    retro_repo.add("seasons/2024/2024BAL.EVN", _game("BAL202404030", "BAL", "BOS"))
    retro_repo.mount()
    cfg = LakeConfig(home=tmp_path)
    source = RetrosheetSource(cache_config=cfg)
    table = source.events(2024)
    assert sorted(table["GAME_ID"].to_pylist()) == ["BAL202404030", "BOS202404010", "NYA202404020"]
    part = source.store.part_path(get_dataset("retrosheet", "events"), "events", 2024)
    meta = pq.ParquetFile(part).metadata
    assert meta.num_rows == 3 and meta.num_row_groups == 3
    assert isinstance(table, pa.Table) and not list(tmp_path.rglob("*.part"))


@respx.mock
def test_process_pool_parsing_matches_in_process_parsing(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    retro_repo.add("seasons/2024/TEAM2024", b"BOS,A\nBAL,A\n")
    retro_repo.add("seasons/2024/2024BOS.EVA", _game("BOS202404010"))
    retro_repo.add("seasons/2024/2024BAL.EVN", _game("BAL202404030", "BAL", "BOS"))
    retro_repo.mount()
    serial = RetrosheetSource(cache_config=LakeConfig(home=tmp_path / "a")).events(2024)
    pooled = RetrosheetSource(cache_config=LakeConfig(home=tmp_path / "b", parse_workers=2)).events(
        2024
    )
    assert serial.equals(pooled)


def test_module_level_names_exist() -> None:
    assert callable(retro_api.ingest_all) and callable(retro_api.schedule)
    assert FetchOutcome.ABSENT == "absent"


@respx.mock
def test_original_schedule_is_its_own_dataset(tmp_path: Path, retro_repo: RetroRepo) -> None:
    retro_repo.add("seasons/2020/2020sched-orig.csv", SCHEDULE.replace(b"2024", b"2020"))
    retro_repo.add(
        "seasons/2020/2020schedule.csv", SCHEDULE.replace(b"2024", b"2020").replace(b"BAL", b"NYA")
    )
    retro_repo.mount()
    source = RetrosheetSource(cache_config=LakeConfig(home=tmp_path))
    assert source.schedule_original(2020)["visitor_team"].to_pylist() == ["BAL"]
    assert source.schedule(2020)["visitor_team"].to_pylist() == ["NYA"]
    assert get_dataset("retrosheet", "schedule_original").view == "retrosheet_schedule_original"
