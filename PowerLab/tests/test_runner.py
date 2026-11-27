"""统一仿真执行器：四种真实分析 + 元数据与质量检查。"""

from __future__ import annotations

import pytest

from circuits.rc_circuit import build_rc_lowpass, build_rc_transient
from circuits.voltage_divider import build_voltage_divider
from simulations.models import AnalysisType, SimulationResult
from simulations.runner import SimulationRunner


@pytest.fixture(scope="module")
def runner() -> SimulationRunner:
    return SimulationRunner(25.0)


@pytest.fixture(scope="module")
def divider_result(runner):
    circuit = build_voltage_divider(12.0, 1_000.0, 1_000.0)
    return runner.run_operating_point(circuit)


def test_operating_point_result_fields(divider_result):
    result = divider_result
    assert isinstance(result, SimulationResult)
    assert result.analysis_type is AnalysisType.OP
    assert result.point_count == 1
    assert result.data.loc[0, "out_v"] == pytest.approx(6.0, abs=1e-9)
    assert result.data.loc[0, "vinput_branch_current_a"] == pytest.approx(-0.006, abs=1e-9)
    assert result.units["out_v"] == "V"
    assert result.data_source == "spice_simulation"
    assert ".op" in result.circuit_netlist


def test_dc_sweep_columns_and_quality(runner):
    circuit = build_voltage_divider(12.0, 1_000.0, 1_000.0)
    result = runner.run_dc(circuit, "input", 0.0, 12.0, 1.0)
    assert result.analysis_type is AnalysisType.DC
    assert list(result.data["sweep_v"]) == pytest.approx(list(range(13)))
    assert "out_v" in result.data.columns
    assert result.metadata["sweep_source"] == "input"
    assert result.metadata["quality"]["valid"] is True
    assert ".dc" in result.circuit_netlist


def test_dc_sweep_unknown_source_raises(runner):
    circuit = build_voltage_divider()
    with pytest.raises(Exception):
        runner.run_dc(circuit, "missing", 0.0, 1.0, 0.1)


def test_ac_keeps_complex_parts(runner):
    circuit = build_rc_lowpass(1_000.0, 1e-6)
    result = runner.run_ac(circuit, 10.0, 1_000.0, 10)
    assert result.analysis_type is AnalysisType.AC
    for column in ("out_real_v", "out_imag_v", "vin_real_v", "vin_imag_v"):
        assert column in result.data.columns
    assert result.data["frequency_hz"].iloc[0] == pytest.approx(10.0)
    assert result.data["frequency_hz"].iloc[-1] == pytest.approx(1_000.0)
    assert result.point_count == pytest.approx(21)


def test_transient_time_axis_strictly_increasing(runner):
    circuit = build_rc_transient(5.0, 1_000.0, 1e-6, pulse_width_s=2e-3, period_s=4e-3)
    result = runner.run_transient(circuit, 1e-5, 4e-3)
    assert result.analysis_type is AnalysisType.TRANSIENT
    time_s = result.data["time_s"].to_numpy()
    assert len(time_s) > 100
    assert (time_s[1:] > time_s[:-1]).all()
    assert result.metadata["quality"]["valid"] is True


def test_invalid_transient_parameters_raise(runner):
    circuit = build_rc_transient()
    with pytest.raises(ValueError):
        runner.run_transient(circuit, -1e-5, 1e-3)
    with pytest.raises(ValueError):
        runner.run_transient(circuit, 1e-5, 0.0)


def test_invalid_temperature_raises():
    with pytest.raises(ValueError):
        SimulationRunner(-273.15)
