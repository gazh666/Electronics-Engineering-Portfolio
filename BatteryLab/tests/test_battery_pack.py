"""3S1P 电池组测试。"""

from __future__ import annotations

import numpy as np
import pytest

from battery_models.battery_pack import (
    PackError,
    SeriesBatteryPack,
    build_inconsistent_pack,
    build_uniform_pack,
    simulate_series_pack,
)
from battery_models.ocv_model import ConstantOcvModel, load_ocv_reference
from battery_models.parameters import load_ecm_models
from simulations.load_profiles import single_pulse_profile


@pytest.fixture(scope="module")
def models():
    return load_ecm_models()


def test_uniform_pack_voltage_is_three_times_cell(models) -> None:
    definition = models["second_order_rc"]
    pack = build_uniform_pack(definition, ConstantOcvModel(3.8), count=3, initial_soc=0.6)
    times, currents = single_pulse_profile().sample(0.1)
    result = simulate_series_pack(pack, times, currents)
    pack_frame = result["pack_frame"]
    assert pack_frame["pack_voltage_v"].iloc[0] == pytest.approx(11.4)
    assert pack_frame.loc[pack_frame["time_s"] == 10.0, "pack_voltage_v"].iloc[0] == pytest.approx(11.22)
    assert float(pack_frame["voltage_sum_error_v"].abs().max()) < 1e-9
    assert float(pack_frame["delta_cell_voltage_v"].max()) == pytest.approx(0.0, abs=1e-12)
    assert result["metadata"]["total_r0_ohm"] == pytest.approx(0.09)


def test_sixty_second_pack_voltage(models) -> None:
    definition = models["second_order_rc"]
    pack = build_uniform_pack(definition, ConstantOcvModel(3.8))
    times = np.array([0.0, 10.0, 70.0])
    currents = np.array([0.0, 2.0, 2.0])
    result = simulate_series_pack(pack, times, currents)
    assert float(result["pack_frame"]["pack_voltage_v"].iloc[-1]) == pytest.approx(11.0491, abs=1e-4)


def test_identical_cells_have_identical_states(models) -> None:
    definition = models["first_order_rc"]
    pack = build_uniform_pack(definition, ConstantOcvModel(3.8))
    times, currents = single_pulse_profile().sample(0.5)
    result = simulate_series_pack(pack, times, currents)
    cell_frame = result["cell_frame"]
    pivot = cell_frame.pivot_table(index="time_s", columns="cell_id", values="terminal_voltage_v")
    assert np.allclose(pivot["cell1"], pivot["cell2"])
    assert np.allclose(pivot["cell1"], pivot["cell3"])
    socs = cell_frame.pivot_table(index="time_s", columns="cell_id", values="soc")
    assert np.allclose(socs["cell1"], socs["cell3"])


def test_resistance_mismatch_creates_voltage_spread_and_consistent_losses(models) -> None:
    definition = models["second_order_rc"]
    pack = build_inconsistent_pack(
        definition,
        ConstantOcvModel(3.8),
        socs=[0.6, 0.6, 0.6],
        r0_ohm=[0.030, 0.040, 0.060],
    )
    times = np.array([0.0, 10.0, 10.1])
    currents = np.array([0.0, 2.0, 2.0])
    result = simulate_series_pack(pack, times, currents)
    frame = result["cell_frame"]
    at_step = frame[frame["time_s"] == 10.0].set_index("cell_id")["terminal_voltage_v"]
    assert at_step["cell1"] == pytest.approx(3.74)
    assert at_step["cell2"] == pytest.approx(3.72)
    assert at_step["cell3"] == pytest.approx(3.68)
    pack_frame = result["pack_frame"]
    pack_loss = float(pack_frame["pack_ohmic_loss_w"].iloc[1])
    cell_loss = float(frame[(frame["time_s"] == 10.0)]["ohmic_loss_w"].sum())
    assert pack_loss == pytest.approx(cell_loss, abs=1e-12)
    assert pack_loss == pytest.approx(4.0 * 0.13)


def test_capacity_mismatch_terminates_at_weakest_cell(models) -> None:
    definition = models["second_order_rc"]
    pack = build_inconsistent_pack(
        definition,
        ConstantOcvModel(3.8),
        socs=[0.6, 0.6, 0.6],
        capacities_ah=[2.0, 1.9, 1.8],
    )
    times = np.arange(0.0, 2501.0, 1.0)
    currents = np.full(times.size, 2.0)
    result = simulate_series_pack(pack, times, currents)
    assert result["metadata"]["termination"] == "terminated"
    assert result["metadata"]["termination_cell"] == "cell3"
    assert result["metadata"]["termination_reason"] == "soc_lower_limit"
    assert result["metadata"]["termination_time_s"] == pytest.approx(0.6 * 1.8 * 3600.0 / 2.0, rel=2e-3)


def test_soc_mismatch_creates_voltage_spread(models) -> None:
    definition = models["second_order_rc"]
    pack = build_inconsistent_pack(definition, load_ocv_reference(), socs=[0.7, 0.6, 0.5])
    times = np.array([0.0, 1.0])
    currents = np.array([0.0, 0.0])
    result = simulate_series_pack(pack, times, currents)
    frame = result["cell_frame"]
    first = frame[frame["time_s"] == 0.0].set_index("cell_id")["terminal_voltage_v"]
    assert first["cell1"] > first["cell2"] > first["cell3"]
    assert result["metadata"]["final_delta_cell_voltage_v"] > 0.13


def test_pack_rejects_invalid_configuration(models) -> None:
    definition = models["rint"]
    with pytest.raises(PackError):
        SeriesBatteryPack([])
    with pytest.raises(PackError):
        build_inconsistent_pack(definition, ConstantOcvModel(3.8), socs=[0.6, 0.6], capacities_ah=[2.0])
