"""串联 RLC 电路：三种阻尼状态瞬态 + 交流谐振。

运行：``python -m scripts.rlc_demo``

阻尼状态由 R 相对 Rcrit=2√(L/C) 的位置决定，不预先假定哪个标签一定成立。
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np
import pandas as pd

from analysis.error_metrics import interpolate_to_time_axis
from analysis.frequency_response import peak_metrics, resonance_peak
from analysis.theory import (
    DATA_SOURCE,
    rlc_alpha,
    rlc_critical_resistance,
    rlc_damped_frequency,
    rlc_damping_ratio,
    rlc_frequency_response,
    rlc_natural_frequency,
    rlc_peak_frequency,
    rlc_quality_factor,
    rlc_step_overshoot_percent,
)
from circuits.rlc_circuit import build_rlc_ac, build_rlc_transient
from simulations.config import BasicCircuitsConfig, load_basic_circuits_config
from simulations.runner import SimulationRunner
from storage.result_store import ResultStore
from visualization.plots import plot_bode, plot_comparison, plot_rlc_damping


def _final_value(time_s: np.ndarray, values: np.ndarray, fraction: float = 0.05) -> float:
    span = time_s[-1] - time_s[0]
    mask = time_s >= time_s[-1] - fraction * span
    return float(np.mean(values[mask]))


def _overshoot(time_s: np.ndarray, values: np.ndarray, final_value: float) -> dict[str, Any]:
    index = int(np.argmax(values))
    peak = float(values[index])
    denominator = abs(final_value)
    percent = (peak - final_value) / denominator * 100.0 if denominator > 0 else None
    return {
        "peak_v": peak,
        "peak_time_s": float(time_s[index]),
        "overshoot_percent": percent,
        "is_interior_peak": bool(0 < index < len(time_s) - 1),
        "definition": "(Vpeak - Vfinal) / |Vfinal| * 100%, Vpeak = global maximum",
    }


def _oscillation(time_s: np.ndarray, values: np.ndarray, final_value: float, start_index: int) -> dict[str, Any]:
    residual = values[start_index:] - final_value
    local_time = time_s[start_index:]
    nonzero = np.where(residual != 0)[0]
    if nonzero.size < 3:
        return {"found": False, "reason": "too few nonzero residual samples"}
    signs = np.sign(residual[nonzero])
    times = local_time[nonzero]
    changes = np.where(np.diff(signs) != 0)[0]
    if changes.size < 3:
        return {"found": False, "reason": "fewer than three zero crossings", "crossing_count": int(changes.size)}

    crossings = []
    for change in changes:
        left = int(change)
        right = int(change + 1)
        t0, t1 = times[left], times[right]
        v0, v1 = residual[nonzero[left]], residual[nonzero[right]]
        crossings.append(float(t0 - v0 * (t1 - t0) / (v1 - v0)))
    crossings_array = np.asarray(crossings)
    span = crossings_array[-1] - crossings_array[0]
    frequency = (len(crossings_array) - 1) / (2.0 * span) if span > 0 else None
    return {
        "found": True,
        "frequency_hz": float(frequency) if frequency is not None else None,
        "crossing_count": int(len(crossings_array)),
        "first_crossing_s": float(crossings_array[0]),
        "last_crossing_s": float(crossings_array[-1]),
    }


def _settling_time(
    time_s: np.ndarray,
    values: np.ndarray,
    final_value: float,
    tolerance: float = 0.02,
) -> dict[str, Any]:
    band = abs(final_value) * tolerance
    outside = np.abs(values - final_value) > band
    definition = f"last time |V - Vfinal| leaves the +/-{tolerance * 100:.0f}% band"
    if not outside.any():
        return {
            "settled": True,
            "settling_time_s": float(time_s[0]),
            "definition": definition,
        }
    last_outside = int(np.where(outside)[0][-1])
    if last_outside == len(time_s) - 1:
        return {
            "settled": False,
            "settling_time_s": None,
            "definition": definition,
            "note": "still outside the settling band at the end of the simulated window",
        }
    return {
        "settled": True,
        "settling_time_s": float(time_s[last_outside + 1]),
        "definition": definition,
    }


def analyze(
    config: BasicCircuitsConfig | None = None,
    store: ResultStore | None = None,
) -> dict[str, Any]:
    config = config or load_basic_circuits_config()
    store = store or ResultStore()
    runner = SimulationRunner(config.simulation_temperature_c)
    rlc = config.rlc
    transient = config.rlc_transient
    ac_config = config.rlc_ac

    f0 = rlc_natural_frequency(rlc.inductance_h, rlc.capacitance_f)
    critical_resistance = rlc_critical_resistance(rlc.inductance_h, rlc.capacitance_f)
    damping_resistances = config.rlc_damping_resistances_ohm
    labels = ("underdamped", "critical", "overdamped")

    transient_cases: list[dict[str, Any]] = []
    saved_runs: list[dict[str, Any]] = []
    curves: dict[str, np.ndarray] = {}
    common_time: np.ndarray | None = None

    for resistance, label in zip(damping_resistances, labels):
        circuit = build_rlc_transient(
            resistance,
            rlc.inductance_h,
            rlc.capacitance_f,
            input_v=rlc.input_v,
            rise_time_s=rlc.rise_time_s,
        )
        result = runner.run_transient(circuit, transient.step_s, transient.end_s)
        time_s = result.data["time_s"].to_numpy()
        voltage = result.data["out_v"].to_numpy()
        inductor_current = result.data["l1_branch_current_a"].to_numpy()
        supply_current = -result.data["vinput_branch_current_a"].to_numpy()

        final_value = _final_value(time_s, voltage)
        overshoot = _overshoot(time_s, voltage, final_value)
        start_index = int(np.argmax(voltage))
        oscillation = _oscillation(time_s, voltage, final_value, start_index)
        settling = _settling_time(time_s, voltage, final_value)

        zeta = rlc_damping_ratio(resistance, rlc.inductance_h, rlc.capacitance_f)
        alpha = rlc_alpha(resistance, rlc.inductance_h)
        quality = rlc_quality_factor(resistance, rlc.inductance_h, rlc.capacitance_f)
        theory_overshoot = rlc_step_overshoot_percent(resistance, rlc.inductance_h, rlc.capacitance_f)
        theory_oscillation = rlc_damped_frequency(resistance, rlc.inductance_h, rlc.capacitance_f)

        case = {
            "label": label,
            "resistance_ohm": resistance,
            "damping_ratio": zeta,
            "alpha_1_s": alpha,
            "quality_factor": quality,
            "final_value_v": final_value,
            "final_value_error_v": final_value - rlc.input_v,
            "overshoot": overshoot,
            "theoretical_overshoot_percent": theory_overshoot,
            "oscillation": oscillation,
            "theoretical_oscillation_hz": theory_oscillation,
            "settling": settling,
            "points": result.point_count,
            "duration_ms": result.duration_ms,
            "analysis_command": result.metadata.get("analysis_command"),
            "run_id": result.run_id,
        }
        transient_cases.append(case)

        waveform = result.data.copy()
        waveform["capacitor_voltage_v"] = voltage
        waveform["inductor_current_a"] = inductor_current
        waveform["supply_current_a"] = supply_current
        waveform["residual_voltage_v"] = voltage - final_value

        theory_frame = pd.DataFrame(
            [
                {
                    "resistance_ohm": resistance,
                    "damping_ratio": zeta,
                    "alpha_1_s": alpha,
                    "quality_factor": quality,
                    "natural_frequency_hz": f0,
                    "critical_resistance_ohm": critical_resistance,
                    "theoretical_overshoot_percent": theory_overshoot,
                    "theoretical_oscillation_hz": theory_oscillation,
                    "data_source": DATA_SOURCE,
                }
            ]
        )
        comparison = pd.DataFrame(
            [
                {
                    "quantity": "overshoot_percent",
                    "simulated": overshoot["overshoot_percent"],
                    "theoretical": theory_overshoot,
                },
                {
                    "quantity": "oscillation_frequency_hz",
                    "simulated": oscillation.get("frequency_hz"),
                    "theoretical": theory_oscillation,
                },
                {
                    "quantity": "final_value_v",
                    "simulated": final_value,
                    "theoretical": rlc.input_v,
                },
            ]
        )

        if common_time is None:
            common_time = time_s
        curves[f"R={resistance:g} Ohm, zeta={zeta:.3f}"] = interpolate_to_time_axis(
            time_s, voltage, common_time
        )
        saved_runs.append(
            {
                "result": result,
                "case": case,
                "waveform": waveform,
                "theory": theory_frame,
                "comparison": comparison,
                "run_id": result.run_id,
            }
        )

    # 三种阻尼对比图（保存到第一个瞬态运行目录）
    if common_time is None:
        raise RuntimeError("no RLC transient case was simulated")
    first = saved_runs[0]
    _, first_dir = store.create_run_dir(first["run_id"])
    first["case"]["run_dir"] = str(first_dir)
    first_figure = plot_comparison(
        common_time,
        first["waveform"]["capacitor_voltage_v"].to_numpy(),
        np.full(common_time.shape, rlc.input_v),
        first_dir / "waveform.png",
        title=f"Series RLC Step Response (R={first['case']['resistance_ohm']:g} Ohm)",
        y_label="Capacitor voltage (V)",
        theoretical_label="Steady-state target (5 V)",
    )
    damping_figure = plot_rlc_damping(
        common_time,
        curves,
        first_dir / "damping_comparison.png",
        title="RLC Damping Comparison (L=10 mH, C=1 uF)",
    )
    store.save_result(
        first["result"],
        run_dir=first_dir,
        analysis_parameters={
            "resistance_ohm": first["case"]["resistance_ohm"],
            "inductance_h": rlc.inductance_h,
            "capacitance_f": rlc.capacitance_f,
            "natural_frequency_hz": f0,
            "critical_resistance_ohm": critical_resistance,
        },
        config_snapshot=config.to_dict(),
        theory=first["theory"],
        comparison=first["comparison"],
        waveform=first["waveform"],
        summary={"status": "PASS", "case": first["case"], "run_dir": str(first_dir)},
        figures={"waveform.png": first_figure, "damping_comparison.png": damping_figure},
        log_lines=[f"RLC case {first['case']['label']}"],
    )

    for item in saved_runs[1:]:
        _, run_dir = store.create_run_dir(item["run_id"])
        item["case"]["run_dir"] = str(run_dir)
        figure = plot_comparison(
            item["waveform"]["time_s"].to_numpy(),
            item["waveform"]["capacitor_voltage_v"].to_numpy(),
            np.full(item["waveform"]["time_s"].to_numpy().shape, rlc.input_v),
            run_dir / "waveform.png",
            title=f"Series RLC Step Response (R={item['case']['resistance_ohm']:g} Ohm)",
            y_label="Capacitor voltage (V)",
            theoretical_label="Steady-state target (5 V)",
        )
        store.save_result(
            item["result"],
            run_dir=run_dir,
            analysis_parameters={
                "resistance_ohm": item["case"]["resistance_ohm"],
                "inductance_h": rlc.inductance_h,
                "capacitance_f": rlc.capacitance_f,
                "natural_frequency_hz": f0,
                "critical_resistance_ohm": critical_resistance,
            },
            config_snapshot=config.to_dict(),
            theory=item["theory"],
            comparison=item["comparison"],
            waveform=item["waveform"],
            summary={"status": "PASS", "case": item["case"], "run_dir": str(run_dir)},
            figures={"waveform.png": figure},
            log_lines=[f"RLC case {item['case']['label']}"],
        )

    # ------------------------------------------------------------- RLC AC
    ac_circuit = build_rlc_ac(
        damping_resistances[0],
        rlc.inductance_h,
        rlc.capacitance_f,
    )
    ac_result = runner.run_ac(
        ac_circuit,
        ac_config.start_hz,
        ac_config.stop_hz,
        ac_config.points_per_decade,
        variation=ac_config.variation,
    )
    frequency = ac_result.data["frequency_hz"].to_numpy()
    vin = ac_result.data["vin_real_v"].to_numpy() + 1j * ac_result.data["vin_imag_v"].to_numpy()
    vout = ac_result.data["out_real_v"].to_numpy() + 1j * ac_result.data["out_imag_v"].to_numpy()
    transfer = vout / vin
    magnitude = np.abs(transfer)
    gain_db = 20.0 * np.log10(magnitude)
    phase_deg = np.angle(transfer, deg=True)
    inductor_current = ac_result.data["l1_real_a"].to_numpy() + 1j * ac_result.data["l1_imag_a"].to_numpy()
    current_magnitude = np.abs(inductor_current)

    theory_ac = rlc_frequency_response(
        frequency, damping_resistances[0], rlc.inductance_h, rlc.capacitance_f
    )
    capacitor_peak = resonance_peak(frequency, magnitude)
    current_peak = peak_metrics(frequency, current_magnitude)
    theory_peak_frequency = rlc_peak_frequency(
        damping_resistances[0], rlc.inductance_h, rlc.capacitance_f
    )

    ac_waveform = ac_result.data.copy()
    ac_waveform["capacitor_magnitude_v"] = magnitude
    ac_waveform["gain_db"] = gain_db
    ac_waveform["phase_deg"] = phase_deg
    ac_waveform["inductor_current_magnitude_a"] = current_magnitude

    ac_theory = pd.DataFrame(
        {
            "frequency_hz": frequency,
            "theoretical_magnitude": theory_ac["magnitude"],
            "theoretical_gain_db": theory_ac["gain_db"],
            "theoretical_phase_deg": theory_ac["phase_deg"],
            "data_source": DATA_SOURCE,
        }
    )
    ac_comparison = pd.DataFrame(
        {
            "frequency_hz": frequency,
            "simulated_magnitude": magnitude,
            "theoretical_magnitude": theory_ac["magnitude"],
            "magnitude_error": magnitude - theory_ac["magnitude"],
            "gain_error_db": gain_db - theory_ac["gain_db"],
            "phase_error_deg": phase_deg - theory_ac["phase_deg"],
        }
    )

    _, ac_dir = store.create_run_dir(ac_result.run_id)
    ac_magnitude_figure, ac_phase_figure = plot_bode(
        frequency,
        gain_db,
        phase_deg,
        ac_dir / "waveform.png",
        ac_dir / "phase.png",
        title="Series RLC AC Response (R=10 Ohm, capacitor voltage)",
        marker_hz=capacitor_peak["peak_frequency_hz"],
        marker_label="f_peak",
        reference_db=None,
        reference_phase_deg=None,
    )

    ac_summary = {
        "status": "PASS",
        "resistance_ohm": damping_resistances[0],
        "damping_ratio": rlc_damping_ratio(
            damping_resistances[0], rlc.inductance_h, rlc.capacitance_f
        ),
        "natural_frequency_hz": f0,
        "theoretical_peak_frequency_hz": theory_peak_frequency,
        "capacitor_voltage_peak": capacitor_peak,
        "inductor_current_peak": current_peak,
        "theoretical_peak_magnitude": rlc_quality_factor(
            damping_resistances[0], rlc.inductance_h, rlc.capacitance_f
        ),
        "points": ac_result.point_count,
        "duration_ms": ac_result.duration_ms,
        "analysis_command": ac_result.metadata.get("analysis_command"),
        "run_dir": str(ac_dir),
    }
    ac_checks = {
        "interior_peak_found": capacitor_peak["is_interior_peak"],
        "peak_frequency_within_3_percent": bool(
            theory_peak_frequency is not None
            and abs(capacitor_peak["peak_frequency_hz"] - theory_peak_frequency)
            / theory_peak_frequency
            < 0.03
        ),
        "peak_magnitude_within_10_percent": bool(
            abs(capacitor_peak["peak_value"] - ac_summary["theoretical_peak_magnitude"])
            / ac_summary["theoretical_peak_magnitude"]
            < 0.10
        ),
    }
    ac_summary["checks"] = ac_checks
    ac_summary["status"] = "PASS" if all(ac_checks.values()) else "FAIL"

    store.save_result(
        ac_result,
        run_dir=ac_dir,
        analysis_parameters={
            "resistance_ohm": damping_resistances[0],
            "inductance_h": rlc.inductance_h,
            "capacitance_f": rlc.capacitance_f,
            "natural_frequency_hz": f0,
            "derived_peak_frequency_hz": capacitor_peak["peak_frequency_hz"],
        },
        config_snapshot=config.to_dict(),
        theory=ac_theory,
        comparison=ac_comparison,
        waveform=ac_waveform,
        summary=ac_summary,
        figures={"waveform.png": ac_magnitude_figure, "phase.png": ac_phase_figure},
        log_lines=["RLC AC sweep completed", f"peak at {capacitor_peak['peak_frequency_hz']} Hz"],
    )

    underdamped = transient_cases[0]
    critical = transient_cases[1]
    overdamped = transient_cases[2]
    checks = {
        "underdamped_has_overshoot": bool(
            underdamped["overshoot"]["overshoot_percent"] is not None
            and underdamped["overshoot"]["overshoot_percent"] > 30.0
        ),
        "underdamped_oscillates": bool(
            underdamped["oscillation"].get("found")
            and underdamped["theoretical_oscillation_hz"] is not None
            and abs(
                underdamped["oscillation"]["frequency_hz"] - underdamped["theoretical_oscillation_hz"]
            )
            / underdamped["theoretical_oscillation_hz"]
            < 0.05
        ),
        "critical_low_overshoot": bool(
            critical["overshoot"]["overshoot_percent"] is not None
            and critical["overshoot"]["overshoot_percent"] < 5.0
        ),
        "overdamped_low_overshoot": bool(
            overdamped["overshoot"]["overshoot_percent"] is not None
            and overdamped["overshoot"]["overshoot_percent"] < 2.0
        ),
        "all_settled": all(case["settling"]["settled"] for case in transient_cases),
        "all_final_near_5V": all(abs(case["final_value_error_v"]) < 0.05 for case in transient_cases),
    }

    return {
        "status": "PASS" if all(checks.values()) and ac_summary["status"] == "PASS" else "FAIL",
        "parameters": {
            "natural_frequency_hz": f0,
            "critical_resistance_ohm": critical_resistance,
            "inductance_h": rlc.inductance_h,
            "capacitance_f": rlc.capacitance_f,
        },
        "transient_cases": transient_cases,
        "ac": ac_summary,
        "checks": checks,
        "data_source": {"waveform": "spice_simulation", "theory": DATA_SOURCE},
    }


def main() -> int:
    try:
        summary = analyze()
    except Exception as exc:  # noqa: BLE001
        ResultStore().save_failure(analysis_name="rlc_demo", error=exc)
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
