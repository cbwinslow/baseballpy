"""Statcast raw files for the round-trip check: CSV downloads, and the pages whose rows are embedded JSON."""

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec
from baseballpy.core.roundtrip import RawSample, csv_samples
from baseballpy.sources.statcast.lb_catalog import BY_SLUG
from baseballpy.sources.statcast.lb_parse import html_json_to_csv


def raw_reader(
    config: LakeConfig, spec: DatasetSpec, sample_files: int, season: int | None, every: bool
) -> list[RawSample]:
    """The raw files of one Statcast dataset as text tables (a leaderboard kept as a page is decoded first)."""
    defn = BY_SLUG.get(spec.name.removeprefix("leaderboard_"))
    if defn is not None and defn.fmt == "html_json":
        name = defn.html_var
        return csv_samples(
            config,
            spec,
            sample_files,
            season,
            every,
            suffixes=(".html", ".html.gz"),
            decode=lambda page: html_json_to_csv(page, name),
        )
    return csv_samples(config, spec, sample_files, season, every)
