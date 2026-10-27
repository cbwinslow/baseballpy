"""Migrate a v1 data lake (``cache/<source>/...``) to layout v2 (``raw/`` + ``processed/``).

The migration copies (never moves unless ``delete_old``), verifies row counts and byte
equality after each copy, carries the v1 manifest entries over so freshness decisions keep
working, skips files already present with identical content (idempotent), reports files it
does not recognise, and stamps ``VERSION`` only when everything else succeeded.
"""

import hashlib
import json
import logging
import re
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from baseballpy.core.atomic import ManifestTracker, atomic_write, atomic_write_parquet
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LAYOUT_VERSION, LakeConfig
from baseballpy.core.layout import V1_SOURCE_DIRS, detect_layout, v1_cache_root, write_version
from baseballpy.core.stores import PARQUET_COMPRESSION, manifest_key

logger = logging.getLogger(__name__)

Tier = Literal["raw", "processed"]
Kind = Literal["copy", "events_postseason"]

_YEAR_FILE = re.compile(r"(\d{4})")
_LEADERBOARD_STEM = re.compile(r"^(?P<name>[a-z0-9_]+?)_(?P<year>\d{4})(?:_(?P<params>.*))?$")
_SEASON_DIR = re.compile(r"^season=(\d{4})$")


@dataclass(frozen=True)
class ManifestMove:
    """One v1 manifest entry to carry into a v2 dataset manifest."""

    old_manifest: Path
    old_key: str
    tier: Tier
    source: str
    dataset: str
    new_key: str


@dataclass(frozen=True)
class Step:
    """Copy one v1 file to its v2 location."""

    src: Path
    dst: Path
    tier: Tier
    source: str
    dataset: str
    kind: Kind = "copy"
    manifests: tuple[ManifestMove, ...] = ()


@dataclass
class MigrationReport:
    """What a migration did (or would do, when ``dry_run``)."""

    dry_run: bool
    home: Path
    steps: list[Step] = field(default_factory=list)
    copied: list[Step] = field(default_factory=list)
    skipped: list[Step] = field(default_factory=list)
    unknown: list[Path] = field(default_factory=list)
    manifest_entries: int = 0
    rows_verified: int = 0
    postseason_duplicate_rows_dropped: int = 0
    deleted_files: int = 0
    version_written: bool = False
    already_migrated: bool = False

    def summary_rows(self) -> list[tuple[str, int]]:
        """``(label, count)`` rows for a summary table."""
        return [
            (
                "planned" if self.dry_run else "copied",
                len(self.steps if self.dry_run else self.copied),
            ),
            ("skipped (identical)", len(self.skipped)),
            ("unknown (left in place)", len(self.unknown)),
            ("manifest entries carried", self.manifest_entries),
            ("rows verified", self.rows_verified),
            ("duplicate postseason rows dropped", self.postseason_duplicate_rows_dropped),
            ("v1 files deleted", self.deleted_files),
        ]


class MigrationError(RuntimeError):
    """Raised when verification of a copied file fails; v1 data is left untouched."""


def _season_dirs(path: Path) -> Iterator[tuple[int, Path]]:
    if not path.is_dir():
        return
    for child in sorted(path.iterdir()):
        match = _SEASON_DIR.match(child.name)
        if child.is_dir() and match:
            yield int(match.group(1)), child


def _files(path: Path, pattern: str = "*") -> list[Path]:
    return (
        sorted(p for p in path.glob(pattern) if p.is_file() and p.suffix != ".part")
        if path.is_dir()
        else []
    )


