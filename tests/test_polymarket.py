"""Polymarket source: scope, typing, keyset paging, catalog ingest, price windows, adapter, limits."""

import decimal
import gzip
import json
import threading
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from baseballpy.core.config import (
    POLYMARKET_CLOB_HOST,
    POLYMARKET_DATA_HOST,
    POLYMARKET_GAMMA_HOST,
    LakeConfig,
    RateLimitConfig,
)
from baseballpy.core.datasets import get_dataset
from baseballpy.core.http import HttpResult
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.ingest.types import JobStatus, Selection
from baseballpy.sources import catalog
from baseballpy.sources.polymarket.adapter import PolymarketAdapter
from baseballpy.sources.polymarket.endpoints import DATASET_KEYS, MAX_WINDOW_SECONDS
from baseballpy.sources.polymarket.extractor import PolymarketExtractor
from baseballpy.sources.polymarket.ingest import IngestOutcome, ingest, month_of
from baseballpy.sources.polymarket.normalizer import PolymarketNormalizer
from baseballpy.sources.polymarket.price_ingest import (
    MarketRow,
    ingest_day,
    markets_digest,
    plan_days,
    traded_markets,
)
from baseballpy.sources.polymarket.records import (
    outcome_rows,
    price_row,
    price_window,
    snake_keys,
    split_event,
    windows,
)
from baseballpy.sources.polymarket.schema import POLYMARKET_SCHEMAS

TOKEN_YES = "41909998635010155392319593028397525010248198614602609441899154590928041123429"  # noqa: S105 - a public outcome token id, not a secret
TOKEN_NO = "70973335216055436257901503767218568703106620935175766976323885941497560064350"  # noqa: S105 - a public outcome token id, not a secret


def market(market_id: int, start: str, *, closed: bool = True, volume: float = 100.0) -> dict:
    """A market as Gamma sends it (camelCase, lists as JSON text)."""
    return {
        "id": str(market_id),
        "conditionId": f"0xc{market_id}",
        "question": f"Will team {market_id} win?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.505", "0.495"]',
        "clobTokenIds": json.dumps(
            [f"{TOKEN_YES[:-3]}{market_id:03d}", f"{TOKEN_NO[:-3]}{market_id:03d}"]
        ),
        "startDate": start,
        "endDate": "2026-01-20T12:00:00Z",
        "closedTime": "2026-01-20 12:00:00+00" if closed else None,
        "closed": closed,
        "active": True,
        "bestBid": "0.504",
        "volume": "232805.220348",
        "volumeNum": volume,
    }


def event(event_id: int, start: str, markets: list[dict]) -> dict:
    """An event as Gamma sends it, with its markets inside."""
    return {
        "id": str(event_id),
        "slug": f"event-{event_id}",
        "title": f"Event {event_id}",
        "startDate": start,
        "closed": True,
        "tags": [{"id": "1", "label": "MLB"}],
        "markets": markets,
    }


SPORTS = [
    {"sport": "mlbb", "primaryTagId": 1},
    {"sport": "mlb", "primaryTagId": 100381},
]


class FakeHttp:
    """A stand-in for the shared client: /sports, /events/keyset pages and /prices-history."""

    def __init__(self, event_pages: list[list[dict]], sports: list[dict] | None = None) -> None:
        self.event_pages = event_pages
        self.sports = SPORTS if sports is None else sports
        self.history_calls: list[dict[str, str]] = []
        self.event_calls: list[dict[str, str]] = []
        self._lock = threading.Lock()

    def get_sync(self, url: str, *, params: dict[str, str] | None = None, **_: Any) -> HttpResult:
        params = dict(params or {})
        if url.endswith("/sports"):
            body: Any = self.sports
        elif url.endswith("/events/keyset"):
            with self._lock:
                self.event_calls.append(params)
            index = int(params.get("after_cursor", "p0")[1:])
            nxt = f"p{index + 1}" if index + 1 < len(self.event_pages) else None
            body = {"events": self.event_pages[index], "next_cursor": nxt}
        elif url.endswith("/prices-history"):
            with self._lock:
                self.history_calls.append(params)
            first, last = int(params["startTs"]), int(params["endTs"])
            body = {"history": [{"t": first, "p": 0.5}, {"t": last, "p": 0.75}]}
        else:
            raise AssertionError(f"unexpected url {url}")
        return HttpResult(url, 200, json.dumps(body).encode(), None, False, 0.0)


