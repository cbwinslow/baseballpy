"""The count rules of Kalshi and Polymarket raw pages (``sources/page_counts.py``, ``core/rawpages.py``)."""

import gzip
import json
from pathlib import Path

from baseballpy.core.config import LakeConfig
from baseballpy.core.rawpages import distinct_tuples, tuples_counter
from baseballpy.sources import page_counts


def _write_pages(
    config: LakeConfig, source: str, dataset: str, pages: list[tuple[str, dict]]
) -> None:
    """One ``*.jsonl.gz`` raw log: one line per page, the page text in ``body`` (the shared RawLog shape)."""
    folder = config.raw_dir(source, dataset)
    folder.mkdir(parents=True, exist_ok=True)
    with gzip.open(folder / "pages-2026-01-01.jsonl.gz", "wt", encoding="utf-8") as handle:
        for ticker, body in pages:
            line = {"route": dataset, "ticker": ticker, "page": 0, "body": json.dumps(body)}
            handle.write(json.dumps(line) + "\n")


def test_kalshi_candlesticks_count_both_page_shapes_and_a_repeated_candle_once(
    tmp_path: Path,
) -> None:
    config = LakeConfig(home=tmp_path)
    single = {"ticker": "A", "candlesticks": [{"end_period_ts": 1}, {"end_period_ts": 2}]}
    batch = {
        "markets": [
            {"market_ticker": "B", "candlesticks": [{"end_period_ts": 1}]},
            {"market_ticker": "A", "candlesticks": [{"end_period_ts": 2}, {"end_period_ts": 3}]},
        ]
    }
    _write_pages(config, "kalshi", "candlesticks", [("A", single), ("batch", batch)])
    count = tuples_counter("kalshi", "candlesticks", page_counts.kalshi_candlestick_keys)
    assert count(config, 0) == 4, (
        "(A,1) (A,2) (B,1) (A,3): the candle (A,2) on two pages is one row"
    )


def test_polymarket_prices_are_keyed_by_the_request_token_and_the_time(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    page = {"history": [{"t": 10, "p": 0.5}, {"t": 11, "p": 0.6}]}
    _write_pages(config, "polymarket", "prices", [("tok1", page), ("tok2", page), ("tok1", page)])
    got = distinct_tuples(config, ("polymarket", "prices"), page_counts.polymarket_price_keys)
    assert got == 4, "two tokens with two times each; the repeated page adds nothing"


def test_polymarket_outcomes_come_from_the_outcome_list_of_each_market(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    events = {
        "events": [
            {
                "markets": [
                    {"id": 1, "outcomes": '["Yes","No"]'},
                    {"id": 2, "outcomes": ["A", "B", "C"]},
                ]
            },
            {"markets": [{"id": 1, "outcomes": '["Yes","No"]'}, {"id": 3, "outcomes": "not json"}]},
        ]
    }
    _write_pages(config, "polymarket", "events", [("e", events)])
    got = distinct_tuples(config, ("polymarket", "events"), page_counts.polymarket_outcome_keys)
    assert got == 5, (
        "market 1 twice is one (2), market 2 has three, a market with no readable list has none"
    )


def test_a_missing_raw_folder_counts_zero(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    assert distinct_tuples(config, ("kalshi", "nothing"), page_counts.kalshi_candlestick_keys) == 0
