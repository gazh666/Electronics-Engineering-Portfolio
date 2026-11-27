"""平均 Buck 模型测试（解析工作点与线性化，不运行 SPICE）。"""

from __future__ import annotations

import numpy as np
import pytest

from control.averaged_buck import (
    AveragedBuckParameters,
    buck_derivatives,
    ccm_check,
    linearize,
    nonideal_derivatives,
    operating_point,
)


def _ideal(**overrides) -> AveragedBuckParameters:
    payload = dict(
        vin_v=12.0,
        inductance_h=47e-6,
        capacitance_f=100e-6,
        load_resistance_ohm=2.5,
        dcr_ohm=0.0,
        esr_ohm=0.0,
        rds_on_ohm=0.0,
        diode_forward_v=0.0,
    )
    payload.update(overrides)
    return AveragedBuckParameters(**payload)


def test_parameter_defaults_and_model_source():
    parameters = AveragedBuckParameters()
    assert parameters.period_s == pytest.approx(10e-6)
    assert parameters.to_dict()["model_source"] == "averaged_model"
    with pytest.raises(ValueError):
        AveragedBuckParameters(rds_on_ohm=5.0)


def test_ideal_operating_point_matches_duty_times_vin():
    parameters = _ideal()
    op = operating_point(0.5, parameters, nonideal=False)
    assert op.output_voltage_v == pytest.approx(6.0)
    assert op.inductor_current_a == pytest.approx(2.4)
    assert op.delta_inductor_current_a > 0.0
    assert op.continuous_conduction is True


def test_nonideal_operating_point_is_lower_than_ideal():
    parameters = AveragedBuckParameters(diode_forward_v=0.5, rds_on_ohm=0.01, dcr_ohm=0.05)
    ideal = operating_point(0.5, parameters, nonideal=False)
    real = operating_point(0.5, parameters, nonideal=True)
    assert real.output_voltage_v < ideal.output_voltage_v
    assert real.inductor_current_a == pytest.approx(real.output_voltage_v / 2.5)


def test_derivatives_at_steady_state_are_zero():
    parameters = _ideal()
    op = operating_point(0.5, parameters, nonideal=False)
    di, dv = buck_derivatives(op.inductor_current_a, op.capacitor_voltage_v, 0.5, parameters)
    assert di == pytest.approx(0.0, abs=1e-6)
    assert dv == pytest.approx(0.0, abs=1e-6)


def test_constant_current_load_derivatives():
    parameters = _ideal(load_type="constant_current", load_current_a=2.0)
    di, dv = buck_derivatives(2.0, 6.0, 0.5, parameters)
    assert di == pytest.approx(0.0, abs=1e-6)
    assert dv == pytest.approx(0.0, abs=1e-9)


def test_derivatives_reject_invalid_duty():
    parameters = _ideal()
    with pytest.raises(ValueError):
        buck_derivatives(1.0, 5.0, 1.2, parameters)
    with pytest.raises(ValueError):
        nonideal_derivatives(1.0, 5.0, -0.1, parameters)


def test_esr_raises_output_voltage_for_positive_current():
    parameters = _ideal(esr_ohm=0.03)
    assert parameters.output_voltage(3.0, 5.0) > 5.0
    assert parameters.output_voltage(3.0, 5.0) < 5.0 + 0.03 * 3.0


def test_linearize_shapes_and_signs():
    parameters = AveragedBuckParameters()
    a, b, c, d = linearize(parameters, 0.44)
    assert a.shape == (2, 2)
    assert b.shape == (2, 1)
    assert c.shape == (1, 2)
    assert d.shape == (1, 1)
    assert b[0, 0] > 0
    assert a[0, 0] < 0


def test_ccm_check_detects_dcm_condition():
    parameters = _ideal()
    delta, valley, ccm = ccm_check(0.1, 6.0, 0.5, parameters)
    assert delta == pytest.approx((12.0 - 6.0) * 0.5 * 10e-6 / 47e-6)
    assert valley == pytest.approx(0.1 - 0.5 * delta)
    assert ccm is False
    _, _, ccm_high = ccm_check(2.0, 6.0, 0.5, parameters)
    assert ccm_high is True
