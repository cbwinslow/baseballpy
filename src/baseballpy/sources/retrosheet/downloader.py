"""Downloader for Retrosheet data from the GitHub mirror with atomic, honest caching."""

import concurrent.futures
import logging
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

from baseballpy.core.atomic import ManifestTracker, atomic_write
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig
from baseballpy.core.http import HttpClient, get_http_client

logger = logging.getLogger(__name__)

GITHUB_RETROSHEET_BASE = "https://raw.githubusercontent.com/chadwickbureau/retrosheet/master"

POSTSEASON_GAMELOGS = {
    "wild_card": "GLWC.TXT",
    "division_series": "GLDV.TXT",
    "lcs": "GLLC.TXT",
    "world_series": "GLWS.TXT",
    "all_star": "GLAS.TXT",
}

REFERENCE_TABLES = {
    "ballparks": "reference/ballparks.csv",
    "teams": "reference/teams.csv",
    "ejections": "reference/ejections.csv",
    "coaches": "reference/coaches.csv",
    "relatives": "reference/relatives.csv",
    "biofile": "reference/biofile.csv",
}

POSTSEASON_SUFFIXES = (
    "AS.EVE",
    "ALW1.EVE",
    "ALW2.EVE",
    "NLW1.EVE",
    "NLW2.EVE",
    "ALD1.EVE",
    "ALD2.EVE",
    "NLD1.EVE",
    "NLD2.EVE",
    "ALCS.EVE",
    "NLCS.EVE",
    "WS.EVE",
)


class FetchOutcome(StrEnum):
    """Result of trying to obtain one remote file."""

    DOWNLOADED = "downloaded"
    CACHED = "cached"
    ABSENT = "absent"  # upstream answered 404: the file does not exist


def _count_lines(path: Path) -> int:
    """Count newline characters without loading the file into memory."""
    total = 0
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            total += block.count(b"\n")
    return total


