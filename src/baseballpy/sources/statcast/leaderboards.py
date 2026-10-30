"""Baseball Savant (Statcast) leaderboards: registry-driven extraction with strict schemas.

Every variant in :mod:`baseballpy.sources.statcast.lb_catalog` is a registered dataset
(``statcast.leaderboard_<slug>``) whose schema was generated from the live CSV headers. Requests
that deviate from the variant's canonical parameters (a different ``min`` qualifier, ad hoc
``custom_leaderboard`` selections) return a table but are never written into the registered
dataset, so a dataset always holds one consistent population.
"""

import logging
from dataclasses import dataclass
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.lazy import lazy_singleton
from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import infer_type_name, normalize_csv, read_csv_strings, snake
from baseballpy.core.stores import ProcessedStore, RawStore, manifest_key, schema_matches
from baseballpy.core.upstream import response_fingerprint
from baseballpy.sources import catalog
from baseballpy.sources.statcast.lb_catalog import (
    BY_SLUG,
    SAVANT_BASE,
    SUPPORTED,
    LeaderboardDef,
    request_params,
    resolve,
)
from baseballpy.sources.statcast.lb_parse import html_json_to_csv
from baseballpy.sources.statcast.lb_schema import (
    LEADERBOARD_SCHEMAS,
    default_min,
    min_year,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SAVANT_BASE",
    "LeaderboardReport",
    "StatcastLeaderboardExtractor",
    "StatcastLeaderboardNormalizer",
    "bat_tracking",
    "custom_leaderboard",
    "exit_velocity",
    "expected_statistics",
    "get_leaderboard",
    "leaderboard_spec",
    "outs_above_average",
    "sprint_speed",
]


def leaderboard_spec(name: str, schema: pa.Schema | None = None) -> DatasetSpec:
    """The registered spec of a variant, or an unregistered spec for an ad hoc leaderboard name."""
    catalog.register_all()
    slug = name.lower()
    if slug in LEADERBOARD_SCHEMAS:
        return get_dataset("statcast", f"leaderboard_{slug}")
    return DatasetSpec(
        source="statcast",
        name=f"leaderboard_{slug}",
        view=f"statcast_leaderboard_{slug}",
        schema=schema or pa.schema([]),
        partition="season",
        keys=(),
        description=f"Ad hoc Baseball Savant {slug} leaderboard (schema inferred).",
        endpoint_doc="sources/statcast.md#2-leaderboards-leaderboardroute",
    )


class StatcastLeaderboardNormalizer:
    """Maps Savant leaderboard payloads onto the strict generated schema of a variant."""

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    def normalize(self, raw_bytes: bytes, slug: str | None = None) -> pa.Table:
        """Typed table for ``slug``; without a slug the types are inferred (ad hoc results only)."""
        defn = BY_SLUG[slug] if slug is not None else None
        payload = (
            html_json_to_csv(raw_bytes, defn.html_var)
            if defn is not None and defn.fmt == "html_json"
            else raw_bytes
        )
        if slug is not None:
            return normalize_csv(
                payload,
                LEADERBOARD_SCHEMAS[slug],
                source="statcast",
                dataset=f"leaderboard_{slug}",
                quarantine=self._quarantine,
            )
        return _infer_table(payload)


def _infer_table(raw: bytes) -> pa.Table:
    """Ad hoc typing: infer each column over the full payload (never persisted to the lake)."""
    table = read_csv_strings(raw)
    columns = []
    names = []
    for name in table.column_names:
        column = table.column(name)
        kind = infer_type_name(column.to_pylist())
        target = {
            "int16": pa.int32(),
            "int32": pa.int32(),
            "int64": pa.int64(),
            "float64": pa.float64(),
        }.get(kind)
        columns.append(column.cast(target) if target is not None else column)
        names.append(snake(name))
    return pa.table(columns, names=names)


@dataclass(frozen=True)
class LeaderboardReport:
    """Outcome of ingesting one variant: rows per season (``None`` = served from cache)."""

    slug: str
    seasons: dict[int, int | None]
    unsupported: str | None = None


