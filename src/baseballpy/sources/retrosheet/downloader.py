"""Tree-driven downloader for Retrosheet data from the pinned GitHub mirror.

The git tree at the pinned commit decides which seasons and files exist. Files are fetched with
bounded concurrency through the shared HttpClient, stored atomically with a recorded sha256, a 404
for a file the tree lists is recorded ``ABSENT`` (never success), and a season is COMPLETED only
when every file the tree lists for it is present.
"""

import concurrent.futures
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from baseballpy.core.atomic import ManifestTracker, cleanup_stale_parts
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.github_tree import fetch_tree
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.sources_lock import SourceRef, get_source_ref
from baseballpy.core.stores import RawStore
from baseballpy.sources.retrosheet.tree import (
    POSTSEASON_GAMELOG_KINDS,
    RetroFile,
    RetroTree,
    classify,
)

logger = logging.getLogger(__name__)

#: Default (pinned) base URL; instances derive theirs from the lock / env override.
GITHUB_RETROSHEET_BASE = get_source_ref("retrosheet").raw_base()


class FetchOutcome(StrEnum):
    """Result of trying to obtain one remote file."""

    DOWNLOADED = "downloaded"
    CACHED = "cached"
    ABSENT = "absent"  # the tree lists it but upstream answered 404


@dataclass
class SeasonDownload:
    """Result of :meth:`RetrosheetDownloader.download_season`."""

    year: int
    files: list[RetroFile] = field(default_factory=list)
    outcomes: dict[str, FetchOutcome] = field(default_factory=dict)
    complete: bool = False
    cache_hit: bool = False

    @property
    def absent(self) -> list[str]:
        """Names of tree-listed files that upstream does not serve."""
        return sorted(n for n, o in self.outcomes.items() if o is FetchOutcome.ABSENT)


