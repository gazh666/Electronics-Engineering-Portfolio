"""二极管直流伏安特性：真实 ngspice 扫描与 Shockley 理论对比。

运行：``python -m scripts.diode_iv_demo``

注意：模型参数 IS=1e-9 A、N=1.8、RS=0.5 Ω 为教学参数，
不对应任何经过验证的商业器件，也不声称 0.7 V 是固定导通电压。
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np
import pandas as pd

from analysis.error_metrics import calculate_error_metrics, relative_error_percent, scalar_relative_error_percent
from analysis.theory import DATA_SOURCE, diode_ideal_current, diode_thermal_voltage
from circuits.diode_circuit import build_diode_iv_circuit
from simulations.config import BasicCircuitsConfig, load_basic_circuits_config
from simulations.runner import SimulationRunner
from storage.result_store import ResultStore
from visualization.plots import plot_diode_iv


def _voltage_at_current(voltage: np.ndarray, current: np.ndarray, target: float) -> float | None:
    above = np.where(current >= target)[0]
    if above.size == 0:
        return None
    index = int(above[0])
    if index == 0:
        return float(voltage[0])
    v0, v1 = voltage[index - 1], voltage[index]
    i0, i1 = current[index - 1], current[index]
    if i1 == i0:
        return float(v1)
    return float(v0 + (target - i0) * (v1 - v0) / (i1 - i0))


def analyze(
    config: BasicCircuitsConfig | None = None,
    store: ResultStore | None = None,
) -> dict[str, Any]:
    config = config or load_basic_circuits_config()
    store = store or ResultStore()
    runner = SimulationRunner(config.simulation_temperature_c)
    diode = config.diode
    sweep_config = config.diode_dc_sweep

    circuit = build_diode_iv_circuit(diode)
    result = runner.run_dc(
        circuit,
        "bias",
        sweep_config.start_v,
        sweep_config.stop_v,
        sweep_config.step_v,
        parameters=diode.to_dict(),
    )

    voltage = result.data["sweep_v"].to_numpy()
    external_voltage = result.data["anode_v"].to_numpy()
    bias_branch_current = result.data["vbias_branch_current_a"].to_numpy()
    diode_current = -bias_branch_current
    theory_current = diode_ideal_current(
        external_voltage,
        diode.saturation_current_a,
        diode.ideality_factor,
        diode.temperature_c,
    )

    metrics = calculate_error_metrics(diode_current, theory_current)
    relative = relative_error_percent(diode_current, theory_current)
    last_index = int(np.argmin(np.abs(voltage - 0.8)))
    at_0p8 = {
        "voltage_v": float(external_voltage[last_index]),
        "simulated_current_a": float(diode_current[last_index]),
        "shockley_without_rs_a": float(theory_current[last_index]),
        "relative_difference_percent": scalar_relative_error_percent(
            float(theory_current[last_index]), float(diode_current[last_index])
        ),
    }
    reverse_index = int(np.argmin(np.abs(voltage + 1.0)))
    reverse_current = float(diode_current[reverse_index])

    voltage_at_1ma = _voltage_at_current(external_voltage, diode_current, 1e-3)
    voltage_at_10ma = _voltage_at_current(external_voltage, diode_current, 1e-2)
    theory_voltage_at_1ma = _voltage_at_current(external_voltage, np.asarray(theory_current), 1e-3)
    theory_voltage_at_10ma = _voltage_at_current(external_voltage, np.asarray(theory_current), 1e-2)

    waveform = pd.DataFrame(
        {
            "bias_voltage_v": voltage,
            "anode_voltage_v": external_voltage,
            "diode_current_a": diode_current,
            "source_branch_current_a": bias_branch_current,
        }
    )
    theory_frame = pd.DataFrame(
        {
            "voltage_v": external_voltage,
            "shockley_current_a": theory_current,
            "data_source": DATA_SOURCE,
        }
    )
    comparison = pd.DataFrame(
        {
            "voltage_v": external_voltage,
            "simulated_current_a": diode_current,
            "shockley_without_rs_a": theory_current,
            "absolute_difference_a": diode_current - theory_current,
            "relative_error_percent": relative,
        }
    )

    _, run_dir = store.create_run_dir(result.run_id)
    figure = plot_diode_iv(
        external_voltage,
        diode_current,
        run_dir / "waveform.png",
        theory_voltage_v=external_voltage,
        theory_current_a=theory_current,
        title="Diode I-V (IS=1 nA, N=1.8, RS=0.5 Ohm, 25 C)",
    )

    summary = {
        "status": "PASS",
        "points": result.point_count,
        "thermal_voltage_v": diode_thermal_voltage(diode.temperature_c),
        "reverse_current_at_minus_1v_a": reverse_current,
        "forward_current_at_0p8v_a": at_0p8["simulated_current_a"],
        "shockley_without_rs_at_0p8v_a": at_0p8["shockley_without_rs_a"],
        "shockley_vs_spice_relative_percent": at_0p8["relative_difference_percent"],
        "voltage_at_1ma_v": voltage_at_1ma,
        "voltage_at_10ma_v": voltage_at_10ma,
        "shockley_voltage_at_1ma_v": theory_voltage_at_1ma,
        "shockley_voltage_at_10ma_v": theory_voltage_at_10ma,
        "max_absolute_difference_a": metrics["max_absolute_error"],
        "mae_a": metrics["mae"],
        "rmse_a": metrics["rmse"],
        "duration_ms": result.duration_ms,
        "analysis_command": result.metadata.get("analysis_command"),
        "run_dir": str(run_dir),
        "data_source": {"waveform": "spice_simulation", "theory": DATA_SOURCE},
        "note": (
            "Shockley theory uses the external terminal voltage and ignores RS; "
            "at high forward current RS causes a lower current than the ideal formula. "
            "The model is educational and is not a verified commercial device."
        ),
    }

    forward_mask = external_voltage > 0.5
    checks = {
        "reverse_current_below_2nA": abs(reverse_current) < 2e-9,
        "forward_current_monotonic": bool(np.all(np.diff(diode_current[forward_mask]) > 0)),
        "forward_current_above_20mA_at_0p8v": at_0p8["simulated_current_a"] > 0.02,
        "shockley_above_spice_with_rs": at_0p8["shockley_without_rs_a"]
        > at_0p8["simulated_current_a"],
        "one_ma_voltage_between_0p6_and_0p75": bool(
            voltage_at_1ma is not None and 0.6 < voltage_at_1ma < 0.75
        ),
    }
    summary["checks"] = checks
    summary["status"] = "PASS" if all(checks.values()) else "FAIL"

    store.save_result(
        result,
        run_dir=run_dir,
        analysis_parameters={
            "saturation_current_a": diode.saturation_current_a,
            "ideality_factor": diode.ideality_factor,
            "series_resistance_ohm": diode.series_resistance_ohm,
            "temperature_c": diode.temperature_c,
            "sweep_start_v": sweep_config.start_v,
            "sweep_stop_v": sweep_config.stop_v,
            "sweep_step_v": sweep_config.step_v,
        },
        config_snapshot=config.to_dict(),
        theory=theory_frame,
        comparison=comparison,
        waveform=waveform,
        summary=summary,
        figures={"waveform.png": figure},
        log_lines=[
            f"diode sweep points={result.point_count}",
            f"I(0.8 V)={at_0p8['simulated_current_a']:.9g} A",
        ],
    )
    return summary


def main() -> int:
    try:
        summary = analyze()
    except Exception as exc:  # noqa: BLE001
        ResultStore().save_failure(analysis_name="diode_iv_demo", error=exc)
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
