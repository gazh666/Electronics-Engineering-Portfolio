"""守恒检查测试：使用自洽的合成波形，不运行 SPICE。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from circuits.nonideal_config import load_nonideal_buck_config
from validation.conservation_checks import (
    check_charge_balance,
    check_energy_balance,
    check_node_current,
    check_volt_second,
    run_conservation_checks,
    steady_state_slice,
)


@pytest.fixture(scope="module")
def config():
    return load_nonideal_buck_config()


def _frame(
    config,
    *,
    inductor_current_a: float = 1.0,
    inductor_voltage_v: float = 0.0,
    capacitor_current_a: float = 0.0,
    load_current_a: float = 1.0,
    vout_v: float = 5.0,
    vin_v: float = 12.0,
    input_current_scale: float = 1.0,
) -> pd.DataFrame:
    period = 1.0 / config.switching_frequency_hz
    time = np.linspace(0.0, 5.0 * period, 1001)
    dcr = config.inductor.dcr_ohm
    esr = config.capacitor.esr_ohm
    p_out = vout_v * load_current_a
    p_loss = inductor_current_a**2 * dcr + capacitor_current_a**2 * esr
    input_current = input_current_scale * (p_out + p_loss) / vin_v
    return pd.DataFrame(
        {
            "time_s": time,
            "inductor_current_a": np.full_like(time, inductor_current_a),
            "inductor_voltage_v": np.full_like(time, inductor_voltage_v),
            "capacitor_current_a": np.full_like(time, capacitor_current_a),
            "load_current_a": np.full_like(time, load_current_a),
            "input_current_a": np.full_like(time, input_current),
            "vin_v": np.full_like(time, vin_v),
            "vout_v": np.full_like(time, vout_v),
            "mosfet_drain_terminal_current_a": np.full_like(time, 0.5),
            "data_source": np.full(time.shape, "synthetic_test_data", dtype=object),
        }
    )


def test_steady_state_slice_takes_last_complete_cycles(config):
    frame = _frame(config)
    period = 1.0 / config.switching_frequency_hz
    window = steady_state_slice(frame, config.switching_frequency_hz, cycles=5)
    assert len(window) == len(frame)
    assert window["time_s"].iloc[0] == pytest.approx(0.0)
    assert window["time_s"].iloc[-1] == pytest.approx(5.0 * period)


def test_steady_state_slice_requires_two_cycles(config):
    with pytest.raises(ValueError):
        steady_state_slice(_frame(config), config.switching_frequency_hz, cycles=1)


def test_volt_second_balance_passes_for_zero_volt_seconds(config):
    check = check_volt_second(_frame(config), config.switching_frequency_hz)
    assert check.status.value == "PASS"
    assert check.value == pytest.approx(0.0, abs=1e-12)


def test_volt_second_balance_fails_for_injected_offset(config):
    check = check_volt_second(
        _frame(config, inductor_voltage_v=1.0), config.switching_frequency_hz
    )
    assert check.status.value == "FAIL"
    # ∫vL dt = 1 V * 5T；scale = 5 V * 5T -> 比值 0.2。
    assert check.value == pytest.approx(0.2, rel=1e-6)


def test_charge_balance_passes_for_zero_capacitor_current(config):
    check = check_charge_balance(_frame(config), config.switching_frequency_hz)
    assert check.status.value == "PASS"
    assert check.value == pytest.approx(0.0, abs=1e-12)


def test_charge_balance_fails_for_injected_charge(config):
    check = check_charge_balance(
        _frame(config, capacitor_current_a=0.5), config.switching_frequency_hz
    )
    assert check.status.value == "FAIL"
    assert check.value == pytest.approx(0.5, rel=1e-6)


def test_node_current_consistency_passes_for_consistent_waveform(config):
    check = check_node_current(_frame(config))
    assert check.status.value == "PASS"
    assert check.value == pytest.approx(0.0, abs=1e-12)


def test_node_current_consistency_fails_for_mismatch(config):
    check = check_node_current(_frame(config, capacitor_current_a=0.1))
    assert check.status.value == "FAIL"
    assert check.value == pytest.approx(0.1, rel=1e-6)


def test_energy_balance_passes_for_consistent_accounting(config):
    check = check_energy_balance(_frame(config), config)
    assert check.status.value == "PASS"
    assert check.value == pytest.approx(0.0, abs=1e-9)
    assert "Pin=" in check.message


def test_energy_balance_fails_when_input_power_is_inflated(config):
    check = check_energy_balance(_frame(config, input_current_scale=2.0), config)
    assert check.status.value == "FAIL"
    assert check.value > check.limit


def test_run_conservation_checks_returns_four_consistent_passes(config):
    checks = run_conservation_checks(_frame(config), config)
    assert len(checks) == 4
    assert [check.name for check in checks] == [
        "volt_second_balance",
        "charge_balance",
        "node_current_consistency",
        "energy_balance",
    ]
    assert all(check.status.value == "PASS" for check in checks)


def test_run_conservation_checks_honors_strict_limits(config):
    checks = run_conservation_checks(
        _frame(config, input_current_scale=1.1),
        config,
        limits={"energy_residual_ratio": 1e-6},
    )
    energy = [check for check in checks if check.name == "energy_balance"][0]
    assert energy.status.value == "FAIL"
