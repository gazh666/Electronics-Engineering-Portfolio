"""第四阶段端到端集成测试：真实短时瞬态与 KCL 校验。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.buck_waveforms import NONIDEAL_WAVEFORM_COLUMNS
from circuits.nonideal_buck import get_variant_features
from circuits.nonideal_config import load_nonideal_buck_config
from scripts.nonideal_common import build_frame
from simulations.nonideal_buck_runner import run_nonideal_buck_transient

SHORT_END_S = 150e-6
MAX_STEP_S = 50e-9


@pytest.fixture(scope="module")
def config():
    return load_nonideal_buck_config()


def _frame(config, variant: str):
    result = run_nonideal_buck_transient(
        config, variant, end_time_s=SHORT_END_S, max_step_time_s=MAX_STEP_S
    )
    return result, build_frame(result, config, get_variant_features(variant))


def test_model_a_keeps_stage3_baseline_metadata(config):
    result, _ = _frame(config, "A")
    assert "legacy_baseline" in result.metadata
    assert result.metadata["model_variant"]["variant"] == "A"
    assert "SWMOD" in result.circuit_netlist


def test_model_b_waveform_columns_and_kcl(config):
    result, frame = _frame(config, "B")
    missing = set(NONIDEAL_WAVEFORM_COLUMNS) - set(frame.columns)
    assert missing == set()
    assert len(result.data) > 100

    inductor = frame["inductor_current_a"].to_numpy()
    input_current = frame["input_current_a"].to_numpy()
    diode_current = frame["diode_current_a"].to_numpy()
    np.testing.assert_allclose(inductor, input_current + diode_current, atol=1e-6)

    capacitor = frame["capacitor_current_a"].to_numpy()
    load = frame["load_current_a"].to_numpy()
    np.testing.assert_allclose(capacitor, inductor - load, atol=1e-6)


def test_model_d_uses_nmos_and_kcl(config):
    result, frame = _frame(config, "D")
    assert "NMOS_EDU" in result.circuit_netlist
    assert "VDRV" in result.circuit_netlist

    inductor = frame["inductor_current_a"].to_numpy()
    drain = frame["mosfet_drain_terminal_current_a"].to_numpy()
    diode_current = frame["diode_current_a"].to_numpy()
    # 栅极位移电流使开关瞬间残差略大，用 5 mA 容差
    np.testing.assert_allclose(inductor, drain + diode_current, atol=5e-3)

    gate_source = frame["mosfet_vgs_v"].to_numpy()
    assert gate_source.max() <= 10.0 + 1e-6
    assert gate_source.min() >= -1e-6


def test_model_e_adds_capacitors_to_netlist(config):
    result, _ = _frame(config, "E")
    netlist = result.circuit_netlist
    assert "CGS" in netlist and "CGD" in netlist and "CDS" in netlist
