"""任务注册表、白名单与单位转换测试（第九阶段 Task 10、16）。"""

from __future__ import annotations

import pytest

from jobs.models import InvalidJobRequest
from jobs.registry import (
    ALLOWED_JOB_TYPES,
    MODEL_SPECS,
    resolve_handler,
    validate_closed_loop_request,
    validate_monte_carlo_request,
    validate_request,
    validate_sweep_request,
    validate_validation_request,
)


def _defaults(model: str) -> dict:
    payload = {field.name: field.default for field in MODEL_SPECS[model].fields}
    payload["model"] = model
    return payload


def test_six_job_types_allowed():
    assert ALLOWED_JOB_TYPES == (
        "circuit_simulation",
        "performance_analysis",
        "parameter_sweep",
        "closed_loop_experiment",
        "numerical_validation",
        "monte_carlo",
    )


def test_six_models_registered():
    assert set(MODEL_SPECS) == {
        "voltage_divider",
        "rc_transient",
        "rl_transient",
        "rlc_transient",
        "buck_ideal",
        "nonideal_buck",
    }


def test_voltage_divider_request_uses_volts():
    validated = validate_request("circuit_simulation", _defaults("voltage_divider"))
    assert validated["vin_v"] == pytest.approx(12.0)
    assert validated["r1_ohm"] == pytest.approx(1000.0)


def test_time_fields_convert_ms_and_ns_to_seconds():
    validated = validate_request("circuit_simulation", _defaults("nonideal_buck"))
    assert validated["end_time_s"] == pytest.approx(5e-3)
    assert validated["step_time_s"] == pytest.approx(100e-9)
    assert validated["max_step_time_s"] == pytest.approx(50e-9)


def test_passive_fields_convert_to_si():
    validated = validate_request("circuit_simulation", _defaults("nonideal_buck"))
    assert validated["inductance_h"] == pytest.approx(47e-6)
    assert validated["capacitance_f"] == pytest.approx(100e-6)
    assert validated["switching_frequency_hz"] == pytest.approx(100e3)


def test_rc_request_conversion():
    validated = validate_request("circuit_simulation", _defaults("rc_transient"))
    assert validated["capacitance_f"] == pytest.approx(1e-6)
    assert validated["end_time_s"] == pytest.approx(6e-3)
    assert validated["step_time_s"] == pytest.approx(10e-6)


def test_unknown_model_rejected():
    with pytest.raises(InvalidJobRequest):
        validate_request("circuit_simulation", {"model": "ideal_opamp"})


def test_unknown_field_rejected():
    payload = _defaults("voltage_divider")
    payload["magic_gain"] = 3.0
    with pytest.raises(InvalidJobRequest):
        validate_request("circuit_simulation", payload)


def test_missing_field_rejected():
    payload = _defaults("voltage_divider")
    payload.pop("r2_ohm")
    with pytest.raises(InvalidJobRequest):
        validate_request("circuit_simulation", payload)


def test_below_minimum_rejected():
    payload = _defaults("voltage_divider")
    payload["vin_v"] = 0.0
    with pytest.raises(InvalidJobRequest):
        validate_request("circuit_simulation", payload)


def test_non_numeric_rejected():
    payload = _defaults("voltage_divider")
    payload["vin_v"] = "12"
    with pytest.raises(InvalidJobRequest):
        validate_request("circuit_simulation", payload)


def test_invalid_variant_rejected():
    payload = _defaults("nonideal_buck")
    payload["variant"] = "Z"
    with pytest.raises(InvalidJobRequest):
        validate_request("circuit_simulation", payload)


def test_max_step_larger_than_step_rejected():
    payload = _defaults("nonideal_buck")
    payload["step_time_s"] = 30.0
    payload["max_step_time_s"] = 50.0
    with pytest.raises(InvalidJobRequest):
        validate_request("circuit_simulation", payload)


def test_buck_target_must_stay_below_input():
    payload = _defaults("buck_ideal")
    payload["target_output_voltage_v"] = 12.0
    payload["input_voltage_v"] = 12.0
    with pytest.raises(InvalidJobRequest):
        validate_request("circuit_simulation", payload)


def test_sweep_values_convert_to_si():
    validated = validate_sweep_request(
        {"parameter": "inductance_h", "values": [22, 47], "base": _defaults("nonideal_buck")}
    )
    assert validated["values"] == pytest.approx([22e-6, 47e-6])
    assert validated["base"]["model"] == "nonideal_buck"


def test_sweep_requires_two_values():
    with pytest.raises(InvalidJobRequest):
        validate_sweep_request({"parameter": "inductance_h", "values": [47]})


