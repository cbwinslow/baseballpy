"""The MLB schema generator's key probe finds a unique key from the payload's own dimensions."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import gen_mlb_schemas as gen  # noqa: E402


def test_a_key_is_unique_over_the_rows() -> None:
    records = [
        {"team.id": 1, "season": "2024", "stat.avg": ".250"},
        {"team.id": 2, "season": "2024", "stat.avg": ".250"},
    ]
    key = gen.minimal_key(records)
    assert key == ("team.id",)
    assert len({tuple(r[c] for c in key) for r in records}) == len(records)


def test_totals_and_detail_rows_are_told_apart_by_sometimes_populated_dimensions() -> None:
    records = [
        {"team.id": 1, "stats.totalSplits": 3, "stat.avg": ".1"},
        {"team.id": 1, "stats.totalSplits": 3, "stat.avg": ".2", "pitcher.id": 10},
        {"team.id": 1, "stats.totalSplits": 3, "stat.avg": ".3", "pitcher.id": 11},
    ]
    key = gen.minimal_key(records)
    assert "pitcher.id" in key
    assert len({tuple(r.get(c) for c in key) for r in records}) == len(records)


def test_statistics_and_split_counts_are_never_part_of_a_key() -> None:
    records = [
        {"team.id": 1, "stats.totalSplits": 1, "stat.avg": ".1", "opponent.id": 5},
        {"team.id": 1, "stats.totalSplits": 2, "stat.avg": ".2", "opponent.id": 6},
        {"team.id": 1, "stats.totalSplits": 3, "stat.avg": ".3", "opponent.id": 7},
    ]
    key = gen.minimal_key(records)
    assert "opponent.id" in key
    assert not [c for c in key if c.startswith("stat.") or c == "stats.totalSplits"]


def test_the_key_check_maps_names_over_every_record_not_the_first() -> None:
    chunk = [
        {"batter.id": 1, "gameType": "R", "numTeams": 1},
        {"batter.id": 1, "pitcher.id": 10, "season": "2024", "gameType": "R"},
        {"batter.id": 1, "pitcher.id": 11, "season": "2024", "gameType": "R"},
    ]
    assert gen.key_unique_per_request([chunk], ("batter_id", "pitcher_id", "season", "game_type"))
    assert not gen.key_unique_per_request([chunk], ("batter_id",))


def test_key_overrides_name_existing_endpoints_and_are_used() -> None:
    from baseballpy.sources.mlb_api.endpoints import BY_NAME, KEY_OVERRIDES

    assert KEY_OVERRIDES
    for name, key in KEY_OVERRIDES.items():
        assert BY_NAME[name].keys == key


def test_a_provider_error_is_logged_and_remembered_never_read_as_no_data(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import httpx
    import respx

    from baseballpy.core.http import HttpClient

    gen.PROVIDER_ERRORS.clear()
    with respx.mock:
        respx.get(url__startswith=gen.BASE + "v1/stats").mock(return_value=httpx.Response(406))
        assert gen.get_json(HttpClient(), "v1/stats", {"stats": "season"}) is None
    assert gen.PROVIDER_ERRORS == [("v1/stats", 406)]
    assert "provider error HTTP 406" in capsys.readouterr().out
    gen.PROVIDER_ERRORS.clear()


def test_an_empty_league_wide_table_is_never_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "src" / "baseballpy" / "sources" / "mlb_api" / "stat_combos.py"
    target.parent.mkdir(parents=True)
    target.write_text("KEEP = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="refusing to write stat_combos.py"):
        gen.write_combos([], [("season", "hitting", ("season",))], [])
    assert target.read_text(encoding="utf-8") == "KEEP = 1\n"
