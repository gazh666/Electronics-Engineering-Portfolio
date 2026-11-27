"""SQLite 数据库备份：正常备份、一致性、完整性、不覆盖与异常分支。"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.backup_database as backup_module
from core.paths import RESULTS_DIR
from engine.models import TestResult, TestStatus
from scripts.backup_database import BackupError, backup_database, main
from storage.sqlite_store import SQLiteStore


def _make_db(path: Path) -> None:
    store = SQLiteStore(path)
    store.start_run("run_backup", suite_id="S1", suite_name="备份测试", planned_count=1)
    store.save_result(
        TestResult(
            run_id="run_backup",
            case_id="TC001",
            case_name="备份用例",
            started_at="2026-01-01T00:00:00.000+00:00",
            finished_at="2026-01-01T00:00:00.100+00:00",
            duration_ms=100.0,
            status=TestStatus.PASS,
            expected_state="NORMAL",
            actual_state="NORMAL",
            execution_index=0,
        )
    )


def _counts(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("runs", "test_results", "check_results", "fault_events")
        }


def test_backup_normal(tmp_path: Path):
    source = tmp_path / "source.db"
    _make_db(source)
    destination = backup_database(source, tmp_path / "backups")
    assert destination.is_file()
    assert destination.parent == (tmp_path / "backups").resolve()
    with closing(sqlite3.connect(destination)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute(
            "SELECT COUNT(*) FROM runs WHERE run_id='run_backup'"
        ).fetchone()[0] == 1


def test_backup_matches_source_records(tmp_path: Path):
    source = tmp_path / "source.db"
    _make_db(source)
    destination = backup_database(source, tmp_path / "backups")
    assert _counts(source) == _counts(destination)


def test_backup_missing_source(tmp_path: Path):
    with pytest.raises(BackupError):
        backup_database(tmp_path / "missing.db", tmp_path / "backups")


def test_backup_does_not_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "source.db"
    _make_db(source)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D102 - 固定时间便于测试
            return datetime(2026, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(backup_module, "datetime", FixedDatetime)
    first = backup_database(source, tmp_path / "backups")
    assert first.is_file()
    with pytest.raises(BackupError):
        backup_database(source, tmp_path / "backups")


def test_backup_is_independent_of_real_database(tmp_path: Path):
    real = RESULTS_DIR / "testlab.db"
    before = real.stat().st_mtime_ns if real.is_file() else None
    source = tmp_path / "source.db"
    _make_db(source)
    backup_database(source, tmp_path / "backups")
    after = real.stat().st_mtime_ns if real.is_file() else None
    assert before == after


def test_backup_cli_success_and_failure(tmp_path: Path, capsys):
    source = tmp_path / "source.db"
    _make_db(source)
    code = main(["--source", str(source), "--backup-dir", str(tmp_path / "backups")])
    assert code == 0
    assert "完整性" in capsys.readouterr().out

    code = main(["--source", str(tmp_path / "missing.db"), "--backup-dir", str(tmp_path)])
    assert code == 2


def test_backup_list(tmp_path: Path, capsys):
    source = tmp_path / "source.db"
    _make_db(source)
    backup_database(source, tmp_path / "backups")
    assert main(["--list", "--backup-dir", str(tmp_path / "backups")]) == 0
    assert "testlab_" in capsys.readouterr().out
