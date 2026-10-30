"""Savant leaderboard coverage: registry <-> schema <-> fixture <-> enum, typing, extraction."""

import json
from datetime import date
from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx

from baseballpy.core.config import LakeConfig, QuarantineConfig
from baseballpy.core.datasets import datasets_for, get_dataset
from baseballpy.core.quarantine import Quarantine
from baseballpy.core.upstream import Fingerprint, stored_fingerprint
from baseballpy.sources import catalog
from baseballpy.sources.statcast.lb_catalog import (
    BY_SLUG,
    LEADERBOARDS,
    SAVANT_BASE,
    SUPPORTED,
    request_params,
    resolve,
)
from baseballpy.sources.statcast.lb_parse import html_json_to_csv
from baseballpy.sources.statcast.lb_schema import LEADERBOARD_SCHEMAS, default_min, min_year
from baseballpy.sources.statcast.leaderboards import (
    StatcastLeaderboardExtractor,
    StatcastLeaderboardNormalizer,
)
from baseballpy.sources.statcast.schema import StatcastLeaderboard

FIXTURES = Path(__file__).parent / "fixtures" / "savant"
SLUGS = [d.slug for d in SUPPORTED]


def _fixture(slug: str) -> bytes:
    suffix = "html" if BY_SLUG[slug].fmt == "html_json" else "csv"
    return (FIXTURES / f"{slug}.{suffix}").read_bytes()


def test_registry_schema_dataset_fixture_and_enum_agree() -> None:
    catalog.register_all()
    assert set(LEADERBOARD_SCHEMAS) == set(SLUGS)
    assert {m.value for m in StatcastLeaderboard} == set(SLUGS)
    for defn in SUPPORTED:
        spec = get_dataset("statcast", defn.dataset)
        assert spec.schema == LEADERBOARD_SCHEMAS[defn.slug]
        assert spec.partition == ("none" if defn.year_style == "none" else "season")
        assert spec.keys == defn.keys
        assert set(defn.keys) <= set(spec.schema.names), defn.slug
        assert (FIXTURES / f"{defn.slug}.{'html' if defn.fmt == 'html_json' else 'csv'}").exists()
    assert len({d.slug for d in LEADERBOARDS}) == len(LEADERBOARDS)


def test_unsupported_variants_are_documented_not_registered() -> None:
    catalog.register_all()
    unsupported = [d for d in LEADERBOARDS if d.unsupported is not None]
    assert unsupported, "the probe found routes without CSV; they must stay listed"
    for defn in unsupported:
        assert defn.unsupported
        with pytest.raises(KeyError):
            get_dataset("statcast", defn.dataset)


@pytest.mark.parametrize("slug", SLUGS)
def test_fixture_normalizes_completely_and_typed(slug: str, tmp_path: Path) -> None:
    quarantine = Quarantine(QuarantineConfig(base_dir=tmp_path / "q"))
    table = StatcastLeaderboardNormalizer(quarantine).normalize(_fixture(slug), slug)
    schema = LEADERBOARD_SCHEMAS[slug]
    assert table.schema.names == schema.names
    assert [f.type for f in table.schema] == [f.type for f in schema]
    assert table.num_rows >= 1
    assert table.column("_extras").null_count == table.num_rows, "live headers fully covered"
    for key in BY_SLUG[slug].keys:
        assert table.column(key).null_count == 0, f"{slug}.{key} has NULL key cells"
    assert not (tmp_path / "q").exists() or not list((tmp_path / "q").rglob("*.jsonl"))


def test_regression_column_typing() -> None:
    """Name-guessing used to type `bats`/`pa`/`average_*`/`hp_to_1b` wrongly."""
    norm = StatcastLeaderboardNormalizer()
    speed = norm.normalize(_fixture("sprint_speed"), "sprint_speed")
    assert speed.schema.field("hp_to_1b").type == pa.float64()
    assert speed.schema.field("sprint_speed").type == pa.float64()
    assert speed.schema.field("competitive_runs").type in (pa.int16(), pa.int32())
    assert speed.schema.field("position").type == pa.string()
    splits = norm.normalize(_fixture("running_splits"), "running_splits")
    assert splits.schema.field("bat_side").type == pa.string()
    arsenals = norm.normalize(_fixture("pitch_arsenals"), "pitch_arsenals")
    assert arsenals.schema.field("ff_avg_speed").type == pa.float64()
    expected = norm.normalize(_fixture("expected_statistics_batter"), "expected_statistics_batter")
    assert expected.schema.field("pa").type in (pa.int16(), pa.int32())
    assert expected.schema.field("est_ba").type == pa.float64()


