"""Kalshi source: scope, typing, paging, threaded catalog ingest, adapter and rate defaults."""

import decimal
import json
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from baseballpy.core.config import KALSHI_HOST, LakeConfig, RateLimitConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.http import HttpResult
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.ingest.types import JobStatus, Selection
from baseballpy.sources import catalog
from baseballpy.sources.kalshi.adapter import KalshiAdapter
from baseballpy.sources.kalshi.endpoints import (
    BY_NAME,
    DATASET_KEYS,
    ENDPOINTS,
    MLB_SCOPE,
    KalshiEndpoint,
)
from baseballpy.sources.kalshi.extractor import KalshiExtractor
from baseballpy.sources.kalshi.ingest import IngestOutcome, ingest
from baseballpy.sources.kalshi.normalizer import KalshiNormalizer
from baseballpy.sources.kalshi.schema import KALSHI_SCHEMAS

MARKET = {
    "ticker": "KXMLBGAME-26OCT28MILTB-MIL",
    "event_ticker": "KXMLBGAME-26OCT28MILTB",
    "market_type": "binary",
    "status": "finalized",
    "result": "yes",
    "open_time": "2026-10-28T05:25:00Z",
    "close_time": "2026-10-29T03:14:32Z",
    "updated_time": "2026-10-29T03:20:00.5Z",
    "last_price_dollars": "0.5400",
    "yes_bid_dollars": "0.5300",
    "volume_fp": "1234567.50",
    "price_ranges": [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}],
    "custom_strike": {"Team": "abc"},
    "exchange_index": 0,
}


def test_the_scope_rule_keeps_mlb_series_and_drops_look_alikes() -> None:
    keep = [
        {"ticker": "KXMLBGAME", "tags": ["Baseball"]},
        {"ticker": "KXLEADERMLBHR", "tags": None},
        {"ticker": "KXWSAL", "tags": ["Baseball"]},
    ]
    drop = [
        {"ticker": "KXEWCMLBB", "tags": ["Esports"]},
        {"ticker": "KXNPBGAME", "tags": ["Baseball"]},
        {"ticker": "KXNFLGAME", "tags": ["Football"]},
    ]
    assert all(MLB_SCOPE.includes(s) for s in keep)
    assert not any(MLB_SCOPE.includes(s) for s in drop)


def test_every_route_feeds_a_registered_dataset_whose_key_is_typed() -> None:
    registry = catalog.register_all()
    for endpoint in ENDPOINTS:
        spec = registry[f"kalshi.{endpoint.dataset}"]
        assert set(spec.keys) == set(DATASET_KEYS[endpoint.dataset])
        assert set(spec.keys) <= set(spec.schema.names)
        assert spec.schema.names[-1] == "_extras"
        assert spec.partition == "none"
    assert {spec.name for k, spec in registry.items() if k.startswith("kalshi.")} == {
        e.dataset for e in ENDPOINTS
    }


def test_a_market_is_typed_exactly_and_unknown_keys_are_kept_not_lost() -> None:
    table = KalshiNormalizer().normalize(
        "markets", [MARKET | {"a_field_kalshi_added_tomorrow": "x"}]
    )
    row = table.to_pylist()[0]
    schema = KALSHI_SCHEMAS["markets"]
    assert schema.field("last_price_dollars").type == pa.decimal128(9, 4)
    assert schema.field("volume_fp").type == pa.decimal128(18, 2)
    assert row["last_price_dollars"] == decimal.Decimal("0.5400")
    assert row["volume_fp"] == decimal.Decimal("1234567.50")
    assert row["close_time"].year == 2026 and row["updated_time"].microsecond == 500000
    assert json.loads(row["price_ranges"])[0]["step"] == "0.0100"
    assert row["_extras"] == '{"a_field_kalshi_added_tomorrow": "x"}'
    clean = KalshiNormalizer().normalize("markets", [MARKET]).to_pylist()[0]
    assert clean["_extras"] is None, "every key in a real market must have a typed column"


def test_a_page_of_decimals_that_is_not_a_number_is_quarantined(tmp_path: Path) -> None:
    bad = MARKET | {"last_price_dollars": "n/a"}
    table = KalshiNormalizer().normalize("markets", [MARKET, bad])
    assert table.column("last_price_dollars").to_pylist() == [decimal.Decimal("0.5400"), None]


