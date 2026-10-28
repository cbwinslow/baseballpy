"""Generic MLB Stats API normalizer + extractor driven by :mod:`.endpoints` and ``mlb_tables``.

The normalizer maps flattened records onto the strict schema generated for an endpoint (by upstream
key), keeps unknown fields as JSON in ``_extras`` and quarantines cells that do not fit their type.
The extractor fetches every request an endpoint needs (``requests_for``), stores the raw JSON with a
sha256, writes one typed part per request and skips requests whose part is still fresh.
"""

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import cleanup_stale_parts
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.http import HttpClient, HttpResult, get_http_client
from baseballpy.core.quarantine import Quarantine, checked_cast, safe_array
from baseballpy.core.schema_tools import EXTRAS, UPSTREAM_KEY, pa_type
from baseballpy.core.stores import ProcessedStore, RawStore, manifest_key
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.endpoints import (
    BY_NAME,
    MLB_BASE_URL,
    PAGE_SIZE,
    Context,
    MlbEndpoint,
    Request,
    requests_for,
)
from baseballpy.sources.mlb_api.flatten import Scalar, iter_records
from baseballpy.sources.mlb_api.mlb_schema import MLB_SCHEMAS

logger = logging.getLogger(__name__)

_TEXT_TYPES = (pa.date32(), pa.timestamp("us", tz="UTC"))


def _total_splits(payload: Any) -> int | None:
    """``stats[0].totalSplits`` of a paginated ``/v1/stats`` response (``None`` if absent)."""
    stats = payload.get("stats") if isinstance(payload, dict) else None
    if isinstance(stats, list) and stats and isinstance(stats[0], dict):
        total = stats[0].get("totalSplits")
        return int(total) if isinstance(total, int) else None
    return None


#: a paginated request announcing more rows than this is refused unless heavy ingestion is allowed
MAX_SPLITS = 20_000


#: seconds a page of an all-time pool may take: deep offsets into a ~190k-row pool exceed the
#: default 30 s request timeout upstream (a real run of ``stats_single_season_hitting`` timed out)
HEAVY_PAGE_TIMEOUT = 180.0


class HeavyEndpointError(RuntimeError):
    """A paginated request would download an unexpectedly huge result (all-time stat pools)."""


class UnsupportedEndpointError(NotImplementedError):
    """The endpoint is registered as unsupported (the reason is in the message)."""


def _as_string(value: Scalar) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class MlbRecordNormalizer:
    """Flattened MLB records -> strictly typed Arrow table of one endpoint."""

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    def normalize(
        self,
        endpoint: MlbEndpoint | str,
        payload: Any,
        *,
        extra: Mapping[str, Scalar] | None = None,
        dataset: str | None = None,
    ) -> pa.Table:
        """Typed table of the records of ``payload`` (empty table when it has none).

        ``extra`` columns (the request's fan-out value, e.g. ``game_pk``) are added to every record.
        """
        ep = BY_NAME[endpoint] if isinstance(endpoint, str) else endpoint
        schema = MLB_SCHEMAS[ep.name]
        records = [{**(extra or {}), **r} for r in iter_records(payload, ep.records)]
        return self.from_records(records, schema, dataset or ep.name)

    def from_records(
        self, records: Sequence[dict[str, Scalar]], schema: pa.Schema, dataset: str
    ) -> pa.Table:
        """Map ``records`` onto ``schema`` (field metadata ``upstream`` = flattened key)."""
        if not records:
            return schema.empty_table()
        known = {
            f.name: (f.metadata or {}).get(UPSTREAM_KEY, f.name.encode()).decode() for f in schema
        }
        upstream_to_field = {v: k for k, v in known.items() if k != EXTRAS}
        columns: list[pa.Array] = []
        for field in schema:
            if field.name == EXTRAS:
                continue
            key = known[field.name]
            values = [r.get(key) for r in records]
            columns.append(self._array(values, field, dataset))
        if EXTRAS in schema.names:
            extra_keys = sorted({k for r in records for k in r} - upstream_to_field.keys())
            if extra_keys:
                logger.warning(
                    "schema_drift: mlb_api/%s has unknown field(s) %s; preserving them in _extras",
                    dataset,
                    extra_keys,
                )
            payloads = [
                json.dumps({k: r[k] for k in extra_keys if r.get(k) is not None}) for r in records
            ]
            columns.append(pa.array([p if p != "{}" else None for p in payloads], pa.string()))
        return pa.Table.from_arrays(columns, schema=schema)

    def _array(self, values: list[Scalar], field: pa.Field, dataset: str) -> pa.Array:
        if field.type == pa.string():
            return pa.array([_as_string(v) for v in values], pa.string())
        if field.type in _TEXT_TYPES:
            strings = pa.chunked_array([pa.array([_as_string(v) for v in values], pa.string())])
            return checked_cast(
                strings,
                field.type,
                quarantine=self._quarantine,
                source="mlb_api",
                dataset=dataset,
                column=field.name,
            ).combine_chunks()
        return safe_array(
            values,
            field.type,
            source="mlb_api",
            dataset=dataset,
            column=field.name,
            quarantine=self._quarantine,
        )