def test_sweep_rejects_too_many_values():
    with pytest.raises(InvalidJobRequest):
        validate_sweep_request({"parameter": "inductance_h", "values": list(range(1, 50))})


def test_sweep_rejects_non_positive_values():
    with pytest.raises(InvalidJobRequest):
        validate_sweep_request({"parameter": "inductance_h", "values": [0, 47]})


def test_sweep_rejects_duty_at_or_above_one():
    with pytest.raises(InvalidJobRequest):
        validate_sweep_request({"parameter": "duty_cycle", "values": [0.4, 1.0]})


def test_sweep_rejects_unknown_parameter():
    with pytest.raises(InvalidJobRequest):
        validate_sweep_request({"parameter": "temperature_c", "values": [1, 2]})


def test_closed_loop_request_converts_units():
    validated = validate_closed_loop_request(
        {
            "mode": "closed_loop",
            "variant": "E",
            "end_time_ms": 8.0,
            "step_time_ns": 100.0,
            "max_step_time_ns": 100.0,
            "soft_start_ms": 2.0,
        }
    )
    assert validated["end_time_s"] == pytest.approx(8e-3)
    assert validated["step_time_s"] == pytest.approx(100e-9)
    assert validated["soft_start_s"] == pytest.approx(2e-3)
    assert validated["duty_max"] == pytest.approx(0.9)


def test_closed_loop_rejects_bad_duty_limits():
    with pytest.raises(InvalidJobRequest):
        validate_closed_loop_request({"duty_min": 0.9, "duty_max": 0.5})


def test_closed_loop_rejects_long_simulation():
    with pytest.raises(InvalidJobRequest):
        validate_closed_loop_request({"end_time_ms": 30.0})


def test_closed_loop_rejects_step_order():
    with pytest.raises(InvalidJobRequest):
        validate_closed_loop_request({"step_time_ns": 50.0, "max_step_time_ns": 100.0})


def test_closed_loop_rejects_negative_gain():
    with pytest.raises(InvalidJobRequest):
        validate_closed_loop_request({"kp": -1.0})


def test_closed_loop_rejects_unknown_field():
    with pytest.raises(InvalidJobRequest):
        validate_closed_loop_request({"ctrl_mode": "pid"})


def test_validation_request_converts_steps():
    validated = validate_validation_request({"steps_ns": [200, 100, 50]})
    assert validated["steps_s"] == pytest.approx([200e-9, 100e-9, 50e-9])
    assert validated["variant"] == "E"


def test_validation_request_rejects_single_step():
    with pytest.raises(InvalidJobRequest):
        validate_validation_request({"steps_ns": [100]})


def test_validation_request_rejects_out_of_range_step():
    with pytest.raises(InvalidJobRequest):
        validate_validation_request({"steps_ns": [100, 6000]})


def test_monte_carlo_defaults():
    validated = validate_monte_carlo_request({"samples": 5})
    assert validated["samples"] == 5
    assert validated["end_time_s"] == pytest.approx(4e-3)
    assert set(validated["tolerances"]) == {"inductor", "capacitor", "dcr", "esr"}


def test_monte_carlo_rejects_unsupported_sample_count():
    with pytest.raises(InvalidJobRequest):
        validate_monte_carlo_request({"samples": 7})


def test_monte_carlo_rejects_large_tolerance():
    with pytest.raises(InvalidJobRequest):
        validate_monte_carlo_request({"samples": 5, "tolerances": {"inductor": 0.9}})


def test_monte_carlo_rejects_unknown_tolerance_key():
    with pytest.raises(InvalidJobRequest):
        validate_monte_carlo_request({"samples": 5, "tolerances": {"resistor": 0.1}})


def test_monte_carlo_rejects_negative_seed():
    with pytest.raises(InvalidJobRequest):
        validate_monte_carlo_request({"samples": 5, "seed": -1})


def test_performance_analysis_needs_run_id():
    with pytest.raises(InvalidJobRequest):
        validate_request("performance_analysis", {})
    assert validate_request("performance_analysis", {"run_id": " 20261125_120000_abcd "}) == {
        "run_id": "20261125_120000_abcd"
    }


def test_unknown_job_type_rejected():
    with pytest.raises(InvalidJobRequest):
        validate_request("shell_command", {})


@pytest.mark.parametrize("job_type", ALLOWED_JOB_TYPES)
def test_every_job_type_resolves_to_handler(job_type):
    assert callable(resolve_handler(job_type))


def test_unknown_job_type_has_no_handler():
    with pytest.raises(InvalidJobRequest):
        resolve_handler("rm_rf")