def _catalog_pages() -> list[list[dict]]:
    return [
        [event(1, "2026-01-05T10:00:00Z", [market(11, "2026-01-05T10:00:00Z")])],
        [
            event(
                2,
                "2026-02-10T10:00:00Z",
                [market(21, "2026-02-10T10:00:00Z"), market(22, "2026-02-11T10:00:00Z")],
            ),
            event(1, "2026-01-05T10:00:00Z", [market(11, "2026-01-05T10:00:00Z")]),  # seen again
        ],
    ]


def _run_catalog(tmp_path: Path) -> tuple[LakeConfig, FakeHttp]:
    config = LakeConfig(home=tmp_path)
    fake = FakeHttp(_catalog_pages())
    ingest(config=config, extractor=PolymarketExtractor(config, fake))  # type: ignore[arg-type]
    return config, fake


def test_every_dataset_is_registered_with_a_typed_key_and_prices_are_opt_in() -> None:
    registry = catalog.register_all()
    names = {spec.name for k, spec in registry.items() if k.startswith("polymarket.")}
    assert names == set(DATASET_KEYS)
    for name in names:
        spec = registry[f"polymarket.{name}"]
        assert set(spec.keys) == set(DATASET_KEYS[name]) <= set(spec.schema.names)
        assert spec.schema.names[-1] == "_extras" and spec.partition == "none"
    assert registry["polymarket.prices"].ingest == "opt_in"
    assert registry["polymarket.markets"].ingest == "default"


def test_a_market_is_typed_exactly_and_unknown_keys_are_kept_not_lost() -> None:
    raw = market(11, "2026-01-05T10:00:00Z") | {"aFieldPolymarketAddedTomorrow": "x"}
    row = PolymarketNormalizer().normalize("markets", [raw]).to_pylist()[0]
    assert row["id"] == 11 and row["best_bid"] == decimal.Decimal("0.504")
    assert row["volume"] == decimal.Decimal("232805.220348")
    assert row["start_date"].year == 2026 and row["closed_time"].hour == 12
    assert json.loads(row["outcomes"]) == ["Yes", "No"]
    assert row["_extras"] == '{"a_field_polymarket_added_tomorrow": "x"}'
    assert POLYMARKET_SCHEMAS["markets"].field("closed").type == pa.bool_()


def test_keys_become_snake_case_and_a_collision_is_refused() -> None:
    assert snake_keys({"clobTokenIds": 1, "negRiskMarketID": 2}) == {
        "clob_token_ids": 1,
        "neg_risk_market_id": 2,
    }
    with pytest.raises(ValueError, match="collide"):
        snake_keys({"fooBar": 1, "foo_bar": 2})


def test_outcome_rows_pair_labels_tokens_and_prices_and_tokens_stay_text() -> None:
    rows = outcome_rows(market(11, "2026-01-05T10:00:00Z"))
    assert [(r["outcomeIndex"], r["outcome"], r["price"]) for r in rows] == [
        (0, "Yes", "0.505"),
        (1, "No", "0.495"),
    ]
    typed = PolymarketNormalizer().normalize("outcomes", rows).to_pylist()
    assert typed[0]["token_id"].endswith("011") and len(typed[0]["token_id"]) == 77
    assert typed[0]["price"] == decimal.Decimal("0.5050")


def test_price_windows_are_cut_at_fourteen_days_and_end_a_little_after_the_close() -> None:
    day = 86_400
    pieces = windows(0, 35 * day)
    assert [(a, b) for a, b in pieces] == [
        (0, 14 * day),
        (14 * day, 28 * day),
        (28 * day, 35 * day),
    ]
    assert all(b - a <= MAX_WINDOW_SECONDS for a, b in pieces)
    assert windows(5, 5) == [(5, 5)]
    closed = price_window("2026-01-05T10:00:00Z", "2026-01-20 12:00:00+00", True, 2_000_000_000)
    assert closed is not None and closed[1] - closed[0] == 15 * day + 2 * 3600 + 3600
    still_open = price_window("2026-01-05T10:00:00Z", None, False, 1_768_000_000)
    assert still_open is not None and still_open[1] == 1_768_000_000
    assert price_window(None, None, True, 1) is None
    assert price_row("tok", {"t": 1_767_607_200, "p": 0.5})["t"] == "2026-01-05T10:00:00Z"


def test_the_sport_tag_comes_from_the_sports_list_and_a_missing_sport_is_an_error(
    tmp_path: Path,
) -> None:
    config = LakeConfig(home=tmp_path)
    assert PolymarketExtractor(config, FakeHttp([[]])).sport_tag_id() == 100381  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="no sport 'mlb'"):
        PolymarketExtractor(
            config, FakeHttp([[]], sports=[{"sport": "nfl", "primaryTagId": 9}])
        ).sport_tag_id()  # type: ignore[arg-type]


