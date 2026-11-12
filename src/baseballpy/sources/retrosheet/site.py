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
import zipfile
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import pyarrow as pa

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


@dataclass(frozen=True)
class SiteDataset:
    """One typed dataset parsed from a member of a stored site zip (registry name -> where it comes from)."""

    zip_name: str
    member: str
    description: str
    #: upstream header -> column name (the others are snake_cased); files without a header use ``header``
    renames: tuple[tuple[str, str], ...] = ()
    header: str | None = None
    key: tuple[str, ...] = ()
    #: columns holding ``YYYYMMDD`` dates: ``date32`` when every value is a valid date, else text (partial dates such as ``19520000``)
    dates: tuple[str, ...] = ()
    #: columns kept as the upstream text on purpose (partial dates: a ``00`` month or day means "not known")
    text: tuple[str, ...] = ()
    #: many member files of one zip (every member whose name ends with this) become one table; ``member`` is then empty
    suffix: str = ""
    #: a column added from the member's file name (the part before ``suffix``) when the files do not carry the id
    id_column: str = ""
    #: columns that are numbers although a few upstream cells are not (a stray ``?``, a misplaced id): typed from the
    #: numbers; the odd cells are quarantined (and stay in the raw zip), never silently dropped
    numeric: tuple[str, ...] = ()


