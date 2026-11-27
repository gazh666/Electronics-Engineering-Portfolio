"""发布验收脚本：单项检查、失败路径与真实数据库隔离。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.paths import RESULTS_DIR
from scripts import verify_release as verify


def test_individual_checks_pass():
    assert verify.check_python()
    assert "模块" in verify.check_imports()
    assert "YAML" in verify.check_configs()
    assert "资源" in verify.check_instruments()
    assert "vout" in verify.check_virtual_dut()
    assert verify.check_version()


def test_missing_config_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(verify, "CONFIG_FILES", (tmp_path / "missing.yaml",))
    with pytest.raises(AssertionError):
        verify.check_configs()


def test_missing_version_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(verify, "PROJECT_ROOT", tmp_path)
    with pytest.raises(AssertionError):
        verify.check_version()


def test_main_passes_and_keeps_real_database_untouched(tmp_path: Path):
    real_db = RESULTS_DIR / "testlab.db"
    before = (real_db.stat().st_size, real_db.stat().st_mtime_ns) if real_db.is_file() else None

    assert verify.main([]) == 0

    after = (real_db.stat().st_size, real_db.stat().st_mtime_ns) if real_db.is_file() else None
    assert before == after


def test_core_flow_in_temp_directory(tmp_path: Path):
    detail = verify.check_automation_and_faults_and_report(tmp_path)
    assert "SUITE-SMOKE" in detail
    assert "F001" in detail
    assert "test_report_" in detail
