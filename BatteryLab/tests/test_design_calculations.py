import pytest

from eda_tools.copper_calculations import calculate_copper_trace
from eda_tools.design_calculations import (
    calculate_balancing_branch,
    calculate_differential_rc,
    calculate_mosfet_path,
    calculate_shunt,
    calculate_shunt_scale,
)
from eda_tools.feedback_design import (
    calculate_actual_feedback_voltage,
    calculate_bq24610_adapter_current,
    calculate_bq24610_charge_current,
    calculate_bq24610_precharge_current,
    calculate_feedback_divider,
    nearest_e96,
)
from eda_tools.inductor_design import (
    calculate_buck_inductor,
    calculate_lc_resonance,
    calculate_ripple_for_inductance,
)
from eda_tools.thermal_calculations import (
    estimate_junction_temperature,
    estimate_rds_on_at_temperature,
)


def test_shunt_power():
    result = calculate_shunt(current_a=2.0, resistance_ohm=0.01, rated_power_w=0.5)
    assert result["voltage_drop_v"] == pytest.approx(0.02)
    assert result["power_loss_w"] == pytest.approx(0.04)
    assert result["nominal_power_limit_pass"] is True


def test_shunt_overload():
    result = calculate_shunt(current_a=10.0, resistance_ohm=0.1, rated_power_w=0.5)
    assert result["nominal_power_limit_pass"] is False
    assert result["nominal_power_utilization_percent"] == pytest.approx(2000.0)


def test_shunt_rejects_nonpositive():
    with pytest.raises(ValueError):
        calculate_shunt(current_a=1.0, resistance_ohm=0.0, rated_power_w=0.5)


def test_shunt_scale_uses_adc_lsb():
    result = calculate_shunt_scale(0.01, 0.2, 7.568e-6)
    assert result["full_scale_current_a"] == pytest.approx(20.0)
    assert result["current_lsb_a"] == pytest.approx(7.568e-4, rel=1e-6)


def test_back_to_back_mosfet_loss():
    result = calculate_mosfet_path(current_rms_a=2.0, resistances_ohm=[0.01, 0.01])
    assert result["total_conduction_loss_w"] == pytest.approx(0.08)
    assert result["path_resistance_ohm"] == pytest.approx(0.02)


def test_mosfet_path_rejects_empty():
    with pytest.raises(ValueError):
        calculate_mosfet_path(current_rms_a=1.0, resistances_ohm=[])


def test_balancing_current():
    result = calculate_balancing_branch(
        cell_voltage_v=4.0, balance_resistance_ohm=100.0, switch_resistance_ohm=0.0
    )
    assert result["balancing_current_a"] == pytest.approx(0.04)
    assert result["resistor_power_w"] == pytest.approx(0.16)


def test_balancing_with_internal_switch_resistance():
    result = calculate_balancing_branch(
        cell_voltage_v=4.05, balance_resistance_ohm=47.0, switch_resistance_ohm=28.0
    )
    assert result["balancing_current_a"] == pytest.approx(4.05 / 75.0)
    assert result["resistor_power_w"] == pytest.approx((4.05 / 75.0) ** 2 * 47.0)


def test_rc_cutoff():
    result = calculate_differential_rc(
        resistance_high_ohm=47.0,
        resistance_low_ohm=47.0,
        capacitance_f=220e-9,
        interference_frequency_hz=100000.0,
    )
    assert result["cutoff_frequency_hz"] == pytest.approx(7696.08, rel=0.001)
    assert result["attenuation_db"] == pytest.approx(-22.30, rel=0.001)


def test_rc_rejects_zero_capacitance():
    with pytest.raises(ValueError):
        calculate_differential_rc(47.0, 47.0, 0.0, 100000.0)


def test_junction_temperature():
    result = estimate_junction_temperature(25.0, 0.2, 50.0)
    assert result["estimated_temperature_rise_c"] == pytest.approx(10.0)
    assert result["estimated_junction_temperature_c"] == pytest.approx(35.0)


def test_junction_temperature_rejects_negative_power():
    with pytest.raises(ValueError):
        estimate_junction_temperature(25.0, -1.0, 50.0)


def test_rds_on_scaling():
    result = estimate_rds_on_at_temperature(0.0022, 125.0)
    assert result["scale_factor"] == pytest.approx(1.5)
    assert result["rds_on_ohm"] == pytest.approx(0.0033)


def test_feedback_divider():
    result = calculate_feedback_divider(12.15, 2.1, 100_000.0)
    assert result["upper_resistance_ohm"] == pytest.approx(478_571.4286, rel=1e-6)
    assert result["divider_current_a"] == pytest.approx(12.15 / 578_571.4286, rel=1e-6)


def test_feedback_divider_rejects_invalid_voltage():
    with pytest.raises(ValueError):
        calculate_feedback_divider(2.0, 2.1, 100_000.0)


def test_actual_feedback_voltage():
    voltage = calculate_actual_feedback_voltage(2.1, 475_000.0, 100_000.0)
    assert voltage == pytest.approx(12.075)


def test_nearest_e96():
    assert nearest_e96(478_571.0) == pytest.approx(475_000.0)
    assert nearest_e96(154_000.0) == pytest.approx(154_000.0)


def test_bq24610_current_equations():
    assert calculate_bq24610_charge_current(0.2, 0.01) == pytest.approx(1.0)
    assert calculate_bq24610_precharge_current(0.1, 0.01) == pytest.approx(0.1)
    assert calculate_bq24610_adapter_current(0.3, 0.01) == pytest.approx(1.5)


def test_buck_inductor():
    result = calculate_buck_inductor(18.0, 12.15, 1.0, 600e3, 0.3)
    assert result["ideal_duty"] == pytest.approx(0.675)
    assert result["required_inductance_h"] == pytest.approx(21.944e-6, rel=1e-3)
    assert result["estimated_peak_current_a"] == pytest.approx(1.15)


def test_buck_inductor_rejects_boost():
    with pytest.raises(ValueError):
        calculate_buck_inductor(10.0, 12.0, 1.0, 600e3, 0.3)


def test_ripple_for_inductance():
    result = calculate_ripple_for_inductance(18.0, 12.15, 22e-6, 600e3)
    assert result["estimated_ripple_a"] == pytest.approx(0.299, rel=1e-2)


def test_lc_resonance():
    frequency = calculate_lc_resonance(22e-6, 9.4e-6)
    assert frequency == pytest.approx(11067.0, rel=1e-3)


def test_copper_trace():
    result = calculate_copper_trace(20.0, 2.0, 35.0, 2.5, 20.0)
    assert result["resistance_ohm"] == pytest.approx(4.9257e-3, rel=1e-3)
    assert result["power_loss_w"] == pytest.approx(0.0308, rel=1e-2)


def test_copper_trace_rejects_bad_geometry():
    with pytest.raises(ValueError):
        calculate_copper_trace(0.0, 2.0, 35.0, 2.5)
