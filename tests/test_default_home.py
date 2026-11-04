"""Where the data folder is when nothing is configured: the project folder, else the user's home."""

from pathlib import Path

import pytest

from baseballpy.core import config
from baseballpy.core.config import LakeConfig, find_project_root, get_default_base_dir


@pytest.fixture(autouse=True)
def _no_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BASEBALLPY_HOME", raising=False)
    monkeypatch.delenv("BASEBALLPY_CACHE_DIR", raising=False)


def test_default_is_dot_baseballpy_in_the_nearest_project_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "work" / "project"
    deep = project / "src" / "pkg"
    deep.mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.chdir(deep)
    assert find_project_root() == project.resolve()
    assert get_default_base_dir() == (project / ".baseballpy").resolve()
    assert LakeConfig().home == (project / ".baseballpy").resolve()


def test_a_git_folder_also_marks_a_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    assert get_default_base_dir() == (tmp_path / ".baseballpy").resolve()


def test_outside_any_project_the_home_folder_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    monkeypatch.chdir(lonely)
    monkeypatch.setattr(config, "find_project_root", lambda start=None: None)
    assert get_default_base_dir() == (Path.home() / ".baseballpy").resolve()


def test_environment_variables_still_win(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    other = tmp_path / "elsewhere"
    monkeypatch.setenv("BASEBALLPY_HOME", str(other))
    assert get_default_base_dir() == other.resolve()
    monkeypatch.delenv("BASEBALLPY_HOME")
    monkeypatch.setenv("BASEBALLPY_CACHE_DIR", str(other / "cache"))
    assert get_default_base_dir() == other.resolve()


def test_the_repository_ignores_its_own_data_folder() -> None:
    root = Path(__file__).resolve().parent.parent
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".baseballpy/" in lines
