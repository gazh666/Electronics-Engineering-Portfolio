"""Task 13/15/16：双向电流检测、分流电阻选型与输出滤波。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from circuits.current_sensing import (
    run_output_filter_ac,
    run_output_filter_step,
    shunt_selection_table,
    solve_current,
    sweep_current_fast,
)
from scripts.stage4_common import current_sense_config, afe
from sensing.config import load_current_sensing_config
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame, write_plots
from visualization.plots import plot_dual_axis, plot_histogram, plot_multi_series, plot_xy

SOURCE = "真实 ngspice 工作点求解（spice_simulation）"


def main() -> int:
    config = afe()
    detail = load_current_sensing_config()
    current_config = current_sense_config(config)
    run = new_sensing_run("sensing")

    all_currents = np.arange(-3.5, 3.5001, 0.25)
    all_rows = sweep_current_fast(all_currents.tolist(), current_config)
    sweep_frame = pd.DataFrame([row for row in all_rows if abs(row["current_a"]) <= 2.5 + 1e-9])
    write_frame(run, "current_dc_sweep.csv", sweep_frame)

    slope, intercept = np.polyfit(sweep_frame["current_a"], sweep_frame["vout_v"], 1)
    ideal_errors = sweep_frame["error_v"].abs()
    max_error_v = float(ideal_errors.max())

    saturation_frame = pd.DataFrame([row for row in all_rows if abs(row["current_a"]) > 2.5 + 1e-9])
    write_frame(run, "current_saturation.csv", saturation_frame)

    filter_ac = run_output_filter_ac(
        float(config["current_sensing"]["output_filter_resistance_ohm"]),
        float(config["current_sensing"]["output_filter_capacitance_f"]),
    )
    filter_step = run_output_filter_step(
        float(config["current_sensing"]["output_filter_resistance_ohm"]),
        float(config["current_sensing"]["output_filter_capacitance_f"]),
    )
    write_frame(
        run,
        "output_filter_ac.csv",
        pd.DataFrame({"frequency_hz": filter_ac["frequency_hz"], "gain_db": filter_ac["gain_db"]}),
    )

    shunt_rows = shunt_selection_table(
        currents_a=[-2.5, 2.5],
        shunt_values_ohm=[float(value) for value in detail["shunt"]["research_values_ohm"]],
        fixed_gain=float(detail["research_gain_values"]["fixed_gain_50"]),
        reference_v=current_config.reference_v,
        adc_reference_v=current_config.adc_reference_v,
        fair_gain_by_shunt={float(key): float(value) for key, value in detail["research_gain_values"]["fair_range_gain_by_shunt"].items()},
    )
    shunt_frame = pd.DataFrame(shunt_rows)
    write_frame(run, "shunt_selection.csv", shunt_frame)

    plots = write_plots(
        run,
        [
            (
                "09_bidirectional_current_transfer.png",
                plot_multi_series,
                {
                    "series": [
                        ("SPICE 输出", sweep_frame["current_a"].tolist(), sweep_frame["vout_v"].tolist()),
                        ("理论输出", sweep_frame["current_a"].tolist(), sweep_frame["theory_v"].tolist()),
                    ],
                    "xlabel": "电流 (A，放电为正)",
                    "ylabel": "放大器输出 (V)",
                    "title": "双向电流检测输入-输出曲线",
                    "annotation": f"{SOURCE}；Rshunt=10 mΩ，G=50，零点 1.65 V。",
                },
            ),
            (
                "10_shunt_power.png",
                plot_xy,
                {
                    "x": sweep_frame["current_a"].tolist(),
                    "y": [value * 1000.0 for value in sweep_frame["shunt_power_w"].tolist()],
                    "xlabel": "电流 (A)",
                    "ylabel": "分流电阻功耗 (mW)",
                    "title": "分流电阻功耗 P=I²R",
                    "annotation": f"{SOURCE}；理论 2 A 时 40 mW，2.5 A 时 62.5 mW。",
                    "color": "#d62728",
                },
            ),
            (
                "11_current_saturation.png",
                plot_xy,
                {
                    "x": saturation_frame["current_a"].tolist(),
                    "y": saturation_frame["vout_v"].tolist(),
                    "xlabel": "超量程电流 (A)",
                    "ylabel": "放大器输出 (V)",
                    "title": "电流采集超量程与饱和工况",
                    "annotation": f"{SOURCE}；放大器输出下限 0.1 V、ADC 上限 3.3 V。",
                    "color": "#9467bd",
                },
            ),
            (
                "12_current_output_filter_bode.png",
                plot_xy,
                {
                    "x": filter_ac["frequency_hz"].tolist(),
                    "y": filter_ac["gain_db"].tolist(),
                    "xlabel": "频率 (Hz)",
                    "ylabel": "增益 (dB)",
                    "title": "电流输出 RC 滤波 Bode 图（1 kΩ / 100 nF）",
                    "annotation": f"{SOURCE}；理论截止约 {filter_ac['theoretical_cutoff_hz']:.1f} Hz。",
                    "color": "#2ca02c",
                },
            ),
        ],
    )

    summary = {
        "shunt_ohm": current_config.shunt_ohm,
        "amplifier_gain": current_config.amplifier_gain,
        "zero_reference_v": current_config.reference_v,
        "measured_transconductance_v_per_a": float(slope),
        "theory_transconductance_v_per_a": current_config.amplifier_gain * current_config.shunt_ohm,
        "theoretical_intercept_v": current_config.reference_v,
        "max_theory_error_v": max_error_v,
        "max_shunt_drop_v": float(sweep_frame["shunt_voltage_v"].abs().max()),
        "max_shunt_power_w": float(sweep_frame["shunt_power_w"].max()),
        "saturation": saturation_frame.to_dict("records"),
        "output_filter": {
            "theoretical_cutoff_hz": filter_ac["theoretical_cutoff_hz"],
            "step_rise_time_s": filter_step["rise_time_10_90_s"],
            "theoretical_rise_time_s": filter_step["theoretical_rise_time_s"],
            "steady_state_error_v": filter_step["steady_state_error_v"],
        },
        "shunt_selection": shunt_rows,
        "plots": plots,
    }
    payload = finalize_run(
        run,
        script="scripts/current_sensing_demo.py",
        summary=summary,
        metadata={"config": "configs/afe_config.yaml", "detail": "configs/current_sensing.yaml"},
    )

    print(f"run_id={run.run_id}")
    print(f"实测跨导={slope:.9f} V/A（理论 {current_config.amplifier_gain * current_config.shunt_ohm:.9f}）")
    print(f"最大理论与 SPICE 误差={max_error_v*1000:.6f} mV")
    print(f"2.5 A 分流压降={sweep_frame['shunt_voltage_v'].abs().max()*1000:.3f} mV，功耗={sweep_frame['shunt_power_w'].max()*1000:.3f} mW")
    print(f"输出滤波理论截止={filter_ac['theoretical_cutoff_hz']:.2f} Hz，阶跃建立={filter_step['time_63p2_s']*1e6:.2f} µs")
    print(saturation_frame[["current_a", "vout_v", "amplifier_saturated", "adc_saturated"]].to_string(index=False))
    print(f"真实 SPICE 求解次数={payload['real_spice_solves']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