class FakeHttp:
    """A stand-in for the shared client: pages by cursor, records the in-flight peak."""

    def __init__(self, pages: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, str]]] = []
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def get_sync(self, url: str, *, params: dict[str, str] | None = None, **_: Any) -> HttpResult:
        params = dict(params or {})
        path = url.split("/trade-api/v2", 1)[1]
        with self._lock:
            self.calls.append((path, params))
            self._active += 1
            self.peak = max(self.peak, self._active)
        try:
            ticker = params.get("series_ticker", "")
            cursor = params.get("cursor", "")
            records = self.pages.get((path + "|" + ticker, cursor), [])
            key = "series" if path == "/series" else path.split("/")[-1]
            nxt = {"": "c1", "c1": "c2"}.get(cursor, "") if len(records) == 1 and ticker else ""
            body = {key: records, "cursor": nxt if self._more(path, ticker, cursor) else ""}
            return HttpResult(url, 200, json.dumps(body).encode(), None, False, 0.0)
        finally:
            with self._lock:
                self._active -= 1

    def _more(self, path: str, ticker: str, cursor: str) -> bool:
        return (path + "|" + ticker, {"": "c1", "c1": "c2"}.get(cursor, "~")) in self.pages


def _pages() -> dict[tuple[str, str], list[dict[str, Any]]]:
    def market(ticker: str, updated: str, price: str) -> dict[str, Any]:
        return MARKET | {"ticker": ticker, "updated_time": updated, "last_price_dollars": price}

    series = [
        {"ticker": "KXMLBGAME", "title": "MLB game", "category": "Sports", "tags": ["Baseball"]},
        {"ticker": "KXNPBGAME", "title": "NPB game", "category": "Sports", "tags": ["Baseball"]},
        {"ticker": "KXWSAL", "title": "AL champion", "category": "Sports", "tags": ["Baseball"]},
    ]
    events = {"event_ticker": "KXMLBGAME-E1", "series_ticker": "KXMLBGAME", "title": "Game"}
    return {
        ("/series|", ""): series,
        ("/events|KXMLBGAME", ""): [events],
        ("/events|KXMLBGAME", "c1"): [events | {"event_ticker": "KXMLBGAME-E2"}],
        ("/events|KXWSAL", ""): [events | {"event_ticker": "KXWSAL-E1", "series_ticker": "KXWSAL"}],
        ("/markets|KXMLBGAME", ""): [market("M-OLD", "2026-10-01T00:00:00Z", "0.1000")],
        ("/markets|KXMLBGAME", "c1"): [market("M-LIVE", "2026-10-02T00:00:00Z", "0.2000")],
        ("/historical/markets|KXMLBGAME", ""): [
            market("M-OLD", "2026-10-05T00:00:00Z", "0.9000"),
            market("M-ARCH", "2026-09-01T00:00:00Z", "0.3000"),
        ],
        ("/markets|KXWSAL", ""): [market("W-1", "2026-10-01T00:00:00Z", "0.4000")],
    }


def _ingest(tmp_path: Path, workers: int = 4) -> tuple[IngestOutcome, FakeHttp, LakeConfig]:
    config = LakeConfig(base_dir=tmp_path)
    fake = FakeHttp(_pages())
    extractor = KalshiExtractor(config, fake)  # type: ignore[arg-type]
    return ingest(config=config, extractor=extractor, workers=workers), fake, config


def test_extractor_follows_the_cursor_and_keeps_every_raw_page_in_one_gzip(
    tmp_path: Path,
) -> None:
    import gzip

    from baseballpy.sources.kalshi.raw import RawLog

    config = LakeConfig(base_dir=tmp_path)
    fake = FakeHttp(_pages())
    extractor = KalshiExtractor(config, fake)  # type: ignore[arg-type]
    raw = RawLog()
    rows = extractor.records(BY_NAME["events"], "KXMLBGAME", raw)
    assert [r["event_ticker"] for r in rows] == ["KXMLBGAME-E1", "KXMLBGAME-E2"]
    extractor.keep("events", "events-KXMLBGAME.jsonl.gz", raw)
    store = RawStore(config)
    assert store.verify("kalshi", "events", "events-KXMLBGAME.jsonl.gz")
    pages = gzip.decompress(store.get("kalshi", "events", "events-KXMLBGAME.jsonl.gz")).splitlines()
    assert len(pages) == 2, "both pages answered are kept"
    assert [
        p.name
        for p in (tmp_path / "raw" / "kalshi" / "events").iterdir()
        if not p.name.startswith("_manifest.json")
    ] == ["events-KXMLBGAME.jsonl.gz"], "no file per page"