@dataclass(frozen=True)
class EndpointReport:
    """Outcome of ingesting one endpoint: rows per request (``None`` = served from cache)."""

    name: str
    requests: int
    rows: int
    cached: int
    unsupported: str | None = None
    missing: int = 0  # requests answered 404 and recorded as empty (``tolerate_missing``)
    raw_only: int = 0  # requests stored as raw JSON only (the probe found no records to type)


class MlbEndpointExtractor:
    """Fetch/cache/store any registered :class:`MlbEndpoint`."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        catalog.register_all()
        self.cache_config = cache_config or LakeConfig()
        self.http = http or (
            HttpClient(rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.normalizer = MlbRecordNormalizer()
        self.store = ProcessedStore(self.cache_config)
        self.raw = RawStore(self.cache_config)
        cleanup_stale_parts(self.cache_config.raw_root / "mlb_api")
        cleanup_stale_parts(self.cache_config.processed_root / "mlb_api")
        self.missing = 0

    @staticmethod
    def spec(endpoint: MlbEndpoint) -> DatasetSpec:
        """Registered dataset of an endpoint."""
        return get_dataset("mlb_api", endpoint.name)

    def _is_cached(self, endpoint: MlbEndpoint, request: Request, refresh: bool) -> bool:
        spec = self.spec(endpoint)
        path = self.store.part_path(spec, request.ident, request.season)
        entry = self.cache_config.dataset_manifest("mlb_api", endpoint.name).get_chunk(
            manifest_key(request.ident, request.season)
        )
        return path.exists() and self.cache_config.is_fresh(
            entry, endpoint.freshness, season=request.season, refresh=refresh
        )

    def _get_pages(
        self, endpoint: MlbEndpoint, request: Request, url: str, allow_heavy: bool = False
    ) -> list[tuple[str, HttpResult]]:
        """The response(s) of a request as ``(raw file name, result)``; paginated ones loop."""
        if not endpoint.paginated:
            result = self.http.get_sync(
                url,
                params=request.params,
                allow=(200, 404) if endpoint.tolerate_missing else (200,),
            )
            return [(f"{request.ident}.json", result)]
        pages: list[tuple[str, HttpResult]] = []
        offset = 0
        while True:
            params = {**request.params, "limit": PAGE_SIZE, "offset": offset}
            result = self.http.get_sync(
                url, params=params, timeout=HEAVY_PAGE_TIMEOUT if allow_heavy else None
            )
            pages.append((f"{request.ident}.p{len(pages)}.json", result))
            payload = result.json()
            got = sum(1 for _ in iter_records(payload, endpoint.records))
            total = _total_splits(payload)
            if total is not None and total > MAX_SPLITS and not allow_heavy and not pages[1:]:
                raise HeavyEndpointError(
                    f"{endpoint.name} announces {total:,} rows (> {MAX_SPLITS:,}); it ignores the "
                    "season. Pass include_history=True / allow_heavy=True to download it anyway."
                )
            offset += PAGE_SIZE
            if (
                got == 0
                or (total is not None and offset >= total)
                or (total is None and got < PAGE_SIZE)
            ):
                return pages

    def fetch_request(
        self,
        endpoint: MlbEndpoint,
        request: Request,
        refresh: bool = False,
        allow_heavy: bool = False,
    ) -> pa.Table:
        """One request -> typed table (cache-or-fetch; raw JSON + typed part are stored)."""
        if endpoint.unsupported is not None:
            raise UnsupportedEndpointError(f"{endpoint.name}: {endpoint.unsupported}")
        spec = self.spec(endpoint)
        url = f"{MLB_BASE_URL}/{request.path}"
        part = self.store.part_path(spec, request.ident, request.season)
        if self._is_cached(endpoint, request, refresh):
            with default_audit_logger.track(
                operation=f"mlb_{endpoint.name}",
                source="mlb_api",
                endpoint=url,
                destination=str(part),
            ) as hit:
                hit.set_cache_hit(True)
                table = pq.read_table(part, schema=spec.schema)
                hit.set_records(len(table))
                return table
        with default_audit_logger.track(
            operation=f"mlb_{endpoint.name}",
            source="mlb_api",
            endpoint=url,
            destination=str(part),
        ) as tracker:
            pages = self._get_pages(endpoint, request, url, allow_heavy)
            if pages[0][1].status == 404:
                # nothing there (e.g. an award without a recipients list): keep an empty typed part
                self.missing += 1
                logger.info("%s: HTTP 404 for %s; recorded as empty", endpoint.name, url)
                empty = spec.schema.empty_table()
                if self.cache_config.enabled:
                    self.store.put(
                        spec,
                        empty,
                        chunk_id=request.ident,
                        season=request.season,
                        metadata={"http_status": 404},
                    )
                tracker.set_cache_hit(False)
                tracker.set_records(0)
                return empty
            tables = [
                self.normalizer.normalize(endpoint, result.json(), extra=request.extra)
                for _, result in pages
            ]
            table = pa.concat_tables(tables) if len(tables) > 1 else tables[0]
            if self.cache_config.enabled:
                for name, result in pages:
                    self.raw.put(
                        "mlb_api",
                        endpoint.name,
                        name,
                        result.content,
                        season=request.season,
                        source_ref=url,
                        etag=result.etag or "",
                    )
                self.store.put(spec, table, chunk_id=request.ident, season=request.season)
            tracker.set_cache_hit(False)
            tracker.set_records(len(table))
            return table

    def _ingest_raw_only(self, ep: MlbEndpoint, ctx: Context, refresh: bool) -> EndpointReport:
        """Endpoints with no generated schema still keep every response as raw JSON (lossless).

        The generation probe saw no records for them (e.g. ``standings_first_half`` in 2024), so
        there is nothing to type yet; the raw files are typed later by regenerating the schemas.
        """
        n = stored = cached = 0
        for request in requests_for(ep, ctx):
            n += 1
            name = f"{request.ident}.json"
            path = self.raw.path_for("mlb_api", ep.name, name, request.season)
            if path.exists() and not refresh:
                cached += 1
                continue
            url = f"{MLB_BASE_URL}/{request.path}"
            result = self.http.get_sync(
                url,
                params=request.params,
                allow=(200, 404) if ep.tolerate_missing else (200,),
            )
            if result.status != 200:
                continue
            self.raw.put(
                "mlb_api",
                ep.name,
                name,
                result.content,
                season=request.season,
                source_ref=url,
                etag=result.etag or "",
            )
            stored += 1
        return EndpointReport(ep.name, n, 0, cached, raw_only=stored + cached)

    def ingest(
        self,
        endpoint: MlbEndpoint | str,
        ctx: Context,
        refresh: bool = False,
        allow_heavy: bool = False,
    ) -> EndpointReport:
        """Ingest every request of ``endpoint`` for ``ctx`` (resumable; cached parts are skipped)."""
        ep = BY_NAME[endpoint] if isinstance(endpoint, str) else endpoint
        if ep.unsupported is not None:
            return EndpointReport(ep.name, 0, 0, 0, unsupported=ep.unsupported)
        if ep.name not in MLB_SCHEMAS:
            return self._ingest_raw_only(ep, ctx, refresh)
        rows = cached = n = 0
        self.missing = 0
        for request in requests_for(ep, ctx):
            n += 1
            was_cached = self._is_cached(ep, request, refresh)
            table = self.fetch_request(ep, request, refresh, allow_heavy)
            rows += table.num_rows
            cached += int(was_cached)
        return EndpointReport(ep.name, n, rows, cached, missing=self.missing)


def read_endpoint(
    endpoint: MlbEndpoint | str, season: int | None = None, config: LakeConfig | None = None
) -> pa.Table:
    """All stored rows of an endpoint (optionally one season) as a typed table."""
    catalog.register_all()
    ep = BY_NAME[endpoint] if isinstance(endpoint, str) else endpoint
    store = ProcessedStore(config)
    return store.read(get_dataset("mlb_api", ep.name), season if ep.partitioned else None)


def endpoints_matching(names: Iterable[str] | None = None) -> list[MlbEndpoint]:
    """Registered endpoints by name (all supported ones when ``names`` is ``None``)."""
    if names is None:
        return [e for e in BY_NAME.values() if e.unsupported is None]
    return [BY_NAME[n] for n in names]


__all__ = [
    "EndpointReport",
    "MlbEndpointExtractor",
    "MlbRecordNormalizer",
    "UnsupportedEndpointError",
    "endpoints_matching",
    "pa_type",
    "read_endpoint",
]