class _Planner:
    """Builds the list of copy steps from a v1 tree and records unrecognised files."""

    def __init__(self, config: LakeConfig) -> None:
        self.config = config
        self.root = v1_cache_root(config)
        self.steps: list[Step] = []
        self.claimed: set[Path] = set()

    def _add(
        self,
        src: Path,
        tier: Tier,
        source: str,
        dataset: str,
        dst_rel: str,
        season: int | None = None,
        kind: Kind = "copy",
        manifests: tuple[ManifestMove, ...] = (),
    ) -> None:
        base = (
            self.config.raw_dir(source, dataset, season)
            if tier == "raw"
            else self.config.processed_dir(source, dataset, season)
        )
        self.steps.append(Step(src, base / dst_rel, tier, source, dataset, kind, manifests))
        self.claimed.add(src)

    @staticmethod
    def _mm(
        old: Path, key: str, tier: Tier, source: str, dataset: str, new_key: str
    ) -> tuple[ManifestMove, ...]:
        return (ManifestMove(old, key, tier, source, dataset, new_key),)

    # -- statcast ---------------------------------------------------------------------
    def statcast(self) -> None:
        base = self.root / "statcast"
        manifest = base / "manifest.json"
        for season, directory in _season_dirs(base):
            for f in _files(directory, "*.parquet"):
                self._add(
                    f,
                    "processed",
                    "statcast",
                    "pitches",
                    f"part-{f.stem}.parquet",
                    season,
                    manifests=self._mm(
                        manifest,
                        f.stem,
                        "processed",
                        "statcast",
                        "pitches",
                        manifest_key(f.stem, season),
                    ),
                )
        for f in _files(
            base, "*.parquet"
        ):  # legacy flat chunk files: <start>_<end>[_filters].parquet
            match = _YEAR_FILE.match(f.stem)
            if not match:
                continue
            season = int(match.group(1))
            self._add(
                f,
                "processed",
                "statcast",
                "pitches",
                f"part-{f.stem}.parquet",
                season,
                manifests=self._mm(
                    manifest,
                    f.stem,
                    "processed",
                    "statcast",
                    "pitches",
                    manifest_key(f.stem, season),
                ),
            )
        lb_dir = base / "leaderboards"
        lb_manifest = lb_dir / "manifest.json"
        for f in _files(lb_dir, "*.parquet"):
            match = _LEADERBOARD_STEM.match(f.stem)
            if not match:
                continue
            name, year = match["name"], int(match["year"])
            chunk = f.stem.replace("=", "-")
            dataset = f"leaderboard_{name}"
            self._add(
                f,
                "processed",
                "statcast",
                dataset,
                f"part-{chunk}.parquet",
                year,
                manifests=self._mm(
                    lb_manifest, f.stem, "processed", "statcast", dataset, manifest_key(chunk, year)
                ),
            )

    # -- retrosheet -------------------------------------------------------------------
    def retrosheet(self) -> None:
        raw = self.root / "retrosheet" / "raw"
        raw_manifest = raw / "manifest.json"
        for child in sorted(raw.iterdir()) if raw.is_dir() else []:
            if child.is_dir() and re.fullmatch(r"\d{4}", child.name):
                year = int(child.name)
                for f in _files(child):
                    if f.suffix.upper() == ".ROS":
                        self._add(f, "raw", "retrosheet", "rosters", f.name, year)
                    else:
                        self._add(f, "raw", "retrosheet", "event_files", f.name, year)
                for key in (f"season_{year}", f"season_{year}_postseason"):
                    self._attach_manifest(
                        "retrosheet", "event_files", "raw", raw_manifest, key, key
                    )
        for f in _files(raw / "gamelogs"):
            self._add(f, "raw", "retrosheet", "gamelogs", f.name)
        for f in _files(raw / "reference"):
            self._add(
                f,
                "raw",
                "retrosheet",
                f"reference_{f.stem}",
                f.name,
                manifests=self._mm(
                    raw_manifest,
                    f"reference_{f.stem}",
                    "raw",
                    "retrosheet",
                    f"reference_{f.stem}",
                    f"reference_{f.stem}",
                ),
            )

        proc = self.root / "retrosheet" / "processed"
        proc_manifest = proc / "manifest.json"
        simple: dict[str, tuple[str, Callable[[int], str]]] = {
            "boxscores_batting": ("batting", lambda y: f"box_batting_{y}"),
            "boxscores_pitching": ("pitching", lambda y: f"box_pitching_{y}"),
            "daily_splits": ("daily_splits", lambda y: f"daily_splits_{y}"),
            "substitutions": ("substitutions", lambda y: f"substitutions_{y}"),
        }
        for dataset, (chunk, old_key) in simple.items():
            for season, directory in _season_dirs(proc / dataset):
                for f in _files(directory, "*.parquet"):
                    new_chunk = f.stem if f.stem != chunk else chunk
                    self._add(
                        f,
                        "processed",
                        "retrosheet",
                        dataset,
                        f"part-{new_chunk}.parquet",
                        season,
                        manifests=self._mm(
                            proc_manifest,
                            old_key(season),
                            "processed",
                            "retrosheet",
                            dataset,
                            manifest_key(new_chunk, season),
                        ),
                    )
        for season, directory in _season_dirs(proc / "events"):
            events = directory / "events.parquet"
            if events.is_file():
                self._add(
                    events,
                    "processed",
                    "retrosheet",
                    "events",
                    "part-events.parquet",
                    season,
                    manifests=self._mm(
                        proc_manifest,
                        f"events_{season}",
                        "processed",
                        "retrosheet",
                        "events",
                        manifest_key("events", season),
                    ),
                )
            events_all = directory / "events_all.parquet"
            if events_all.is_file():
                self._add(
                    events_all,
                    "processed",
                    "retrosheet",
                    "events_postseason",
                    "part-events.parquet",
                    season,
                    kind="events_postseason",
                    manifests=self._mm(
                        proc_manifest,
                        f"events_{season}_postseason",
                        "processed",
                        "retrosheet",
                        "events_postseason",
                        manifest_key("events", season),
                    ),
                )
        gl_dir = proc / "gamelogs"
        for f in _files(gl_dir, "gl*.parquet"):
            match = _YEAR_FILE.search(f.stem)
            if match:
                year = int(match.group(1))
                self._add(
                    f,
                    "processed",
                    "retrosheet",
                    "gamelogs",
                    f"part-{f.stem}.parquet",
                    year,
                    manifests=self._mm(
                        proc_manifest,
                        f"gamelogs_{year}",
                        "processed",
                        "retrosheet",
                        "gamelogs",
                        manifest_key(f.stem, year),
                    ),
                )
        for f in _files(gl_dir / "postseason", "gl_*.parquet"):
            kind = f.stem.removeprefix("gl_")
            self._add(
                f,
                "processed",
                "retrosheet",
                "gamelogs_postseason",
                f"part-{kind}.parquet",
                manifests=self._mm(
                    proc_manifest,
                    f"gamelogs_postseason_{kind}",
                    "processed",
                    "retrosheet",
                    "gamelogs_postseason",
                    kind,
                ),
            )
        for f in _files(proc / "rosters", "rosters_*.parquet"):
            match = _YEAR_FILE.search(f.stem)
            if match:
                year = int(match.group(1))
                self._add(
                    f,
                    "processed",
                    "retrosheet",
                    "rosters",
                    f"part-{f.stem}.parquet",
                    year,
                    manifests=self._mm(
                        proc_manifest,
                        f"rosters_{year}",
                        "processed",
                        "retrosheet",
                        "rosters",
                        manifest_key(f.stem, year),
                    ),
                )
        for f in _files(proc / "reference", "*.parquet"):
            self._add(
                f,
                "processed",
                "retrosheet",
                f"reference_{f.stem}",
                "part-data.parquet",
                manifests=self._mm(
                    proc_manifest,
                    f"reference_{f.stem}",
                    "processed",
                    "retrosheet",
                    f"reference_{f.stem}",
                    "data",
                ),
            )

    def _attach_manifest(
        self, source: str, dataset: str, tier: Tier, old: Path, old_key: str, new_key: str
    ) -> None:
        """Attach a manifest entry to the first matching step (so it is counted/carried once)."""
        for i, step in enumerate(self.steps):
            if step.source == source and step.dataset == dataset and step.tier == tier:
                move = ManifestMove(old, old_key, tier, source, dataset, new_key)
                self.steps[i] = Step(
                    step.src,
                    step.dst,
                    step.tier,
                    step.source,
                    step.dataset,
                    step.kind,
                    (*step.manifests, move),
                )
                return

    # -- lahman -----------------------------------------------------------------------
    def lahman(self) -> None:
        base = self.root / "lahman"
        manifest = base / "manifest.json"
        for f in _files(base / "raw", "*.csv"):
            self._add(
                f,
                "raw",
                "lahman",
                f.stem,
                f.name,
                manifests=self._mm(manifest, f.stem, "raw", "lahman", f.stem, f.stem),
            )
        for f in _files(base / "processed", "*.parquet"):
            self._add(f, "processed", "lahman", f.stem, "part-data.parquet")

    # -- chadwick ---------------------------------------------------------------------
    def chadwick(self) -> None:
        base = self.root / "chadwick"
        manifest = base / "manifest.json"
        for f in _files(base / "shards", "people-*.csv"):
            self._add(f, "raw", "chadwick", "register", f.name)
        for name, dataset in (
            ("names.csv", "register_names"),
            ("links.csv", "register_links"),
            ("countries.csv", "register_countries"),
        ):
            if (base / name).is_file():
                self._add(base / name, "raw", "chadwick", dataset, name)
        self._attach_manifest("chadwick", "register", "raw", manifest, "commit_sha", "commit_sha")
        for old, dataset in (
            ("people.parquet", "register"),
            ("names.parquet", "register_names"),
            ("links.parquet", "register_links"),
        ):
            if (base / old).is_file():
                self._add(base / old, "processed", "chadwick", dataset, "part-data.parquet")
        # an earlier layout wrote processed/register.parquet
        if (base / "processed" / "register.parquet").is_file():
            self._add(
                base / "processed" / "register.parquet",
                "processed",
                "chadwick",
                "register",
                "part-data.parquet",
            )

    # -- mlb_api ----------------------------------------------------------------------
    def mlb_api(self) -> None:
        base = self.root / "mlb_api"
        manifest = base / "manifest.json"

        def season_of(stem: str) -> int | None:
            match = re.search(r"_(\d{4})", stem)
            return int(match.group(1)) if match else None

        flat_year_datasets = {
            "schedule": "schedule",
            "standings": "standings",
            "transactions": "transactions",
            "draft": "draft",
        }
        for category, dataset in flat_year_datasets.items():
            for f in _files(base / category, "*.parquet"):
                season = season_of(f.stem)
                if season is None:
                    continue
                self._add(
                    f,
                    "processed",
                    "mlb_api",
                    dataset,
                    f"part-{f.stem}.parquet",
                    season,
                    manifests=self._mm(
                        manifest,
                        f.stem,
                        "processed",
                        "mlb_api",
                        dataset,
                        manifest_key(f.stem, season),
                    ),
                )
        for category, dataset in (("teams", "teams"), ("venues", "venues"), ("rosters", "rosters")):
            for f in _files(base / category, "*.parquet"):
                self._add(
                    f,
                    "processed",
                    "mlb_api",
                    dataset,
                    f"part-{f.stem}.parquet",
                    manifests=self._mm(manifest, f.stem, "processed", "mlb_api", dataset, f.stem),
                )
        seasons = self._game_pk_seasons(base / "schedule")
        for category, dataset in (
            ("boxscores_batting", "box_batting"),
            ("boxscores_pitching", "box_pitching"),
        ):
            for f in _files(base / category, "*.parquet"):
                try:
                    season = seasons[int(f.stem)]
                except (KeyError, ValueError):
                    continue  # season cannot be determined: reported as unknown, never guessed
                moves: tuple[ManifestMove, ...] = ()
                if dataset == "box_batting":
                    moves = (
                        ManifestMove(
                            manifest,
                            f"box_{f.stem}",
                            "processed",
                            "mlb_api",
                            dataset,
                            f"box_{f.stem}",
                        ),
                    )
                self._add(
                    f,
                    "processed",
                    "mlb_api",
                    dataset,
                    f"part-{f.stem}.parquet",
                    season,
                    manifests=moves,
                )

    @staticmethod
    def _game_pk_seasons(schedule_dir: Path) -> dict[int, int]:
        mapping: dict[int, int] = {}
        for f in _files(schedule_dir, "*.parquet"):
            try:
                table = pq.read_table(f, columns=["game_pk", "season"])
            except (OSError, pa.ArrowInvalid, KeyError):
                logger.warning("could not read %s to map game_pk to season", f)
                continue
            for pk, season in zip(
                table["game_pk"].to_pylist(), table["season"].to_pylist(), strict=True
            ):
                if pk is not None and season is not None:
                    mapping[int(pk)] = int(season)
        return mapping

    def unknown_files(self) -> list[Path]:
        """v1 files that no rule claimed (excluding manifests, locks and part files)."""
        unknown: list[Path] = []
        for name in V1_SOURCE_DIRS:
            for f in sorted((self.root / name).rglob("*") if (self.root / name).is_dir() else []):
                if not f.is_file() or f in self.claimed:
                    continue
                if (
                    f.name == "manifest.json"
                    or f.name.endswith((".lock", ".part"))
                    or ".corrupt-" in f.name
                ):
                    continue
                unknown.append(f)
        return unknown