def test_catalog_ingest_runs_series_on_threads_and_merges_live_with_archived(
    tmp_path: Path,
) -> None:
    outcome, fake, config = _ingest(tmp_path)
    assert outcome.series == 2, "NPB is out of scope, the league champion series is in"
    assert outcome.rows == {"series": 2, "events": 3, "markets": 4}
    store = ProcessedStore(config)
    markets = store.read(get_dataset("kalshi", "markets")).to_pylist()
    by_ticker = {m["ticker"]: m for m in markets}
    assert sorted(by_ticker) == ["M-ARCH", "M-LIVE", "M-OLD", "W-1"]
    assert by_ticker["M-OLD"]["last_price_dollars"] == decimal.Decimal("0.9000"), (
        "the newer of the live and archived rows wins"
    )
    assert {p.name for p in store.files(get_dataset("kalshi", "markets"))} == {
        "part-KXMLBGAME.parquet",
        "part-KXWSAL.parquet",
    }
    assert not any(
        c[0] == "/events" and c[1].get("series_ticker") == "KXNPBGAME" for c in fake.calls
    )


def test_a_dataset_subset_only_asks_for_its_routes(tmp_path: Path) -> None:
    config = LakeConfig(base_dir=tmp_path)
    fake = FakeHttp(_pages())
    outcome = ingest(["events"], config=config, extractor=KalshiExtractor(config, fake))  # type: ignore[arg-type]
    assert set(outcome.rows) == {"series", "events"}
    assert {path for path, _ in fake.calls} == {"/series", "/events"}
    with pytest.raises(ValueError, match="unknown dataset"):
        ingest(["nope"], config=config, extractor=KalshiExtractor(config, fake))  # type: ignore[arg-type]


def test_the_adapter_plans_one_catalog_job_and_reports_rows() -> None:
    seen: list[Sequence[str] | None] = []

    def loader(datasets: Sequence[str] | None) -> IngestOutcome:
        seen.append(datasets)
        return IngestOutcome(rows={"series": 2, "markets": 5}, series=2)

    adapter = KalshiAdapter(loader)
    assert adapter.all_seasons() == []
    (job,) = adapter.plan(Selection(seasons=(2024,)))
    assert job.job_id == "kalshi:catalog"
    result = adapter.run(job)
    assert (result.status, result.rows) == (JobStatus.COMPLETED, 7)
    (subset,) = adapter.plan(Selection(datasets=("markets",)))
    assert subset.job_id == "kalshi:catalog:datasets=markets"
    adapter.run(subset)
    assert seen == [None, ["markets"]]
    with pytest.raises(ValueError, match="unknown dataset"):
        adapter.plan(Selection(datasets=("nope",)))


def test_the_kalshi_host_has_its_own_rate_and_in_flight_caps() -> None:
    tuned = RateLimitConfig(kalshi_rps=40.0, kalshi_concurrency=8)
    assert (tuned.host_rates[KALSHI_HOST], tuned.host_concurrency[KALSHI_HOST]) == (40.0, 8)
    assert KALSHI_HOST in RateLimitConfig().host_rates


def test_every_route_names_its_dataset_and_a_page_size() -> None:
    for endpoint in ENDPOINTS:
        assert isinstance(endpoint, KalshiEndpoint)
        assert endpoint.paged == (endpoint.page_limit > 0)
        assert endpoint.dataset in DATASET_KEYS


# ----------------------------------------------------------------------------- signing


def _key_pair() -> tuple[bytes, Any]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return pem, private.public_key()


def test_a_signature_verifies_with_the_public_key_and_ignores_the_query() -> None:
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    from baseballpy.sources.kalshi.signing import KalshiSigner

    pem, public = _key_pair()
    signer = KalshiSigner("key-id-1", pem, clock=lambda: 1_700_000_000.123)
    url = "https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=X&limit=5"
    headers = signer.headers("get", url)
    assert headers["KALSHI-ACCESS-KEY"] == "key-id-1"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1700000000123"
    public.verify(
        base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"]),
        b"1700000000123GET/trade-api/v2/markets",
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )  # raises InvalidSignature on a mismatch


