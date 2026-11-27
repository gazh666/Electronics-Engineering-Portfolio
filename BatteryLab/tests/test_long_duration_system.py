"""电池端口、保护适配与长期放电模型测试。"""

from __future__ import annotations

import pytest

from integration.battery_port_adapter import build_battery_port
from integration.protection_adapter import ProtectionGate
from system_models.converter_power_map import ConverterPowerMap, PowerMapPoint
from system_models.long_duration_system import simulate_discharge, unused_charge_ah


def fake_map(load: float = 1.5) -> ConverterPowerMap:
    points = [
        PowerMapPoint(
            input_voltage_v=vin, load_current_a=load, output_voltage_v=5.0,
            output_current_a=load, input_current_a=load * 5.0 / vin / 0.92,
            input_power_w=load * 5.0 / 0.92, output_power_w=load * 5.0,
            efficiency_percent=92.0, output_ripple_vpp=0.02, inductor_peak_current_a=load + 0.4,
            ccm=True, controller_configuration={}, steady_state_status="STEADY_STATE_REACHED",
            status="CONVERGED", run_id="fake",
        )
        for vin in (9.0, 9.6, 10.5, 11.1, 12.0, 12.6)
    ]
    return ConverterPowerMap(load_current_a=load, points=points, source="test")


def test_battery_port_state_inside_identified_window() -> None:
    port = build_battery_port(initial_soc=(0.4, 0.4, 0.4))
    state = port.get_port_state()
    assert state.inside_identified_window
    assert state.effective_voltage_v == pytest.approx(10.878, abs=0.02)
    assert state.total_series_resistance_ohm > 0.23


def test_terminal_voltage_drops_with_current() -> None:
    port = build_battery_port()
    low = port.calculate_terminal_state(0.1).pack_voltage_v
    high = port.calculate_terminal_state(2.0).pack_voltage_v
    assert high < low


def test_advance_reduces_soc() -> None:
    port = build_battery_port()
    before = port.socs
    port.advance(2.0, 60.0)
    after = port.socs
    assert all(a < b for a, b in zip(after, before))


def test_soc_outside_window_is_flagged() -> None:
    port = build_battery_port(initial_soc=(0.8, 0.8, 0.8))
    assert not port.get_port_state().inside_identified_window


def test_discharge_runs_to_termination() -> None:
    port = build_battery_port()
    gate = ProtectionGate.from_stage5_config(port.cell_ids)
    gate.arm(0.0)
    result = simulate_discharge(port, gate, fake_map(), duration_s=3600.0, dt_s=5.0)
    assert result["records"]
    assert result["status"] in {"TIME_LIMIT_REACHED", "BMS_UNDERVOLTAGE", "BATTERY_MODEL_LIMIT"}
    assert result["duration_s"] <= 3600.0
    assert result["energy"]["load_energy_wh"] > 0


def test_discharge_terminates_on_undervoltage() -> None:
    port = build_battery_port(initial_soc=(0.05, 0.05, 0.05))
    gate = ProtectionGate.from_stage5_config(port.cell_ids)
    gate.arm(0.0)
    result = simulate_discharge(port, gate, fake_map(2.0), duration_s=3600.0, dt_s=2.0)
    assert result["status"] in {"BMS_UNDERVOLTAGE", "PROTECTION_TRIPPED", "BATTERY_MODEL_LIMIT"}


def test_power_map_gap_terminates() -> None:
    port = build_battery_port(initial_soc=(0.15, 0.15, 0.15))
    gate = ProtectionGate.from_stage5_config(port.cell_ids)
    gate.arm(0.0)
    narrow = ConverterPowerMap(
        load_current_a=2.0,
        points=[fake_map(2.0).points[-1]],
        source="test",
    )
    result = simulate_discharge(port, gate, narrow, duration_s=3600.0, dt_s=5.0)
    assert result["status"] in {
        "POWER_MAP_NOT_VERIFIED",
        "NO_VERIFIED_OPERATING_POINT",
        "OUT_OF_VERIFIED_DOMAIN",
    }


def test_unused_charge() -> None:
    result = {"final_socs": [0.1, 0.2]}
    assert unused_charge_ah(result, [2.0, 2.0]) == pytest.approx(0.6)
