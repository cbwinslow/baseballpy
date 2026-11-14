"""The round-trip check for JSON raw answers (MLB Stats API).

A tiny raw JSON answer is stored with the processed table the real normalizer makes from it (no network). The
check flattens the raw answer with the ingest's own code and compares every scalar with the stored cell:

* a clean answer is ``ok``;
* a stored float rounded to 32 bits, a string that lost its leading zero, a value set to NULL and a timestamp
  moved by a second are each reported;
* a JSON key that neither a schema column nor ``_extras`` holds is ``unmapped_raw_column``;
* per-game answers are read from the raw response log (ADR 95), not from loose files;
* a league-wide pool kept by both routes (``/v1/stats`` and the hydrate fallback) is compared with the route its
  stored rows came from.

Each loss test fails if the check is removed (the clean case passes on the same data).
"""

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.responselog import COMMIT_NAME, Response
from baseballpy.core.roundtrip import DatasetCheck, register_raw_reader, roundtrip_dataset
from baseballpy.core.roundtrip_json import records_table, scalar_text
from baseballpy.core.segments import SegmentWriter
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.endpoints import BY_NAME, SUPPORTED, Context, request_extra
from baseballpy.sources.mlb_api.endpoints import requests_for as all_requests
from baseballpy.sources.mlb_api.game_segments import game_normalizer, game_url_groups
from baseballpy.sources.mlb_api.generic import MlbRecordNormalizer, stats_payload
from baseballpy.sources.mlb_api.roundtrip import raw_reader, request_ident

SOURCE = "mlb_api"
SEASON = 2024


@pytest.fixture(autouse=True)
def _registered() -> None:
    catalog.register_all()
    register_raw_reader(SOURCE, raw_reader)


def _picks() -> dict[str, Any]:
    person_one = {
        "fullName": "Travis Bazzana",
        "birthDate": "2002-08-28",
        "strikeZoneTop": 3.371,
        "strikeZoneBottom": 1.6,
        "nickName": "007",
        "nameSuffix": "1.000",
        "active": True,
    }
    person_two = {"fullName": "Charlie Condon", "strikeZoneTop": 3.49, "nickName": "042"}
    picks = [
        {"pickNumber": 1, "pickRound": "1", "isDrafted": True, "person": person_one},
        {"pickNumber": 2, "pickRound": "1", "isDrafted": False, "person": person_two},
    ]
    return {"drafts": {"draftYear": SEASON, "rounds": [{"round": "1", "picks": picks}]}}


def _store_answer(
    config: LakeConfig, dataset: str, ident: str, payload: Any, table: pa.Table | None = None
) -> pa.Table:
    """The raw answer as a loose file and the normalizer's table as its processed chunk."""
    endpoint = BY_NAME[dataset]
    body = json.dumps(payload).encode()
    RawStore(config).put(SOURCE, dataset, f"{ident}.json", body, season=SEASON)
    made = MlbRecordNormalizer().normalize(endpoint, payload)
    ProcessedStore(config).put(
        get_dataset(SOURCE, dataset),
        made if table is None else table,
        chunk_id=ident,
        season=SEASON,
    )
    return made


def _check(config: LakeConfig, dataset: str) -> DatasetCheck:
    return roundtrip_dataset(config, get_dataset(SOURCE, dataset))


def _losses(check: DatasetCheck) -> dict[tuple[str, str], int]:
    return {(x.kind, x.column): x.count for x in check.losses}


def _replace(table: pa.Table, column: str, values: pa.Array) -> pa.Table:
    return table.set_column(table.schema.get_field_index(column), column, values)


def test_scalars_keep_the_text_the_provider_sent() -> None:
    assert scalar_text("1.000") == "1.000" and scalar_text("007") == "007"
    assert scalar_text(0.1) == "0.1" and scalar_text(3) == "3" and scalar_text(True) == "true"
    assert scalar_text("") is None and scalar_text(None) is None
    table = records_table([{"a": 1}, {"b": "x"}])
    assert table.column_names == ["a", "b"] and table.column("a").to_pylist() == ["1", None]