class RetrosheetDownloader:
    """Downloads raw Retrosheet files for any season the pinned tree lists."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
        ref: str | None = None,
    ) -> None:
        self.cache_config = cache_config or LakeConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        locked = get_source_ref("retrosheet", self.cache_config.home)
        self.source_ref = SourceRef(locked.key, locked.repo, ref) if ref else locked
        self.base_url = self.source_ref.raw_base()
        self.raw = RawStore(self.cache_config)
        #: season completeness chunks (``season_<year>``) live in the event_files manifest
        self.manifest = self.cache_config.dataset_manifest("retrosheet", "event_files", "raw")
        self._tree: RetroTree | None = None
        # discard orphaned .part files from killed runs
        cleanup_stale_parts(self.cache_config.raw_root / "retrosheet")

    # ------------------------------------------------------------------ discovery
    def tree(self, refresh: bool = False) -> RetroTree:
        """The classified repository tree (cached in memory and under ``cache/http``)."""
        if self._tree is None or refresh:
            entries = fetch_tree(self.source_ref, self.cache_config, self.http, refresh=refresh)
            self._tree = classify(entries)
            if self._tree.uncovered:
                logger.warning(
                    "Retrosheet tree has %d file(s) no dataset covers yet (first: %s)",
                    len(self._tree.uncovered),
                    self._tree.uncovered[0],
                )
        return self._tree

    def seasons(self) -> list[int]:
        """Seasons available upstream at the pinned ref."""
        return self.tree().seasons()

    # ------------------------------------------------------------------ paths
    def raw_path(self, file: RetroFile) -> Path:
        """Where ``file`` is (or will be) stored under ``raw/retrosheet``."""
        return self.raw.path_for("retrosheet", file.raw_dataset, file.name, file.season)

    def local_paths(self, year: int, *kinds: str) -> list[Path]:
        """Existing local raw paths for the season's files of the given kinds, sorted by name."""
        files = self.tree().season_files(year, kinds or None)
        return sorted(p for f in files if (p := self.raw_path(f)).exists())

    def roster_dir(self, year: int) -> Path:
        """``raw/retrosheet/rosters/season=YYYY`` (the ``*.ROS`` files)."""
        return self.cache_config.raw_dir("retrosheet", "rosters", year)

    # ------------------------------------------------------------------ files
    def _chunk_current(self, manifest: ManifestTracker, chunk_id: str) -> bool:
        """COMPLETED and not recorded at a different upstream ref (legacy entries are trusted)."""
        entry = manifest.get_chunk(chunk_id)
        if entry is None or entry.get("status") != "COMPLETED":
            return False
        return entry.get("source_ref") in (None, self.source_ref.ref)

    def _is_cached(self, file: RetroFile) -> bool:
        path = self.raw_path(file)
        if not path.exists() or path.stat().st_size == 0:
            return False
        entry = self.cache_config.dataset_manifest(
            "retrosheet", file.raw_dataset, "raw", file.season
        ).get_chunk(file.name)
        if entry is None:
            return False  # not recorded: could be a partial leftover from an old layout
        return bool(
            entry.get("status") == "COMPLETED"
            and entry.get("source_ref") in (None, self.source_ref.ref)
            and entry.get("bytes") == path.stat().st_size
        )

    def download_file(self, file: RetroFile, refresh: bool = False) -> FetchOutcome:
        """Atomically fetch one tree-listed file; 404 is recorded ``ABSENT``."""
        if not refresh and self._is_cached(file):
            return FetchOutcome.CACHED
        result = self.http.get_sync(f"{self.base_url}/{file.path}", allow=(200, 404))
        if result.status == 404:
            self.cache_config.dataset_manifest(
                "retrosheet", file.raw_dataset, "raw", file.season
            ).set_absent(file.name, "listed in the git tree but not served")
            return FetchOutcome.ABSENT
        self.raw.put(
            "retrosheet",
            file.raw_dataset,
            file.name,
            result.content,
            season=file.season,
            source_ref=self.source_ref.ref,
            etag=result.etag or "",
        )
        return FetchOutcome.DOWNLOADED

    def download_files(
        self, files: Sequence[RetroFile], refresh: bool = False
    ) -> dict[str, FetchOutcome]:
        """Download files with bounded concurrency; errors other than 404 propagate."""
        workers = max(1, self.rate_limit_config.max_concurrency)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {f.path: pool.submit(self.download_file, f, refresh) for f in files}
            return {path: future.result() for path, future in futures.items()}

    # ------------------------------------------------------------------ seasons
    def download_season(
        self,
        year: int,
        kinds: Iterable[str] | None = None,
        refresh: bool = False,
    ) -> SeasonDownload:
        """Download the season's files (all kinds, or just ``kinds``).

        The ``season_<year>`` chunk is recorded COMPLETED only for an all-kinds download in which
        every tree-listed file is present; otherwise missing files are recorded ``ABSENT`` and a
        later run retries. A season the tree does not list yields an empty, incomplete result.
        """
        chunk_id = f"season_{year}"
        all_files = self.tree().season_files(year)
        wanted = self.tree().season_files(year, kinds)
        result = SeasonDownload(year=year, files=wanted)
        with default_audit_logger.track(
            operation="retrosheet_download_season",
            source="retrosheet",
            endpoint=f"{self.base_url}/seasons/{year}/",
            destination=str(self.cache_config.raw_dir("retrosheet", "event_files", year)),
        ) as tracker:
            if not all_files:
                self.manifest.set_absent(chunk_id, f"season {year} is not in the upstream tree")
                tracker.set_records(0)
                return result

            if (
                kinds is None
                and not refresh
                and self._chunk_current(self.manifest, chunk_id)
                and all(self.raw_path(f).exists() for f in wanted)
            ):
                result.outcomes = {f.name: FetchOutcome.CACHED for f in wanted}
                result.complete = result.cache_hit = True
                tracker.set_cache_hit(True)
                tracker.set_records(len(wanted))
                return result

            outcomes = self.download_files(wanted, refresh)
            result.outcomes = {f.name: outcomes[f.path] for f in wanted}
            missing = result.absent
            result.complete = not missing and len(wanted) == len(all_files)
            if kinds is None:
                if missing:
                    logger.warning(
                        "retrosheet season %s incomplete: %d file(s) absent upstream: %s",
                        year,
                        len(missing),
                        ", ".join(missing[:10]),
                    )
                    self.manifest.set_absent(chunk_id, f"missing files: {', '.join(missing)}")
                else:
                    total = sum(self.raw_path(f).stat().st_size for f in wanted)
                    self.manifest.set_completed(
                        chunk_id,
                        records_count=len(wanted),
                        metadata={"source_ref": self.source_ref.ref, "bytes": total},
                    )
            tracker.set_cache_hit(False)
            tracker.set_records(len(wanted))
            return result

    # ------------------------------------------------------------------ single files
    def _single(self, file: RetroFile | None, what: str, refresh: bool) -> Path:
        if file is None:
            raise FileNotFoundError(f"Retrosheet {what} is not in the upstream tree")
        outcome = self.download_file(file, refresh)
        if outcome is FetchOutcome.ABSENT:
            raise FileNotFoundError(f"Retrosheet {what} ({file.path}) is listed but not served")
        return self.raw_path(file)

    def download_gamelog(self, year: int, refresh: bool = False) -> Path:
        """Download the season's game log ``GL<year>.TXT``."""
        file = next(iter(self.tree().season_files(year, ["gamelog"])), None)
        return self._single(file, f"game log for {year}", refresh)

    def download_postseason_gamelog(self, kind: str, refresh: bool = False) -> Path:
        """Download a postseason/all-star game log (wild_card, division_series, lcs, ...)."""
        if kind.lower() not in POSTSEASON_GAMELOG_KINDS:
            valid = list(POSTSEASON_GAMELOG_KINDS)
            raise ValueError(f"Unknown postseason gamelog kind '{kind}'. Valid kinds: {valid}")
        return self._single(self.tree().postseason_gamelog(kind), f"{kind} game log", refresh)

    def download_reference_table(self, table_name: str, refresh: bool = False) -> Path:
        """Download ``reference/<table_name>.csv``."""
        file = self.tree().reference_file(table_name)
        if file is None:
            known = sorted(f.name.removesuffix(".csv") for f in self.tree().reference)
            raise ValueError(f"Unknown reference table '{table_name}'. Valid tables: {known}")
        return self._single(file, f"reference table {table_name}", refresh)