def plan_migration(config: LakeConfig) -> tuple[list[Step], list[Path]]:
    """Compute the copy plan and the unknown (unmapped) v1 files without touching disk."""
    planner = _Planner(config)
    planner.statcast()
    planner.retrosheet()
    planner.lahman()
    planner.chadwick()
    planner.mlb_api()
    return planner.steps, planner.unknown_files()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _same_file(a: Path, b: Path) -> bool:
    return b.exists() and a.stat().st_size == b.stat().st_size and _sha256(a) == _sha256(b)


def _rows(path: Path) -> int:
    return int(pq.ParquetFile(path).metadata.num_rows)


def _copy_verified(step: Step, report: MigrationReport) -> None:
    """Copy one file atomically and verify bytes (and parquet row counts)."""
    with atomic_write(step.dst) as part:
        shutil.copyfile(step.src, part)
    if _sha256(step.src) != _sha256(step.dst):
        raise MigrationError(f"checksum mismatch after copying {step.src} -> {step.dst}")
    if step.dst.suffix == ".parquet":
        src_rows, dst_rows = _rows(step.src), _rows(step.dst)
        if src_rows != dst_rows:
            raise MigrationError(f"row count {src_rows} != {dst_rows} for {step.dst}")
        report.rows_verified += dst_rows