def test_signing_is_off_without_a_configured_key_and_on_with_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baseballpy.core.config import KalshiAuthConfig
    from baseballpy.sources.kalshi.signing import KalshiSigner

    for name in (
        "BASEBALLPY_KALSHI_KEY_ID",
        "KALSHI_TOKEN",
        "BASEBALLPY_KALSHI_PRIVATE_KEY_PATH",
        "KALSHI_PRIVATE_KEY_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    assert KalshiSigner.from_config() is None
    assert RateLimitConfig().host_rates[KALSHI_HOST] == 4.0
    assert RateLimitConfig().host_concurrency[KALSHI_HOST] == 4
    pem, _ = _key_pair()
    key_file = tmp_path / "key.pem"
    key_file.write_bytes(pem)
    monkeypatch.setenv("KALSHI_TOKEN", "abc")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(key_file))
    assert KalshiAuthConfig().configured
    assert "abc" not in repr(KalshiAuthConfig()), "the key id must not appear in a repr"
    assert KalshiSigner.from_config() is not None
    assert RateLimitConfig().host_rates[KALSHI_HOST] == 20.0
    assert RateLimitConfig().host_concurrency[KALSHI_HOST] == 16


def test_the_header_hook_signs_every_attempt_and_other_hosts_stay_unsigned() -> None:
    import httpx
    import respx

    from baseballpy.core.http import HttpClient

    seen: list[tuple[str, str | None]] = []

    def hook(method: str, url: str) -> dict[str, str]:
        seen.append((method, url))
        return {"KALSHI-ACCESS-TIMESTAMP": str(len(seen))}

    with respx.mock:
        signed = respx.get("https://signed.example.com/x").mock(
            side_effect=[httpx.Response(429, headers={"Retry-After": "0"}), httpx.Response(200)]
        )
        plain = respx.get("https://plain.example.com/x").mock(return_value=httpx.Response(200))
        client = HttpClient(RateLimitConfig(backoff_factor=0.01, max_retries=3), http2=False)
        client.set_header_hook("signed.example.com", hook)
        try:
            client.get_sync("https://signed.example.com/x")
            client.get_sync("https://plain.example.com/x")
        finally:
            client.close()
    assert [
        r.headers.get("KALSHI-ACCESS-TIMESTAMP") for r in (c.request for c in signed.calls)
    ] == [
        "1",
        "2",
    ], "a retry is signed again, not replayed"
    assert "KALSHI-ACCESS-TIMESTAMP" not in plain.calls[0].request.headers
    assert [m for m, _ in seen] == ["GET", "GET"]


def test_a_fresh_kalshi_download_has_the_lake_shape(tmp_path: Path) -> None:
    """The shared lake contract (layout, raw integrity, typed views) holds after a download."""
    from lake_contract import assert_lake_contract

    _ingest(tmp_path)
    views = assert_lake_contract(LakeConfig(base_dir=tmp_path), ["kalshi"])
    assert views.get("kalshi_markets") == 4


def test_the_round_trip_check_counts_kalshi_pages_and_finds_a_lost_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The raw pages are JSON: the distinct tickers in them are the rows the table must hold."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from baseballpy.core.roundtrip import roundtrip_dataset
    from baseballpy.ingest import adapters as adapter_registry
    from baseballpy.sources.adapters import register_all_adapters

    # other tests may have registered fake adapters: start from an empty registry so this one is order-proof
    monkeypatch.setattr(adapter_registry, "ADAPTERS", {})
    register_all_adapters()
    _, _, config = _ingest(tmp_path)
    spec = get_dataset("kalshi", "markets")
    check = roundtrip_dataset(config, spec)
    assert check.status == "ok" and check.raw_rows == 4 and check.compared == 4, check
    for part in ProcessedStore(config).files(spec):  # drop one row from one stored file
        table = pq.read_table(part)
        pq.write_table(table.slice(1) if table.num_rows > 1 else pa.table({}), part)
        break
    lost = roundtrip_dataset(config, spec)
    assert lost.status == "loss" and lost.losses[0].kind == "row_missing", lost