def test_events_follow_the_keyset_cursor_and_every_raw_page_is_kept_in_one_gzip(
    tmp_path: Path,
) -> None:
    config, fake = _run_catalog(tmp_path)
    assert [c.get("after_cursor") for c in fake.event_calls] == [None, "p1"]
    assert all(c["tag_id"] == "100381" and c["limit"] == "100" for c in fake.event_calls)
    store = RawStore(config)
    assert store.verify("polymarket", "events", "events-all.jsonl.gz")
    lines = gzip.decompress(store.get("polymarket", "events", "events-all.jsonl.gz")).splitlines()
    assert len(lines) == 3, "the sports list and both event pages are kept"
    folder = tmp_path / "raw" / "polymarket" / "events"
    assert [p.name for p in folder.iterdir() if p.name != "_manifest.json"] == [
        "events-all.jsonl.gz"
    ], "no file per request"


def test_catalog_ingest_splits_events_markets_and_outcomes_by_month_without_duplicates(
    tmp_path: Path,
) -> None:
    config, _ = _run_catalog(tmp_path)
    store = ProcessedStore(config)
    events = store.read(get_dataset("polymarket", "events")).to_pylist()
    markets = store.read(get_dataset("polymarket", "markets")).to_pylist()
    outcomes = store.read(get_dataset("polymarket", "outcomes")).to_pylist()
    assert sorted(e["id"] for e in events) == [1, 2], "an event seen on two pages is kept once"
    assert sorted(m["id"] for m in markets) == [11, 21, 22]
    assert {m["event_id"] for m in markets} == {1, 2}
    assert len(outcomes) == 6
    assert sorted(
        p.name for p in config.processed_dir("polymarket", "markets").glob("*.parquet")
    ) == [
        "part-2026-01.parquet",
        "part-2026-02.parquet",
    ]
    assert month_of({"startDate": "2026-03-04T00:00:00Z"}) == "2026-03"
    assert month_of({}) == "undated"
    with pytest.raises(ValueError, match="unknown dataset"):
        ingest(["trades"], config=config, extractor=PolymarketExtractor(config, FakeHttp([[]])))  # type: ignore[arg-type]


def _price_run(
    tmp_path: Path, markets: list[MarketRow], fake: FakeHttp, day: str, **kw: Any
) -> Any:
    config = LakeConfig(home=tmp_path)
    return ingest_day(
        day,
        markets,
        config=config,
        extractor=PolymarketExtractor(config, fake),  # type: ignore[arg-type]
        normalizer=PolymarketNormalizer(),
        clock=lambda: 1_800_000_000,
        **kw,
    )


def _row(
    market_id: int, closed: bool = True, start: str = "2026-01-05T10:00:00+00:00"
) -> MarketRow:
    from datetime import datetime

    return MarketRow(
        market_id=market_id,
        tokens=(f"tok{market_id}a", f"tok{market_id}b"),
        start=datetime.fromisoformat(start),
        end=datetime.fromisoformat("2026-01-20T12:00:00+00:00") if closed else None,
        closed=closed,
    )


def test_price_ingest_asks_each_token_per_window_and_keeps_one_point_per_token_and_time(
    tmp_path: Path,
) -> None:
    fake = FakeHttp([[]])
    result = _price_run(tmp_path, [_row(1), _row(2)], fake, "2026-01-05")
    # 15 days + margins = 2 windows per token, 4 tokens
    assert len(fake.history_calls) == 8
    assert all(c["fidelity"] == "60" for c in fake.history_calls)
    spans = [(int(c["startTs"]), int(c["endTs"])) for c in fake.history_calls]
    assert all(b - a <= MAX_WINDOW_SECONDS for a, b in spans)
    # each window returns its two end points; the shared boundary second is one point
    assert result.rows["prices"] == 4 * 3
    table = ProcessedStore(LakeConfig(home=tmp_path)).read(get_dataset("polymarket", "prices"))
    keys = [(r["token_id"], r["t"]) for r in table.to_pylist()]
    assert len(keys) == len(set(keys))
    assert table.to_pylist()[0]["p"] in (decimal.Decimal("0.5000"), decimal.Decimal("0.7500"))