#: the site datasets of phase 1 (opt-in: a default ingest never contacts retrosheet.org). The column types are
#: generated from the real files by ``scripts/gen_retrosheet_site_schemas.py`` into ``site_tables.py``.
SITE_DATASETS: dict[str, SiteDataset] = {
    "transactions": SiteDataset(
        "tranDB.zip",
        "tran.txt",
        "Transactions database (trades, draft, free agency, injured list, ...), tranDB.zip.",
        header=(
            "primary_date,time,approximate,secondary_date,secondary_approximate,transaction_id,player,"
            "type,from_team,from_league,to_team,to_league,draft_type,draft_round,pick_number,info"
        ),
        #: a trade shares one id across its players, so the id alone is not a key; one exact duplicate row exists upstream (kept)
        key=(
            "transaction_id",
            "player",
            "type",
            "from_team",
            "from_league",
            "to_team",
            "to_league",
            "draft_type",
            "draft_round",
            "pick_number",
            "info",
        ),
        text=("primary_date", "secondary_date"),
    ),
    "managers0": SiteDataset(
        "biodata.zip",
        "managers0.csv",
        "Managers with first and last game dates (biodata.zip managers0.csv).",
        renames=(("id", "manager_id"), ("lastname", "last_name"), ("firstname", "first_name")),
        key=("manager_id",),
        dates=("first_g", "last_g"),
    ),
    "umpires0": SiteDataset(
        "biodata.zip",
        "umpires0.csv",
        "Umpires with first and last game dates (biodata.zip umpires0.csv).",
        renames=(("id", "umpire_id"), ("lastname", "last_name"), ("firstname", "first_name")),
        key=("umpire_id",),
        dates=("first_g", "last_g"),
    ),
    "coaches0": SiteDataset(
        "biodata.zip",
        "coaches0.csv",
        "Coaches by year, team and role (biodata.zip coaches0.csv).",
        renames=(("id", "coach_id"), ("team", "team_id")),
        key=("coach_id", "year", "team_id", "role", "first_g"),
        dates=("first_g", "last_g"),
    ),
    "ballparks0": SiteDataset(
        "biodata.zip",
        "ballparks0.csv",
        "Ballparks with first and last game dates (biodata.zip ballparks0.csv).",
        renames=(("site", "park_id"),),
        key=("park_id",),
        dates=("first_g", "last_g"),
    ),
    "teams0": SiteDataset(
        "biodata.zip",
        "teams0.csv",
        "Teams with first and last game dates (biodata.zip teams0.csv).",
        renames=(("team", "team_id"),),
        key=("team_id", "first_g"),
        dates=("first_g", "last_g"),
    ),
    "player_batting_logs": SiteDataset(
        "playerlogs.zip",
        "",
        "Batting lines of every player game (playerlogs.zip, one file per player: <id>_b.csv).",
        key=("id", "gid", "team", "stattype", "b_lp", "b_seq"),
        dates=("date",),
        suffix="_b.csv",
    ),
    "player_fielding_logs": SiteDataset(
        "playerlogs.zip",
        "",
        "Fielding lines of every player game (playerlogs.zip: <id>_f.csv).",
        key=("id", "gid", "team", "stattype", "d_seq", "d_pos"),
        dates=("date",),
        numeric=("d_pos",),  # upstream: "?" in 11 rows
        suffix="_f.csv",
    ),
    "player_pitching_logs": SiteDataset(
        "playerlogs.zip",
        "",
        "Pitching lines of every player game (playerlogs.zip: <id>_p.csv).",
        key=("id", "gid", "stattype", "p_seq"),
        dates=("date",),
        suffix="_p.csv",
    ),
    "manager_logs": SiteDataset(
        "mgrlogs.zip",
        "",
        "Team lines of every game a manager managed (mgrlogs.zip: <id>_mlog.csv).",
        key=("mgr", "gid", "team", "stattype"),
        dates=("date",),
        numeric=("b_k", "p_k"),  # upstream: one "?" in each
        # a line score keeps its text: "x" means the inning was not played, "?" unknown (as in the game logs)
        text=tuple(f"inn{i}" for i in range(1, 29)),
        suffix="_mlog.csv",
    ),
    "umpire_logs": SiteDataset(
        "umplogs.zip",
        "",
        "Game info and ejections of every game an umpire worked (umplogs.zip: <id>_ulog.csv).",
        key=("umpire_id", "gid", "gs", "inn", "pos"),
        dates=("date",),
        suffix="_ulog.csv",
        id_column="umpire_id",
        numeric=("temp",),  # upstream: "unknown" in 3 rows
    ),
    "negro_players": SiteDataset(
        "negroleagues.zip",
        "allplayers.csv",
        "Negro Leagues players with games by position per team (negroleagues.zip allplayers.csv).",
        renames=(("last", "last_name"), ("first", "first_name")),
        key=("id", "team"),
    ),
    "negro_games": SiteDataset(
        "negroleagues.zip",
        "gameinfo.csv",
        "Negro Leagues game information, one row per game (negroleagues.zip gameinfo.csv).",
        key=("gid",),
        dates=("date",),
    ),
    "negro_team_stats": SiteDataset(
        "negroleagues.zip",
        "teamstats.csv",
        "Negro Leagues team game lines with line scores (negroleagues.zip teamstats.csv).",
        key=("gid", "team", "stattype"),
        text=tuple(
            f"inn{i}" for i in range(1, 29)
        ),  # line scores: x = inning not played, ? unknown
    ),
    "negro_batting": SiteDataset(
        "negroleagues.zip",
        "batting.csv",
        "Negro Leagues batting lines per player game (negroleagues.zip batting.csv).",
        key=("id", "gid", "team", "stattype", "b_lp", "b_seq"),
    ),
    "negro_pitching": SiteDataset(
        "negroleagues.zip",
        "pitching.csv",
        "Negro Leagues pitching lines per player game (negroleagues.zip pitching.csv).",
        key=("id", "gid", "team", "stattype", "p_seq"),
    ),
    "negro_fielding": SiteDataset(
        "negroleagues.zip",
        "fielding.csv",
        "Negro Leagues fielding lines per player game (negroleagues.zip fielding.csv).",
        key=("id", "gid", "team", "stattype", "d_seq", "d_pos"),
    ),
    "negro_plays": SiteDataset(
        "negroleagues.zip",
        "plays.csv",
        "Negro Leagues play-by-play, one row per play (negroleagues.zip plays.csv).",
        key=("gid", "pn"),
    ),
}