def _migrate_events_postseason(step: Step, report: MigrationReport) -> None:
    """``events_all`` held regular + postseason rows: keep only games absent from ``events``."""
    table = pq.read_table(step.src)
    regular = (
        step.dst.parent.parent.parent / "events" / step.dst.parent.name / "part-events.parquet"
    )
    regular_src = step.src.with_name("events.parquet")
    reference = regular if regular.exists() else regular_src
    if reference.exists() and "GAME_ID" in table.column_names:
        regular_ids = pq.read_table(reference, columns=["GAME_ID"])["GAME_ID"]
        keep = pc.invert(pc.is_in(table["GAME_ID"], value_set=regular_ids))
        filtered = table.filter(keep)
    else:
        filtered = table
    dropped = table.num_rows - filtered.num_rows
    report.postseason_duplicate_rows_dropped += dropped
    if filtered.num_rows == 0:
        return
    if step.dst.exists() and _rows(step.dst) == filtered.num_rows:
        report.skipped.append(step)
        return
    atomic_write_parquet(filtered, step.dst, compression=PARQUET_COMPRESSION)
    if _rows(step.dst) != filtered.num_rows:
        raise MigrationError(f"row count mismatch for {step.dst}")
    report.rows_verified += filtered.num_rows
    report.copied.append(step)


