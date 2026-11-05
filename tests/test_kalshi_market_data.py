"""Kalshi trades and candlesticks: routing, windows, de-duplication, raw logs, resumable days."""

import decimal
import gzip
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.http import HttpResult
from baseballpy.core.stores import ProcessedStore, RawStore, portable_name_problem
from baseballpy.ingest.types import Selection, make_job
from baseballpy.sources import catalog
from baseballpy.sources.kalshi.adapter import KalshiAdapter
from baseballpy.sources.kalshi.day_ingest import (
    UNDATED,
    DayOutcome,
    day_of,
    ingest_day,
    markets_digest,
    plan_days,
    traded_markets,
)
from baseballpy.sources.kalshi.market_data import (
    MAX_CANDLE_PERIODS,
    KalshiMarketData,
    MarketRow,
    RawLog,
    flatten_candle,
)
from baseballpy.sources.kalshi.normalizer import KalshiNormalizer

CUTOFF = datetime(2026, 9, 6, tzinfo=UTC)
NOW = datetime(2026, 11, 6, tzinfo=UTC)


def _t(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def _market(
    ticker: str,
    open_time: str | None,
    end: str | None,
    status: str = "finalized",
) -> MarketRow:
    return MarketRow(
        ticker=ticker,
        status=status,
        open_time=_t(open_time) if open_time else None,
        close_time=_t(end) if end else None,
        settlement_ts=_t(end) if end else None,
    )


OLD = _market("OLD-1", "2025-04-15T12:00:00", "2025-04-16T03:00:00")
NEW = _market("NEW-1", "2026-10-27T12:00:00", "2026-10-28T03:00:00")
SPAN = _market("SPAN-1", "2026-08-30T12:00:00", "2026-09-10T03:00:00")


def _trade(trade_id: str, price: str = "0.4400") -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "ticker": "X",
        "created_time": "2026-10-28T01:00:00.123456Z",
        "yes_price_dollars": price,
        "no_price_dollars": "0.5600",
        "count_fp": "12.50",
        "taker_side": "yes",
        "taker_outcome_side": "yes",
        "taker_book_side": "ask",
        "is_block_trade": False,
    }


def _candle(end_ts: int, price: str = "0.4400") -> dict[str, Any]:
    return {
        "end_period_ts": end_ts,
        "price": {"open": price, "high": price, "low": price, "close": price, "mean": None},
        "yes_bid": {"open": "0.4000", "close": "0.4200"},
        "yes_ask": {"open": "0.4500", "close": "0.4600"},
        "volume": "21.00",
        "open_interest": "417.00",
    }


