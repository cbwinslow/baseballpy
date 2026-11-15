"""Where the data folder is when nothing is configured: the global ``~/.baseballpy`` (ADR 135)."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.config import LakeConfig, get_default_base_dir, resolve_home


@pytest.fixture(autouse=True)
def _no_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BASEBALLPY_HOME", raising=False)
    monkeypatch.delenv("BASEBALLPY_CACHE_DIR", raising=False)
    fake_home = tmp_path / "userhome"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))


def test_the_default_is_the_global_folder_even_inside_a_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project folder (pyproject.toml, .git) does not get its own copy of the data any more."""
    project = tmp_path / "work" / "project"
    deep = project / "src" / "pkg"
    deep.mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname='x'\n")
    (project / ".git").mkdir()
    monkeypatch.chdir(deep)
    expected = (tmp_path / "userhome" / ".baseballpy").resolve()
    assert get_default_base_dir() == expected
    assert LakeConfig().home == expected
    assert resolve_home()[1] == "the global default"


def test_a_project_can_ask_for_its_own_folder_in_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    deep = project / "a" / "b"
    deep.mkdir(parents=True)
    (project / "pyproject.toml").write_text('[tool.baseballpy]\nhome = "data/lake"\n')
    monkeypatch.chdir(deep)
    home, reason = resolve_home()
    assert home == (project / "data" / "lake").resolve()
    assert "[tool.baseballpy] home" in reason


def test_a_pyproject_without_the_setting_or_with_broken_toml_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = tmp_path / "outer" / "inner"
    inner.mkdir(parents=True)
    (inner / "pyproject.toml").write_text("this is [not toml")
    (tmp_path / "outer" / "pyproject.toml").write_text('[tool.baseballpy]\nhome = "elsewhere"\n')
    monkeypatch.chdir(inner)
    assert resolve_home()[0] == (tmp_path / "outer" / "elsewhere").resolve()


def test_environment_variables_win_over_the_project_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.baseballpy]\nhome = "proj"\n')
    monkeypatch.chdir(tmp_path)
    other = tmp_path / "elsewhere"
    monkeypatch.setenv("BASEBALLPY_HOME", str(other))
    assert get_default_base_dir() == other.resolve()
    monkeypatch.delenv("BASEBALLPY_HOME")
    monkeypatch.setenv("BASEBALLPY_CACHE_DIR", str(other / "cache"))
    assert get_default_base_dir() == other.resolve()


def test_the_home_command_says_where_and_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "mylake"
    (lake / "raw").mkdir(parents=True)
    monkeypatch.setenv("BASEBALLPY_HOME", str(lake))
    result = CliRunner().invoke(main, ["home"])
    assert result.exit_code == 0, result.output
    assert str(lake.resolve()) in result.output.replace("\n", "")
    assert "BASEBALLPY_HOME environment variable" in result.output.replace("\n", " ")
    assert "Exists:" in result.output and "yes" in result.output


def test_the_repository_ignores_its_own_data_folder() -> None:
    root = Path(__file__).resolve().parent.parent
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".baseballpy/" in lines
