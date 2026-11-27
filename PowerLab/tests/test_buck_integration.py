"""真实 ngspice Buck 仿真集成测试。

这些测试必须真实调用 ngspice；若求解失败会直接抛出异常，不生成替代数据。
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from analysis.buck_waveforms import WAVEFORM_COLUMNS
from analysis.conduction_mode import ConductionMode
from analysis.steady_state import STATUS_STEADY_STATE
from circuits.buck_config import load_buck_config
from scripts.buck_common import default_validation_limits, record_failure, run_and_analyze
from simulations import buck_runner
from simulations.buck_runner import (
    extended_end_time,
    run_buck_transient,
    time_step_statistics,
)


@pytest.fixture(scope="module")
def default_case():
    return run_and_analyze(
        load_buck_config(),
        end_time_s=5e-3,
        allow_extension=False,
        validation_limits=default_validation_limits(),
    )


@pytest.fixture(scope="module")
def light_load_case():
    parameters = load_buck_config()
    light = replace(
        parameters,
        circuit=replace(parameters.circuit, load_resistance_ohm=50.0),
    )
    return run_and_analyze(
        light,
        end_time_s=20e-3,
        allow_extension=False,
        validation_limits=default_validation_limits(),
    )


def test_real_transient_solves_with_valid_time_axis(default_case):
    result = default_case.result
    assert result.point_count > 10_000
    assert result.metadata["analysis_command"].startswith(".tran")
    time = default_case.waveforms["time_s"].to_numpy()
    assert np.all(np.diff(time) > 0)
    assert time[0] == pytest.approx(0.0)
    assert time[-1] == pytest.approx(5e-3, rel=1e-6)
    assert np.isfinite(default_case.waveforms.to_numpy()).all()


def test_waveform_contains_real_pwm_and_switch_node(default_case):
    waveforms = default_case.waveforms
    assert tuple(waveforms.columns) == WAVEFORM_COLUMNS
    gate = waveforms["gate_v"]
    assert gate.max() == pytest.approx(5.0, abs=0.01)
    assert gate.min() == pytest.approx(0.0, abs=0.01)
    switch_node = waveforms["switch_node_v"]
    assert switch_node.max() > 11.0
    assert switch_node.min() < 1.0


def test_pwm_frequency_and_duty_measured_from_gate(default_case):
    pwm = default_case.pwm
    assert pwm.mean_frequency_hz == pytest.approx(100e3, rel=0.001)
    assert pwm.mean_duty_cycle == pytest.approx(5.0 / 12.0, abs=0.005)
    assert pwm.complete_cycles >= 490


def test_output_voltage_reaches_expected_operating_range(default_case):
    assert default_case.window.status == STATUS_STEADY_STATE
    assert default_case.metrics is not None
    mean_voltage = default_case.metrics["output_voltage_mean_v"]
    assert 4.5 < mean_voltage < 5.0
    assert default_case.metrics["output_voltage_ripple_vpp"] < 0.05
    current_ripple = default_case.metrics["inductor_current_ripple_app"]
    assert 0.4 < current_ripple < 0.9


def test_heavy_load_is_ccm_and_validation_passes(default_case):
    assert default_case.mode.mode is ConductionMode.CCM
    assert default_case.validation is not None
    assert default_case.validation.status == "PASS"


def test_time_step_limit_is_respected(default_case):
    statistics = default_case.result.metadata["time_step_statistics"]
    assert statistics["max_step_respected"]
    assert statistics["sample_count"] == default_case.result.point_count
    assert statistics["max_step_s"] <= 50e-9 * 1.001


def test_light_load_enters_dcm_without_forcing_five_volts(light_load_case):
    assert light_load_case.window.status == STATUS_STEADY_STATE
    assert light_load_case.mode.mode is ConductionMode.DCM
    assert light_load_case.mode.near_zero_time_ratio > 0.02
    assert light_load_case.metrics is not None
    vout = light_load_case.metrics["output_voltage_mean_v"]
    assert vout > 6.5
    assert abs(vout - 5.0) > 1.0


def test_duty_cycle_changes_real_output_voltage():
    parameters = load_buck_config()

    def run(duty: float):
        modified = replace(
            parameters,
            circuit=replace(parameters.circuit, duty_cycle=duty),
            pwm=replace(parameters.pwm, duty_cycle=duty),
        )
        return run_and_analyze(
            modified,
            end_time_s=5e-3,
            allow_extension=False,
            validation_limits=default_validation_limits(),
        )

    low = run(0.25)
    high = run(0.5)
    assert low.window.is_steady and high.window.is_steady
    assert low.metrics is not None and high.metrics is not None
    assert high.metrics["output_voltage_mean_v"] > low.metrics["output_voltage_mean_v"] + 1.0
    assert low.pwm.mean_duty_cycle == pytest.approx(0.25, abs=0.005)
    assert high.pwm.mean_duty_cycle == pytest.approx(0.5, abs=0.005)


def test_backend_failure_raises_and_records_no_waveform(monkeypatch, tmp_path):
    def boom(self, *args, **kwargs):
        raise RuntimeError("injected ngspice failure")

    monkeypatch.setattr(buck_runner.SimulationRunner, "run_transient", boom)
    with pytest.raises(RuntimeError, match="injected ngspice failure"):
        run_buck_transient(load_buck_config())

    directory = record_failure(
        "buck_unit_failure", RuntimeError("injected"), root=tmp_path
    )
    assert (directory / "metadata.json").is_file()
    assert not (directory / "waveform.csv").exists()


def test_time_step_statistics_and_extension_helper():
    statistics = time_step_statistics([0.0, 1e-8, 2e-8], configured_max_step_s=1e-8)
    assert statistics["sample_count"] == 3
    assert statistics["max_step_respected"]
    with pytest.raises(ValueError):
        time_step_statistics([0.0, 0.0])
    with pytest.raises(ValueError):
        time_step_statistics([0.0, float("nan")])

    assert extended_end_time(5e-3) == pytest.approx(10e-3)
    assert extended_end_time(15e-3) == pytest.approx(20e-3)
    assert extended_end_time(20e-3) is None
