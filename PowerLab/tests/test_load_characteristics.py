"""负载特性扫描测试（真实 SPICE，两个负载点）。"""

from __future__ import annotations

import pytest

from circuits.nonideal_config import load_nonideal_buck_config
from experiments.load_characteristics import run_load_characteristic


@pytest.fixture(scope="module")
def sweep():
    config = load_nonideal_buck_config()
    return run_load_characteristic(
        config,
        (5.0, 2.5),
        variant="E",
        maximum_end_time_s=5e-3,
    )


def test_load_sweep_rows_come_from_spice(sweep):
    table = sweep.table
    assert len(table) == 2
    assert set(table["variant"]) == {"E"}
    assert set(table["steady_state"]) == {True}
    assert list(table["load_resistance_ohm"]) == [5.0, 2.5]
    for column in (
        "output_voltage_v",
        "output_current_a",
        "output_voltage_ripple_vpp",
        "inductor_current_mean_a",
        "efficiency_system_percent",
        "conduction_mode",
        "overall_status",
        "run_id",
    ):
        assert column in table.columns
    assert table["run_id"].is_unique
    assert (table["output_voltage_v"] > 4.0).all()
    assert (table["output_voltage_v"] < 6.0).all()
    assert table["efficiency_system_percent"].between(80.0, 100.0).all()


def test_load_sweep_regulation_summary(sweep):
    regulation = sweep.regulation
    assert regulation["status"] == "AVAILABLE"
    assert regulation["data_source"] == "spice_simulation"
    assert regulation["points"] == 2
    assert regulation["excluded_not_settled"] == 0
    assert regulation["ccm_points"] == 2
    assert regulation["span_v"] == pytest.approx(
        abs(
            sweep.table["output_voltage_v"].iloc[0]
            - sweep.table["output_voltage_v"].iloc[1]
        ),
        rel=1e-9,
    )
    assert sweep.runs[0]["run_id"] == sweep.table["run_id"].iloc[0]
    assert "max_step_time_s" in sweep.runs[0]
    assert sweep.to_dict()["data_source"] == "spice_simulation"


def test_load_sweep_rejects_invalid_arguments():
    config = load_nonideal_buck_config()
    with pytest.raises(ValueError):
        run_load_characteristic(config, (5.0,))
    with pytest.raises(ValueError):
        run_load_characteristic(config, (5.0, 0.0))
    with pytest.raises(ValueError):
        run_load_characteristic("not-a-config", (5.0, 2.5))
