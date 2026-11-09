"""Which Parquet files are data: ``season=*/*.parquet`` or ``*.parquet``, never underscore folders or ``.part``."""

from pathlib import Path

from baseballpy.core.listing import dataset_files, dataset_glob, is_hidden, visible_parquet


def _touch(*paths: Path) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")


def test_a_split_dataset_is_read_one_folder_down_and_hidden_files_are_left_out(
    tmp_path: Path,
) -> None:
    data = [
        tmp_path / "season=2023" / "part-1.parquet",
        tmp_path / "season=2023" / "compact-0001.parquet",
        tmp_path / "season=2024" / "seg-0001.parquet",
    ]
    hidden = [
        tmp_path / "season=2024" / "_open" / "seg-0002.parquet",
        tmp_path / "season=2024" / "_legacy" / "part-9.parquet",
        tmp_path / "season=2024" / "seg-0003.parquet.part",
        tmp_path / "season=2024" / "_stray.parquet",
        tmp_path / "loose.parquet",  # not in a season folder: not part of a split dataset
        tmp_path / "season=2025" / "deeper" / "seg-0004.parquet",
    ]
    _touch(*data, *hidden)
    assert dataset_files(tmp_path, by_season=True) == sorted(data)
    assert dataset_glob(tmp_path, by_season=True) == tmp_path / "season=*" / "*.parquet"


def test_an_unsplit_dataset_is_read_from_its_folder_only(tmp_path: Path) -> None:
    data = [tmp_path / "part-1.parquet", tmp_path / "seg-0001.parquet"]
    _touch(
        *data, tmp_path / "_open" / "seg-0002.parquet", tmp_path / "season=2024" / "part-1.parquet"
    )
    assert dataset_files(tmp_path, by_season=False) == sorted(data)
    assert dataset_glob(tmp_path, by_season=False) == tmp_path / "*.parquet"


def test_a_missing_folder_has_no_files(tmp_path: Path) -> None:
    assert dataset_files(tmp_path / "nope", by_season=True) == []
    assert list(visible_parquet(tmp_path / "nope")) == []


def test_an_unknown_layout_is_walked_but_hidden_files_are_still_left_out(tmp_path: Path) -> None:
    shown = tmp_path / "a" / "b" / "x.parquet"
    _touch(shown, tmp_path / "a" / "_open" / "y.parquet", tmp_path / "z.parquet.part")
    assert list(visible_parquet(tmp_path)) == [shown]
    assert is_hidden(tmp_path / "a" / "_open" / "y.parquet", tmp_path)
    assert not is_hidden(shown, tmp_path)
