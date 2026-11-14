"""A stale hydrate pool chunk is parsed again from its stored raw pages, offline (ADR 130)."""

import gzip
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.stores import manifest_key
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.endpoints import BY_NAME, Context, Request, requests_for
from baseballpy.sources.mlb_api.generic import (
    HYDRATE_MARKER,
    HYDRATE_PARSE_REV,
    PARSE_REV_KEY,
    VIA_DIRECT,
    VIA_HYDRATE,
    VIA_KEY,
    MlbEndpointExtractor,
    MlbRecordNormalizer,
)

DATASET = "stats_expected_statistics_hitting"
SEASON = 2008
_BLOCK = {"type": {"displayName": "expectedStatistics"}, "group": {"displayName": "hitting"}}


def _split(player_id: int) -> dict[str, Any]:
    return {
        "season": str(SEASON),
        "stat": {"avg": ".000", "woba": ".073"},
        "player": {"id": player_id, "fullName": "Some Player", "nameSlug": f"p-{player_id}"},
        "sport": {"id": 11, "name": "Triple A"},
        "gameType": "R",
    }


def _hydrate_page(ids: list[int]) -> dict[str, Any]:
    people = [
        {"id": i, "stats": [{**_BLOCK, "exemptions": [], "splits": [_split(i)]}]} for i in ids
    ]
    return {"people": people}


def _requests() -> tuple[Request, Request]:
    ctx = Context(season=SEASON, sport_ids=(1, 11))
    direct, stale = list(requests_for(BY_NAME[DATASET], ctx))
    return direct, stale  # sport 1 = direct chunk, sport 11 = stale hydrate chunk


class _NoNetwork:
    """An HTTP client that fails the test on any request."""

    def get_sync(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"a network request was made: {args} {kwargs}")

    def limit_for(self, host: str) -> int:
        return 1


def _lake(tmp_path: Path) -> tuple[LakeConfig, MlbEndpointExtractor, Request, Request]:
    catalog.register_all()
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake, http=_NoNetwork())  # type: ignore[arg-type]
    direct, stale = _requests()
    ep = BY_NAME[DATASET]
    spec = extractor.spec(ep)
    # the stale hydrate chunk: rows as the old loader wrote them (block fields NULL), raw page kept
    pages = [_hydrate_page([1, 2]), _hydrate_page([3])]
    old_rows = []
    for page in pages:
        payload: dict[str, Any] = {
            "stats": [{"splits": [p["stats"][0]["splits"][0] for p in page["people"]]}]
        }
        old_rows.append(MlbRecordNormalizer().normalize(ep, payload, extra=stale.extra))
    import pyarrow as pa

    old = pa.concat_tables(old_rows)
    assert old["stats_type_display_name"].null_count == 3
    for idx, page in enumerate(pages):
        extractor.raw.put(
            "mlb_api",
            DATASET,
            f"{stale.ident}{HYDRATE_MARKER}p{idx}.json",
            json.dumps(page).encode(),
            season=SEASON,
        )
    extractor.store.put(
        spec, old, chunk_id=stale.ident, season=SEASON, metadata={VIA_KEY: VIA_HYDRATE}
    )
    # the direct chunk: complete rows, via=direct, a raw page that must never be looked at
    direct_rows = MlbRecordNormalizer().normalize(
        ep,
        {"stats": [{**_BLOCK, "splits": [_split(9)]}]},
        extra=direct.extra,
    )
    extractor.store.put(
        spec, direct_rows, chunk_id=direct.ident, season=SEASON, metadata={VIA_KEY: VIA_DIRECT}
    )
    return lake, extractor, direct, stale


