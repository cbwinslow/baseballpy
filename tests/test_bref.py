"""Baseball-Reference WAR: typing, the NULL marker, one download, never a retry after a refusal."""

import decimal
import gzip
import hashlib
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pytest
import respx

from baseballpy.core.config import BREF_HOST, LakeConfig, RateLimitConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.http import HttpClient, HttpResult, HttpStatusError
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.ingest.types import JobStatus, Selection
from baseballpy.sources import catalog
from baseballpy.sources.bref.adapter import BrefAdapter
from baseballpy.sources.bref.endpoints import BY_DATASET, DATASET_KEYS, FILES
from baseballpy.sources.bref.extractor import BrefBlockedError, BrefExtractor
from baseballpy.sources.bref.ingest import IngestOutcome, ingest
from baseballpy.sources.bref.normalizer import BrefNormalizer
from baseballpy.sources.bref.schema import BREF_SCHEMAS
from baseballpy.sources.bref.tables import BREF_COLUMNS

HEADER = [name for name, _ in BREF_COLUMNS["war_batting"]]


def batting_csv(rows: list[dict[str, str]]) -> bytes:
    """A WAR batting file with the real header; unnamed cells are NULL."""
    lines = [",".join(HEADER)]
    for row in rows:
        lines.append(",".join(row.get(name, "NULL") for name in HEADER))
    return ("\n".join(lines) + "\n").encode("utf-8")


ROWS = [
    {"name_common": "Aaron Judge", "player_ID": "judgeaa01", "year_ID": "2024", "stint_ID": "1",
     "team_ID": "NYY", "lg_ID": "AL", "WAR": "10.90", "age": "32", "mlb_ID": "592450"},
    {"name_common": "Aaron Judge", "player_ID": "judgeaa01", "year_ID": "2023", "stint_ID": "1",
     "team_ID": "NYY", "lg_ID": "AL", "WAR": "5.06", "age": "31", "mlb_ID": "592450"},
    {"name_common": "Old Timer", "player_ID": "timerol01", "year_ID": "1871", "stint_ID": "1",
     "team_ID": "BOS", "lg_ID": "NA", "WAR": "NULL", "age": "NULL", "mlb_ID": "NULL"},
]  # fmt: skip