def test_a_clean_json_answer_round_trips(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    _store_answer(config, "draft_picks", "draft_picks_2024", _picks())
    check = _check(config, "draft_picks")
    assert check.status == "ok", check
    assert check.raw_rows == 2 and check.compared == 2 and not check.losses


def test_a_rounded_float_a_dropped_zero_and_a_null_are_reported(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    good = MlbRecordNormalizer().normalize(BY_NAME["draft_picks"], _picks())
    bad = _replace(
        good,
        "person_strike_zone_top",
        pa.array([3.371, 3.49], pa.float32()).cast(pa.float64()),  # stored through 32 bits
    )
    bad = _replace(bad, "person_nick_name", pa.array(["7", "042"]))  # "007" lost its zeros
    bad = _replace(bad, "person_birth_date", pa.array([None, None], pa.date32()))
    bad = _replace(bad, "person_name_suffix", pa.array(["1.0", None]))  # "1.000" lost its zeros
    _store_answer(config, "draft_picks", "draft_picks_2024", _picks(), bad)
    check = _check(config, "draft_picks")
    losses = _losses(check)
    assert check.status == "loss"
    assert losses[("changed_cell", "person_strike_zone_top")] == 2, "3.371 and 3.49 are not exact"
    assert losses[("changed_cell", "person_nick_name")] == 1
    assert losses[("changed_cell", "person_name_suffix")] == 1
    assert losses[("lost_to_null", "person_birth_date")] == 1
    example = next(x.example for x in check.losses if x.column == "person_nick_name")
    assert "'007'" in example and "'7'" in example


def test_a_timestamp_is_compared_by_the_instant_it_names(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    team = {"team": {"id": 147, "name": "Yankees"}, "lastUpdated": "2024-10-01T03:05:07.25Z"}
    payload = {"records": [{"standingsType": "regularSeason", "teamRecords": [team]}]}
    good = MlbRecordNormalizer().normalize(BY_NAME["standings_regular_season"], payload)
    _store_answer(config, "standings_regular_season", "standings_regular_season_2024", payload)
    assert _check(config, "standings_regular_season").status == "ok"
    moved = _replace(
        good,
        "last_updated",
        pa.array([1727751907000000], pa.timestamp("us", tz="UTC")),  # 03:05:07, the .25 s cut
    )
    other = LakeConfig(home=tmp_path / "moved")
    _store_answer(
        other, "standings_regular_season", "standings_regular_season_2024", payload, moved
    )
    assert _losses(_check(other, "standings_regular_season")) == {
        ("changed_cell", "last_updated"): 1
    }


def test_a_json_key_nobody_holds_is_reported(tmp_path: Path) -> None:
    payload = _picks()
    payload["drafts"]["rounds"][0]["picks"][0]["scoutGrade"] = "070"
    config = LakeConfig(home=tmp_path)
    made = _store_answer(config, "draft_picks", "draft_picks_2024", payload)
    assert _check(config, "draft_picks").status == "ok", "the normalizer keeps it in _extras"
    lost = _replace(made, "_extras", pa.array([None, None], pa.string()))
    other = LakeConfig(home=tmp_path / "lost")
    _store_answer(other, "draft_picks", "draft_picks_2024", payload, lost)
    check = _check(other, "draft_picks")
    assert _losses(check) == {("unmapped_raw_column", "scoutGrade"): 1}


def _linescore(home_runs: int) -> bytes:
    innings = [
        {
            "num": 1,
            "ordinalNum": "1st",
            "home": {"runs": home_runs, "hits": 1},
            "away": {"runs": 0},
        },
        {"num": 2, "ordinalNum": "2nd", "home": {"runs": 0}, "away": {"runs": 2, "errors": 1}},
    ]
    return json.dumps({"currentInning": 2, "innings": innings}).encode()


def _game_lake(tmp_path: Path) -> tuple[LakeConfig, SegmentWriter, str]:
    """One game's linescore kept in the raw response log, its rows in a processed segment."""
    config = LakeConfig(home=tmp_path)
    group = next(g for g in game_url_groups() if "game_linescore" in g.datasets)
    url = group.url(745000)
    writer = SegmentWriter(config, SOURCE, SEASON, game_normalizer())
    writer.add_unit("745000", [Response(url, _linescore(1), "2024-07-01T00:00:00+00:00")])
    writer.commit()
    return config, writer, url


def test_game_answers_are_read_from_the_raw_response_log(tmp_path: Path) -> None:
    config, writer, url = _game_lake(tmp_path)
    assert not (config.raw_root / SOURCE / "game_linescore").exists(), "no loose raw file"
    check = _check(config, "game_linescore")
    assert check.status == "ok", check
    assert check.raw_rows == 2 and check.files == ["season=2024/seg-0001.parquet#745000"]
    # a refresh keeps the old answer beside the new one; the stored rows name the new one
    writer.refresh(1, {"745000": [Response(url, _linescore(5), "2024-07-02T00:00:00+00:00")]})
    assert _check(config, "game_linescore").status == "ok"


def test_a_changed_cell_in_a_processed_segment_is_reported(tmp_path: Path) -> None:
    config, _, _ = _game_lake(tmp_path)
    path = config.processed_dir(SOURCE, "game_linescore", SEASON) / "seg-0001.parquet"
    table = pq.read_table(path)
    pq.write_table(_replace(table, "home_runs", pa.array([4, 0], pa.int32())), path)
    check = _check(config, "game_linescore")
    assert _losses(check) == {("changed_cell", "home_runs"): 1}


def _pool_page(stat: float) -> dict[str, Any]:
    splits = [
        {"player": {"id": 1, "fullName": "A"}, "stat": {"woba": stat}},
        {"player": {"id": 2, "fullName": "B"}, "stat": {"woba": 0.3}},
    ]
    return {"stats": [{"totalSplits": 2, "splits": splits}]}


def test_a_pool_kept_by_both_routes_is_compared_with_the_route_it_was_built_from(
    tmp_path: Path,
) -> None:
    config = LakeConfig(home=tmp_path)
    dataset, ident = "stats_projected_hitting", "stats_projected_hitting_2024_sport1"
    page = _pool_page(0.35)
    RawStore(config).put(
        SOURCE, dataset, f"{ident}.p0.json", json.dumps(page).encode(), season=SEASON
    )
    fallback = {"people": [{"stats": [{"splits": _pool_page(0.351)["stats"][0]["splits"][:1]}]}]}
    RawStore(config).put(
        SOURCE, dataset, f"{ident}.hydrate.p0.json", json.dumps(fallback).encode(), season=SEASON
    )
    table = MlbRecordNormalizer().normalize(BY_NAME[dataset], page, extra={"sport_id": 1})
    ProcessedStore(config).put(get_dataset(SOURCE, dataset), table, chunk_id=ident, season=SEASON)
    check = _check(config, dataset)
    assert check.status == "ok", check
    assert check.files == [f"{ident}.p0.json.gz"], "the fallback's page made no stored row"


def test_request_ids_give_back_the_fan_out_columns() -> None:
    ctx = Context(
        season=SEASON,
        sport_ids=(1, 11),
        team_ids=(147,),
        game_pks=(745000,),
        person_ids=(660271,),
        metrics=("launchSpeed",),
        opposing_team_ids=(121,),
        opposing_player_ids=(592450,),
        award_ids=("ALMVP", "MLB_HOF"),
        leader_categories=("homeRuns",),
        sit_codes=("vl",),
        updated_since="2024-01-01",
        query="smith",
    )
    checked = 0
    for endpoint in SUPPORTED:
        for request in all_requests(endpoint, ctx):
            want = {k: str(v) for k, v in request.extra.items()}
            assert request_extra(endpoint, request.ident) == want, request.ident
            checked += 1
    assert checked > len(SUPPORTED)
    assert request_ident("x_2024_sport1.hydrate.p12.json.gz") == "x_2024_sport1"
    assert request_ident("x_2024.p0.json") == "x_2024" and request_ident("x.json.gz") == "x"


def test_a_dataset_never_downloaded_says_so(tmp_path: Path) -> None:
    check = _check(LakeConfig(home=tmp_path), "draft_picks")
    assert check.status == "skipped" and "never downloaded" in check.reason


def test_full_check_of_game_answers_refuses_above_the_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baseballpy.core.roundtrip import roundtrip_lake
    from baseballpy.sources.mlb_api import roundtrip as mlb_roundtrip

    config, _, _ = _game_lake(tmp_path)
    spec = get_dataset(SOURCE, "game_linescore")
    assert roundtrip_dataset(config, spec, full=True).status == "ok"
    monkeypatch.setattr(mlb_roundtrip, "FULL_GAME_LIMIT", 1)
    (check,) = roundtrip_lake(config, [spec], full=True)
    assert check.status == "skipped" and "--full would read" in check.reason
    assert "limit" in check.reason and "ADR 114" in check.reason
    assert roundtrip_dataset(config, spec).status == "ok", "a sample is never refused"


def test_no_sample_for_a_game_dataset_does_not_claim_the_raw_is_missing(tmp_path: Path) -> None:
    config, _, _ = _game_lake(tmp_path)
    # a dataset of another URL group: the log holds no answer at its URL, and no folder of its own exists
    other = next(g.datasets[0] for g in game_url_groups() if "game_linescore" not in g.datasets)
    ProcessedStore(config).put(
        get_dataset(SOURCE, other),
        pa.Table.from_pylist([], schema=get_dataset(SOURCE, other).schema),
        chunk_id="empty",
        season=SEASON,
    )
    check = _check(config, other)
    assert check.status == "skipped"
    assert "without their raw files" not in check.reason, check.reason
    assert "shared" in check.reason and "not a clean verdict" in check.reason


def test_a_hydrate_pool_is_compared_with_the_hydrate_pages(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    dataset, ident = "stats_projected_hitting", "stats_projected_hitting_2024_sport1"
    page = _pool_page(0.35)
    RawStore(config).put(
        SOURCE, dataset, f"{ident}.p0.json", json.dumps(page).encode(), season=SEASON
    )
    fallback = {"people": [{"stats": [{"splits": page["stats"][0]["splits"][:1]}]}]}
    RawStore(config).put(
        SOURCE, dataset, f"{ident}.hydrate.p0.json", json.dumps(fallback).encode(), season=SEASON
    )
    made = MlbRecordNormalizer().normalize(
        BY_NAME[dataset], stats_payload(fallback), extra={"sport_id": 1}
    )
    ProcessedStore(config).put(
        get_dataset(SOURCE, dataset),
        made,
        chunk_id=ident,
        season=SEASON,
        metadata={"via": "hydrate"},
    )
    check = _check(config, dataset)
    assert check.status == "ok", check
    assert check.files == [f"{ident}.hydrate.p0.json.gz"]


def test_stored_text_is_taken_as_large_string_so_a_season_over_2gib_does_not_overflow() -> None:
    from baseballpy.core.roundtrip import _take_rows

    table = pa.table({"a": pa.chunked_array([["x", "y"], ["z"]], pa.string()), "n": [1, 2, 3]})
    taken = _take_rows(table, pa.array([2, 0], pa.int64()))
    assert taken.schema.field("a").type == pa.large_string()
    assert taken.column("a").to_pylist() == ["z", "x"] and taken.column("n").to_pylist() == [3, 1]


def _put_loose(config: LakeConfig, dataset: str, name: str, body: bytes) -> None:
    RawStore(config).put(SOURCE, dataset, name, body, season=SEASON)


def test_an_error_on_one_answer_is_an_error_verdict_and_a_non_zero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from baseballpy.cli import main
    from baseballpy.core.roundtrip import roundtrip_lake

    config = LakeConfig(home=tmp_path)
    _store_answer(config, "draft_picks", "draft_picks_2024", _picks())
    _put_loose(config, "draft_picks", "draft_picks_2025.json", b"{torn body")
    spec = get_dataset(SOURCE, "draft_picks")
    (check,) = roundtrip_lake(config, [spec], sample_files=5)
    assert check.status == "error", check
    assert "BadBodyError" in check.reason or "not JSON" in check.reason
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    result = CliRunner().invoke(main, ["verify-roundtrip", "mlb_api", "-d", "draft_picks"])
    assert result.exit_code == 1, result.output
    assert "stopped by an error" in result.output


def test_a_listed_game_with_no_answer_in_its_segment_is_noted(tmp_path: Path) -> None:
    config, _, url = _game_lake(tmp_path)
    group = next(g for g in game_url_groups() if "game_linescore" in g.datasets)
    path = config.raw_root / SOURCE / f"season={SEASON}" / COMMIT_NAME
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    lines[-1]["units"] = [*lines[-1]["units"], "745999"]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    assert group.url(745999) != url
    check = _check(config, "game_linescore")
    assert any("745999" in n and "no answer" in n for n in check.notes), check.notes


def test_full_check_counts_loose_files_toward_the_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baseballpy.core.roundtrip import roundtrip_lake
    from baseballpy.sources.mlb_api import roundtrip as mlb_roundtrip

    config = LakeConfig(home=tmp_path)
    _store_answer(config, "draft_picks", "draft_picks_2024", _picks())
    spec = get_dataset(SOURCE, "draft_picks")
    assert roundtrip_dataset(config, spec, full=True).status == "ok"
    monkeypatch.setattr(mlb_roundtrip, "FULL_GAME_LIMIT", 1)
    (check,) = roundtrip_lake(config, [spec], full=True)
    assert check.status == "skipped" and "--full would read" in check.reason


def test_rows_that_name_no_raw_answer_are_noted(tmp_path: Path) -> None:
    config, writer, url = _game_lake(tmp_path)
    path = config.processed_dir(SOURCE, "game_linescore", SEASON) / "seg-0001.parquet"
    table = pq.read_table(path)
    nulls = pa.nulls(table.num_rows, pa.string())
    pq.write_table(_replace(table, "_raw_sha256", nulls), path)
    check = _check(config, "game_linescore")
    assert any("_raw_sha256" in n and "745000" not in n for n in check.notes), check.notes


def test_loose_answers_of_a_half_migrated_season_are_still_checked(tmp_path: Path) -> None:
    config, _, _ = _game_lake(tmp_path)
    ident = "game_linescore_745111"
    payload = json.loads(_linescore(1))
    endpoint = BY_NAME["game_linescore"]
    RawStore(config).put(
        SOURCE, "game_linescore", f"{ident}.json", json.dumps(payload).encode(), season=SEASON
    )
    made = MlbRecordNormalizer().normalize(endpoint, payload, extra={"game_pk": 745111})
    ProcessedStore(config).put(
        get_dataset(SOURCE, "game_linescore"), made, chunk_id=ident, season=SEASON
    )
    check = roundtrip_dataset(config, get_dataset(SOURCE, "game_linescore"), sample_files=10)
    assert check.status == "ok", check
    assert any(f.endswith("game_linescore_745111.json.gz") for f in check.files), check.files
    assert any("#745000" in f for f in check.files), check.files