_FILES_BY_NAME = {f.name: f for f in SITE_FILES}


def files_for(datasets: Sequence[str]) -> list[SiteFile]:
    """The site files (once each, in order) the named datasets are parsed from."""
    names = dict.fromkeys(SITE_DATASETS[d].zip_name for d in datasets)
    return [_FILES_BY_NAME[n] for n in names]


def _member_names(archive: zipfile.ZipFile, spec: SiteDataset, name: str) -> list[str]:
    """The member files of ``spec`` in the opened zip (the one ``member``, or every file ending with ``suffix``)."""
    wanted = (
        [n for n in archive.namelist() if n.endswith(spec.suffix)] if spec.suffix else [spec.member]
    )
    if not wanted or (not spec.suffix and spec.member not in archive.namelist()):
        raise ValueError(f"{spec.zip_name} has no member for {name} ({spec.suffix or spec.member})")
    return sorted(wanted)


def site_batches(
    config: LakeConfig, name: str, *, batch_members: int = 500
) -> "Iterator[pa.Table]":
    """The typed table of one site dataset in batches of ``batch_members`` member files (no request).

    Each member is read as text, an id column is added from the file name when the dataset says so, a batch is joined
    and mapped onto the registered schema (strict types, quarantine, unknown columns kept in ``_extras``).
    """
    from baseballpy.core.schema_tools import map_to_schema, read_csv_strings
    from baseballpy.sources.retrosheet.schema import RETROSHEET_FLAT_SCHEMAS

    spec = SITE_DATASETS[name]
    raw = RawStore(config)
    if not raw.exists("retrosheet", RAW_DATASET, spec.zip_name):
        raise FileNotFoundError(
            f"{spec.zip_name} is not in the raw lake: fetch it first (baseballpy ingest retrosheet -d {name})"
        )
    schema = RETROSHEET_FLAT_SCHEMAS[name]
    header = spec.header.split(",") if spec.header else None
    path = raw.path_for("retrosheet", RAW_DATASET, spec.zip_name)
    with zipfile.ZipFile(path) as archive:
        members = _member_names(archive, spec, name)
        workers = max(1, config.parse_workers)
        pool = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None

        def parse(member: str, data: bytes) -> pa.Table:
            table = read_csv_strings(data, header=header)
            if spec.id_column:
                stem = PurePosixPath(member).name.removesuffix(spec.suffix)
                table = table.append_column(
                    spec.id_column, pa.array([stem] * table.num_rows, pa.string())
                )
            return table

        try:
            for start in range(0, len(members), batch_members):
                chosen = members[start : start + batch_members]
                # the zip is read one member at a time (one file handle); the parsing, which releases the
                # GIL inside Arrow, runs on the worker threads
                blobs = [(member, archive.read(member)) for member in chosen]
                if pool is None:
                    parts = [parse(m, b) for m, b in blobs]
                else:
                    parts = list(pool.map(lambda mb: parse(*mb), blobs))
                joined = pa.concat_tables(parts, promote_options="default")
                yield map_to_schema(joined, schema, source="retrosheet", dataset=name)
        finally:
            if pool is not None:
                pool.shutdown()


def read_site_datasets(config: LakeConfig, datasets: Sequence[str]) -> "dict[str, pa.Table]":
    """The named site datasets as whole tables (no request; a missing zip raises)."""
    return {name: pa.concat_tables(site_batches(config, name)) for name in datasets}


def site_client(lock_dir: "object | None" = None) -> HttpClient:
    """The gentle client of the site: one request every four seconds, one connection, no retries."""
    from baseballpy import __version__

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
                tracker.mark_download_complete()  # the rest is checking the answer and moving the file
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
    "SITE_DATASETS",
    "SITE_FILES",
    "SiteDataset",
    "files_for",
    "read_site_datasets",
    "site_batches",
    "SITE_HOST",
    "SiteFile",
    "SiteReport",
    "fetch_site_files",
    "site_client",
]