def test_float_cells_are_not_truncated() -> None:
    raw = (
        b'"last_name, first_name","player_id","year","pa","bip","ba"\n'
        b'"Doe, Jo","1","2024","10","5","0.299"\n'
    )
    table = StatcastLeaderboardNormalizer().normalize(raw, "expected_statistics_batter")
    assert table.column("ba").to_pylist() == [0.299]


def test_unknown_column_is_kept_in_extras_with_warning() -> None:
    raw = (
        b'"last_name, first_name","player_id","year","pa","bip","ba","brand_new"\n'
        b'"Doe, Jo","1","2024","10","5","0.299","zzz"\n'
    )
    table = StatcastLeaderboardNormalizer().normalize(raw, "expected_statistics_batter")
    assert json.loads(table.column("_extras")[0].as_py()) == {"brand_new": "zzz"}


def test_adhoc_normalizer_infers_types_and_survives_garbage() -> None:
    table = StatcastLeaderboardNormalizer().normalize(b'"id","avg"\n1,0.5\n2,0.25\n')
    assert table.schema.field("id").type == pa.int32()
    assert table.schema.field("avg").type == pa.float64()
    assert StatcastLeaderboardNormalizer().normalize(b"").num_rows == 0


def test_html_json_requires_the_embedded_array() -> None:
    with pytest.raises(ValueError, match="no `data"):
        html_json_to_csv(b"<html>nothing</html>")
    csv_bytes = html_json_to_csv(
        b'<script>var data = [{"a": 1, "b": null}, {"a": 2, "c": "x"}];</script>'
    )
    assert csv_bytes.decode().splitlines() == ["a,b,c", "1,,", "2,,x"]


def test_request_params_per_year_style() -> None:
    assert request_params(BY_SLUG["sprint_speed"], 2024, "0")["year"] == 2024
    snake = request_params(BY_SLUG["pitch_tempo"], 2019, "0")
    assert (snake["season_start"], snake["season_end"]) == (2019, 2019) and "year" not in snake
    rng = request_params(BY_SLUG["bat_tracking"], 2024, "0")
    assert (rng["seasonStart"], rng["seasonEnd"]) == (2024, 2024)
    assert "year" not in request_params(BY_SLUG["abs_challenges"], 2025)
    assert request_params(BY_SLUG["pitch_clock"], 2024)["season"] == 2024
    assert "csv" not in request_params(BY_SLUG["park_factors"], 2024)


def test_resolve_legacy_names() -> None:
    assert resolve("expected_statistics", "pitcher").slug == "expected_statistics_pitcher"
    assert resolve("expected_statistics").slug == "expected_statistics_batter"
    assert resolve("bat-tracking").slug == "bat_tracking"
    with pytest.raises(KeyError, match="unknown Savant leaderboard"):
        resolve("nope")