class RetrosheetDownloader:
    """Downloads raw Retrosheet event files, rosters, and game logs with atomic writes."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.base_url = GITHUB_RETROSHEET_BASE
        self.raw_dir = self.cache_config.retrosheet_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = ManifestTracker(self.raw_dir / "manifest.json")

    def _get_season_dir(self, year: int) -> Path:
        path = self.raw_dir / str(year)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def download_file(
        self, relative_url: str, target_path: Path, refresh: bool = False
    ) -> FetchOutcome:
        """Atomically download one file; reports whether it was fetched, cached, or absent."""
        if not refresh and target_path.exists() and target_path.stat().st_size > 0:
            return FetchOutcome.CACHED

        full_url = f"{self.base_url}/{relative_url.lstrip('/')}"
        result = self.http.get_sync(full_url, allow=(200, 404))
        if result.status == 404:
            return FetchOutcome.ABSENT
        with atomic_write(target_path) as part_file:
            part_file.write_bytes(result.content)
        return FetchOutcome.DOWNLOADED

    def _download_many(
        self, items: Sequence[tuple[str, Path]], refresh: bool
    ) -> dict[Path, FetchOutcome]:
        """Download files with bounded concurrency; errors other than 404 propagate."""
        workers = max(1, self.rate_limit_config.max_concurrency)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                path: pool.submit(self.download_file, rel, path, refresh) for rel, path in items
            }
            return {path: future.result() for path, future in futures.items()}

    def download_season(
        self, year: int, include_postseason: bool = False, refresh: bool = False
    ) -> list[Path]:
        """Download season manifest TEAM{year}, event files (.EVA/.EVN/.EVE), and rosters.

        The season is recorded COMPLETED only when TEAM{year} and every listed event and
        roster file are present. Otherwise it is recorded ABSENT with the missing files so a
        later run retries instead of trusting an incomplete season.
        """
        chunk_id = f"season_{year}_postseason" if include_postseason else f"season_{year}"
        season_dir = self._get_season_dir(year)

        with default_audit_logger.track(
            operation="retrosheet_download_season",
            source="retrosheet",
            endpoint=f"{self.base_url}/seasons/{year}/",
            destination=str(season_dir),
        ) as tracker:
            if not refresh and self.manifest.is_completed(chunk_id):
                tracker.set_cache_hit(True)
                event_files = sorted(season_dir.glob("*.EV*"))
                tracker.set_records(len(event_files))
                return event_files

            team_file = season_dir / f"TEAM{year}"
            team_outcome = self.download_file(
                f"seasons/{year}/TEAM{year}", team_file, refresh=refresh
            )
            if team_outcome is FetchOutcome.ABSENT:
                self.manifest.set_absent(chunk_id, f"TEAM{year} not found upstream")
                tracker.set_records(0)
                return []

            wanted: list[tuple[str, Path]] = []
            event_paths: list[Path] = []
            roster_paths: list[Path] = []
            for line in team_file.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = [p.strip() for p in line.strip().split(",")]
                if not parts or not parts[0]:
                    continue
                team_code = parts[0]
                league = parts[1] if len(parts) > 1 else "A"
                ext = "EVA" if league.upper() == "A" else "EVN"
                event_name = f"{year}{team_code}.{ext}"
                roster_name = f"{team_code}{year}.ROS"
                event_paths.append(season_dir / event_name)
                roster_paths.append(season_dir / roster_name)
                wanted.append((f"seasons/{year}/{event_name}", season_dir / event_name))
                wanted.append((f"seasons/{year}/{roster_name}", season_dir / roster_name))

            outcomes = self._download_many(wanted, refresh)
            missing = sorted(
                p.name for p in event_paths + roster_paths if outcomes[p] is FetchOutcome.ABSENT
            )

            downloaded_files = [p for p in event_paths if outcomes[p] is not FetchOutcome.ABSENT]

            if include_postseason:
                post_items = [
                    (f"seasons/{year}/{year}{suffix}", season_dir / f"{year}{suffix}")
                    for suffix in POSTSEASON_SUFFIXES
                ]
                post_outcomes = self._download_many(post_items, refresh)
                # Postseason files are optional by nature (series differ by year).
                downloaded_files.extend(
                    p for p, outcome in post_outcomes.items() if outcome is not FetchOutcome.ABSENT
                )

            if missing:
                logger.warning(
                    "retrosheet season %s incomplete: %d file(s) absent upstream: %s",
                    year,
                    len(missing),
                    ", ".join(missing[:10]),
                )
                self.manifest.set_absent(chunk_id, f"missing files: {', '.join(missing)}")
            else:
                self.manifest.set_completed(chunk_id, records_count=len(downloaded_files))
            tracker.set_cache_hit(False)
            tracker.set_records(len(downloaded_files))
            return downloaded_files

    def _download_single(
        self,
        chunk_id: str,
        candidates: Sequence[str],
        target_path: Path,
        operation: str,
        refresh: bool,
    ) -> Path:
        """Fetch the first existing candidate; raise FileNotFoundError if none exists."""
        with default_audit_logger.track(
            operation=operation,
            source="retrosheet",
            endpoint=f"{self.base_url}/{candidates[0]}",
            destination=str(target_path),
        ) as tracker:
            if not refresh and self.manifest.is_completed(chunk_id) and target_path.exists():
                tracker.set_cache_hit(True)
                tracker.set_records(_count_lines(target_path))
                return target_path

            for candidate in candidates:
                outcome = self.download_file(candidate, target_path, refresh=refresh)
                if outcome is not FetchOutcome.ABSENT:
                    lines = _count_lines(target_path)
                    self.manifest.set_completed(chunk_id, records_count=lines)
                    tracker.set_cache_hit(False)
                    tracker.set_records(lines)
                    return target_path

            self.manifest.set_absent(chunk_id, f"none of {list(candidates)} exist upstream")
            raise FileNotFoundError(
                f"Retrosheet file not found upstream (tried {', '.join(candidates)})"
            )

    def download_gamelog(self, year: int, refresh: bool = False) -> Path:
        """Download historical season Game Log GL{year}.TXT (case variants are tried)."""
        gamelog_dir = self.raw_dir / "gamelogs"
        gamelog_dir.mkdir(parents=True, exist_ok=True)
        return self._download_single(
            chunk_id=f"gamelog_{year}",
            candidates=[
                f"seasons/{year}/GL{year}.TXT",
                f"seasons/{year}/gl{year}.txt",
                f"gamelog/gl{year}.txt",
                f"gamelog/GL{year}.TXT",
            ],
            target_path=gamelog_dir / f"gl{year}.txt",
            operation="retrosheet_download_gamelog",
            refresh=refresh,
        )

    def download_postseason_gamelog(self, kind: str, refresh: bool = False) -> Path:
        """Download postseason or exhibition game log (wild_card, division_series, lcs, ...)."""
        filename = POSTSEASON_GAMELOGS.get(kind.lower())
        if not filename:
            raise ValueError(
                f"Unknown postseason gamelog kind '{kind}'. Valid kinds: {list(POSTSEASON_GAMELOGS.keys())}"
            )
        gamelog_dir = self.raw_dir / "gamelogs"
        gamelog_dir.mkdir(parents=True, exist_ok=True)
        return self._download_single(
            chunk_id=f"gamelog_postseason_{kind.lower()}",
            candidates=[f"gamelog/{filename}"],
            target_path=gamelog_dir / filename,
            operation="retrosheet_download_postseason_gamelog",
            refresh=refresh,
        )

    def download_reference_table(self, table_name: str, refresh: bool = False) -> Path:
        """Download a reference CSV (ballparks, teams, ejections, coaches, relatives, biofile)."""
        rel_path = REFERENCE_TABLES.get(table_name.lower())
        if not rel_path:
            raise ValueError(
                f"Unknown reference table '{table_name}'. Valid tables: {list(REFERENCE_TABLES.keys())}"
            )
        ref_dir = self.raw_dir / "reference"
        ref_dir.mkdir(parents=True, exist_ok=True)
        return self._download_single(
            chunk_id=f"reference_{table_name.lower()}",
            candidates=[rel_path],
            target_path=ref_dir / f"{table_name.lower()}.csv",
            operation="retrosheet_download_reference",
            refresh=refresh,
        )
