"""联合网表装配与平均模型一致性测试（不运行 ngspice）。"""

from __future__ import annotations

import numpy as np
import pytest

from circuits.system_spice_netlist import build_integrated_system
from system_models.averaged_system import AveragedSystemParams, coupled_system_rhs, simulate_averaged_system
from system_models.system_controller import PIController, soft_start_reference


CELLS = [
    {"ocv_v": 3.6, "r0_ohm": 0.08, "rp_ohm": 0.02, "cp_f": 800.0, "initial_polarization_v": 0.0}
] * 3


def test_integrated_netlist_contains_all_blocks() -> None:
    circuit, layout = build_integrated_system(CELLS, end_time_s=0.005)
    text = str(circuit)
    assert "OCV1" in text and "OCV3" in text
    assert "BPROT" in text and "CIN" in text
    assert "SWMOD" in text and "DFREE" in text
    assert "BCERR" in text and "BCPWM" in text
    assert layout.features["battery_voltage_depends_on_load"] is True
    assert layout.features["switching_level"] is True
    assert layout.features["protection_switch_is_behavioral"] is True


def test_integrated_netlist_has_unique_element_names() -> None:
    circuit, _ = build_integrated_system(CELLS, end_time_s=0.005)
    names = [str(element.name) for element in circuit.elements]
    assert len(names) == len(set(names))


def test_protection_control_points_validated() -> None:
    with pytest.raises(ValueError):
        build_integrated_system(CELLS, end_time_s=0.005, protection_control_points=[(0.006, 1.0)])


def test_invalid_load_rejected() -> None:
    with pytest.raises(ValueError):
        build_integrated_system(CELLS, load_resistance_ohm=0.0)


def test_soft_start_reference() -> None:
    assert soft_start_reference(0.0, 5.0, 2e-3) == pytest.approx(0.0)
    assert soft_start_reference(1e-3, 5.0, 2e-3) == pytest.approx(2.5)
    assert soft_start_reference(3e-3, 5.0, 2e-3) == pytest.approx(5.0)


def test_pi_controller_clamps_duty() -> None:
    controller = PIController(kp=1.0, ki=0.0)
    assert controller.update(10.0, 5.0, 1e-5) == pytest.approx(0.90)
    controller.reset()
    assert controller.update(0.0, 5.0, 1e-5) == pytest.approx(0.02)


def test_averaged_rhs_energy_direction() -> None:
    params = AveragedSystemParams(
        input_capacitance_f=100e-6, output_capacitance_f=100e-6, inductance_h=47e-6,
        battery_resistance_ohm=0.24, path_resistance_ohm=0.05, inductor_dcr_ohm=0.05,
        mosfet_rds_on_ohm=0.02, diode_drop_v=0.35,
    )
    derivative = coupled_system_rhs(0.0, (10.5, 1.0, 5.0), 10.8, 0.45, 2.5, True, params)
    assert derivative[0] > 0  # 电池向输入电容充电
    assert derivative[2] == pytest.approx((1.0 - 2.0) / 100e-6)


def test_averaged_simulation_rises_to_reference() -> None:
    params = AveragedSystemParams(
        input_capacitance_f=100e-6, output_capacitance_f=100e-6, inductance_h=47e-6,
        battery_resistance_ohm=0.24, path_resistance_ohm=0.05, inductor_dcr_ohm=0.05,
        mosfet_rds_on_ohm=0.02, diode_drop_v=0.35,
    )
    result = simulate_averaged_system(
        params, effective_battery_voltage_v=10.8, target_output_voltage_v=5.0,
        duration_s=0.006, dt_s=2e-6, soft_start_s=1e-3,
        controller=PIController(), load_profile=((0.0, 2.5),),
        initial_state=(10.5, 1.0, 4.0),
    )
    vout = np.array([row["output_voltage_v"] for row in result["records"]])
    assert vout[-1] == pytest.approx(5.0, abs=0.1)
    assert np.all(np.isfinite(vout))


def test_averaged_disconnect_zeroes_battery_current() -> None:
    params = AveragedSystemParams(
        input_capacitance_f=100e-6, output_capacitance_f=100e-6, inductance_h=47e-6,
        battery_resistance_ohm=0.24, path_resistance_ohm=0.05, inductor_dcr_ohm=0.05,
        mosfet_rds_on_ohm=0.02, diode_drop_v=0.35,
    )
    result = simulate_averaged_system(
        params, effective_battery_voltage_v=10.8, target_output_voltage_v=5.0,
        duration_s=0.003, dt_s=5e-6, soft_start_s=1e-3,
        controller=PIController(), load_profile=((0.0, 2.5),),
        protection_disconnect_time_s=0.0015, initial_state=(10.5, 1.0, 5.0),
    )
    tail = [row for row in result["records"] if row["time_s"] > 0.0016]
    assert tail and all(row["battery_current_a"] == 0.0 for row in tail)
