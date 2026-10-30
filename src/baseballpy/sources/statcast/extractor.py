"""Extractor for Baseball Savant (Statcast) pitch tracking data with chunking and truncation guard."""

import asyncio
import concurrent.futures
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from baseballpy.core.atomic import cleanup_stale_parts
from baseballpy.core.audit import default_audit_logger, get_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.lazy import lazy_singleton
from baseballpy.core.stores import ProcessedStore, RawStore, manifest_key, schema_matches
from baseballpy.core.upstream import response_fingerprint
from baseballpy.sources import catalog
from baseballpy.sources.statcast.normalizer import StatcastNormalizer

logger = logging.getLogger(__name__)

SAVANT_BASE_URL = "https://baseballsavant.mlb.com/statcast_search/csv"
SAVANT_ROW_CAP = 25_000
#: Chunks ending within this many days of today are always revalidated (scoring corrections).
REVALIDATE_TRAILING_DAYS = 3


class TruncatedResultError(RuntimeError):
    """Raised when a single day still hits Savant's row cap (data would be silently truncated)."""


#: first season Savant serves pitch-level data for (PITCHf/x era; probed 2026-10-27)
FIRST_SEASON = 2008
#: first season with minor-league tracking data (probed 2026-10-27: nothing in 2014-2020)
FIRST_MINORS_SEASON = 2021
#: affiliated minor-league sports whose calendars bound the minor-league season
MINOR_SPORTS = (11, 12, 13, 14)
MLB_SEASONS_URL = "https://statsapi.mlb.com/api/v1/seasons"
PITCH_KEY = ("game_pk", "at_bat_number", "pitch_number")
GAME_TYPES = {
    "S": "spring",
    "R": "regular",
    "F": "wild card",
    "D": "division series",
    "L": "league championship",
    "W": "world series",
    "A": "all-star",
}


@dataclass(frozen=True)
class StatcastQuery:
    """Typed filters of a Savant pitch search; every set field changes the returned population.

    Only the unfiltered query is stored in the ``statcast.pitches`` dataset: a filtered result is
    returned to the caller but never written to the lake (it would duplicate pitches).
    """

    game_types: tuple[str, ...] = ()
    team: str | None = None
    player_type: str | None = None
    #: the minor-league population (``minors=true``); its own dataset, ``pitches_minors``
    minors: bool = False
    #: ``hfLevel`` filter (``AAA``, ``A``, ...); only valid together with ``minors``
    levels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.levels and not self.minors:
            raise ValueError("levels filter requires minors=True (hfLevel is ignored otherwise)")
        unknown = [g for g in self.game_types if g not in GAME_TYPES]
        if unknown:
            raise ValueError(
                f"unknown game type(s) {unknown}; expected a subset of {sorted(GAME_TYPES)}"
            )
        if self.player_type not in (None, "batter", "pitcher"):
            raise ValueError("player_type must be 'batter', 'pitcher' or None")

    @property
    def is_unfiltered(self) -> bool:
        """True when the query selects a whole population (MLB, or all minors): it is persisted."""
        return not self.game_types and self.team is None and not self.levels

    def params(self) -> dict[str, str]:
        """Savant query parameters for the set filters."""
        out: dict[str, str] = {}
        if self.minors:
            out["minors"] = "true"
        if self.levels:
            out["hfLevel"] = "".join(f"{level}|" for level in self.levels)
        if self.game_types:
            out["hfGT"] = "".join(f"{g}|" for g in self.game_types)
        if self.team is not None:
            out["team"] = self.team
        if self.player_type is not None:
            out["player_type"] = self.player_type
        return out

    @classmethod
    def from_filters(cls, filters: dict[str, Any]) -> "StatcastQuery":
        """Build from raw keyword filters (legacy ``statcast_search(**filters)`` calls)."""
        known = {"game_types", "team", "player_type", "minors", "levels"}
        extra = set(filters) - known
        if extra:
            raise TypeError(f"unsupported Statcast filter(s) {sorted(extra)}; use {sorted(known)}")
        types = filters.get("game_types") or ()
        return cls(
            game_types=tuple(types),
            team=filters.get("team"),
            player_type=filters.get("player_type"),
            minors=bool(filters.get("minors", False)),
            levels=tuple(filters.get("levels") or ()),
        )


