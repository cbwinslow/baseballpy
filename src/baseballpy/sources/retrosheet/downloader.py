"""Downloader for Retrosheet data from GitHub mirror with atomic caching."""

from pathlib import Path

import httpx

from baseballpy.core.atomic import ManifestTracker, atomic_write
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig

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


class RetrosheetDownloader:
    """Downloads raw Retrosheet event files, rosters, and game logs with atomic writes."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.base_url = GITHUB_RETROSHEET_BASE
        self.raw_dir = self.cache_config.retrosheet_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = ManifestTracker(self.raw_dir / "manifest.json")

    def _get_season_dir(self, year: int) -> Path:
        path = self.raw_dir / str(year)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def download_file(self, relative_url: str, target_path: Path, refresh: bool = False) -> bool:
        """Atomically download a single file if not present or refreshed."""
        if not refresh and target_path.exists() and target_path.stat().st_size > 0:
            return False

        full_url = f"{self.base_url}/{relative_url.lstrip('/')}"
        with httpx.Client(timeout=self.rate_limit_config.timeout_seconds) as client:
            resp = client.get(full_url)
            if resp.status_code == 404:
                return False
            resp.raise_for_status()

            with atomic_write(target_path) as part_file:
                part_file.write_bytes(resp.content)

        return True

    def download_season(
        self, year: int, include_postseason: bool = False, refresh: bool = False
    ) -> list[Path]:
        """Download season manifest TEAM{year}, event files (.EVA/.EVN/.EVE), and rosters."""
        chunk_id = f"season_{year}"
        season_dir = self._get_season_dir(year)

        with default_audit_logger.track(
            operation="retrosheet_download_season",
            source="retrosheet",
            endpoint=f"{self.base_url}/seasons/{year}/",
            destination=str(season_dir),
        ) as tracker:
            if not refresh and self.manifest.is_completed(chunk_id):
                tracker.set_cache_hit(True)
                event_files = list(season_dir.glob("*.EV*"))
                tracker.set_records(len(event_files))
                return event_files

            # 1. Download TEAM manifest
            team_file = season_dir / f"TEAM{year}"
            self.download_file(f"seasons/{year}/TEAM{year}", team_file, refresh=refresh)

            downloaded_files: list[Path] = []
            if team_file.exists():
                lines = team_file.read_text(encoding="utf-8", errors="replace").splitlines()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    team_code = parts[0].strip()
                    league = parts[1].strip() if len(parts) > 1 else "A"

                    # Event extension: .EVA for American, .EVN for National
                    ext = "EVA" if league.upper() == "A" else "EVN"
                    event_filename = f"{year}{team_code}.{ext}"
                    roster_filename = f"{team_code}{year}.ROS"

                    event_path = season_dir / event_filename
                    roster_path = season_dir / roster_filename

                    self.download_file(
                        f"seasons/{year}/{event_filename}", event_path, refresh=refresh
                    )
                    self.download_file(
                        f"seasons/{year}/{roster_filename}", roster_path, refresh=refresh
                    )

                    if event_path.exists():
                        downloaded_files.append(event_path)

            # 2. Optionally download postseason and all-star event files (.EVE)
            if include_postseason:
                postseason_suffixes = [
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
                ]
                for suffix in postseason_suffixes:
                    ps_filename = f"{year}{suffix}"
                    ps_path = season_dir / ps_filename
                    if (
                        self.download_file(f"seasons/{year}/{ps_filename}", ps_path, refresh=refresh)
                        and ps_path.exists()
                    ):
                        downloaded_files.append(ps_path)

            self.manifest.set_completed(chunk_id, records_count=len(downloaded_files))
            tracker.set_cache_hit(False)
            tracker.set_records(len(downloaded_files))
            return downloaded_files

    def download_gamelog(self, year: int, refresh: bool = False) -> Path:
        """Download historical season Game Log gl{year}.txt."""
        chunk_id = f"gamelog_{year}"
        gamelog_dir = self.raw_dir / "gamelogs"
        gamelog_dir.mkdir(parents=True, exist_ok=True)
        target_path = gamelog_dir / f"gl{year}.txt"

        with default_audit_logger.track(
            operation="retrosheet_download_gamelog",
            source="retrosheet",
            endpoint=f"{self.base_url}/gamelog/gl{year}.txt",
            destination=str(target_path),
        ) as tracker:
            if not refresh and self.manifest.is_completed(chunk_id) and target_path.exists():
                tracker.set_cache_hit(True)
                tracker.set_records(
                    target_path.read_text(encoding="utf-8", errors="replace").count("\n")
                )
                return target_path

            self.download_file(f"gamelog/gl{year}.txt", target_path, refresh=refresh)
            lines_count = (
                target_path.read_text(encoding="utf-8", errors="replace").count("\n")
                if target_path.exists()
                else 0
            )
            self.manifest.set_completed(chunk_id, records_count=lines_count)
            tracker.set_cache_hit(False)
            tracker.set_records(lines_count)
            return target_path

    def download_postseason_gamelog(self, kind: str, refresh: bool = False) -> Path:
        """Download postseason or exhibition game log (wild_card, division_series, lcs, world_series, all_star)."""
        filename = POSTSEASON_GAMELOGS.get(kind.lower())
        if not filename:
            raise ValueError(
                f"Unknown postseason gamelog kind '{kind}'. Valid kinds: {list(POSTSEASON_GAMELOGS.keys())}"
            )

        chunk_id = f"gamelog_postseason_{kind.lower()}"
        gamelog_dir = self.raw_dir / "gamelogs"
        gamelog_dir.mkdir(parents=True, exist_ok=True)
        target_path = gamelog_dir / filename

        with default_audit_logger.track(
            operation="retrosheet_download_postseason_gamelog",
            source="retrosheet",
            endpoint=f"{self.base_url}/gamelog/{filename}",
            destination=str(target_path),
        ) as tracker:
            if not refresh and self.manifest.is_completed(chunk_id) and target_path.exists():
                tracker.set_cache_hit(True)
                tracker.set_records(
                    target_path.read_text(encoding="utf-8", errors="replace").count("\n")
                )
                return target_path

            self.download_file(f"gamelog/{filename}", target_path, refresh=refresh)
            lines_count = (
                target_path.read_text(encoding="utf-8", errors="replace").count("\n")
                if target_path.exists()
                else 0
            )
            self.manifest.set_completed(chunk_id, records_count=lines_count)
            tracker.set_cache_hit(False)
            tracker.set_records(lines_count)
            return target_path

    def download_reference_table(self, table_name: str, refresh: bool = False) -> Path:
        """Download a reference CSV (ballparks, teams, ejections, coaches, relatives, biofile)."""
        rel_path = REFERENCE_TABLES.get(table_name.lower())
        if not rel_path:
            raise ValueError(
                f"Unknown reference table '{table_name}'. Valid tables: {list(REFERENCE_TABLES.keys())}"
            )

        chunk_id = f"reference_{table_name.lower()}"
        ref_dir = self.raw_dir / "reference"
        ref_dir.mkdir(parents=True, exist_ok=True)
        target_path = ref_dir / f"{table_name.lower()}.csv"

        with default_audit_logger.track(
            operation="retrosheet_download_reference",
            source="retrosheet",
            endpoint=f"{self.base_url}/{rel_path}",
            destination=str(target_path),
        ) as tracker:
            if not refresh and self.manifest.is_completed(chunk_id) and target_path.exists():
                tracker.set_cache_hit(True)
                tracker.set_records(
                    target_path.read_text(encoding="utf-8", errors="replace").count("\n")
                )
                return target_path

            self.download_file(rel_path, target_path, refresh=refresh)
            lines_count = (
                target_path.read_text(encoding="utf-8", errors="replace").count("\n")
                if target_path.exists()
                else 0
            )
            self.manifest.set_completed(chunk_id, records_count=lines_count)
            tracker.set_cache_hit(False)
            tracker.set_records(lines_count)
            return target_path
