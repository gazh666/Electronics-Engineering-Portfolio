"""SPICE 行为 PI 控制器网表测试（不运行仿真）。"""

from __future__ import annotations

import pytest
from PySpice.Spice.Netlist import Circuit

from control.models import CarrierConfig, ControllerConfig, SoftStartConfig
from control.spice_controller import add_behavioral_pi_controller


def _controller(**overrides) -> ControllerConfig:
    payload = dict(kp=0.0585, ki=117.66, duty_min=0.02, duty_max=0.9)
    payload.update(overrides)
    return ControllerConfig(**payload)


def _build(drive_mode: str, *, carrier: CarrierConfig | None = None):
    circuit = Circuit("controller_test")
    layout = add_behavioral_pi_controller(
        circuit,
        _controller(),
        SoftStartConfig(enabled=True, duration_s=0.002),
        carrier or CarrierConfig(carrier_type="sine", frequency_hz=100e3),
        target_v=5.0,
        end_time_s=0.012,
        drive_mode=drive_mode,
    )
    return circuit, layout


def test_mosfet_drive_netlist_contains_behavioral_loop():
    circuit, layout = _build("mosfet")
    netlist = str(circuit)
    assert "V(ref)-V(out)" in netlist
    assert "V(ref)/max(V(vin),2)" in netlist
    assert "V(ff)+V(prop)+V(integ)" in netlist
    assert "0.5*(1+sin(" in netlist
    assert "V(duty)-V(ramp)" in netlist
    assert layout.elements["gate_resistor"] == "RCG"
    assert layout.elements["gate_pulldown"] == "RCGS"
    assert layout.elements["driver"] == "ECDRV"
    assert layout.nodes["gate"] == "gate"


def test_integrator_current_source_orientation():
    circuit, _ = _build("mosfet")
    netlist = str(circuit).upper()
    # 积分电流源必须注入 integ 节点；节点顺序反了会形成正反馈。
    assert "0 INTEG" in netlist
    assert "INTEG 0 I=" not in netlist


def test_switch_drive_uses_zero_to_five_volt_control():
    circuit, layout = _build("switch")
    netlist = str(circuit)
    assert "5*V(pwm)" in netlist
    assert "10*V(pwm)" not in netlist
    assert layout.nodes["gate"] == ""
    assert layout.elements["gate_resistor"] == ""
    assert layout.elements["driver"] == "BCCTRL"
    assert layout.nodes["drv"] == "ctrl"


def test_back_calculation_term_is_present():
    circuit, _ = _build("mosfet")
    assert "117.66*V(err)+2000*" in str(circuit)


def test_conditional_anti_windup_expression_changes():
    circuit = Circuit("conditional")
    layout = add_behavioral_pi_controller(
        circuit,
        _controller(anti_windup="conditional"),
        SoftStartConfig(),
        CarrierConfig(),
        target_v=5.0,
        end_time_s=0.012,
    )
    assert "max(V(err),0)" in layout.expressions["integral"]
    assert "min(V(err),0)" in layout.expressions["integral"]


def test_feedforward_can_be_disabled_in_netlist():
    circuit = Circuit("feedforward_off")
    layout = add_behavioral_pi_controller(
        circuit,
        _controller(feedforward_enabled=False),
        SoftStartConfig(enabled=True, duration_s=0.002),
        CarrierConfig(carrier_type="sine", frequency_hz=100e3),
        target_v=5.0,
        end_time_s=0.012,
    )
    netlist = str(circuit)
    assert "V(ref)/max(V(vin),2)" not in netlist
    assert layout.expressions["feedforward"] == "0"
    assert "V(ff)+V(prop)+V(integ)" in netlist


def test_sawtooth_carrier_is_rejected_for_spice():
    with pytest.raises(ValueError):
        _build("mosfet", carrier=CarrierConfig(carrier_type="sawtooth", frequency_hz=100e3))


def test_invalid_drive_mode_rejected():
    circuit = Circuit("bad")
    with pytest.raises(ValueError):
        add_behavioral_pi_controller(
            circuit,
            _controller(),
            SoftStartConfig(),
            CarrierConfig(),
            target_v=5.0,
            end_time_s=0.012,
            drive_mode="relay",
        )
