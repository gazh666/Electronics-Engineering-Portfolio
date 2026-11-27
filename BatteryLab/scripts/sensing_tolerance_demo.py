"""Task 27/28/29：误差预算、1000 组蒙特卡洛与角点真实 SPICE 复验。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from analysis.error_budget import current_error_budget, summarize_budget, temperature_error_budget, voltage_error_budget
from analysis.tolerance_analysis import (
    run_current_tolerance,
    run_temperature_tolerance,
    run_voltage_tolerance,
    select_corner_samples,
)
from circuits.current_sensing import CurrentSenseConfig, sweep_current_fast
from circuits.differential_amplifier import DifferentialAmplifierConfig, sweep_high_voltage_fast
from circuits.ntc_sensing import NtcConfig, sweep_temperatures_fast
from circuits.opamp_models import CurrentAmplifierSpec, OpAmpSpec
from scripts.stage4_common import adc_settings, afe, limits, tolerances
from sensing.config import load_current_sensing_config, load_ntc_config
from sensing.temperature_decoder import divider_voltage, ntc_resistance
from sensing.voltage_decoder import four_resistor_output
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame, write_plots
from storage.result_store import write_json
from visualization.plots import plot_histogram, plot_multi_series, plot_xy

SOURCE = "真实 ngspice 直流扫描（spice_simulation）"


def main() -> int:
    config = afe()
    tol = tolerances()
    current_detail = load_current_sensing_config()
    ntc_detail = load_ntc_config()
    adc = adc_settings(config)
    run = new_sensing_run("sensing")

    sample_count = int(tol["sample_count"])
    seed = int(tol["random_seed"])
    voltage_result = run_voltage_tolerance(config=config, tolerances=tol, sample_count=sample_count, seed=seed)
    current_result = run_current_tolerance(
        config=config, tolerances=tol, current_config=current_detail, sample_count=sample_count, seed=seed
    )
    temperature_result = run_temperature_tolerance(
        config=config, tolerances=tol, ntc_config=ntc_detail, sample_count=sample_count, seed=seed
    )

    voltage_rows = voltage_result["parameter_samples"]
    current_rows = current_result["parameter_samples"]
    temperature_rows = temperature_result["parameter_samples"]

    write_frame(run, "voltage_sample_metrics.csv", pd.DataFrame(voltage_rows))
    write_frame(run, "current_sample_metrics.csv", pd.DataFrame(current_rows))
    write_frame(run, "temperature_sample_metrics.csv", pd.DataFrame(temperature_rows))

    amp = config["differential_amplifier"]
    voltage_budget = voltage_error_budget(
        r1_ohm=float(amp["r1_ohm"]),
        r2_ohm=float(amp["r2_ohm"]),
        r3_ohm=float(amp["r3_ohm"]),
        r4_ohm=float(amp["r4_ohm"]),
        reference_v=float(amp["reference_voltage_v"]),
        adc_config=adc,
        cell_voltage_v=4.0,
        common_mode_v=9.7,
        resistor_tolerance_percent=float(tol["voltage_sensing"]["resistor_tolerance_percent"]),
        opamp_offset_v=float(tol["voltage_sensing"]["opamp_input_offset_max_v"]),
        adc_offset_v=float(tol["adc"]["input_offset_max_v"]),
        adc_gain_error_fraction=0.001,
        adc_noise_v=0.0002,
        reference_tolerance_percent=float(tol["adc"]["reference_tolerance_percent"]),
        opamp_cmrr_db=100.0,
    )
    current_budget = current_error_budget(
        shunt_ohm=float(config["current_sensing"]["shunt_resistance_ohm"]),
        amplifier_gain=float(config["current_sensing"]["amplifier_gain"]),
        reference_v=float(config["current_sensing"]["zero_current_reference_v"]),
        adc_config=adc,
        current_a=2.5,
        shunt_tolerance_percent=float(tol["current_sensing"]["shunt_tolerance_percent"]),
        shunt_tcr_ppm_per_c=float(current_detail["shunt"]["temperature_coefficient_ppm_per_c"]),
        temperature_delta_c=25.0,
        input_offset_v=float(tol["current_sensing"]["input_offset_max_v"]),
        gain_error_fraction=float(tol["current_sensing"]["amplifier_gain_tolerance_percent"]) / 100.0,
        zero_reference_error_v=0.00165,
        adc_offset_v=float(tol["adc"]["input_offset_max_v"]),
        adc_gain_error_fraction=0.001,
        adc_noise_v=0.0002,
        reference_tolerance_percent=float(tol["adc"]["reference_tolerance_percent"]),
    )
    temperature_budget = temperature_error_budget(
        r25_ohm=float(ntc_detail["ntc"]["nominal_resistance_ohm"]),
        beta_k=float(ntc_detail["ntc"]["beta_k"]),
        pullup_ohm=float(ntc_detail["divider"]["pullup_resistance_ohm"]),
        excitation_v=float(ntc_detail["divider"]["excitation_voltage_v"]),
        temperature_c=25.0,
        adc_config=adc,
        r25_tolerance_percent=float(tol["ntc"]["r25_tolerance_percent"]),
        beta_tolerance_percent=float(tol["ntc"]["beta_tolerance_percent"]),
        pullup_tolerance_percent=float(tol["ntc"]["pullup_tolerance_percent"]),
    )
    write_json(run.path / "error_budget_voltage.json", voltage_budget)
    write_json(run.path / "error_budget_current.json", current_budget)
    write_json(run.path / "error_budget_temperature.json", temperature_budget)
    for name, budget in (("voltage", voltage_budget), ("current", current_budget), ("temperature", temperature_budget)):
        write_frame(run, f"error_budget_{name}.csv", pd.DataFrame(budget["items"]))

    # --- 角点真实 SPICE 复验 ---
    corner_rows = []
    voltage_corners = select_corner_samples(voltage_rows, "pre_max_abs")
    current_corners = select_corner_samples(current_rows, "pre_max_abs")
    temperature_corners = select_corner_samples(temperature_rows, "pre_max_abs")

    for corner in voltage_corners:
        corner_config = DifferentialAmplifierConfig(
            r1_ohm=float(corner["r1_ohm"]),
            r2_ohm=float(corner["r2_ohm"]),
            r3_ohm=float(corner["r3_ohm"]),
            r4_ohm=float(corner["r4_ohm"]),
            reference_v=float(amp["reference_voltage_v"]),
            supply_v=float(amp["supply_voltage_v"]),
        )
        spec = OpAmpSpec(
            name="eop",
            model_kind="ideal",
            open_loop_gain=1_000_000.0,
            output_low_v=0.0,
            output_high_v=float(amp["supply_voltage_v"]),
            input_offset_v=float(corner["opamp_offset_v"]),
        )
        spice_rows = sweep_high_voltage_fast([2.5, 3.7, 4.25], corner_config, opamp=spec)
        for spice_row in spice_rows:
            reference = float(spice_row["vhigh_v"])
            math_output = four_resistor_output(
                reference,
                0.0,
                r1_ohm=corner_config.r1_ohm,
                r2_ohm=corner_config.r2_ohm,
                r3_ohm=corner_config.r3_ohm,
                r4_ohm=corner_config.r4_ohm,
                reference_v=corner_config.reference_v,
            ) + (1.0 + corner_config.nominal_gain) * float(corner["opamp_offset_v"])
            corner_rows.append(
                {
                    "channel": "voltage",
                    "role": corner["role"],
                    "sample": corner["sample"],
                    "input": reference,
                    "spice_output_v": float(spice_row["vout_v"]),
                    "math_output_v": float(math_output),
                    "difference_v": float(spice_row["vout_v"] - math_output),
                }
            )

    for corner in current_corners:
        corner_config = CurrentSenseConfig(
            shunt_ohm=float(corner["shunt_ohm"]),
            amplifier_gain=float(corner["gain"]),
            reference_v=float(config["current_sensing"]["zero_current_reference_v"]),
        )
        spec = CurrentAmplifierSpec(
            name="ina240_corner",
            gain=float(corner["gain"]),
            reference_voltage_v=float(config["current_sensing"]["zero_current_reference_v"]),
            input_offset_v=float(corner["input_offset_v"]),
            cmrr_db=132.0,
            bandwidth_hz=400e3,
            output_low_v=0.1,
            output_high_v=4.9,
        )
        spice_rows = sweep_current_fast([-2.5, 0.0, 2.5], corner_config, amplifier_spec=spec)
        for spice_row in spice_rows:
            input_current = float(spice_row["current_a"])
            math_output = (
                float(config["current_sensing"]["zero_current_reference_v"])
                + float(corner["gain"]) * float(corner["shunt_ohm"]) * input_current
                + float(corner["gain"]) * float(corner["input_offset_v"])
            )
            corner_rows.append(
                {
                    "channel": "current",
                    "role": corner["role"],
                    "sample": corner["sample"],
                    "input": input_current,
                    "spice_output_v": float(spice_row["vout_v"]),
                    "math_output_v": float(math_output),
                    "difference_v": float(spice_row["vout_v"] - math_output),
                }
            )

    for corner in temperature_corners:
        actual_ntc = NtcConfig(r25_ohm=float(corner["r25_ohm"]), beta_k=float(corner["beta_k"]), pullup_ohm=float(corner["pullup_ohm"]))
        spice_rows = sweep_temperatures_fast([0.0, 25.0, 60.0], actual_ntc)
        for spice_row in spice_rows:
            temperature = float(spice_row["temperature_c"])
            math_voltage = divider_voltage(
                ntc_resistance(temperature, r25_ohm=actual_ntc.r25_ohm, beta_k=actual_ntc.beta_k),
                pullup_ohm=actual_ntc.pullup_ohm,
                excitation_v=actual_ntc.excitation_v,
            )
            corner_rows.append(
                {
                    "channel": "temperature",
                    "role": corner["role"],
                    "sample": corner["sample"],
                    "input": temperature,
                    "spice_output_v": float(spice_row["spice_voltage_v"]),
                    "math_output_v": float(math_voltage),
                    "difference_v": float(spice_row["spice_voltage_v"] - math_voltage),
                }
            )

    corner_frame = pd.DataFrame(corner_rows)
    write_frame(run, "corner_spice_verification.csv", corner_frame)
    write_frame(run, "corner_samples.csv", pd.DataFrame(voltage_corners))

    voltage_comparison = voltage_result["calibration_comparison"]
    current_comparison = current_result["calibration_comparison"]
    temperature_comparison = temperature_result["calibration_comparison"]

    budget_voltage_frame = pd.DataFrame(voltage_budget["items"])
    budget_current_frame = pd.DataFrame(current_budget["items"])

    plots = write_plots(
        run,
        [
            (
                "23_voltage_tolerance_histogram.png",
                plot_histogram,
                {
                    "values": [row["post_max_abs"] * 1000.0 for row in voltage_rows],
                    "xlabel": "两点校准后最大单体电压误差 (mV)",
                    "title": f"1000 组容差样本：单体电压误差分布（校准后）",
                    "annotation": "独立均匀分布教学假设；数学行为模型，不是 1000 次 SPICE。",
                    "bins": 50,
                },
            ),
            (
                "24_current_tolerance_histogram.png",
                plot_histogram,
                {
                    "values": [row["post_max_abs"] * 1000.0 for row in current_rows],
                    "xlabel": "两点校准后最大电流误差 (mA)",
                    "title": "1000 组容差样本：双向电流误差分布（校准后）",
                    "annotation": "独立均匀分布教学假设；数学行为模型。",
                    "bins": 50,
                },
            ),
            (
                "25_temperature_tolerance_histogram.png",
                plot_histogram,
                {
                    "values": [row["post_max_abs"] for row in temperature_rows],
                    "xlabel": "两点校准后最大温度误差 (℃)",
                    "title": "1000 组容差样本：NTC 温度误差分布（校准后）",
                    "annotation": "独立均匀分布教学假设；NTC 自热未建模。",
                    "bins": 50,
                },
            ),
            (
                "26_calibration_improvement.png",
                plot_multi_series,
                {
                    "series": [
                        ("单体电压 MAE (mV)", [1, 2], [voltage_comparison["pre_calibration"]["mae"] * 1000.0, voltage_comparison["post_calibration"]["mae"] * 1000.0]),
                        ("电流 MAE (mA)", [1, 2], [current_comparison["pre_calibration"]["mae"] * 1000.0, current_comparison["post_calibration"]["mae"] * 1000.0]),
                        ("温度 MAE (0.1℃)", [1, 2], [temperature_comparison["pre_calibration"]["mae"] * 10.0, temperature_comparison["post_calibration"]["mae"] * 10.0]),
                    ],
                    "xlabel": "1=校准前，2=两点校准后",
                    "ylabel": "MAE（按图例单位）",
                    "title": "校准前后平均绝对误差对照",
                    "annotation": "校准集与验证集分离；验证点不参与拟合。",
                },
            ),
            (
                "27_voltage_budget.png",
                plot_xy,
                {
                    "x": list(range(1, len(budget_voltage_frame) + 1)),
                    "y": (budget_voltage_frame["value"] * 1000.0).tolist(),
                    "xlabel": "误差项索引（见 error_budget_voltage.csv）",
                    "ylabel": "输入折算误差 (mV)",
                    "title": "单体电压采集误差预算（顶端单体、共模 9.7 V）",
                    "annotation": f"最坏情况线性叠加={voltage_budget['worst_case_linear_sum']*1000:.3f} mV，RSS={voltage_budget['rss_estimate']*1000:.3f} mV（统计估计）。",
                    "color": "#d62728",
                },
            ),
            (
                "28_current_budget.png",
                plot_xy,
                {
                    "x": list(range(1, len(budget_current_frame) + 1)),
                    "y": (budget_current_frame["value"] * 1000.0).tolist(),
                    "xlabel": "误差项索引（见 error_budget_current.csv）",
                    "ylabel": "输入折算误差 (mA)",
                    "title": "双向电流采集误差预算（2.5 A）",
                    "annotation": f"最坏情况线性叠加={current_budget['worst_case_linear_sum']*1000:.3f} mA，RSS={current_budget['rss_estimate']*1000:.3f} mA（统计估计）。",
                    "color": "#ff7f0e",
                },
            ),
        ],
    )

    summary = {
        "sample_count": sample_count,
        "seed": seed,
        "voltage": {
            "pre": voltage_comparison["pre_calibration"],
            "post": voltage_comparison["post_calibration"],
            "improvement_percent": voltage_comparison["improvement_percent"],
        },
        "current": {
            "pre": current_comparison["pre_calibration"],
            "post": current_comparison["post_calibration"],
            "zero_only": current_comparison["zero_calibration_only"],
            "improvement_percent": current_comparison["improvement_percent"],
        },
        "temperature": {
            "pre": temperature_comparison["pre_calibration"],
            "post": temperature_comparison["post_calibration"],
            "improvement_percent": temperature_comparison["improvement_percent"],
        },
        "error_budget": {
            "voltage": {key: voltage_budget[key] for key in ("worst_case_linear_sum", "rss_estimate", "dominant_item", "dominant_value")},
            "current": {key: current_budget[key] for key in ("worst_case_linear_sum", "rss_estimate", "dominant_item", "dominant_value")},
            "temperature": {key: temperature_budget[key] for key in ("worst_case_linear_sum", "rss_estimate", "dominant_item", "dominant_value")},
        },
        "corner_verification": corner_rows,
        "max_spice_math_difference_v": float(corner_frame["difference_v"].abs().max()),
        "plots": plots,
    }
    payload = finalize_run(
        run,
        script="scripts/sensing_tolerance_demo.py",
        summary=summary,
        metadata={
            "distribution": tol["distribution"],
            "note": "1000 组为数学行为模型样本；角点才调用真实 SPICE。",
            "limits": limits(),
        },
    )

    print(f"run_id={run.run_id}")
    print(f"单体电压：校准前 MAE={voltage_comparison['pre_calibration']['mae']*1000:.3f} mV，校准后 MAE={voltage_comparison['post_calibration']['mae']*1000:.3f} mV，最大={voltage_comparison['post_calibration']['max_abs_error']*1000:.3f} mV")
    print(f"双向电流：校准前 MAE={current_comparison['pre_calibration']['mae']*1000:.3f} mA，零点后={current_comparison['zero_calibration_only']['mae']*1000:.3f} mA，两点后={current_comparison['post_calibration']['mae']*1000:.3f} mA，最大={current_comparison['post_calibration']['max_abs_error']*1000:.3f} mA")
    print(f"NTC 温度：校准前 MAE={temperature_comparison['pre_calibration']['mae']:.4f} ℃，校准后 MAE={temperature_comparison['post_calibration']['mae']:.4f} ℃，最大={temperature_comparison['post_calibration']['max_abs_error']:.4f} ℃")
    print(f"电压预算：最坏={voltage_budget['worst_case_linear_sum']*1000:.3f} mV，RSS={voltage_budget['rss_estimate']*1000:.3f} mV")
    print(f"电流预算：最坏={current_budget['worst_case_linear_sum']*1000:.3f} mA，RSS={current_budget['rss_estimate']*1000:.3f} mA")
    print(f"温度预算：最坏={temperature_budget['worst_case_linear_sum']:.4f} ℃，RSS={temperature_budget['rss_estimate']:.4f} ℃")
    print(f"角点 SPICE 与解析最大偏差={corner_frame['difference_v'].abs().max()*1e6:.3f} µV")
    print(f"真实 SPICE 求解次数={payload['real_spice_solves']}（另有 {sample_count} 组数学样本 × 3 通道）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