class FakeHttp:
    """A stand-in for the shared client: serves the batting file, counts the calls."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body, self.status, self.calls = body, status, 0

    def get_sync(self, url: str, **_: Any) -> HttpResult:
        self.calls += 1
        if self.status != 200:
            raise HttpStatusError(url, self.status)
        return HttpResult(url, 200, self.body, None, False, 0.0)


def test_the_files_are_registered_with_season_partitions_and_unique_keys() -> None:
    registry = catalog.register_all()
    for file in FILES:
        spec = registry[f"bref.{file.dataset}"]
        assert spec.partition == "season" and spec.keys == DATASET_KEYS[file.dataset]
        assert set(spec.keys) <= set(spec.schema.names) and spec.schema.names[-1] == "_extras"


def test_null_cells_are_null_numbers_are_exact_and_unknown_headers_are_kept() -> None:
    table = BrefNormalizer().normalize("war_batting", batting_csv(ROWS))
    rows = {(r["player_ID"], r["year_ID"]): r for r in table.to_pylist()}
    judge = rows[("judgeaa01", 2024)]
    assert judge["WAR"] == decimal.Decimal("10.90") and judge["age"] == 32
    assert BREF_SCHEMAS["war_batting"].field("WAR").type == pa.decimal128(9, 2)
    old = rows[("timerol01", 1871)]
    assert old["WAR"] is None and old["age"] is None and old["mlb_ID"] is None
    assert old["lg_ID"] == "NA", "NA is a league code here, not a missing value"
    extra = batting_csv(ROWS).replace(b"\n", b",surprise\n", 1).replace(
        b"NULL\n", b"NULL,5\n"
    )  # fmt: skip
    drift = BrefNormalizer().normalize("war_batting", extra)
    assert drift.num_rows == 3 and "surprise" in str(drift.column("_extras").to_pylist())


def test_a_file_is_downloaded_once_kept_with_its_checksum_and_reused_while_recent(
    tmp_path: Path,
) -> None:
    config = LakeConfig(home=tmp_path)
    body = batting_csv(ROWS)
    fake = FakeHttp(body)
    extractor = BrefExtractor(config, fake)  # type: ignore[arg-type]
    file = BY_DATASET["war_batting"]
    assert extractor.fetch(file) == body and fake.calls == 1
    assert extractor.fetch(file) == body and fake.calls == 1, "recent: read from raw/, no request"
    assert extractor.fetch(file, refresh=True) == body and fake.calls == 2
    store = RawStore(config)
    assert store.verify("bref", "war_batting", "war_daily_bat.txt")
    stored = tmp_path / "raw" / "bref" / "war_batting" / "war_daily_bat.txt.gz"
    assert gzip.decompress(stored.read_bytes()) == body
    entry = config.dataset_manifest("bref", "war_batting", "raw").get_chunk("war_daily_bat.txt")
    assert entry is not None and entry["sha256"] == hashlib.sha256(body).hexdigest()


def test_a_refusal_or_a_web_page_stops_the_run_and_says_to_wait_a_day(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    file = BY_DATASET["war_batting"]
    with pytest.raises(BrefBlockedError, match="24 hours"):
        BrefExtractor(config, FakeHttp(b"", status=429)).fetch(file)  # type: ignore[arg-type]
    with pytest.raises(BrefBlockedError, match="web page"):
        BrefExtractor(config, FakeHttp(b"<html>Rate Limited</html>")).fetch(file)  # type: ignore[arg-type]
    assert not RawStore(config).exists("bref", "war_batting", "war_daily_bat.txt")


@respx.mock
def test_the_shared_client_makes_exactly_one_request_when_baseball_reference_refuses() -> None:
    route = respx.get(f"https://{BREF_HOST}/data/war_daily_bat.txt").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "1"})
    )
    client = HttpClient(RateLimitConfig(host_rates={BREF_HOST: 100.0}))
    with pytest.raises(HttpStatusError):
        client.get_sync(f"https://{BREF_HOST}/data/war_daily_bat.txt")
    assert route.call_count == 1, "a refused session must not be asked again"


def test_ingest_stores_one_chunk_per_season_with_every_row(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    fake = FakeHttp(batting_csv(ROWS))
    outcome = ingest(["war_batting"], config=config, extractor=BrefExtractor(config, fake))  # type: ignore[arg-type]
    assert outcome.rows == {"war_batting": 3} and outcome.seasons == {"war_batting": 3}
    store = ProcessedStore(config)
    spec = get_dataset("bref", "war_batting")
    assert store.row_count(spec, 2024) == 1 and store.row_count(spec) == 3
    assert sorted(
        p.parent.name for p in config.processed_dir("bref", "war_batting").rglob("part-*")
    ) == [
        "season=1871",
        "season=2023",
        "season=2024",
    ]
    with pytest.raises(ValueError, match="unknown dataset"):
        ingest(["war_fielding"], config=config)


def test_adapter_plans_one_job_and_runs_it() -> None:
    adapter = BrefAdapter(loader=lambda datasets, refresh: IngestOutcome(rows={"war_batting": 3}))
    assert len(adapter.plan(Selection())) == 1
    subset = adapter.plan(Selection(datasets=("war_batting",)))
    assert subset[0].param("datasets") == "war_batting"
    result = adapter.run(subset[0])
    assert result.status is JobStatus.COMPLETED and result.rows == 3
    with pytest.raises(ValueError, match="unknown dataset"):
        adapter.plan(Selection(datasets=("nope",)))
    assert adapter.all_seasons() == []


def test_a_fresh_bref_download_has_the_lake_shape(tmp_path: Path) -> None:
    """The shared lake contract (layout, raw integrity, typed views) holds after a download."""
    from lake_contract import assert_lake_contract

    config = LakeConfig(home=tmp_path)
    fake = FakeHttp(batting_csv(ROWS))
    ingest(["war_batting"], config=config, extractor=BrefExtractor(config, fake))  # type: ignore[arg-type]
    views = assert_lake_contract(config, ["bref"])
    assert views.get("bref_war_batting") == 3
