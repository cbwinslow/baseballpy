"""Retrosheet raw files for the round-trip check.

Most Retrosheet datasets come from files that are not plain CSV with a header: headerless game logs and rosters, the
umpire list, and the zip members of retrosheet.org's own files. Event files are parsed by Chadwick and have no CSV
raw form; they are checked another way (see the change data-validation-roundtrip).
"""

import zipfile

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec
from baseballpy.core.roundtrip import RawSample, csv_samples
from baseballpy.core.schema_tools import EXTRAS, read_csv_strings
from baseballpy.core.stores import RawStore
from baseballpy.sources.retrosheet.site import RAW_DATASET, SITE_DATASETS

#: the fields of a roster file line, in order (the file has no header row)
_ROSTER_FIELDS = ("player_id", "last_name", "first_name", "bats", "throws", "team", "position")


def _spread(items: list[str], count: int) -> list[str]:
    if count >= len(items):
        return items
    if count <= 1:
        return items[:1]
    return [items[round(i * (len(items) - 1) / (count - 1))] for i in range(count)]


def _site_samples(
    config: LakeConfig, spec: DatasetSpec, sample_files: int, every: bool
) -> list[RawSample]:
    """Member files of the zip the dataset is parsed from, as text tables (the id column added when declared)."""
    site = SITE_DATASETS[spec.name]
    raw = RawStore(config)
    if not raw.exists("retrosheet", RAW_DATASET, site.zip_name):
        return []
    header = site.header.split(",") if site.header else None
    out: list[RawSample] = []
    with zipfile.ZipFile(raw.path_for("retrosheet", RAW_DATASET, site.zip_name)) as archive:
        members = (
            sorted(n for n in archive.namelist() if n.endswith(site.suffix))
            if site.suffix
            else [site.member]
        )
        for member in members if every else _spread(members, sample_files):
            table = read_csv_strings(archive.read(member), header=header)
            if site.id_column:
                stem = member.rsplit("/", 1)[-1].removesuffix(site.suffix)
                table = table.append_column(
                    site.id_column, pa.array([stem] * table.num_rows, pa.string())
                )
            out.append(RawSample(member, None, table))
    return out


def raw_reader(
    config: LakeConfig, spec: DatasetSpec, sample_files: int, season: int | None, every: bool
) -> list[RawSample]:
    """The raw files of one Retrosheet dataset as text tables."""
    if spec.name in SITE_DATASETS:
        return _site_samples(config, spec, sample_files, every)
    if spec.name in ("gamelogs", "gamelogs_postseason"):
        header = [f.name for f in spec.schema if f.name != EXTRAS]
        return csv_samples(
            config, spec, sample_files, season, every, suffixes=(".TXT", ".txt"), header=header
        )
    if spec.name == "umpires":
        return csv_samples(config, spec, sample_files, season, every, suffixes=(".txt",))
    if spec.name == "rosters":
        samples = csv_samples(
            config, spec, sample_files, season, every, suffixes=(".ROS",), header=_ROSTER_FIELDS
        )
        out: list[RawSample] = []
        for sample in samples:  # the year and the roster name are in the folder and the file name
            n = sample.table.num_rows
            table = sample.table.append_column("year", pa.array([str(sample.season)] * n))
            roster = sample.stem.rstrip(
                "0123456789"
            )  # HOU2015.ROS is the roster HOU (as the parser says)
            table = table.append_column("roster", pa.array([roster] * n))
            out.append(RawSample(sample.label, sample.season, table, sample.stem))
        return out
    return csv_samples(config, spec, sample_files, season, every)