class StatcastLeaderboardExtractor:
    """Extracts analytical leaderboards from Baseball Savant with rate limiting and atomic caching."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        catalog.register_all()
        self.cache_config = cache_config or LakeConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.normalizer = StatcastLeaderboardNormalizer()
        self.store = ProcessedStore(self.cache_config)
        self.raw = RawStore(self.cache_config)

    @staticmethod
    def _chunk_id(slug: str, year: int | None) -> str:
        return slug if year is None else f"{slug}_{year}"

    def _manifest(self, slug: str) -> Any:
        return self.cache_config.dataset_manifest("statcast", f"leaderboard_{slug}")

    def _season_of(self, defn: LeaderboardDef, year: int | None) -> int | None:
        return None if defn.year_style == "none" else year

    def _fetch(self, defn: LeaderboardDef, year: int, min_value: str | None) -> bytes:
        url = f"{SAVANT_BASE}/{defn.route}"
        result = self.http.get_sync(url, params=request_params(defn, year, min_value))
        return result.content

    def get_leaderboard(
        self,
        name: str,
        year: int | None = None,
        refresh: bool = False,
        **overrides: Any,
    ) -> pa.Table:
        """Fetch one season of a leaderboard variant as a strictly typed table.

        ``name`` is a variant slug (``expected_statistics_pitcher``) or a legacy name plus
        ``type=`` (``get_leaderboard("expected_statistics", type="pitcher")``). ``min=`` and any
        other override change the population, so the result is returned but not persisted.
        """
        player_type = overrides.get("type")
        defn = resolve(name, str(player_type).lower() if player_type is not None else None)
        if defn.unsupported is not None:
            raise NotImplementedError(
                f"Savant leaderboard {defn.slug!r} is unsupported: {defn.unsupported}"
            )
        year = year if year is not None else self.cache_config.today_or_now().year
        persisted = not {k for k in overrides if k != "type"}
        min_value = str(overrides["min"]) if "min" in overrides else default_min(defn.slug)
        spec = get_dataset("statcast", defn.dataset)
        season = self._season_of(defn, year)
        chunk_id = self._chunk_id(defn.slug, season)
        cache_path = self.store.part_path(spec, chunk_id, season)
        url = f"{SAVANT_BASE}/{defn.route}"

        if persisted:
            entry = self._manifest(defn.slug).get_chunk(manifest_key(chunk_id, season))
            if (
                cache_path.exists()
                and schema_matches(spec, entry)
                and self.cache_config.is_fresh(entry, "leaderboard", season=season, refresh=refresh)
            ):
                with default_audit_logger.track(
                    operation=f"savant_leaderboard_{defn.slug}",
                    source="statcast",
                    endpoint=url,
                    destination=str(cache_path),
                ) as hit:
                    hit.set_cache_hit(True)
                    cached = pq.read_table(cache_path, schema=spec.schema)
                    hit.set_records(len(cached))
                    return cached

        with default_audit_logger.track(
            operation=f"savant_leaderboard_{defn.slug}",
            source="statcast",
            endpoint=url,
            destination=str(cache_path),
        ) as tracker:
            payload = self._fetch(defn, year, min_value)
            table = self.normalizer.normalize(payload, defn.slug)
            if persisted and self.cache_config.enabled:
                suffix = "html" if defn.fmt == "html_json" else "csv"
                self.raw.put(
                    "statcast",
                    spec.name,
                    f"{chunk_id}.{suffix}",
                    payload,
                    season=season,
                    source_ref=url,
                    upstream=response_fingerprint(payload, origin=url),
                )
                self.store.put(spec, table, chunk_id=chunk_id, season=season)
            tracker.set_cache_hit(False)
            tracker.set_records(len(table))
            return table

    def ingest_leaderboard(
        self, name: str, years: list[int] | None = None, refresh: bool = False
    ) -> LeaderboardReport:
        """Ingest every season of one variant from its first season with data (or ``years``)."""
        defn = resolve(name)
        if defn.unsupported is not None:
            return LeaderboardReport(defn.slug, {}, unsupported=defn.unsupported)
        if defn.year_style == "none":
            wanted = [self.cache_config.today_or_now().year]
        elif years is not None:
            wanted = years
        else:
            first = min_year(defn.slug) or self.cache_config.today_or_now().year
            wanted = list(range(first, self.cache_config.today_or_now().year + 1))
        seasons: dict[int, int | None] = {}
        for year in wanted:
            spec = get_dataset("statcast", defn.dataset)
            season = self._season_of(defn, year)
            chunk_id = self._chunk_id(defn.slug, season)
            entry = self._manifest(defn.slug).get_chunk(manifest_key(chunk_id, season))
            cached = self.store.part_path(spec, chunk_id, season).exists() and (
                self.cache_config.is_fresh(entry, "leaderboard", season=season, refresh=refresh)
            )
            table = self.get_leaderboard(defn.slug, year=year, refresh=refresh)
            seasons[year] = None if cached else table.num_rows
        return LeaderboardReport(defn.slug, seasons)

    def ingest_all(
        self, years: list[int] | None = None, refresh: bool = False
    ) -> list[LeaderboardReport]:
        """Ingest every supported variant (unsupported ones are reported with their reason)."""
        reports = [self.ingest_leaderboard(d.slug, years, refresh) for d in SUPPORTED]
        reports.extend(
            LeaderboardReport(d.slug, {}, unsupported=d.unsupported)
            for d in BY_SLUG.values()
            if d.unsupported is not None
        )
        return reports

    def custom_leaderboard(
        self,
        year: int,
        player_type: str = "batter",
        selections: list[str] | None = None,
        min_value: str = "q",
        **params: Any,
    ) -> pa.Table:
        """Savant's custom leaderboard (``selections`` = metric ids). Ad hoc: typed by inference."""
        url = f"{SAVANT_BASE}/custom"
        query: dict[str, str | int] = {
            "year": year,
            "type": player_type,
            "min": min_value,
            "csv": "true",
        }
        if selections:
            query["selections"] = ",".join(selections)
        query.update({k: v for k, v in params.items() if v is not None})
        result = self.http.get_sync(url, params=query)
        return self.normalizer.normalize(result.content)


