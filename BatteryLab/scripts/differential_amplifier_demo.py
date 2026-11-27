"""Task 7/8/9：四电阻差分放大器、共模扫描与电阻匹配实验。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from circuits.differential_amplifier import (
    cmrr_db,
    cmrr_numeric_floor_db,
    common_mode_gain,
    differential_gain,
    resistor_mismatch_values,
    sweep_common_mode_fast,
    sweep_differential_fast,
)
from scripts.stage4_common import amplifier_config, afe
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame, write_plots
from visualization.plots import plot_multi_series, plot_xy

SOURCE = "真实 ngspice 工作点/直流扫描求解（spice_simulation）"
DIFFERENTIAL_VOLTAGES = tuple(np.arange(2.5, 4.2501, 0.25).tolist())
COMMON_MODES_LOW_SIDE = (0.0, 2.0, 4.0, 6.0, 8.0)
CELL_COMMON_MODES = (1.8, 5.5, 9.7)
TOLERANCES = (0.0, 1.0, 0.1)


def main() -> int:
    config = afe()
    amp = amplifier_config(config)
    run = new_sensing_run("sensing")

    experiment_a = sweep_differential_fast(DIFFERENTIAL_VOLTAGES, common_mode_v=5.0, config=amp)
    experiment_b = sweep_common_mode_fast(COMMON_MODES_LOW_SIDE, differential_v=3.7, config=amp)
    gain_a = differential_gain(experiment_a)
    gain_b = common_mode_gain(experiment_b)
    cmrr_value = cmrr_db(gain_a, gain_b)
    numeric_floor = cmrr_numeric_floor_db(gain_a, 1e-7)

    write_frame(run, "differential_sweep.csv", pd.DataFrame(experiment_a))
    write_frame(run, "common_mode_sweep.csv", pd.DataFrame(experiment_b))

    mismatch_rows = []
    cell_error_rows = []
    mismatch_parameters = []
    for tolerance in TOLERANCES:
        rng = np.random.default_rng(42 + int(tolerance * 1000))
        mismatch_config, draws = resistor_mismatch_values(amp, tolerance, rng)
        diff_rows = sweep_differential_fast((3.3, 4.0), common_mode_v=5.0, config=mismatch_config)
        cm_rows = sweep_common_mode_fast((0.0, 8.0), differential_v=3.7, config=mismatch_config)
        actual_gain = differential_gain(diff_rows)
        actual_cm_gain = common_mode_gain(cm_rows)
        actual_cmrr = cmrr_db(actual_gain, actual_cm_gain)
        offset_out = cm_rows[0]["vout_v"] - amp.reference_v - actual_gain * 3.7
        mismatch_rows.append(
            {
                "tolerance_percent": tolerance,
                "r1_ohm": mismatch_config.r1_ohm,
                "r2_ohm": mismatch_config.r2_ohm,
                "r3_ohm": mismatch_config.r3_ohm,
                "r4_ohm": mismatch_config.r4_ohm,
                "draw_r1": draws["r1"],
                "draw_r2": draws["r2"],
                "draw_r3": draws["r3"],
                "draw_r4": draws["r4"],
                "nominal_gain": amp.nominal_gain,
                "actual_gain": actual_gain,
                "common_mode_gain": actual_cm_gain,
                "output_offset_v": offset_out,
                "cmrr_db": actual_cmrr,
                "cmrr_numeric_floor_db": cmrr_numeric_floor_db(actual_gain, 1e-7),
            }
        )
        mismatch_parameters.append(
            {
                "tolerance_percent": tolerance,
                "r1_ohm": mismatch_config.r1_ohm,
                "r2_ohm": mismatch_config.r2_ohm,
                "r3_ohm": mismatch_config.r3_ohm,
                "r4_ohm": mismatch_config.r4_ohm,
            }
        )
        cm_axis = [row["common_mode_v"] for row in cm_rows]
        pin_axis = [row["pin_common_mode_v"] for row in cm_rows]
        for index, (cell_voltage, common_mode) in enumerate(zip((3.6, 3.8, 4.0), CELL_COMMON_MODES), start=1):
            predicted_output = amp.reference_v + actual_gain * cell_voltage + actual_cm_gain * common_mode + offset_out
            estimated = (predicted_output - amp.reference_v) / amp.nominal_gain
            cell_error_rows.append(
                {
                    "tolerance_percent": tolerance,
                    "channel": f"cell{index}",
                    "cell_voltage_v": cell_voltage,
                    "common_mode_v": common_mode,
                    "vout_v": predicted_output,
                    "estimated_cell_v": estimated,
                    "error_v": estimated - cell_voltage,
                    "error_mv": (estimated - cell_voltage) * 1000.0,
                    "pin_common_mode_v": float(np.interp(common_mode, cm_axis, pin_axis)),
                    "note": "由真实 SPICE 提取的 Ad/Acm/失调线性外推，不是逐点 SPICE 求解",
                }
            )

    mismatch_frame = pd.DataFrame(mismatch_rows)
    cell_error_frame = pd.DataFrame(cell_error_rows)
    write_frame(run, "resistor_mismatch_parameters.csv", pd.DataFrame(mismatch_parameters))
    write_frame(run, "resistor_mismatch_gain_cmrr.csv", mismatch_frame)
    write_frame(run, "resistor_mismatch_cell_errors.csv", cell_error_frame)

    plots = write_plots(
        run,
        [
            (
                "04_diff_amp_transfer.png",
                plot_multi_series,
                {
                    "series": [
                        ("SPICE 输出", [row["vhigh_v"] - row["vlow_v"] for row in experiment_a], [row["vout_v"] for row in experiment_a]),
                        ("理论输出", [row["vhigh_v"] - row["vlow_v"] for row in experiment_a], [row["theory_v"] for row in experiment_a]),
                    ],
                    "xlabel": "差分输入 Vhigh - Vlow (V)",
                    "ylabel": "输出电压 (V)",
                    "title": "差分放大器输入-输出曲线（共模 5 V）",
                    "annotation": f"{SOURCE}；增益 0.5，参考 0.2 V。",
                },
            ),
            (
                "05_diff_amp_common_mode_sweep.png",
                plot_multi_series,
                {
                    "series": [
                        ("SPICE 输出", [row["common_mode_v"] for row in experiment_b], [row["vout_v"] for row in experiment_b]),
                        ("理论输出", [row["common_mode_v"] for row in experiment_b], [row["theory_v"] for row in experiment_b]),
                    ],
                    "xlabel": "共模电压 (V)",
                    "ylabel": "输出电压 (V)",
                    "title": "差分放大器共模扫描（固定差分 3.7 V）",
                    "annotation": f"{SOURCE}；理想匹配模型共模增益接近数值零。",
                },
            ),
            (
                "06_resistor_mismatch_cell_error.png",
                plot_multi_series,
                {
                    "series": [
                        (
                            f"{tolerance:g}% 容差",
                            list(range(1, 4)),
                            cell_error_frame[cell_error_frame["tolerance_percent"] == tolerance]["error_mv"].tolist(),
                        )
                        for tolerance in TOLERANCES
                    ],
                    "xlabel": "单体通道（1=底端，3=顶端）",
                    "ylabel": "折算单体电压误差 (mV)",
                    "title": "四电阻独立容差导致的单体电压误差",
                    "annotation": f"{SOURCE}；共模越高误差越明显，电阻比值匹配比绝对精度更重要。",
                },
            ),
        ],
    )

    summary = {
        "differential_gain_spice": gain_a,
        "differential_gain_theory": amp.nominal_gain,
        "common_mode_gain_spice": gain_b,
        "cmrr_db": cmrr_value,
        "cmrr_numeric_floor_db": numeric_floor,
        "cmrr_note": "理想匹配模型 Acm 接近数值零，因此只报告可验证下界，不宣称无限 CMRR。",
        "experiment_a": experiment_a,
        "experiment_b": experiment_b,
        "resistor_mismatch": mismatch_rows,
        "cell_errors": cell_error_rows,
        "plots": plots,
    }
    payload = finalize_run(
        run,
        script="scripts.differential_amplifier_demo.py",
        summary=summary,
        metadata={"config": "configs/afe_config.yaml", "tolerances": list(TOLERANCES)},
    )

    print(f"run_id={run.run_id}")
    print(f"实际差分增益={gain_a:.6f}（理论 {amp.nominal_gain}）")
    print(f"共模增益={gain_b:.3e} CMRR={cmrr_value if cmrr_value is not None else '数值零'} 数值下界={numeric_floor:.1f} dB")
    print(mismatch_frame[["tolerance_percent", "actual_gain", "common_mode_gain", "cmrr_db"]].to_string(index=False))
    print(cell_error_frame[["tolerance_percent", "channel", "error_mv"]].to_string(index=False))
    print(f"真实 SPICE 求解次数={payload['real_spice_solves']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
