"""Retrosheet's own bulk files from retrosheet.org, fetched politely (change retrosheet-site-files).

The Chadwick GitHub mirror is the main way into Retrosheet's event data; the site also publishes files the mirror does
not carry (transactions, the CSV bundles, player and manager logs, official daily totals). An earlier run was banned for
hitting the site many times, so this fetcher is deliberately gentle:

* ``robots.txt`` is read first and obeyed (it disallows ``/boxesetc/`` and ``/gamelogs/``: never requested);
* one connection and one request every four seconds, with a User-Agent that names the library (no personal data);
* the first 403, 429, 503 or connection error stops the whole run and is reported; nothing is retried;
* a file already stored is skipped; each file is stored with its sha256; every download is audit-logged and timed.

Retrosheet's notice allows any use of the data with the attribution "The information used here was obtained free of
charge from and is copyrighted by Retrosheet." and says nothing about automated access. Event files (``/events/``) are
not in this table: they come from the mirror.
"""

import logging
import shutil
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from baseballpy import __version__
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import HttpClient, HttpStatusError, TransportError
from baseballpy.core.stores import RawStore

logger = logging.getLogger(__name__)

SITE_HOST = "www.retrosheet.org"
BASE_URL = f"https://{SITE_HOST}"
#: one request every four seconds
REQUESTS_PER_SECOND = 0.25
#: answers that mean "slow down or go away": the run stops
_STOP_STATUSES = (403, 429, 503)
RAW_DATASET = "site_files"
#: a file larger than this is not read (it is listed as failed; the owner decides)
DEFAULT_MAX_BYTES = 3 * 1024**3
#: the run stops before a download when the disk has less free space than this
DEFAULT_MIN_FREE_BYTES = 4 * 1024**3


@dataclass(frozen=True)
class SiteFile:
    """One bulk file of the site (``path`` is relative to the site root)."""

    group: str
    path: str
    note: str = ""

    @property
    def url(self) -> str:
        """The absolute URL."""
        return f"{BASE_URL}/{self.path}"

    @property
    def name(self) -> str:
        """The stored file name (the last path part)."""
        return PurePosixPath(self.path).name


def _core() -> tuple[SiteFile, ...]:
    items = (
        (
            "downloads/biodata.zip",
            "biographical files: biofile, biofile0, relatives, coaches, ballparks, managers, teams, umpires",
        ),
        (
            "downloads/playerlogs.zip",
            "player logs for all players (batting, pitching, fielding with an eject column)",
        ),
        (
            "downloads/mgrlogs.zip",
            "manager logs for all managers (team stats with an eject column)",
        ),
        (
            "downloads/umplogs.zip",
            "umpire logs for all umpires (game info with an ejections column)",
        ),
        ("biofile.zip", "player, manager, coach and umpire ids"),
        ("rosters.zip", "annual rosters"),
        ("ballparks.zip", "ballpark codes"),
        ("teams.zip", "franchise and team ids"),
        ("ejections.zip", "a complete listing of known ejections"),
        ("schedule/schedule.zip", "every season's original schedule in one file"),
        ("transactions/tranDB.zip", "the transactions database"),
        ("transactions/readme.txt", "layout of the transaction files"),
        ("GameFiles.pdf", "description of the game account files"),
    )
    return tuple(SiteFile("core", path, note) for path, note in items)


def _bundles() -> tuple[SiteFile, ...]:
    items = (("downloads/negroleagues.zip", "the Negro Leagues CSV download (seven CSV files)"),)
    return tuple(SiteFile("bundles", path, note) for path, note in items)


def _event_csvs() -> tuple[SiteFile, ...]:
    """CSV bundles dominated by ``plays.csv``, the parsed play-by-play: event data, so not fetched by default."""
    items = (
        (
            "downloads/csvdownloads.zip",
            "the main CSV download: allplayers, gameinfo, teamstats, batting, pitching, fielding, plays",
        ),
        ("downloads/basiccsvs.zip", "the simplified CSV files"),
    )
    return tuple(SiteFile("event_csvs", path, note) for path, note in items)


def _discrepancies() -> tuple[SiteFile, ...]:
    return tuple(
        SiteFile("discrepancies", f"{decade}sdis.zip", "discrepancy files of the decade")
        for decade in range(1890, 1990, 10)
    )