def _carry_manifests(step: Step, config: LakeConfig) -> int:
    carried = 0
    for move in step.manifests:
        if not move.old_manifest.is_file():
            continue
        try:
            chunks = json.loads(move.old_manifest.read_text(encoding="utf-8")).get("chunks", {})
        except (OSError, ValueError):
            logger.warning("could not read v1 manifest %s", move.old_manifest)
            continue
        entry = chunks.get(move.old_key)
        if not isinstance(entry, dict):
            continue
        tracker: ManifestTracker = config.dataset_manifest(move.source, move.dataset, move.tier)
        if tracker.get_chunk(move.new_key) is None:
            tracker.put_entry(move.new_key, entry)
            carried += 1
    return carried


def _prune_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for directory in sorted(
        (p for p in root.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)
    ):
        if not any(directory.iterdir()):
            directory.rmdir()


def migrate_layout(
    config: LakeConfig | None = None, *, dry_run: bool = False, delete_old: bool = False
) -> MigrationReport:
    """Convert a v1 lake to layout v2; idempotent, verified, and non-destructive by default."""
    cfg = config or LakeConfig()
    report = MigrationReport(dry_run=dry_run, home=cfg.home)
    version = detect_layout(cfg)
    steps, unknown = plan_migration(cfg)
    report.steps = steps
    report.unknown = unknown

    if version == LAYOUT_VERSION and not steps:
        report.already_migrated = True
        return report
    if version is None and not steps:
        return report
    if dry_run:
        return report

    with default_audit_logger.track(
        operation="migrate_layout", source="migrate", destination=str(cfg.home)
    ) as tracker:
        for step in steps:
            if step.kind == "events_postseason":
                _migrate_events_postseason(step, report)
            elif _same_file(step.src, step.dst):
                report.skipped.append(step)
            else:
                _copy_verified(step, report)
                report.copied.append(step)
            report.manifest_entries += _carry_manifests(step, cfg)

        if delete_old:
            for step in report.copied + report.skipped:
                if step.src.exists():
                    step.src.unlink()
                    report.deleted_files += 1
            for name in V1_SOURCE_DIRS:
                _prune_empty_dirs(v1_cache_root(cfg) / name)
        if not (cfg.version_file.exists() and version == LAYOUT_VERSION):
            write_version(cfg)
            report.version_written = True
        tracker.set_records(len(report.copied) + len(report.skipped))

    for path in unknown:
        logger.warning("migrate-layout: left unrecognised v1 file in place: %s", path)
    return report