def _stored(extractor: MlbEndpointExtractor, name: str) -> Path:
    path = extractor.raw.stored_path("mlb_api", DATASET, name, SEASON)
    assert path is not None
    return path


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_a_stale_hydrate_chunk_is_rebuilt_from_raw_without_a_request(tmp_path: Path) -> None:
    lake, extractor, direct, stale = _lake(tmp_path)
    ep = BY_NAME[DATASET]
    spec = extractor.spec(ep)
    raw_paths = [_stored(extractor, f"{stale.ident}{HYDRATE_MARKER}p{i}.json") for i in (0, 1)]
    raw_before = [_bytes(p) for p in raw_paths]
    raw_manifest = lake.dataset_manifest("mlb_api", DATASET, "raw", SEASON)
    sha_before = [
        raw_manifest.get_chunk(f"{stale.ident}{HYDRATE_MARKER}p{i}.json")["sha256"] for i in (0, 1)
    ]
    direct_part = extractor.store.part_path(spec, direct.ident, SEASON)
    direct_before = _bytes(direct_part)

    table = extractor.fetch_request(ep, stale)

    assert table.num_rows == 3
    assert table["stats_type_display_name"].to_pylist() == ["expectedStatistics"] * 3
    stored = pq.read_table(extractor.store.part_path(spec, stale.ident, SEASON))
    assert stored["stats_group_display_name"].to_pylist() == ["hitting"] * 3
    entry = lake.dataset_manifest("mlb_api", DATASET).get_chunk(manifest_key(stale.ident, SEASON))
    assert entry is not None
    assert entry[VIA_KEY] == VIA_HYDRATE and entry[PARSE_REV_KEY] == HYDRATE_PARSE_REV
    assert [_bytes(p) for p in raw_paths] == raw_before
    assert [
        raw_manifest.get_chunk(f"{stale.ident}{HYDRATE_MARKER}p{i}.json")["sha256"] for i in (0, 1)
    ] == sha_before
    assert _bytes(direct_part) == direct_before, "the direct chunk is untouched"
    direct_entry = lake.dataset_manifest("mlb_api", DATASET).get_chunk(
        manifest_key(direct.ident, SEASON)
    )
    assert direct_entry is not None and PARSE_REV_KEY not in direct_entry


def test_a_direct_chunk_is_never_rebuilt(tmp_path: Path) -> None:
    lake, extractor, direct, _ = _lake(tmp_path)
    assert extractor._rebuild_stale_hydrate(BY_NAME[DATASET], direct) is None


def test_a_second_run_changes_nothing(tmp_path: Path) -> None:
    lake, extractor, _, stale = _lake(tmp_path)
    ep = BY_NAME[DATASET]
    spec = extractor.spec(ep)
    extractor.fetch_request(ep, stale)
    part = extractor.store.part_path(spec, stale.ident, SEASON)
    first = _bytes(part)
    manifest_before = lake.dataset_manifest("mlb_api", DATASET).get_chunk(
        manifest_key(stale.ident, SEASON)
    )
    assert extractor._rebuild_stale_hydrate(ep, stale) is None  # no longer stale
    extractor._remember_stats_route(refused=True)  # the cached path, no request
    extractor.fetch_request(ep, stale)
    assert _bytes(part) == first
    assert (
        lake.dataset_manifest("mlb_api", DATASET).get_chunk(manifest_key(stale.ident, SEASON))
        == manifest_before
    )


def test_a_raw_page_that_fails_its_checksum_is_not_trusted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    lake, extractor, _, stale = _lake(tmp_path)
    ep = BY_NAME[DATASET]
    spec = extractor.spec(ep)
    page = _stored(extractor, f"{stale.ident}{HYDRATE_MARKER}p1.json")
    original = gzip.decompress(page.read_bytes()) if page.suffix == ".gz" else page.read_bytes()
    changed = original.replace(b"Some Player", b"Other Player")
    page.write_bytes(gzip.compress(changed) if page.suffix == ".gz" else changed)
    part = extractor.store.part_path(spec, stale.ident, SEASON)
    before = _bytes(part)
    with caplog.at_level(logging.WARNING):
        assert extractor._rebuild_stale_hydrate(ep, stale) is None
    assert "fail their checksum" in caplog.text
    assert _bytes(part) == before
    entry = lake.dataset_manifest("mlb_api", DATASET).get_chunk(manifest_key(stale.ident, SEASON))
    assert entry is not None and PARSE_REV_KEY not in entry


def test_a_chunk_with_an_old_schema_digest_is_rebuilt_too(tmp_path: Path) -> None:
    lake, extractor, _, stale = _lake(tmp_path)
    ep = BY_NAME[DATASET]
    assert extractor._rebuild_stale_hydrate(ep, stale) is not None
    key = manifest_key(stale.ident, SEASON)
    manifest = lake.dataset_manifest("mlb_api", DATASET)
    entry = manifest.get_chunk(key)
    assert entry is not None
    manifest.put_entry(key, {**entry, "schema_sha256": "old"})
    assert extractor._rebuild_stale_hydrate(ep, stale) is not None
    assert extractor._rebuild_stale_hydrate(ep, stale) is None


def test_force_rebuilds_a_chunk_that_is_not_stale(tmp_path: Path) -> None:
    """A chunk rebuilt with a wrong request can be redone from raw: ``force`` skips the stale test."""
    _, extractor, _, stale = _lake(tmp_path)
    ep = BY_NAME[DATASET]
    extractor.fetch_request(ep, stale)  # repaired: no longer stale
    assert extractor._rebuild_stale_hydrate(ep, stale) is None
    table = extractor._rebuild_stale_hydrate(ep, stale, force=True)
    assert table is not None and table.num_rows > 0