def _official_totals() -> tuple[SiteFile, ...]:
    leagues = (
        ("AA", range(1882, 1892)),
        ("UA", (1884,)),
        ("PL", (1890,)),
        ("FL", (1914, 1915)),
        ("AL", range(1901, 1981)),
        ("NL", range(1891, 1981)),
    )
    return tuple(
        SiteFile(
            "officialtotals", f"officialtotals/{year}{league}.zip", "official daily totals ledger"
        )
        for league, years in leagues
        for year in years
    )


SITE_FILES: tuple[SiteFile, ...] = (
    *_core(),
    *_bundles(),
    *_event_csvs(),
    *_discrepancies(),
    *_official_totals(),
)


def site_client(lock_dir: "object | None" = None) -> HttpClient:
    """The gentle client of the site: one request every four seconds, one connection, no retries."""
    rates = RateLimitConfig(
        default_requests_per_second=REQUESTS_PER_SECOND,
        host_rates={SITE_HOST: REQUESTS_PER_SECOND},
        max_concurrency=1,
        max_retries=0,
    )
    agent = f"baseballpy/{__version__} (polite bulk download of Retrosheet's published files)"
    return HttpClient(rates, user_agent=agent, lock_dir=lock_dir)  # type: ignore[arg-type]


@dataclass
class SiteReport:
    """What one fetch run did."""

    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    bytes: int = 0
    stopped: str = ""


def _robots(client: HttpClient) -> urllib.robotparser.RobotFileParser:
    """The site's robots.txt (one request); no file means everything is allowed."""
    parser = urllib.robotparser.RobotFileParser()
    result = client.get_sync(f"{BASE_URL}/robots.txt", allow=(200, 404))
    if result.status == 200:
        parser.parse(result.content.decode("utf-8", errors="replace").splitlines())
    else:
        parser.parse([])
    return parser


def fetch_site_files(
    client: HttpClient,
    config: LakeConfig,
    files: "list[SiteFile] | tuple[SiteFile, ...]",
    *,
    refresh: bool = False,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
) -> SiteReport:
    """Fetch ``files`` into ``raw/retrosheet/site_files/`` as the module docstring says."""
    report = SiteReport()
    raw = RawStore(config)
    robots = _robots(client)
    for item in files:
        if not robots.can_fetch("baseballpy", item.url):
            report.blocked.append(item.path)
            logger.warning("robots.txt disallows %s: not requested", item.url)
            continue
        if not refresh and raw.exists("retrosheet", RAW_DATASET, item.name):
            report.skipped.append(item.path)
            continue
        target = raw.path_for("retrosheet", RAW_DATASET, item.name)
        free_probe = target.parent if target.parent.exists() else config.raw_root
        free_probe.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(free_probe).free < min_free_bytes:
            report.stopped = (
                f"low disk space: less than {min_free_bytes / 1024**3:.0f} GB free, stopped"
            )
            break
        staging = target.with_name(target.name + ".download")
        try:
            with default_audit_logger.track(
                operation="retrosheet_site_download",
                source="retrosheet",
                endpoint=item.url,
                destination=str(target),
            ) as tracker:
                result = client.download_sync(
                    item.url, staging, max_bytes=max_bytes, allow=(200, 404, *_STOP_STATUSES)
                )
                if result.status in _STOP_STATUSES:
                    raise HttpStatusError(item.url, result.status)
                if result.status == 404:
                    report.failed[item.path] = "404 not found"
                    continue
                if result.too_large:
                    report.failed[item.path] = (
                        f"too large: {result.content_length} bytes, the limit is {max_bytes}"
                    )
                    continue
                raw.adopt(
                    "retrosheet",
                    RAW_DATASET,
                    item.name,
                    staging,
                    sha256=result.sha256,
                    size=result.size,
                    source_ref=item.url,
                    etag=result.etag or "",
                )
                tracker.set_records(1)
        except HttpStatusError as exc:
            report.stopped = f"{exc.status} from {item.url}: stopped, nothing else requested"
            break
        except TransportError as exc:
            report.stopped = (
                f"connection error on {item.url} ({exc}): stopped, nothing else requested"
            )
            break
        report.downloaded.append(item.path)
        report.bytes += result.size
    return report


__all__ = [
    "BASE_URL",
    "SITE_FILES",
    "SITE_HOST",
    "SiteFile",
    "SiteReport",
    "fetch_site_files",
    "site_client",
]
