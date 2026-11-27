"""多层模型对照测试：平均模型缺失量标记 NOT_APPLICABLE，缺失数据不得 PASS。"""

from __future__ import annotations

import pytest

from circuits.nonideal_config import load_nonideal_buck_config
from validation.model_cross_validation import (
    MODEL_LEVELS,
    averaged_metrics,
    cross_validate,
    matrix_to_records,
    model_matrix,
)


def _theory() -> dict:
    return {
        "ideal_ccm": {
            "ideal_output_voltage_v": 5.0,
            "ideal_output_current_a": 2.0,
            "inductor_ripple_app": 0.5,
            "inductor_peak_current_a": 2.25,
            "capacitor_ripple_vpp": 0.01,
            "ccm_assumption_valid": True,
        }
    }


def _spice_metrics(vout: float = 5.0) -> dict:
    return {
        "output_voltage_mean_v": vout,
        "inductor_current_ripple_a": 0.5,
        "inductor_current_mean_a": 2.0,
        "output_voltage_ripple_vpp": 0.02,
        "efficiency_system_percent": 90.0,
        "switching_transition_energy_j": 1e-5,
    }


def _rows(config, *, spice_vout: float = 5.0) -> list[dict]:
    return model_matrix(
        _theory(),
        averaged_metrics(config),
        {"C": _spice_metrics(), "E": _spice_metrics(spice_vout)},
    )


def test_model_levels_define_four_layers():
    assert len(MODEL_LEVELS) == 4
    assert [level.key for level in MODEL_LEVELS] == [
        "A_IDEAL_THEORY",
        "B_AVERAGED",
        "C_SWITCHING_SPICE",
        "D_MOSFET_SPICE",
    ]
    averaged = MODEL_LEVELS[1]
    assert averaged.data_source == "averaged_model"
    assert averaged.includes_switching_ripple is False
    assert averaged.includes_switching_loss is False
    assert MODEL_LEVELS[2].includes_switching_ripple is True
    assert MODEL_LEVELS[3].data_source == "spice_simulation"


def test_averaged_metrics_have_no_ripple_or_transition_energy():
    config = load_nonideal_buck_config()
    metrics = averaged_metrics(config)
    assert metrics["data_source"] == "averaged_model"
    assert metrics["not_a_switching_waveform"] is True
    assert metrics["output_voltage_ripple_vpp"] is None
    assert metrics["switching_transition_energy_j"] is None
    assert metrics["output_voltage_mean_v"] > 0
    assert 0 < metrics["efficiency_system_percent"] < 100


def test_model_matrix_reports_missing_variants_as_insufficient_data():
    config = load_nonideal_buck_config()
    rows = model_matrix(_theory(), averaged_metrics(config), {})
    by_level = {row["model_level"]: row for row in rows}
    assert set(by_level) == {
        "A_IDEAL_THEORY",
        "B_AVERAGED",
        "C_SWITCHING_SPICE",
        "D_MOSFET_SPICE",
    }
    assert by_level["C_SWITCHING_SPICE"]["status"] == "INSUFFICIENT_DATA"
    assert by_level["D_MOSFET_SPICE"]["status"] == "INSUFFICIENT_DATA"
    assert "variant C" in by_level["C_SWITCHING_SPICE"]["reason"]


def test_model_matrix_fills_executed_variants():
    config = load_nonideal_buck_config()
    rows = _rows(config)
    by_level = {row["model_level"]: row for row in rows}
    assert by_level["C_SWITCHING_SPICE"]["output_voltage_mean_v"] == pytest.approx(5.0)
    assert by_level["D_MOSFET_SPICE"]["efficiency_system_percent"] == pytest.approx(90.0)


def test_averaged_ripple_and_efficiency_checks_are_not_applicable():
    config = load_nonideal_buck_config()
    checks = cross_validate(_rows(config))
    averaged = [check for check in checks if check.check_id.startswith("XV-B_AVERAGED")]
    assert len(averaged) == 3
    by_metric = {check.metric_name: check for check in averaged}
    assert by_metric["inductor_current_ripple_a"].status.value == "NOT_APPLICABLE"
    assert by_metric["efficiency_system_percent"].status.value == "NOT_APPLICABLE"
    assert by_metric["output_voltage_mean_v"].status.value in ("PASS", "FAIL")


def test_missing_reference_layer_is_insufficient_data():
    checks = cross_validate([{"model_level": "A_IDEAL_THEORY"}])
    assert len(checks) == 1
    assert checks[0].status.value == "INSUFFICIENT_DATA"
    assert checks[0].check_id == "XV-REFERENCE"


def test_missing_averaged_values_are_insufficient_data_never_pass():
    rows = [
        {"model_level": "A_IDEAL_THEORY", "data_source": "analytical_theory", "status": "INSUFFICIENT_DATA"},
        {"model_level": "B_AVERAGED", "data_source": "averaged_model"},
        {
            "model_level": "C_SWITCHING_SPICE",
            "data_source": "spice_simulation",
            **_spice_metrics(),
        },
        {
            "model_level": "D_MOSFET_SPICE",
            "data_source": "spice_simulation",
            **_spice_metrics(),
        },
    ]
    checks = cross_validate(rows)
    averaged = [check for check in checks if check.check_id.startswith("XV-B_AVERAGED")]
    assert averaged
    assert all(check.status.value == "INSUFFICIENT_DATA" for check in averaged)
    assert not any(check.status.value == "PASS" for check in averaged)


def test_matrix_to_records_flattens_and_preserves_none():
    rows = [
        {
            "model_level": "A_IDEAL_THEORY",
            "data_source": "analytical_theory",
            "output_voltage_mean_v": 5.0,
            "output_voltage_ripple_vpp": None,
        },
        {"model_level": "D_MOSFET_SPICE", "status": "INSUFFICIENT_DATA"},
    ]
    records = matrix_to_records(rows)
    assert records[0]["output_voltage_mean_v"] == pytest.approx(5.0)
    assert records[0]["output_voltage_ripple_vpp"] is None
    assert records[0]["status"] == "OK"
    assert records[1]["model_level"] == "D_MOSFET_SPICE"
    assert records[1]["output_voltage_mean_v"] is None
    assert records[1]["status"] == "INSUFFICIENT_DATA"