def test_a_finished_date_is_not_fetched_again_but_an_open_market_is(tmp_path: Path) -> None:
    fake = FakeHttp([[]])
    _price_run(tmp_path, [_row(1)], fake, "2026-01-05")
    calls = len(fake.history_calls)
    again = _price_run(tmp_path, [_row(1)], fake, "2026-01-05")
    assert again.cached and len(fake.history_calls) == calls
    forced = _price_run(tmp_path, [_row(1)], fake, "2026-01-05", force=True)
    assert not forced.cached and len(fake.history_calls) > calls
    other = FakeHttp([[]])
    _price_run(tmp_path, [_row(3, closed=False)], other, "2026-01-05")
    again_open = _price_run(tmp_path, [_row(3, closed=False)], other, "2026-01-05")
    assert not again_open.cached, "an open market can still move"
    assert markets_digest([_row(1)]) != markets_digest([_row(1, closed=False)])


def test_traded_markets_come_from_the_lake_skip_zero_volume_and_plan_newest_first(
    tmp_path: Path,
) -> None:
    config = LakeConfig(home=tmp_path)
    pages = [
        [
            event(1, "2026-01-05T10:00:00Z", [market(11, "2026-01-05T10:00:00Z")]),
            event(2, "2026-02-10T10:00:00Z", [market(21, "2026-02-10T10:00:00Z", volume=0.0)]),
            event(3, "2026-03-01T10:00:00Z", [market(31, "2026-03-01T10:00:00Z")]),
        ]
    ]
    ingest(config=config, extractor=PolymarketExtractor(config, FakeHttp(pages)))  # type: ignore[arg-type]
    rows = traded_markets(ProcessedStore(config))
    assert sorted(r.market_id for r in rows) == [11, 31], "a market nobody traded has no history"
    assert all(len(r.tokens) == 2 and r.tokens[0].endswith(f"{r.market_id:03d}") for r in rows)
    assert plan_days(rows) == ["2026-03-01", "2026-01-05"]


def test_adapter_plans_a_catalog_job_then_one_price_job_per_date_and_runs_them() -> None:
    ran: list[tuple[str, bool]] = []

    class Result:
        rows = {"prices": 7}
        markets = 2
        cached = False

    adapter = PolymarketAdapter(
        loader=lambda datasets: IngestOutcome(rows={"events": 1}, events=1),
        days=lambda: ["2026-03-01", "2026-01-05"],
        day_runner=lambda day, force: (ran.append((day, force)), Result())[1],  # type: ignore[arg-type,return-value]
    )
    jobs = adapter.plan(Selection(datasets=("events", "prices"), seasons=(), limit=None))
    assert [j.task for j in jobs] == ["catalog", "prices", "prices"]
    assert jobs[1].needs == (jobs[0].job_id,) and jobs[1].param("day") == "2026-03-01"
    newest = adapter.plan(Selection(datasets=("prices",), seasons=(), limit=1))
    assert [j.param("day") for j in newest] == ["2026-03-01"] and not newest[0].needs
    result = adapter.run(jobs[1], refresh=True)
    assert (
        result.status is JobStatus.COMPLETED and result.rows == 7 and ran == [("2026-03-01", True)]
    )
    assert adapter.run(jobs[0]).rows == 1
    with pytest.raises(ValueError, match="unknown dataset"):
        adapter.plan(Selection(datasets=("trades",), seasons=(), limit=None))
    assert adapter.all_seasons() == []


def test_hosts_have_documented_rate_and_in_flight_defaults() -> None:
    config = RateLimitConfig()
    assert config.host_rates[POLYMARKET_GAMMA_HOST] == 24.0
    assert config.host_rates[POLYMARKET_CLOB_HOST] == 80.0
    assert config.host_rates[POLYMARKET_DATA_HOST] == 16.0
    assert (
        config.host_concurrency[POLYMARKET_CLOB_HOST]
        > config.host_concurrency[POLYMARKET_GAMMA_HOST]
    )


def test_split_event_keeps_the_event_free_of_its_markets() -> None:
    plain, markets = split_event(
        event(1, "2026-01-05T10:00:00Z", [market(11, "2026-01-05T10:00:00Z")])
    )
    assert "markets" not in plain and markets[0]["eventId"] == "1"


def test_a_fresh_polymarket_download_has_the_lake_shape(tmp_path: Path) -> None:
    """The shared lake contract (layout, raw integrity, typed views) holds after a download."""
    from lake_contract import assert_lake_contract

    config, _ = _run_catalog(tmp_path)
    views = assert_lake_contract(config, ["polymarket"])
    assert views.get("polymarket_markets") == 3
