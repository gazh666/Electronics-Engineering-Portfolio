"""输入特性扫描测试（真实 SPICE，两个输入电压点）。"""

from __future__ import annotations

import pytest

from circuits.nonideal_config import load_nonideal_buck_config
from experiments.line_characteristics import run_line_characteristic


@pytest.fixture(scope="module")
def sweep():
    config = load_nonideal_buck_config()
    return run_line_characteristic(
        config,
        (10.8, 12.0),
        variant="E",
        maximum_end_time_s=5e-3,
    )


def test_line_sweep_rows_come_from_spice(sweep):
    table = sweep.table
    assert len(table) == 2
    assert list(table["input_voltage_v"]) == [10.8, 12.0]
    assert set(table["steady_state"]) == {True}
    assert set(table["constant_target_duty"]) == {True}
    for row in table.to_dict("records"):
        expected_duty = sweep.regulation["nominal_voltage_v"] / row["input_voltage_v"]
        assert row["duty_cycle"] == pytest.approx(expected_duty, rel=1e-12)
        assert row["overall_status"] == "PASS"
    assert sweep.table["run_id"].is_unique


def test_line_sweep_regulation_is_labelled_feedforward(sweep):
    regulation = sweep.regulation
    assert regulation["status"] == "AVAILABLE"
    assert regulation["data_source"] == "spice_simulation"
    assert regulation["points"] == 2
    assert regulation["excluded_not_settled"] == 0
    assert "not closed-loop" in regulation["control_note"]
    assert regulation["sensitivity_mv_per_v"] < 0.0
    assert regulation["r_squared"] == pytest.approx(1.0, abs=1e-9)
    assert sweep.runs[0]["input_voltage_v"] == pytest.approx(10.8)
    assert "max_step_time_s" in sweep.runs[0]


def test_line_sweep_rejects_invalid_arguments():
    config = load_nonideal_buck_config()
    with pytest.raises(ValueError):
        run_line_characteristic(config, (12.0,))
    with pytest.raises(ValueError):
        run_line_characteristic("not-a-config", (10.8, 12.0))
    with pytest.raises(ValueError):
        run_line_characteristic(config, (3.0, 12.0), constant_target_duty=True)
