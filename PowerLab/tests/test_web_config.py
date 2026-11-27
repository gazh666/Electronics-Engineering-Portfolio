"""Web 配置与资源预算文件检查（第九阶段 Task 14）。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_CONFIG = PROJECT_ROOT / "configs" / "web_config.yaml"
JOB_LIMITS = PROJECT_ROOT / "configs" / "job_limits.yaml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_web_config_file_exists():
    assert WEB_CONFIG.is_file()
    assert JOB_LIMITS.is_file()


def test_web_config_is_simulation_only():
    payload = _load(WEB_CONFIG)
    assert payload["application"]["mode"] == "simulation_only"
    assert payload["metadata"]["hardware_validation_available"] is False


def test_web_config_server_port():
    payload = _load(WEB_CONFIG)
    assert payload["server"]["port"] == 8502
    assert payload["server"]["address"] == "127.0.0.1"


def test_web_config_plot_limits():
    payload = _load(WEB_CONFIG)
    visualization = payload["visualization"]
    assert visualization["default_plot_points"] <= visualization["maximum_plot_points"]
    assert visualization["maximum_plot_points"] == 30000
    assert visualization["preserve_original_data"] is True


def test_web_config_history_limits():
    payload = _load(WEB_CONFIG)
    history = payload["history"]
    assert 0 < history["default_page_size"] <= history["maximum_page_size"]


def test_job_limits_single_concurrency():
    limits = _load(JOB_LIMITS)["limits"]
    assert limits["maximum_concurrent_jobs"] == 1
    assert limits["maximum_single_job_seconds"] == 3600


def test_job_limits_spice_run_budget():
    limits = _load(JOB_LIMITS)["limits"]
    assert limits["maximum_unique_spice_runs"] == 120
    assert limits["maximum_monte_carlo_samples"] <= limits["maximum_unique_spice_runs"]
    assert limits["maximum_log_bytes"] > 0


def test_job_limits_profiles():
    payload = _load(JOB_LIMITS)
    profiles = payload["profiles"]
    assert profiles["smoke"]["maximum_unique_spice_runs"] == 8
    assert profiles["standard"]["maximum_unique_spice_runs"] == 120
    assert profiles["extended"]["enabled"] is False


def test_job_limits_requires_explicit_confirmation_for_extended():
    payload = _load(JOB_LIMITS)
    assert payload["profiles"]["extended"]["require_explicit_confirmation"] is True


@pytest.mark.parametrize("key", ["maximum_concurrent_jobs", "maximum_unique_spice_runs"])
def test_job_limits_values_are_positive(key):
    assert _load(JOB_LIMITS)["limits"][key] > 0
