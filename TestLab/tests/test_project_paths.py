"""统一路径配置：默认位置、环境变量优先级与目录创建时机。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import core.paths as paths
from storage.sqlite_store import DEFAULT_DB_PATH


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "TESTLAB_RESULTS_DIR",
        "TESTLAB_RESULTS_ROOT",
        "TESTLAB_DB_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def test_default_results_directory():
    assert paths.results_dir() == paths.DEFAULT_RESULTS_DIR
    assert paths.DEFAULT_RESULTS_DIR == paths.PROJECT_ROOT / "results"
    assert paths.database_path() == paths.DEFAULT_RESULTS_DIR / "testlab.db"


def test_results_dir_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TESTLAB_RESULTS_DIR", str(tmp_path / "custom"))
    assert paths.results_dir() == (tmp_path / "custom").resolve()
    assert paths.database_path() == (tmp_path / "custom").resolve() / "testlab.db"


def test_legacy_results_root_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TESTLAB_RESULTS_ROOT", str(tmp_path / "legacy"))
    assert paths.results_dir() == (tmp_path / "legacy").resolve()


def test_results_dir_takes_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TESTLAB_RESULTS_DIR", str(tmp_path / "new"))
    monkeypatch.setenv("TESTLAB_RESULTS_ROOT", str(tmp_path / "old"))
    assert paths.results_dir() == (tmp_path / "new").resolve()


def test_database_path_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom_db = tmp_path / "data" / "history.db"
    monkeypatch.setenv("TESTLAB_DB_PATH", str(custom_db))
    assert paths.database_path() == custom_db.resolve()


def test_results_dir_does_not_create_on_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "lazy"
    monkeypatch.setenv("TESTLAB_RESULTS_DIR", str(target))
    assert paths.results_dir() == target.resolve()
    assert not target.exists()
    created = paths.ensure_runtime_directories()
    assert created == target.resolve()
    assert target.is_dir()


def test_storage_default_matches_core():
    assert DEFAULT_DB_PATH == paths.DATABASE_PATH


def test_paths_are_pathlib_and_absolute():
    for value in (
        paths.PROJECT_ROOT,
        paths.CONFIG_DIR,
        paths.DEFAULT_RESULTS_DIR,
        paths.RESULTS_DIR,
        paths.DATABASE_PATH,
    ):
        assert isinstance(value, Path)
        assert value.is_absolute()


def test_chinese_yaml_is_utf8_readable():
    payload = yaml.safe_load(
        (paths.CONFIG_DIR / "test_cases.yaml").read_text(encoding="utf-8")
    )
    names = [item["name"] for item in payload["test_cases"]]
    assert any(any("\u4e00" <= char <= "\u9fff" for char in name) for name in names)


def test_no_hardcoded_windows_drive_in_core():
    source = (paths.PROJECT_ROOT / "core" / "paths.py").read_text(encoding="utf-8")
    assert "C:\\" not in source and "D:\\" not in source