# Module-level convenience functions
get_default_extractor = lazy_singleton(StatcastLeaderboardExtractor)


def get_leaderboard(
    name: str, year: int | None = None, refresh: bool = False, **kwargs: Any
) -> pa.Table:
    """Extract any Baseball Savant leaderboard variant by slug (or legacy name + ``type=``)."""
    return get_default_extractor().get_leaderboard(name=name, year=year, refresh=refresh, **kwargs)


def custom_leaderboard(
    year: int,
    player_type: str = "batter",
    selections: list[str] | None = None,
    min_value: str = "q",
    **params: Any,
) -> pa.Table:
    """Savant custom leaderboard with arbitrary metric ``selections`` (ad hoc, inferred types)."""
    return get_default_extractor().custom_leaderboard(
        year, player_type, selections, min_value, **params
    )


def expected_statistics(
    year: int = 2024, player_type: str = "batter", refresh: bool = False
) -> pa.Table:
    """Expected Statistics (xBA, xSLG, xwOBA; xERA for pitchers) leaderboard."""
    return get_default_extractor().get_leaderboard(
        f"expected_statistics_{player_type}", year=year, refresh=refresh
    )


def exit_velocity(year: int = 2024, player_type: str = "batter", refresh: bool = False) -> pa.Table:
    """Exit Velocity & Barrels leaderboard (``batter``, ``pitcher``, ``batter_team``, ...)."""
    return get_default_extractor().get_leaderboard(
        f"exit_velocity_{player_type.replace('-', '_')}", year=year, refresh=refresh
    )


def sprint_speed(year: int = 2024, refresh: bool = False) -> pa.Table:
    """Sprint Speed leaderboard."""
    return get_default_extractor().get_leaderboard("sprint_speed", year=year, refresh=refresh)


def bat_tracking(year: int = 2024, refresh: bool = False) -> pa.Table:
    """Bat tracking (bat speed, swing length, squared-up, blasts) leaderboard (2023+)."""
    return get_default_extractor().get_leaderboard("bat_tracking", year=year, refresh=refresh)


def outs_above_average(year: int = 2024, refresh: bool = False) -> pa.Table:
    """Outs Above Average (OAA) defensive leaderboard."""
    return get_default_extractor().get_leaderboard("outs_above_average", year=year, refresh=refresh)
