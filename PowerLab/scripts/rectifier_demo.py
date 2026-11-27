"""二极管半波整流：真实瞬态波形、时间加权平均/RMS 与负载功率。

运行：``python -m scripts.rectifier_demo``

时间加权统计使用梯形积分，适用于 ngspice 的非均匀时间步。
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np
import pandas as pd

from analysis.theory import DATA_SOURCE, half_wave_theory
from circuits.rectifier import build_half_wave_rectifier
from simulations.config import BasicCircuitsConfig, load_basic_circuits_config
from simulations.runner import SimulationRunner
from storage.result_store import ResultStore
from visualization.plots import plot_rectifier


def _integrate(values: np.ndarray, time_s: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(values, time_s))
    return float(np.trapz(values, time_s))


def analyze(
    config: BasicCircuitsConfig | None = None,
    store: ResultStore | None = None,
) -> dict[str, Any]:
    config = config or load_basic_circuits_config()
    store = store or ResultStore()
    runner = SimulationRunner(config.simulation_temperature_c)
    rectifier = config.rectifier
    transient = config.rectifier_transient

    circuit = build_half_wave_rectifier(rectifier)
    result = runner.run_transient(circuit, transient.step_s, transient.end_s, parameters=rectifier.to_dict())

    time_s = result.data["time_s"].to_numpy()
    input_voltage = result.data["vin_v"].to_numpy()
    output_voltage = result.data["out_v"].to_numpy()
    load_current = output_voltage / rectifier.load_resistance_ohm
    instantaneous_power = output_voltage**2 / rectifier.load_resistance_ohm

    span = float(time_s[-1] - time_s[0])
    average_voltage = _integrate(output_voltage, time_s) / span
    rms_voltage = float(np.sqrt(_integrate(output_voltage**2, time_s) / span))
    average_power = _integrate(instantaneous_power, time_s) / span

    theory = half_wave_theory(rectifier.input_peak_v, rectifier.load_resistance_ohm)
    ideal_average = theory["average_voltage_v"]
    ideal_rms = theory["rms_voltage_v"]
    ideal_power = theory["average_load_power_w"]

    conduction_threshold = 1e-6
    conducting = (load_current > conduction_threshold).astype(float)
    conduction_fraction = _integrate(conducting, time_s) / span

    peak_output = float(np.max(output_voltage))
    peak_input = float(np.max(input_voltage))
    output_negative_max = float(np.min(output_voltage))

    waveform = pd.DataFrame(
        {
            "time_s": time_s,
            "source_voltage_v": input_voltage,
            "load_voltage_v": output_voltage,
            "load_current_a": load_current,
            "load_power_w": instantaneous_power,
            "diode_conducting": conducting,
        }
    )
    theory_frame = pd.DataFrame(
        [
            {
                "ideal_average_voltage_v": ideal_average,
                "ideal_rms_voltage_v": ideal_rms,
                "ideal_average_load_power_w": ideal_power,
                "data_source": DATA_SOURCE,
                "formula": theory["formula"],
            }
        ]
    )
    comparison = pd.DataFrame(
        [
            {
                "quantity": "average_voltage_v",
                "simulated": average_voltage,
                "ideal_theory": ideal_average,
                "absolute_error": average_voltage - ideal_average,
                "relative_error_percent": (average_voltage - ideal_average) / ideal_average * 100.0,
            },
            {
                "quantity": "rms_voltage_v",
                "simulated": rms_voltage,
                "ideal_theory": ideal_rms,
                "absolute_error": rms_voltage - ideal_rms,
                "relative_error_percent": (rms_voltage - ideal_rms) / ideal_rms * 100.0,
            },
            {
                "quantity": "average_load_power_w",
                "simulated": average_power,
                "ideal_theory": ideal_power,
                "absolute_error": average_power - ideal_power,
                "relative_error_percent": (average_power - ideal_power) / ideal_power * 100.0,
            },
        ]
    )

    _, run_dir = store.create_run_dir(result.run_id)
    figure = plot_rectifier(
        time_s,
        input_voltage,
        output_voltage,
        run_dir / "waveform.png",
        title="Half-Wave Rectifier (10 V peak, 50 Hz, 1 kOhm load)",
    )

    summary = {
        "status": "PASS",
        "points": result.point_count,
        "time_span_s": span,
        "simulated_average_voltage_v": average_voltage,
        "simulated_rms_voltage_v": rms_voltage,
        "simulated_average_load_power_w": average_power,
        "ideal_average_voltage_v": ideal_average,
        "ideal_rms_voltage_v": ideal_rms,
        "ideal_average_load_power_w": ideal_power,
        "average_relative_error_percent": (average_voltage - ideal_average) / ideal_average * 100.0,
        "rms_relative_error_percent": (rms_voltage - ideal_rms) / ideal_rms * 100.0,
        "power_relative_error_percent": (average_power - ideal_power) / ideal_power * 100.0,
        "peak_input_v": peak_input,
        "peak_output_v": peak_output,
        "minimum_output_v": output_negative_max,
        "conduction_fraction": conduction_fraction,
        "conduction_angle_estimate_deg": conduction_fraction * 360.0,
        "duration_ms": result.duration_ms,
        "analysis_command": result.metadata.get("analysis_command"),
        "run_dir": str(run_dir),
        "data_source": {"waveform": "spice_simulation", "theory": DATA_SOURCE},
        "non_ideality_note": (
            "The SPICE diode has a finite forward drop and RS=0.5 Ohm, plus a 1 Ohm source "
            "resistance, so average/RMS/power are lower than the ideal half-wave formulas; "
            "the diode also conducts for less than half a cycle."
        ),
    }

    checks = {
        # 反偏时二极管仍有约 1 nA 反向漏电流，1 kOhm 负载上产生约 1 uV 负压，
        # 这是真实 SPICE 模型行为，不是数值错误。
        "output_negative_within_2uV": output_negative_max > -2e-6,
        "average_below_ideal": average_voltage < ideal_average,
        "average_within_15_percent": abs(average_voltage - ideal_average) / ideal_average < 0.15,
        "rms_within_15_percent": abs(rms_voltage - ideal_rms) / ideal_rms < 0.15,
        "power_within_25_percent": abs(average_power - ideal_power) / ideal_power < 0.25,
        "conduction_fraction_between_0p2_and_0p5": 0.2 < conduction_fraction < 0.5,
        "peak_output_below_peak_input": peak_output < peak_input,
    }
    summary["checks"] = checks
    summary["status"] = "PASS" if all(checks.values()) else "FAIL"

    store.save_result(
        result,
        run_dir=run_dir,
        analysis_parameters={
            "input_peak_v": rectifier.input_peak_v,
            "frequency_hz": rectifier.frequency_hz,
            "source_resistance_ohm": rectifier.source_resistance_ohm,
            "load_resistance_ohm": rectifier.load_resistance_ohm,
            "diode": rectifier.diode.to_dict(),
            "step_s": transient.step_s,
            "end_s": transient.end_s,
        },
        config_snapshot=config.to_dict(),
        theory=theory_frame,
        comparison=comparison,
        waveform=waveform,
        summary=summary,
        figures={"waveform.png": figure},
        log_lines=[
            f"rectifier points={result.point_count}",
            f"Vavg={average_voltage:.9g} V, Vrms={rms_voltage:.9g} V",
        ],
    )
    return summary


def main() -> int:
    try:
        summary = analyze()
    except Exception as exc:  # noqa: BLE001
        ResultStore().save_failure(analysis_name="rectifier_demo", error=exc)
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
