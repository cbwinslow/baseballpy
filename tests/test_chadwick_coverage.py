"""Chadwick coverage: header-based schemas, tree discovery, auxiliary datasets, auth, caching."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from baseballpy.core import schema_tools
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.datasets import datasets_for, get_dataset
from baseballpy.core.http import HttpClient
from baseballpy.core.sources_lock import get_source_ref
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.sources import catalog
from baseballpy.sources.chadwick.extractor import HEX_SHARDS, ChadwickExtractor
from baseballpy.sources.chadwick.ingest import _PARSERS, dataset_names, ingest
from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer
from baseballpy.sources.chadwick.register import ChadwickRegister
from baseballpy.sources.chadwick.schema import CHADWICK_PRIMARY_KEYS, CHADWICK_SCHEMAS

FIX = Path(__file__).parent / "fixtures" / "chadwick"
API = "https://api.github.com/repos/chadwickbureau/register/git/trees"


def _rates() -> RateLimitConfig:
    return RateLimitConfig(
        default_requests_per_second=1000,
        host_rates={"raw.githubusercontent.com": 1000, "api.github.com": 1000},
        max_retries=0,
    )


def _tree(files: list[str], ref: str | None = None, status: int = 200) -> respx.Route:
    ref = ref or get_source_ref("chadwick_register").ref
    return respx.get(f"{API}/{ref}?recursive=1").mock(
        return_value=httpx.Response(
            status,
            json={
                "truncated": False,
                "tree": [
                    {"path": f"data/{n}", "type": "blob", "size": 1, "sha": "x"} for n in files
                ],
            },
        )
    )


def _serve(names: list[str], bodies: dict[str, bytes] | None = None) -> None:
    base = f"https://raw.githubusercontent.com/chadwickbureau/register/{get_source_ref('chadwick_register').ref}/data"
    bodies = bodies or {}
    for name in names:
        respx.get(f"{base}/{name}").mock(
            return_value=httpx.Response(200, content=bodies.get(name, b"key_person\nx\n"))
        )


def _extractor(tmp_path: Path) -> tuple[ChadwickExtractor, HttpClient]:
    http = HttpClient(_rates(), http2=False)
    ext = ChadwickExtractor(
        cache_config=LakeConfig(home=tmp_path), rate_limit_config=_rates(), http=http
    )
    return ext, http


def test_real_header_register_fixture_maps_all_40_columns() -> None:
    table = ChadwickNormalizer().normalize((FIX / "people_real_header_sample.csv").read_bytes())
    assert table.schema.equals(CHADWICK_SCHEMAS["register"])
    assert len(table.schema.names) == 41  # 40 upstream columns + _extras
    assert "pro_managed_first" in table.column_names and "mlb_umpired_last" in table.column_names
    assert table["_extras"].null_count == table.num_rows


@pytest.mark.parametrize(
    ("dataset", "fixture", "method"),
    [
        ("register_names", "names_sample.csv", "normalize_names"),
        ("register_links", "links_sample.csv", "normalize_links"),
        ("register_countries", "countries_sample.csv", "normalize_countries"),
    ],
)
def test_auxiliary_fixtures_match_their_real_schema(
    dataset: str, fixture: str, method: str
) -> None:
    table = getattr(ChadwickNormalizer(), method)((FIX / fixture).read_bytes())
    assert table.schema.equals(CHADWICK_SCHEMAS[dataset])
    assert table.num_rows >= 5 and table["_extras"].null_count == table.num_rows
    assert set(CHADWICK_PRIMARY_KEYS[dataset]) <= set(table.column_names)


def test_links_use_the_real_source_and_value_columns() -> None:
    table = ChadwickNormalizer().normalize_links((FIX / "links_sample.csv").read_bytes())
    assert table.column_names[:3] == ["key_person", "source", "value"]
    assert table["source"].to_pylist()[0] == "tsncards" and table["value"].to_pylist()[0] == "12229"


def test_namibia_iso_code_na_is_data_not_null() -> None:
    table = ChadwickNormalizer().normalize_countries((FIX / "countries_sample.csv").read_bytes())
    assert "NA" in table["key_iso_alpha2"].to_pylist()
    assert table["key_iso_alpha2"].null_count == 0


def test_unknown_register_column_goes_to_extras_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    schema_tools.reset_drift_warnings()
    raw = b"key_person,key_mlbam,shiny_new\nabc,1,hello\n"
    with caplog.at_level("WARNING"):
        first = ChadwickNormalizer().normalize(raw)
        ChadwickNormalizer().normalize(raw)
    assert json.loads(first["_extras"][0].as_py()) == {"shiny_new": "hello"}
    assert first["key_mlbam"].to_pylist() == [1] and first["name_last"].to_pylist() == [None]
    assert len([r for r in caplog.records if "schema_drift" in r.getMessage()]) == 1


def test_four_datasets_are_registered() -> None:
    catalog.register_all()
    assert {d.name for d in datasets_for("chadwick")} == {
        "register",
        "register_names",
        "register_links",
        "register_countries",
    }
    assert get_dataset("chadwick", "register_links").view == "chadwick_register_links"


@respx.mock
def test_discovery_picks_up_countries_and_warns_about_uncovered_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _tree([*HEX_SHARDS, "names.csv", "links.csv", "countries.csv", "mystery.csv"])
    ext, http = _extractor(tmp_path)
    try:
        with caplog.at_level("WARNING"):
            files = ext.discover_files()
    finally:
        http.close()
    assert files[:16] == HEX_SHARDS and files[16:] == ["countries.csv", "links.csv", "names.csv"]
    assert any("mystery.csv" in r.getMessage() for r in caplog.records)


@respx.mock
def test_missing_shard_in_tree_is_a_hard_error(tmp_path: Path) -> None:
    _tree([s for s in HEX_SHARDS if s != "people-7.csv"] + ["names.csv"])
    ext, http = _extractor(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="people-7.csv"):
            ext.extract(refresh=True)
    finally:
        http.close()
    assert not ext.manifest.is_completed("commit_sha")


@respx.mock
def test_tree_failure_falls_back_to_known_files_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _tree([], status=403)
    ext, http = _extractor(tmp_path)
    try:
        with caplog.at_level("WARNING"):
            files = ext.discover_files()
    finally:
        http.close()
    assert "countries.csv" in files and len(files) == 19
    assert any("could not discover" in r.getMessage() for r in caplog.records)


@respx.mock
def test_tree_listing_is_cached_in_http_cache_and_token_is_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "s3cret")
    route = _tree([*HEX_SHARDS, "names.csv"])
    ext, http = _extractor(tmp_path)
    try:
        ext.discover_files()
        ext.discover_files()  # pinned ref: served from cache/http, no second call
    finally:
        http.close()
    assert route.call_count == 1
    assert route.calls[0].request.headers["authorization"] == "Bearer s3cret"
    cached = list((tmp_path / "cache" / "http" / "github-tree").glob("*.json"))
    assert len(cached) == 1 and "chadwickbureau__register@" in cached[0].name


@respx.mock
def test_load_persists_all_four_datasets_and_names_feed_alias_search(tmp_path: Path) -> None:
    names = [*HEX_SHARDS, "names.csv", "links.csv", "countries.csv"]
    _tree(names)
    people = (FIX / "people_real_header_sample.csv").read_bytes()
    bodies = {s: people for s in HEX_SHARDS}
    bodies["names.csv"] = (FIX / "names_sample.csv").read_bytes()
    bodies["links.csv"] = (FIX / "links_sample.csv").read_bytes()
    bodies["countries.csv"] = (FIX / "countries_sample.csv").read_bytes()
    _serve(names, bodies)
    cfg = LakeConfig(home=tmp_path)
    register = ChadwickRegister.load(cache_config=cfg)
    catalog.register_all()
    store = ProcessedStore(cfg)
    for name in ("register", "register_names", "register_links", "register_countries"):
        assert store.row_count(get_dataset("chadwick", name)) > 0, name
    links = store.read(get_dataset("chadwick", "register_links"))
    assert links["source"].to_pylist()[0] == "tsncards"
    assert len(register) == 16 * 4
    entry = cfg.dataset_manifest("chadwick", "register").get_chunk("data")
    assert entry is not None and entry["source_ref"] == get_source_ref("chadwick_register").ref


def _serve_everything() -> None:
    names = [*HEX_SHARDS, "names.csv", "links.csv", "countries.csv"]
    _tree(names)
    people = (FIX / "people_real_header_sample.csv").read_bytes()
    bodies = {s: people for s in HEX_SHARDS}
    bodies["names.csv"] = (FIX / "names_sample.csv").read_bytes()
    bodies["links.csv"] = (FIX / "links_sample.csv").read_bytes()
    bodies["countries.csv"] = (FIX / "countries_sample.csv").read_bytes()
    _serve(names, bodies)


def test_ingest_has_a_parser_for_exactly_the_registered_datasets() -> None:
    assert set(_PARSERS) == set(dataset_names())


@respx.mock
def test_ingest_stores_all_datasets_without_building_the_lookup_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: ChadwickRegister, *args: object, **kwargs: object) -> None:
        raise AssertionError("ingest must not construct a ChadwickRegister")

    monkeypatch.setattr(ChadwickRegister, "__init__", boom)
    _serve_everything()
    cfg = LakeConfig(home=tmp_path)
    outcome = ingest(config=cfg)
    assert set(outcome.rows) == set(dataset_names())
    assert all(rows > 0 for rows in outcome.rows.values())
    store = ProcessedStore(cfg)
    for name, rows in outcome.rows.items():
        assert store.row_count(get_dataset("chadwick", name)) == rows


@respx.mock
def test_ingest_subset_reuses_the_cache_and_unknown_names_fail(tmp_path: Path) -> None:
    _serve_everything()
    cfg = LakeConfig(home=tmp_path)
    first = ingest(["register_names"], config=cfg)
    assert list(first.rows) == ["register_names"] and set(first.tables) == {"register_names"}
    requests_after_first = len(respx.calls)
    again = ingest(["register_names"], config=cfg)
    assert again.rows == first.rows and again.tables == {}
    assert len(respx.calls) == requests_after_first  # nothing downloaded the second time
    with pytest.raises(ValueError, match="unknown dataset"):
        ingest(["nope"], config=cfg)


@respx.mock
def test_upstream_readme_is_kept_with_its_sha256_when_the_tree_lists_it(tmp_path: Path) -> None:
    ref = get_source_ref("chadwick_register").ref
    respx.get(f"{API}/{ref}?recursive=1").mock(
        return_value=httpx.Response(
            200,
            json={
                "truncated": False,
                "tree": [
                    {"path": "README.md", "type": "blob", "size": 8, "sha": "r"},
                    *(
                        {"path": f"data/{n}", "type": "blob", "size": 1, "sha": "x"}
                        for n in HEX_SHARDS
                    ),
                ],
            },
        )
    )
    _serve(list(HEX_SHARDS))
    readme = b"# Chadwick Baseball Bureau Persons Register\n"
    respx.get(f"https://raw.githubusercontent.com/chadwickbureau/register/{ref}/README.md").mock(
        return_value=httpx.Response(200, content=readme)
    )
    ext, _ = _extractor(tmp_path)
    ext.extract()
    raw = RawStore(LakeConfig(home=tmp_path))
    assert raw.get("chadwick", "register", "README.md") == readme
    assert raw.verify("chadwick", "register", "README.md")
    calls = len(respx.calls)
    ext.extract()  # cached: the README is present, so nothing is downloaded again
    assert len(respx.calls) == calls
