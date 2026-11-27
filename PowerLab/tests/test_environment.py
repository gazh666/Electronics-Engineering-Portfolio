"""环境检查：依赖、真实后端、结果目录。"""

from __future__ import annotations

import sys
from importlib.metadata import version

import pytest

from simulations.environment import (
    check_results_writable,
    collect_environment,
    verify_backend,
)


def test_python_version():
    assert sys.version_info[:2] == (3, 11)


def test_required_packages_installed():
    assert version("PySpice") == "1.5"
    for name in ("numpy", "scipy", "matplotlib", "pandas", "PyYAML"):
        assert version(name)


def test_environment_report_identifies_simulation_source():
    report = collect_environment()
    assert report["data_source"] == "spice_simulation"
    assert "64bit" in report["architecture"]


def test_ngspice_backend_runs_real_circuit():
    probe = verify_backend()
    assert probe["status"] == "OK"
    assert probe["simulated_vin_v"] == pytest.approx(12.0, abs=1e-6)
    assert probe["simulated_vout_v"] == pytest.approx(6.0, abs=1e-6)


def test_results_directory_is_writable(tmp_path):
    probe = check_results_writable(tmp_path / "results")
    assert not probe.exists()
    assert (tmp_path / "results").is_dir()
