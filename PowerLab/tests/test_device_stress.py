"""器件应力计算与判据测试（合成波形）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.device_stress import check_stress, compute_device_stress


def _frame() -> pd.DataFrame:
    time = np.linspace(0.0, 1e-5, 101)
    period = 1e-5
    on = (time % period) < 4e-6
    return pd.DataFrame(
        {
            "time_s": time,
            "vin_v": np.full_like(time, 12.0),
            "switch_node_v": np.where(on, 12.0, -0.5),
            "mosfet_vds_v": np.where(on, 0.05, 12.0),
            "mosfet_vgs_v": np.where(on, 10.0, 0.0),
            "drive_vgs_command_v": np.where(on, 10.0, 0.0),
            "mosfet_drain_terminal_current_a": np.where(on, 2.0, 0.0),
            "diode_anode_cathode_voltage_v": np.where(on, 0.0, -0.5),
            "diode_current_a": np.where(on, 0.0, 2.0),
            "inductor_current_a": np.full_like(time, 1.9),
            "capacitor_internal_voltage_v": np.full_like(time, 5.0),
            "capacitor_esr_voltage_v": np.full_like(time, 0.01),
        }
    )


def test_compute_device_stress_reports_peaks():
    stress = compute_device_stress(_frame())
    assert stress.mosfet_vds_max_v == pytest.approx(12.0)
    assert stress.drain_current_peak_a == pytest.approx(2.0)
    assert stress.drain_current_p999_a == pytest.approx(2.0)
    assert stress.gate_source_voltage_max_v == pytest.approx(10.0)
    assert stress.diode_reverse_voltage_peak_v == pytest.approx(0.5)
    assert stress.diode_forward_current_peak_a == pytest.approx(2.0)
    assert stress.inductor_current_ripple_a == pytest.approx(0.0)
    assert stress.switch_node_min_v == pytest.approx(-0.5)
    payload = stress.to_dict()
    assert payload["data_source"] == "spice_simulation"
    assert any("p999" in note or "p99.9" in note for note in payload["limitations"])


def test_stress_rejects_bad_frames():
    with pytest.raises(ValueError):
        compute_device_stress("bad")
    with pytest.raises(ValueError):
        compute_device_stress(_frame().head(2))
    missing = _frame().drop(columns=["switch_node_v"])
    with pytest.raises(ValueError):
        compute_device_stress(missing)
    nonfinite = _frame()
    nonfinite.loc[0, "vin_v"] = np.nan
    with pytest.raises(ValueError):
        compute_device_stress(nonfinite)


def test_check_stress_uses_user_limits():
    stress = compute_device_stress(_frame())
    passed = check_stress(
        stress,
        maximum_drain_current_a=5.0,
        maximum_vds_v=20.0,
        maximum_gate_voltage_v=12.0,
        maximum_diode_forward_current_a=5.0,
    )
    assert passed["passed"] is True
    assert "not manufacturer ratings" in passed["note"]

    failed = check_stress(
        stress,
        maximum_drain_current_a=1.0,
        maximum_vds_v=20.0,
        maximum_gate_voltage_v=12.0,
        maximum_diode_forward_current_a=5.0,
    )
    assert failed["passed"] is False
    assert failed["checks"]["drain_current"]["passed"] is False


def test_check_stress_validates_arguments():
    stress = compute_device_stress(_frame())
    with pytest.raises(ValueError):
        check_stress("bad", maximum_drain_current_a=1, maximum_vds_v=1, maximum_gate_voltage_v=1, maximum_diode_forward_current_a=1)
    with pytest.raises(ValueError):
        check_stress(
            stress,
            maximum_drain_current_a=0.0,
            maximum_vds_v=20.0,
            maximum_gate_voltage_v=12.0,
            maximum_diode_forward_current_a=5.0,
        )