@dataclass(frozen=True)
class StatcastSeasonReport:
    """Outcome of ingesting one season: rows written per chunk (``None`` = served from cache)."""

    season: int
    chunks: int
    rows: int
    cached_chunks: int
    duplicate_keys: int
    skipped_reason: str | None = None


def split_date_range(
    start_date: date, end_date: date, chunk_days: int = 5
) -> list[tuple[date, date]]:
    """Split a date interval into consecutive sub-ranges of at most chunk_days."""
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

    ranges: list[tuple[date, date]] = []
    current = start_date
    delta = timedelta(days=chunk_days - 1)

    while current <= end_date:
        chunk_end = min(current + delta, end_date)
        ranges.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)

    return ranges


def grid_windows(start_date: date, end_date: date, chunk_days: int = 5) -> list[tuple[date, date]]:
    """Windows covering ``start_date..end_date`` on a fixed per-year grid.

    Block *k* of a year is January 1 + k x ``chunk_days`` (the last block is clipped at December
    31), so a given day always belongs to the same window whatever range the caller asked for and
    persisted windows can never overlap (``split_date_range`` anchors at the caller's start).
    """
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")
    windows: list[tuple[date, date]] = []
    current = start_date
    while current <= end_date:
        jan1 = date(current.year, 1, 1)
        block = (current - jan1).days // chunk_days
        block_start = jan1 + timedelta(days=block * chunk_days)
        block_end = min(block_start + timedelta(days=chunk_days - 1), date(current.year, 12, 31))
        windows.append((block_start, block_end))
        current = block_end + timedelta(days=1)
    return windows


def _to_date(value: str | date) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date() if isinstance(value, str) else value


