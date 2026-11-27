"""功率映射与静态耦合测试。"""

from __future__ import annotations

import pytest

from system_models.converter_power_map import (
    ConverterPowerMap,
    PowerMapPoint,
    build_points,
    load_power_maps_from_payload,
    solve_power_map_operating_point,
)


def make_point(vin: float, iin: float, load: float = 1.0) -> PowerMapPoint:
    return PowerMapPoint(
        input_voltage_v=vin,
        load_current_a=load,
        output_voltage_v=5.0,
        output_current_a=5.0 / 2.5,
        input_current_a=iin,
        input_power_w=vin * iin,
        output_power_w=5.0 * 5.0 / 2.5,
        efficiency_percent=90.0,
        output_ripple_vpp=0.02,
        inductor_peak_current_a=2.0,
        ccm=True,
        controller_configuration={},
        steady_state_status="STEADY_STATE_REACHED",
        status="CONVERGED",
        run_id="test",
    )


def test_power_map_evaluate_interpolates_inside_range() -> None:
    power_map = ConverterPowerMap(load_current_a=1.0, points=[make_point(9.0, 0.6), make_point(12.0, 0.45)], source="test")
    value = power_map.evaluate(10.5)
    assert value is not None
    assert value["input_current_a"] == pytest.approx(0.525)


def test_power_map_forbids_extrapolation() -> None:
    power_map = ConverterPowerMap(load_current_a=1.0, points=[make_point(9.0, 0.6), make_point(12.0, 0.45)], source="test")
    assert power_map.evaluate(8.9) is None
    assert power_map.evaluate(12.1) is None
    assert power_map.evaluate(float("nan")) is None


def test_power_map_requires_strictly_increasing_voltage() -> None:
    with pytest.raises(ValueError):
        ConverterPowerMap(load_current_a=1.0, points=[make_point(9.0, 0.6), make_point(9.0, 0.5)], source="test")


def test_power_map_rejects_dcm_points() -> None:
    point = PowerMapPoint(**{**make_point(9.0, 0.6).to_dict(), "ccm": False,
                             "controller_configuration": {}, "status": "CONVERGED"})
    with pytest.raises(ValueError):
        ConverterPowerMap(load_current_a=1.0, points=[point, make_point(12.0, 0.5)], source="test")


def test_power_map_rejects_mixed_loads() -> None:
    with pytest.raises(ValueError):
        ConverterPowerMap(load_current_a=1.0, points=[make_point(9.0, 0.6, 1.0), make_point(12.0, 0.5, 1.5)], source="test")


def test_operating_point_solves_residual() -> None:
    grid = [9.0, 10.0, 11.0, 12.0]
    currents = [0.60, 0.54, 0.49, 0.45]
    result = solve_power_map_operating_point(10.8, 0.29, grid, currents)
    assert result.status == "STATIC_POINT_FOUND"
    assert result.converter_input_voltage_v is not None and result.battery_current_a is not None
    residual = result.converter_input_voltage_v + 0.29 * result.battery_current_a - 10.8
    assert abs(residual) < 1e-7


def test_operating_point_out_of_range() -> None:
    result = solve_power_map_operating_point(7.5, 0.29, [9.0, 10.0, 11.0, 12.0], [0.6, 0.54, 0.49, 0.45])
    assert result.status == "NO_VERIFIED_OPERATING_POINT"


def test_invalid_grid_raises() -> None:
    with pytest.raises(ValueError):
        solve_power_map_operating_point(10.8, 0.29, [9.0, 9.0], [0.6, 0.5])
    with pytest.raises(ValueError):
        solve_power_map_operating_point(10.8, -0.1, [9.0, 10.0], [0.6, 0.5])


def test_build_points_filters_failed_runs() -> None:
    payload = {
        "points": [
            {"input_voltage_v": 9.0, "load_current_a": 1.0, "status": "CONVERGED", "ccm": True,
             "metrics": {"output_voltage_mean_v": 5.0, "output_current_mean_a": 2.0,
                         "input_current_mean_a": 0.6, "input_power_w": 5.4, "output_power_w": 10.0,
                         "efficiency_percent": 90.0, "output_voltage_ripple_vpp": 0.02,
                         "inductor_peak_current_a": 2.1, "ccm_fraction": 1.0},
             "steady_state": {"status": "STEADY_STATE_REACHED"}},
            {"input_voltage_v": 10.0, "load_current_a": 1.0, "status": "SOLVER_FAILED"},
        ]
    }
    points = build_points(payload, {})
    assert len(points) == 1
    assert points[0].input_voltage_v == 9.0


def test_load_maps_groups_by_load() -> None:
    payload = {"points": []}
    for load in (1.0, 2.0):
        for vin in (9.0, 10.0, 11.0, 12.0):
            payload["points"].append({
                "input_voltage_v": vin, "load_current_a": load, "status": "CONVERGED", "ccm": True,
                "metrics": {"output_voltage_mean_v": 5.0, "output_current_mean_a": 5.0,
                            "input_current_mean_a": 0.5, "input_power_w": vin * 0.5,
                            "output_power_w": 10.0, "efficiency_percent": 90.0,
                            "output_voltage_ripple_vpp": 0.02, "inductor_peak_current_a": 2.0,
                            "ccm_fraction": 1.0},
                "steady_state": {"status": "STEADY_STATE_REACHED"},
            })
    maps = load_power_maps_from_payload(payload, {})
    assert sorted(maps) == [1.0, 2.0]