class FakeKalshi:
    """A stand-in for the shared client that serves the Kalshi routes from dictionaries."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.trade_pages: dict[tuple[str, str], list[list[dict[str, Any]]]] = {}
        self.archived_candles: dict[str, list[dict[str, Any]]] = {}
        self.live_candles: dict[str, list[dict[str, Any]]] = {}

    def get_sync(self, url: str, *, params: dict[str, str] | None = None, **_: Any) -> HttpResult:
        params = dict(params or {})
        path = url.split("/trade-api/v2", 1)[1]
        self.calls.append((path, params))
        if path == "/historical/cutoff":
            body: dict[str, Any] = {
                "trades_created_ts": CUTOFF.isoformat().replace("+00:00", "Z"),
                "market_settled_ts": CUTOFF.isoformat().replace("+00:00", "Z"),
            }
        elif path in ("/markets/trades", "/historical/trades"):
            pages = self.trade_pages.get((path, params["ticker"]), [[]])
            index = int(params.get("cursor") or 0)
            more = index + 1 < len(pages)
            body = {"trades": pages[index], "cursor": str(index + 1) if more else ""}
        elif m := re.fullmatch(r"/historical/markets/(.+)/candlesticks", path):
            body = {"ticker": m[1], "candlesticks": self.archived_candles.get(m[1], [])}
        elif path == "/markets/candlesticks":
            body = {
                "markets": [
                    {"market_ticker": t, "candlesticks": self.live_candles.get(t, [])}
                    for t in params["market_tickers"].split(",")
                ]
            }
        else:
            raise AssertionError(f"unexpected route {path}")
        return HttpResult(url, 200, json.dumps(body).encode(), None, False, 0.0)

    def routes(self) -> list[str]:
        return [p for p, _ in self.calls if p != "/historical/cutoff"]


def _data(fake: FakeKalshi) -> KalshiMarketData:
    return KalshiMarketData(fake)  # type: ignore[arg-type]


def test_a_candle_is_flattened_with_every_nested_key_and_an_iso_time() -> None:
    row = flatten_candle("T", _candle(1_744_819_200))
    assert row["ticker"] == "T"
    assert row["end_period_ts"] == "2025-04-16T16:00:00+00:00"
    assert (row["price_open"], row["price_mean"]) == ("0.4400", None)
    assert (row["yes_bid_close"], row["yes_ask_open"]) == ("0.4200", "0.4500")
    assert (row["volume"], row["open_interest"]) == ("21.00", "417.00")


def test_candle_windows_cover_the_life_and_stay_under_the_five_thousand_period_cap() -> None:
    start, end = 1_700_000_000, 1_700_000_000 + 400 * 86400  # 9,600 hours: the API refuses one call
    for markets in (1, 100):
        windows = KalshiMarketData._windows(start, end, markets)
        assert windows[0][0] == start and windows[-1][1] == end
        assert all(a < b for a, b in windows)
        assert all(windows[i][1] == windows[i + 1][0] for i in range(len(windows) - 1))
        assert all((b - a) // 3600 * markets <= MAX_CANDLE_PERIODS for a, b in windows)
    assert len(KalshiMarketData._windows(start, start + 3600, 1)) == 1


def test_a_market_takes_the_archive_the_live_route_or_both_from_the_cutoff() -> None:
    data = _data(FakeKalshi())
    assert [e.name for e in data.trade_routes(OLD)] == ["trades_historical"]
    assert [e.name for e in data.trade_routes(NEW)] == ["trades"]
    assert [e.name for e in data.trade_routes(SPAN)] == ["trades_historical", "trades"]
    assert data.candle_route_is_archived(OLD)
    assert not data.candle_route_is_archived(NEW)
    assert not data.candle_route_is_archived(_market("OPEN-1", "2026-10-30T00:00:00", None))


def test_trades_follow_the_cursor_and_a_trade_on_both_routes_counts_once() -> None:
    fake = FakeKalshi()
    fake.trade_pages[("/historical/trades", "SPAN-1")] = [[_trade("a"), _trade("b")], [_trade("c")]]
    fake.trade_pages[("/markets/trades", "SPAN-1")] = [[_trade("c"), _trade("d")]]
    raw = RawLog()
    trades = _data(fake).trades(SPAN, raw)
    assert sorted(t["trade_id"] for t in trades) == ["a", "b", "c", "d"]
    assert len(raw) == 3, "every page answered is kept"
    assert fake.routes() == ["/historical/trades"] * 2 + ["/markets/trades"]


def test_the_raw_log_keeps_each_body_verbatim_and_is_the_same_whatever_the_thread_order() -> None:
    bodies = [(f"T{i}", json.dumps({"trades": [_trade(str(i))]}).encode()) for i in range(5)]
    one, two = RawLog(), RawLog()
    for i, (ticker, body) in enumerate(bodies):
        one.add("trades", ticker, i, body)
    for i, (ticker, body) in reversed(list(enumerate(bodies))):
        two.add("trades", ticker, i, body)
    assert one.to_bytes() == two.to_bytes()
    lines = gzip.decompress(one.to_bytes()).decode().splitlines()
    assert sorted(json.loads(line)["body"] for line in lines) == sorted(
        b.decode() for _, b in bodies
    )


def test_archived_candles_of_a_long_market_are_fetched_in_windows_and_joined_once() -> None:
    long_market = _market(
        "LONG-1", "2025-02-13T15:00:00", "2025-09-24T15:00:00"
    )  # about 5,350 hours
    fake = FakeKalshi()
    ticks = [1_739_000_000 + 3600 * i for i in range(10)]
    fake.archived_candles["LONG-1"] = [
        _candle(t) for t in ticks
    ]  # every window returns the same ten
    rows = _data(fake).candles_archived(long_market, RawLog(), NOW)
    assert len(fake.routes()) >= 2, "more than 4,500 hours needs more than one call"
    assert len(rows) == 10, "a candle seen in two windows is kept once"


def test_live_candles_go_up_to_a_hundred_markets_to_a_call() -> None:
    fake = FakeKalshi()
    markets = [
        _market(f"L-{i:03d}", "2026-10-27T12:00:00", "2026-10-28T03:00:00") for i in range(100)
    ]
    for m in markets:
        fake.live_candles[m.ticker] = [_candle(1_793_000_000)]
    rows = _data(fake).candles_live(markets, RawLog(), NOW)
    assert len(rows) == 100 and {r["ticker"] for r in rows} == {m.ticker for m in markets}
    with pytest.raises(ValueError, match="at most 100"):
        _data(fake).candles_live([*markets, OLD], RawLog(), NOW)


def test_a_market_belongs_to_its_utc_open_date_and_dates_run_newest_first() -> None:
    assert day_of(NEW) == "2026-10-27"
    assert day_of(_market("N", "2026-01-01T00:00:00", None)) == "2026-01-01"
    far = _market("F", "2026-02-01T00:00:00", "2032-11-01T00:00:00")
    assert day_of(far) == "2026-02-01", "a far-future close date must not decide the day"
    assert day_of(_market("U", None, None)) == UNDATED
    days = plan_days([OLD, NEW, SPAN, _market("U", None, None)])
    assert days == ["2026-10-27", "2026-08-30", "2025-04-15", UNDATED]
    assert all(portable_name_problem(d) is None for d in days)


def _lake(tmp_path: Path) -> LakeConfig:
    return LakeConfig(base_dir=tmp_path)


def _ingest(
    config: LakeConfig,
    fake: FakeKalshi,
    day: str,
    markets: list[MarketRow],
    datasets: tuple[str, ...] = ("trades", "candlesticks"),
    force: bool = False,
) -> DayOutcome:
    catalog.register_all()
    return ingest_day(
        day,
        datasets,
        markets,
        config=config,
        data=_data(fake),
        normalizer=KalshiNormalizer(),
        workers=3,
        force=force,
        clock=lambda: NOW,
    )


def _fake_with_data() -> FakeKalshi:
    fake = FakeKalshi()
    fake.trade_pages[("/markets/trades", "NEW-1")] = [[_trade("n1"), _trade("n2", "0.5100")]]
    fake.live_candles["NEW-1"] = [_candle(1_793_000_000), _candle(1_793_003_600, "0.5000")]
    return fake


def test_a_day_is_typed_stored_with_its_raw_answers_and_left_alone_when_unchanged(
    tmp_path: Path,
) -> None:
    config = _lake(tmp_path)
    fake = _fake_with_data()
    first = _ingest(config, fake, "2026-10-27", [NEW])
    assert (first.markets, first.rows, first.cached) == (1, {"trades": 2, "candlesticks": 2}, False)
    store = ProcessedStore(config)
    trades = store.read(get_dataset("kalshi", "trades")).to_pylist()
    assert {t["trade_id"] for t in trades} == {"n1", "n2"}
    assert trades[0]["count_fp"] == decimal.Decimal("12.50")
    assert trades[0]["created_time"].microsecond == 123456
    candles = store.read(get_dataset("kalshi", "candlesticks")).to_pylist()
    assert {c["price_open"] for c in candles} == {
        decimal.Decimal("0.4400"),
        decimal.Decimal("0.5000"),
    }
    assert [p.name for p in store.files(get_dataset("kalshi", "trades"))] == [
        "part-2026-10-27.parquet"
    ]
    raw = RawStore(config)
    assert raw.verify("kalshi", "trades", "trades-2026-10-27.jsonl.gz")
    assert raw.verify("kalshi", "candlesticks", "candlesticks-2026-10-27.jsonl.gz")
    calls = len(fake.calls)

    again = _ingest(config, fake, "2026-10-27", [NEW])
    assert again.cached and again.rows == {"trades": 2, "candlesticks": 2}
    assert len(fake.calls) == calls, "an unchanged, final day makes no request"

    changed = _ingest(
        config,
        fake,
        "2026-10-27",
        [NEW, _market("NEW-2", "2026-10-27T12:00:00", "2026-10-28T04:00:00")],
    )
    assert not changed.cached, "a new market on the day means the day is fetched again"
    forced = _ingest(config, fake, "2026-10-27", [NEW], force=True)
    assert not forced.cached


def test_a_day_with_a_market_that_can_still_trade_is_fetched_on_every_run(tmp_path: Path) -> None:
    config = _lake(tmp_path)
    fake = _fake_with_data()
    active = _market("NEW-1", "2026-10-27T12:00:00", "2026-10-28T03:00:00", status="active")
    _ingest(config, fake, "2026-10-27", [active], datasets=("trades",))
    calls = len(fake.calls)
    again = _ingest(config, fake, "2026-10-27", [active], datasets=("trades",))
    assert not again.cached and len(fake.calls) > calls


def test_an_empty_day_and_a_wrong_dataset_are_handled_plainly(tmp_path: Path) -> None:
    config = _lake(tmp_path)
    assert _ingest(config, FakeKalshi(), "2020-01-01", [NEW]).markets == 0
    with pytest.raises(ValueError, match="unknown market dataset"):
        _ingest(config, FakeKalshi(), "2026-10-27", [NEW], datasets=("series",))


def test_only_markets_that_traded_are_planned(tmp_path: Path) -> None:
    config = _lake(tmp_path)
    store = ProcessedStore(config)
    catalog.register_all()
    spec = get_dataset("kalshi", "markets")
    rows = [
        {"ticker": "A", "status": "finalized", "volume_fp": "10.00", "open_time": "2026-10-27T00:00:00Z",
         "close_time": "2026-10-28T00:00:00Z", "settlement_ts": "2026-10-28T00:00:00Z"},
        {"ticker": "B", "status": "finalized", "volume_fp": "0.00", "open_time": "2026-10-27T00:00:00Z",
         "close_time": "2026-10-28T00:00:00Z", "settlement_ts": "2026-10-28T00:00:00Z"},
    ]  # fmt: skip
    store.put(spec, KalshiNormalizer().normalize("markets", rows), chunk_id="KXMLBGAME")
    assert [m.ticker for m in traded_markets(store)] == ["A"]
    empty = traded_markets(ProcessedStore(_lake(tmp_path / "other")))
    assert empty == []


def test_the_digest_changes_when_a_market_is_added_or_settles() -> None:
    base = markets_digest([OLD, NEW])
    assert base == markets_digest([NEW, OLD]), "order does not matter"
    assert base != markets_digest([OLD])
    assert base != markets_digest(
        [OLD, _market("NEW-1", "2026-10-27T12:00:00", "2026-10-28T03:00:00", "closed")]
    )


def test_the_adapter_plans_one_job_per_day_newest_first_after_the_catalog() -> None:
    ran: list[tuple[str, list[str], bool]] = []

    def runner(day: str, datasets: Any, force: bool) -> DayOutcome:
        ran.append((day, list(datasets), force))
        return DayOutcome(day=day, markets=3, rows={"trades": 7}, cached=force)

    adapter = KalshiAdapter(
        days=lambda: ["2026-10-27", "2026-10-27", "2026-10-26"], day_runner=runner
    )
    jobs = adapter.plan(Selection(datasets=("trades", "markets")))
    assert [j.job_id for j in jobs] == [
        "kalshi:catalog:datasets=markets",
        "kalshi:market_data:datasets=trades:day=2026-10-27",
        "kalshi:market_data:datasets=trades:day=2026-10-27",
        "kalshi:market_data:datasets=trades:day=2026-10-26",
    ]
    assert all(j.needs == (jobs[0].job_id,) for j in jobs[1:])
    only = adapter.plan(Selection(datasets=("trades", "candlesticks"), limit=2))
    assert [j.param("day") for j in only] == ["2026-10-27", "2026-10-27"]
    assert only[0].param("datasets") == "trades,candlesticks" and only[0].needs == ()
    result = adapter.run(only[0], refresh=True)
    assert (result.rows, result.cache_hit) == (7, True)
    assert ran == [("2026-10-27", ["trades", "candlesticks"], True)]
    default = adapter.plan(Selection())
    assert [j.task for j in default] == ["catalog"], "the big datasets are opt-in"


def test_the_adapter_refuses_unknown_names_and_an_empty_catalog() -> None:
    adapter = KalshiAdapter(days=lambda: [])
    with pytest.raises(ValueError, match="unknown dataset"):
        adapter.plan(Selection(datasets=("nope",)))
    with pytest.raises(ValueError, match="ingest kalshi"):
        adapter.plan(Selection(datasets=("trades",)))
    with pytest.raises(ValueError, match="unknown task"):
        adapter.run(make_job("kalshi", "nope"))


def test_the_new_datasets_are_registered_opt_in_with_exact_types() -> None:
    registry = catalog.register_all()
    trades, candles = registry["kalshi.trades"], registry["kalshi.candlesticks"]
    assert trades.ingest == candles.ingest == "opt_in"
    assert trades.keys == ("trade_id",) and candles.keys == ("ticker", "end_period_ts")
    assert trades.schema.field("yes_price_dollars").type == pa.decimal128(9, 4)
    assert trades.schema.field("count_fp").type == pa.decimal128(18, 2)
    assert candles.schema.field("price_open").type == pa.decimal128(9, 4)
    assert candles.schema.field("end_period_ts").type == pa.timestamp("us", tz="UTC")
    assert registry["kalshi.series"].ingest == "default"
    assert datetime.now(UTC) - timedelta(days=0) > CUTOFF