class StatcastExtractor:
    """Extracts pitch-level tracking data from Baseball Savant with chunking and row-cap bisection."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        chunk_days: int = 5,
        http: HttpClient | None = None,
    ) -> None:
        catalog.register_all()
        self.cache_config = cache_config or LakeConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.chunk_days = chunk_days
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.normalizer = StatcastNormalizer()
        self.spec = get_dataset("statcast", "pitches")
        self.spec_minors = get_dataset("statcast", "pitches_minors")
        self.store = ProcessedStore(self.cache_config)
        self.raw = RawStore(self.cache_config)
        self.manifest = self.cache_config.dataset_manifest("statcast", "pitches")
        self.manifest_minors = self.cache_config.dataset_manifest("statcast", "pitches_minors")
        # discard orphaned .part files from killed runs
        cleanup_stale_parts(self.cache_config.raw_root / "statcast")
        cleanup_stale_parts(self.cache_config.processed_root / "statcast")

    def _spec(self, minors: bool) -> DatasetSpec:
        return self.spec_minors if minors else self.spec

    def _today(self) -> date:
        return self.cache_config.today or datetime.now().date()

    @staticmethod
    def _chunk_id(start_dt: date, end_dt: date) -> str:
        """Deterministic chunk id: ``<start>_<end>`` (only unfiltered chunks are persisted)."""
        return f"{start_dt.isoformat()}_{end_dt.isoformat()}"

    def _get_cache_path(self, start_dt: date, end_dt: date, minors: bool = False) -> Path:
        """Path of the processed part for a date chunk (``season=YYYY/part-<chunk>.parquet``)."""
        return self.store.part_path(
            self._spec(minors), self._chunk_id(start_dt, end_dt), start_dt.year
        )

    def _is_chunk_fresh(
        self,
        chunk_id: str,
        cache_path: Path,
        start_dt: date,
        end_dt: date,
        refresh: bool,
        minors: bool = False,
    ) -> tuple[bool, int]:
        """Return (fresh, recorded_row_count) per the freshness policy."""
        manifest = self.manifest_minors if minors else self.manifest
        entry = manifest.get_chunk(manifest_key(chunk_id, start_dt.year))
        if entry is None:
            return False, 0
        rows = int(entry.get("records_count", 0) or 0)
        if rows > 0 and not cache_path.exists():
            return False, rows
        if not schema_matches(self._spec(minors), entry):
            return False, rows  # written under another schema or parser revision (ADR 49, 51)
        if end_dt >= self._today() - timedelta(days=REVALIDATE_TRAILING_DAYS) and (
            start_dt.year >= self._today().year
        ):
            return False, rows
        fresh = self.cache_config.is_fresh(entry, "statcast", season=start_dt.year, refresh=refresh)
        return fresh, rows

    async def _fetch_window(self, start_dt: date, end_dt: date, query: StatcastQuery) -> pa.Table:
        """Fetch a window; bisect when Savant's 25,000-row cap is reached (never truncates)."""
        params: dict[str, Any] = {
            "all": "true",
            "type": "details",
            "game_date_gt": start_dt.isoformat(),
            "game_date_lt": end_dt.isoformat(),
        }
        params.update(query.params())
        result = await self.http.get(SAVANT_BASE_URL, params=params)
        table = self.normalizer.normalize(result.content)
        if len(table) < SAVANT_ROW_CAP:
            if self.cache_config.enabled and query.is_unfiltered and len(table) > 0:
                self.raw.put(
                    "statcast",
                    "pitches_minors" if query.minors else "pitches",
                    f"{self._chunk_id(start_dt, end_dt)}.csv",
                    result.content,
                    season=start_dt.year,
                    source_ref=SAVANT_BASE_URL,
                    etag=result.etag or "",
                    upstream=response_fingerprint(result.content, result.etag, SAVANT_BASE_URL),
                )
            return table
        if start_dt >= end_dt:
            raise TruncatedResultError(
                f"Savant returned {len(table)} rows (the cap) for the single day {start_dt}; "
                "data would be truncated"
            )
        mid = start_dt + (end_dt - start_dt) // 2
        get_audit_logger().log(_bisect_event(start_dt, end_dt, len(table)))
        left = await self._fetch_window(start_dt, mid, query)
        right = await self._fetch_window(mid + timedelta(days=1), end_dt, query)
        return pa.concat_tables([left, right], promote_options="default")

    async def _fetch_chunk(
        self,
        start_dt: date,
        end_dt: date,
        refresh: bool = False,
        query: StatcastQuery | None = None,
    ) -> tuple[pa.Table, bool]:
        """Fetch/normalize one date chunk; returns (table, served_from_cache)."""
        query = query or StatcastQuery()
        persisted = self.cache_config.enabled and query.is_unfiltered
        spec = self._spec(query.minors)
        cache_path = self._get_cache_path(start_dt, end_dt, query.minors)
        chunk_id = self._chunk_id(start_dt, end_dt)

        if persisted:
            fresh, rows = self._is_chunk_fresh(
                chunk_id, cache_path, start_dt, end_dt, refresh, query.minors
            )
            if fresh:
                if rows == 0:
                    return spec.schema.empty_table(), True
                return pq.read_table(cache_path, schema=spec.schema), True

        table = await self._fetch_window(start_dt, end_dt, query)

        if persisted:
            # zero-row chunks are written too, so an empty day is never re-fetched and every
            # season keeps a stable schema for the views
            self.store.put(spec, table, chunk_id=chunk_id, season=start_dt.year)
        return table, False

    async def extract_async(
        self,
        start_date: str | date,
        end_date: str | date,
        refresh: bool = False,
        query: StatcastQuery | None = None,
        **filters: Any,
    ) -> pa.Table:
        """Asynchronously extract and concat all date chunks for the requested range."""
        query = query or StatcastQuery.from_filters(filters)
        start, end = _to_date(start_date), _to_date(end_date)
        chunks = grid_windows(start, end, chunk_days=self.chunk_days)
        gate = asyncio.Semaphore(self.rate_limit_config.max_concurrency)

        async def _bounded(s: date, e: date) -> tuple[pa.Table, bool]:
            async with gate:
                return await self._fetch_chunk(s, e, refresh=refresh, query=query)

        async with default_audit_logger.async_track(
            operation="statcast_extract",
            source="statcast",
            endpoint=SAVANT_BASE_URL,
            destination=str(self.store.dataset_dir(self._spec(query.minors))),
        ) as tracker:
            results = await asyncio.gather(*[_bounded(s, e) for s, e in chunks])
            tables = [table for table, _ in results]
            tracker.set_cache_hit(bool(results) and all(hit for _, hit in results))

            if not tables:
                table = self._spec(query.minors).schema.empty_table()
            else:
                table = pa.concat_tables(tables, promote_options="default")
            # whole grid windows are fetched and stored; the caller gets exactly its days
            if table.num_rows and "game_date" in table.column_names:
                days = table.column("game_date")
                inside = pc.and_(
                    pc.greater_equal(days, pa.scalar(start, pa.date32())),
                    pc.less_equal(days, pa.scalar(end, pa.date32())),
                )
                table = table.filter(inside)
            if self.cache_config.enabled and query.is_unfiltered:
                for year in sorted({s.year for s, _ in chunks}):
                    surplus = self.duplicate_keys(year, query.minors)
                    if surplus:
                        logger.warning(
                            "statcast.%s season %s has %s duplicate pitch keys",
                            self._spec(query.minors).name,
                            year,
                            surplus,
                        )

            tracker.set_records(len(table))
            return table

    def extract(
        self,
        start_date: str | date,
        end_date: str | date,
        refresh: bool = False,
        query: StatcastQuery | None = None,
        **filters: Any,
    ) -> pa.Table:
        """Synchronously extract Statcast pitch data (safe for Jupyter/sync scripts)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.extract_async(start_date, end_date, refresh=refresh, query=query, **filters)
            )
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(
                    self.extract_async(
                        start_date, end_date, refresh=refresh, query=query, **filters
                    )
                )
            ).result()

    # ------------------------------------------------------------------ season ingestion

    def _minor_window(self, season: int) -> tuple[date, date]:
        """Union of the affiliated minor-league calendars (sports 11-14) of a season."""
        cache = self.cache_config.http_cache_root / "mlb-seasons" / f"minors-{season}.json"
        if cache.exists():
            record = json.loads(cache.read_text(encoding="utf-8"))
            return _to_date(record["start"]), min(_to_date(record["end"]), self._today())
        starts: list[date] = []
        ends: list[date] = []
        for sport in MINOR_SPORTS:
            result = self.http.get_sync(
                MLB_SEASONS_URL, params={"sportId": sport, "season": season}
            )
            for item in json.loads(result.content).get("seasons", []):
                begin = item.get("springStartDate") or item.get("regularSeasonStartDate")
                finish = item.get("postSeasonEndDate") or item.get("seasonEndDate")
                if begin and finish:
                    starts.append(_to_date(begin))
                    ends.append(_to_date(finish))
        if not starts:
            raise ValueError(f"MLB Stats API has no minor-league season {season}")
        first, last = min(starts), max(ends)
        if season < self._today().year:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps({"start": first.isoformat(), "end": last.isoformat()}),
                encoding="utf-8",
            )
        return first, min(last, self._today())

    def season_window(self, season: int, minors: bool = False) -> tuple[date, date]:
        """First and last day of a season's games (spring training to the end of the postseason).

        Read from the MLB Stats API ``/v1/seasons?season=<year>`` (``minors``: the union of the
        affiliated minor-league calendars) and cached under ``cache/http/mlb-seasons`` (past
        seasons never change).
        """
        if minors:
            return self._minor_window(season)
        cache = self.cache_config.http_cache_root / "mlb-seasons" / f"{season}.json"
        if cache.exists():
            record = json.loads(cache.read_text(encoding="utf-8"))
        else:
            result = self.http.get_sync(MLB_SEASONS_URL, params={"sportId": 1, "season": season})
            seasons = json.loads(result.content).get("seasons", [])
            if not seasons:
                raise ValueError(f"MLB Stats API has no season {season}")
            record = seasons[0]
            if season < self._today().year:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(record), encoding="utf-8")
        start = record.get("springStartDate") or record.get("regularSeasonStartDate")
        end = record.get("postSeasonEndDate") or record.get("seasonEndDate")
        if not start or not end:
            raise ValueError(f"MLB season {season} has no start/end dates: {record}")
        return _to_date(start), min(_to_date(end), self._today())

    def ingest_season(
        self, season: int, refresh: bool = False, minors: bool = False
    ) -> StatcastSeasonReport:
        """Ingest every pitch of one season (spring training through the postseason).

        Windows come from the MLB season calendar, each is fetched/bisected independently and
        written as its own part, so a re-run only fetches what is missing or still volatile.
        ``minors`` ingests the minor-league population into ``pitches_minors`` (2021 onwards;
        earlier seasons are reported as skipped without any request).
        """
        if minors and season < FIRST_MINORS_SEASON:
            reason = (
                f"no minor-league tracking data before {FIRST_MINORS_SEASON} (probed 2026-10-27)"
            )
            logger.info("pitches_minors season %s skipped: %s", season, reason)
            return StatcastSeasonReport(season, 0, 0, 0, 0, skipped_reason=reason)
        return asyncio.run(self._ingest_season_async(season, refresh, minors))

    async def _ingest_season_async(
        self, season: int, refresh: bool, minors: bool = False
    ) -> StatcastSeasonReport:
        start, end = self.season_window(season, minors)
        query = StatcastQuery(minors=minors)
        windows = grid_windows(start, end, chunk_days=self.chunk_days)
        gate = asyncio.Semaphore(self.rate_limit_config.max_concurrency)

        async def _one(s: date, e: date) -> tuple[int, bool]:
            async with gate:
                table, hit = await self._fetch_chunk(s, e, refresh=refresh, query=query)
                return table.num_rows, hit

        results = await asyncio.gather(*[_one(s, e) for s, e in windows])
        duplicates = self.duplicate_keys(season, minors)
        if duplicates:
            logger.warning(
                "statcast.%s season %s has %s duplicate (game_pk, at_bat_number, pitch_number) keys",
                self._spec(minors).name,
                season,
                duplicates,
            )
        return StatcastSeasonReport(
            season=season,
            chunks=len(results),
            rows=sum(rows for rows, _ in results),
            cached_chunks=sum(1 for _, hit in results if hit),
            duplicate_keys=duplicates,
        )

    def ingest_all(
        self,
        start: int | None = None,
        end: int | None = None,
        refresh: bool = False,
        minors: bool = False,
    ) -> list[StatcastSeasonReport]:
        """Ingest ``start..end`` seasons (default: first season with data to today), resumable."""
        first = start if start is not None else (FIRST_MINORS_SEASON if minors else FIRST_SEASON)
        last = end if end is not None else self._today().year
        return [self.ingest_season(season, refresh, minors) for season in range(first, last + 1)]

    def duplicate_keys(self, season: int, minors: bool = False) -> int:
        """Number of surplus rows sharing a pitch key within a season (0 when keys are unique)."""
        files = sorted(self.store.dataset_dir(self._spec(minors), season).glob("part-*.parquet"))
        if not files:
            return 0
        table = pa.concat_tables(
            [pq.read_table(f, columns=list(PITCH_KEY)) for f in files], promote_options="default"
        )
        grouped = table.group_by(list(PITCH_KEY)).aggregate([([], "count_all")])
        return int(pc.sum(pc.subtract(grouped["count_all"], 1)).as_py() or 0)


def _bisect_event(start: date, end: date, rows: int) -> Any:
    from baseballpy.core.audit import AuditEvent

    now = datetime.now().astimezone().isoformat()
    return AuditEvent(
        timestamp_utc=now,
        operation="statcast_row_cap_bisect",
        source="statcast",
        status="RETRY",
        records_count=rows,
        endpoint=SAVANT_BASE_URL,
        destination=f"{start.isoformat()}..{end.isoformat()}",
        error="row_cap_bisect",
    )


get_default_extractor = lazy_singleton(StatcastExtractor)


def statcast_search(
    start_date: str | date,
    end_date: str | date,
    refresh: bool = False,
    query: StatcastQuery | None = None,
    **filters: Any,
) -> pa.Table:
    """Synchronously extract Statcast pitch data (safe for Jupyter and scripts).

    ``query`` (or the equivalent ``game_types=``/``team=``/``player_type=`` keywords) narrows the
    search; a filtered result is returned but never written to the lake.
    """
    return get_default_extractor().extract(
        start_date=start_date, end_date=end_date, refresh=refresh, query=query, **filters
    )


def ingest_season(season: int, refresh: bool = False, minors: bool = False) -> StatcastSeasonReport:
    """Ingest one full season of pitches (``minors``: minor-league pitches) into the lake."""
    return get_default_extractor().ingest_season(season, refresh=refresh, minors=minors)


def ingest_all(
    start: int | None = None,
    end: int | None = None,
    refresh: bool = False,
    minors: bool = False,
) -> list[StatcastSeasonReport]:
    """Ingest the seasons ``start..end`` of pitches into the lake (resumable)."""
    return get_default_extractor().ingest_all(start, end, refresh, minors)