@respx.mock
def test_get_leaderboard_persists_strict_season_partition(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = StatcastLeaderboardExtractor(cache_config=lake)
    route = respx.get(f"{SAVANT_BASE}/sprint_speed").mock(
        return_value=httpx.Response(200, content=_fixture("sprint_speed"))
    )
    table = extractor.get_leaderboard("sprint_speed", year=2024)
    assert table.num_rows == 4 and route.call_count == 1
    assert dict(route.calls[0].request.url.params)["min"] == default_min("sprint_speed")
    parts = list(lake.processed_dir("statcast", "leaderboard_sprint_speed").rglob("*.parquet"))
    assert [p.parent.name for p in parts] == ["season=2024"]
    assert extractor.raw.verify(
        "statcast", "leaderboard_sprint_speed", "sprint_speed_2024.csv", 2024
    )
    raw_entry = lake.dataset_manifest(
        "statcast", "leaderboard_sprint_speed", "raw", 2024
    ).get_chunk("sprint_speed_2024.csv")
    assert (stored_fingerprint(raw_entry) or Fingerprint("none", "")).kind == "content_sha256"
    # past seasons are immutable: a second call never touches the network
    respx.get(f"{SAVANT_BASE}/sprint_speed").mock(return_value=httpx.Response(500))
    again = extractor.get_leaderboard("sprint_speed", year=2024)
    assert again.schema == LEADERBOARD_SCHEMAS["sprint_speed"] and again.num_rows == 4


@respx.mock
def test_overrides_return_data_but_never_pollute_the_dataset(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path)
    extractor = StatcastLeaderboardExtractor(cache_config=lake)
    respx.get(f"{SAVANT_BASE}/sprint_speed").mock(
        return_value=httpx.Response(200, content=_fixture("sprint_speed"))
    )
    table = extractor.get_leaderboard("sprint_speed", year=2024, min="q")
    assert table.num_rows == 4
    assert not list(lake.processed_dir("statcast", "leaderboard_sprint_speed").rglob("*.parquet"))


@respx.mock
def test_legacy_type_kwarg_selects_the_variant(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path)
    extractor = StatcastLeaderboardExtractor(cache_config=lake)
    respx.get(f"{SAVANT_BASE}/expected_statistics").mock(
        return_value=httpx.Response(200, content=_fixture("expected_statistics_pitcher"))
    )
    table = extractor.get_leaderboard("expected_statistics", year=2024, type="pitcher")
    assert "xera" in table.column_names and table.num_rows == 4


def test_unsupported_leaderboard_raises_clearly(tmp_path: Path) -> None:
    extractor = StatcastLeaderboardExtractor(cache_config=LakeConfig(home=tmp_path))
    with pytest.raises(NotImplementedError, match="404"):
        extractor.get_leaderboard("catcher_throwing", year=2024)


@respx.mock
def test_html_json_variant_and_flat_snapshot(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = StatcastLeaderboardExtractor(cache_config=lake)
    respx.get(f"{SAVANT_BASE}/statcast-park-factors").mock(
        return_value=httpx.Response(200, content=_fixture("park_factors"))
    )
    park = extractor.get_leaderboard("park_factors", year=2024)
    assert park.num_rows == 4 and park.column("venue_id").null_count == 0
    respx.get(f"{SAVANT_BASE}/abs-challenges").mock(
        return_value=httpx.Response(200, content=_fixture("abs_challenges"))
    )
    abs_table = extractor.get_leaderboard("abs_challenges")
    assert abs_table.num_rows == 4
    flat = list(lake.processed_dir("statcast", "leaderboard_abs_challenges").glob("*.parquet"))
    assert len(flat) == 1 and flat[0].parent.name == "leaderboard_abs_challenges"


@respx.mock
def test_ingest_leaderboard_walks_from_min_year_and_resumes(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2025, 6, 1))
    extractor = StatcastLeaderboardExtractor(cache_config=lake)
    first = min_year("bat_tracking")
    assert first == 2023
    route = respx.get(f"{SAVANT_BASE}/bat-tracking").mock(
        return_value=httpx.Response(200, content=_fixture("bat_tracking"))
    )
    report = extractor.ingest_leaderboard("bat_tracking")
    assert report.seasons == {2023: 4, 2024: 4, 2025: 4}
    assert route.call_count == 3
    # 2023 and 2024 are complete seasons: a second run only revalidates the current one
    second = extractor.ingest_leaderboard("bat_tracking")
    assert second.seasons[2023] is None and second.seasons[2024] is None
    assert extractor.ingest_leaderboard("catcher_throwing").unsupported is not None


@respx.mock
def test_custom_leaderboard_is_adhoc_and_typed_by_inference(tmp_path: Path) -> None:
    extractor = StatcastLeaderboardExtractor(cache_config=LakeConfig(home=tmp_path))
    route = respx.get(f"{SAVANT_BASE}/custom").mock(
        return_value=httpx.Response(
            200, content=b'"player_id","xba","pa"\n1,0.31,500\n2,0.25,400\n'
        )
    )
    table = extractor.custom_leaderboard(2024, selections=["xba", "pa"])
    assert table.schema.field("xba").type == pa.float64()
    assert dict(route.calls[0].request.url.params)["selections"] == "xba,pa"


@respx.mock
def test_game_feed_is_raw_only_cached_when_final_and_validated(tmp_path: Path) -> None:
    from baseballpy.sources.statcast.game_feed import (
        GAME_FEED_URL,
        GameFeedError,
        StatcastGameFeed,
    )

    lake = LakeConfig(home=tmp_path)
    feed = StatcastGameFeed(cache_config=lake)
    body = {"game_status_code": "F", "scoreboard": {"gamePk": 7}, "game_date": "6/23/2024"}
    route = respx.get(GAME_FEED_URL).mock(return_value=httpx.Response(200, json=body))
    assert feed.get(7)["scoreboard"] == {"gamePk": 7}
    assert feed.get(7)["game_status_code"] == "F"
    assert route.call_count == 1, "a final game is read back from raw/"
    assert feed.raw.verify("statcast", "game_feed", "7.json", 2024)
    live = dict(body, game_status_code="I")
    respx.get(GAME_FEED_URL).mock(return_value=httpx.Response(200, json=live))
    assert feed.get(8)["game_status_code"] == "I"
    assert feed.get(8)["game_status_code"] == "I"
    assert route.call_count == 3, "a game still in progress is refetched every time"
    respx.get(GAME_FEED_URL).mock(return_value=httpx.Response(200, json={"oops": 1}))
    with pytest.raises(GameFeedError, match="lacks"):
        feed.get(9)
    respx.get(GAME_FEED_URL).mock(return_value=httpx.Response(200, content=b"<html>"))
    with pytest.raises(GameFeedError, match="not JSON"):
        feed.get(10)


def test_statcast_doc_lists_every_variant_and_unsupported_route() -> None:
    doc = (Path(__file__).parent.parent / "docs" / "sources" / "statcast.md").read_text("utf-8")
    for defn in LEADERBOARDS:
        assert f"`{defn.slug}`" in doc or f"`leaderboard_{defn.slug}`" in doc, defn.slug
        if defn.unsupported:
            assert defn.unsupported in doc


@respx.mock
def test_game_feed_season_ingest_is_resumable(tmp_path: Path) -> None:
    from baseballpy.sources.statcast.game_feed import (
        GAME_FEED_URL,
        MLB_SCHEDULE_URL,
        StatcastGameFeed,
    )

    feed = StatcastGameFeed(cache_config=LakeConfig(home=tmp_path))
    games = [
        {"gamePk": pk, "status": {"abstractGameState": state}}
        for pk, state in ((11, "Final"), (12, "Final"), (13, "Live"))
    ]
    respx.get(MLB_SCHEDULE_URL).mock(
        return_value=httpx.Response(200, json={"dates": [{"games": games}]})
    )
    body = {"game_status_code": "F", "scoreboard": {}, "game_date": "6/23/2024"}
    route = respx.get(GAME_FEED_URL).mock(return_value=httpx.Response(200, json=body))
    first = feed.ingest_season(2024)
    assert (first.games, first.fetched, first.cached, route.call_count) == (2, 2, 0, 2)
    again = feed.ingest_season(2024)
    assert (again.fetched, again.cached, route.call_count) == (0, 2, 2)
    assert feed.ingest_season(2024, max_games=1, refresh=True).fetched == 1


@respx.mock
def test_game_feed_fetches_and_season_ingests_are_audit_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baseballpy.core.audit import AuditConfig, AuditLogger
    from baseballpy.sources.statcast import game_feed as module

    audit = AuditLogger(AuditConfig(base_dir=tmp_path / "audit"))
    monkeypatch.setattr(module, "default_audit_logger", audit)
    feed = module.StatcastGameFeed(cache_config=LakeConfig(home=tmp_path / "lake"))
    body = {"game_status_code": "F", "scoreboard": {"gamePk": 7}, "game_date": "6/23/2024"}
    respx.get(module.GAME_FEED_URL).mock(return_value=httpx.Response(200, json=body))
    respx.get(module.MLB_SCHEDULE_URL).mock(
        return_value=httpx.Response(
            200,
            json={"dates": [{"games": [{"gamePk": 7, "status": {"abstractGameState": "Final"}}]}]},
        )
    )
    feed.ingest_season(2024)
    feed.ingest_season(2024)  # served from the raw store
    events = audit.read_events(source="statcast")
    assert [e.operation for e in events] == [
        "statcast_game_feed",
        "statcast_game_feed_season",
        "statcast_game_feed_season",
    ]
    assert [e.cache_hit for e in events[1:]] == [False, True]
    assert events[0].records_count == 1 and all(e.status == "SUCCESS" for e in events)


@respx.mock
def test_every_raw_file_records_an_upstream_fingerprint(tmp_path: Path) -> None:
    import hashlib

    from baseballpy.core.upstream import CONTENT_SHA256, ETAG, stored_fingerprint
    from baseballpy.sources.statcast.game_feed import GAME_FEED_URL, StatcastGameFeed

    lake = LakeConfig(home=tmp_path)
    feed = StatcastGameFeed(cache_config=lake)
    body = {"game_status_code": "F", "scoreboard": {"gamePk": 7}, "game_date": "6/23/2024"}
    respx.get(GAME_FEED_URL).mock(return_value=httpx.Response(200, json=body))
    feed.get(7)
    entry = lake.dataset_manifest("statcast", "game_feed", "raw", 2024).get_chunk("7.json")
    stored = stored_fingerprint(entry)
    assert stored is not None and stored.kind == CONTENT_SHA256
    assert (
        stored.value
        == hashlib.sha256(feed.raw.get("statcast", "game_feed", "7.json", 2024)).hexdigest()
    )

    respx.get(GAME_FEED_URL).mock(
        return_value=httpx.Response(200, json=body, headers={"ETag": '"abc"'})
    )
    feed.get(7, refresh=True)
    entry = lake.dataset_manifest("statcast", "game_feed", "raw", 2024).get_chunk("7.json")
    fingerprint = stored_fingerprint(entry)
    assert fingerprint is not None and fingerprint.kind == ETAG


@respx.mock
def test_a_leaderboard_written_under_another_schema_is_fetched_again(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = StatcastLeaderboardExtractor(cache_config=lake)
    route = respx.get(f"{SAVANT_BASE}/sprint_speed").mock(
        return_value=httpx.Response(200, content=_fixture("sprint_speed"))
    )
    extractor.get_leaderboard("sprint_speed", year=2024)
    extractor.get_leaderboard("sprint_speed", year=2024)
    assert route.call_count == 1
    manifest = lake.dataset_manifest("statcast", "leaderboard_sprint_speed")
    for key, entry in list(manifest.chunks().items()):
        manifest.put_entry(key, {**entry, "schema_sha256": "0" * 64})
    extractor.get_leaderboard("sprint_speed", year=2024)
    assert route.call_count == 2


@respx.mock
def test_the_data_dictionary_page_is_kept_once_with_a_fingerprint(tmp_path: Path) -> None:
    from baseballpy.sources.statcast.extractor import DOCUMENT_PAGES, StatcastExtractor

    lake = LakeConfig(home=tmp_path)
    extractor = StatcastExtractor(cache_config=lake)
    url = DOCUMENT_PAGES["csv-docs.html"]
    route = respx.get(url).mock(
        return_value=httpx.Response(200, content=b"<html>dictionary</html>")
    )
    assert extractor.keep_documents() == ["csv-docs.html"]
    assert extractor.keep_documents() == []  # already kept: nothing downloaded
    assert route.call_count == 1
    assert (lake.raw_root / "statcast" / "documents" / "csv-docs.html").read_bytes() == (
        b"<html>dictionary</html>"
    )
    entry = lake.dataset_manifest("statcast", "documents", "raw").get_chunk("csv-docs.html")
    assert (stored_fingerprint(entry) or Fingerprint("none", "")).kind == "content_sha256"
    extractor.keep_documents(refresh=True)
    assert route.call_count == 2


def test_the_planner_adds_one_documents_job_per_run() -> None:
    from baseballpy.ingest.types import Selection
    from baseballpy.sources.statcast.adapter import StatcastAdapter

    jobs = StatcastAdapter().plan(Selection(seasons=(2024, 2025)))
    assert [j.task for j in jobs].count("documents") == 1


@respx.mock
def test_table_reaches_every_registered_dataset_by_name(tmp_path: Path) -> None:
    from baseballpy.sources.statcast import access

    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    respx.get(f"{SAVANT_BASE}/sprint_speed").mock(
        return_value=httpx.Response(200, content=_fixture("sprint_speed"))
    )
    table = access.table("leaderboard_sprint_speed", 2024, cache_config=lake)
    assert table.num_rows == 4
    assert {spec.name for spec in datasets_for("statcast")} == set(access.datasets())
    assert {"pitches", "pitches_minors", "leaderboard_sprint_speed"} <= set(access.datasets())
    with pytest.raises(ValueError, match="unknown statcast dataset 'nope'.*pitches"):
        access.table("nope", 2024, cache_config=lake)
