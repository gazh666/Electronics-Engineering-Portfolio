"""Task 6/7/8：CC-CV 软启动、PI 网格与抗积分饱和复验入口。

运行：
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.hardening_charging
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from charging.config import load_charger_config, load_controller_config  # noqa: E402
from hardening.charging_control_comparison import (  # noqa: E402
    pi_grid,
    run_antiwindup,
    run_cc_case,
    run_soft_start,
)
from hardening.common import compare_performance, new_run, write_csv, write_json  # noqa: E402


def _dump_waveform(path: Path, payload: dict[str, np.ndarray], stride: int = 10) -> None:
    names = list(payload)
    length = len(payload[names[0]])
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(names)
        for index in range(0, length, stride):
            writer.writerow([f"{float(payload[name][index]):.9g}" for name in names])


def main() -> int:
    run = new_run("charging")
    charger = load_charger_config()
    controller = load_controller_config()

    # ---- 软启动：0/1/2/5 ms（8 ms 窗口）+ 10 ms（12 ms 窗口） ----
    soft_rows = []
    for soft in (0.0, 0.001, 0.002, 0.005):
        row = run_soft_start(soft, duration_s=0.008, charger=charger, controller=controller)
        _dump_waveform(run / f"soft_start_{int(soft * 1e3):02d}ms.csv.gz", row.pop("waveform"))
        soft_rows.append(row)
    extended = run_soft_start(0.010, duration_s=0.012, charger=charger, controller=controller)
    _dump_waveform(run / "soft_start_10ms_extended.csv.gz", extended.pop("waveform"))
    extended["window_note"] = "10 ms 软启动需要 12 ms 窗口，评价窗口不同，不与其他行直接比较。"
    write_csv(run / "soft_start_comparison.csv", soft_rows + [extended])

    baseline_soft = soft_rows[0]
    soft_compare = {}
    for row in soft_rows[1:]:
        key = f"{int(row['soft_start_time_s'] * 1e3)}ms"
        soft_compare[key] = {
            "overshoot_fraction": compare_performance(baseline_soft["overshoot_fraction"], row["overshoot_fraction"]),
            "peak_current": compare_performance(baseline_soft["peak_charging_current_a"], row["peak_charging_current_a"]),
            "peak_input_filtered": compare_performance(
                baseline_soft["peak_input_current_filtered_a"], row["peak_input_current_filtered_a"]
            ),
            "startup_energy": compare_performance(baseline_soft["startup_energy_j"], row["startup_energy_j"]),
            "rise_time_90": compare_performance(
                baseline_soft["rise_time_90_s"], row["rise_time_90_s"]
            ) if row["rise_time_90_s"] is not None else None,
        }

    # ---- PI 网格：频域筛选 + 真实 SPICE 复验 ----
    grid = pi_grid(multipliers=[0.5, 0.8, 1.0, 1.2, 1.5], charger=charger, controller=controller)
    write_csv(run / "pi_grid.csv", grid)
    passing = [row for row in grid if row["passes"] and row["current_multiplier"] != 1.0]
    passing.sort(key=lambda row: (row["voltage_crossover_hz"] or 0.0), reverse=True)
    # 预先登记的 5× 带宽分离判据若全部不满足，保留该失败事实；
    # 另取"PM 全部 ≥45° 且分离比最大"的候选作为探索性对照，明确标注未通过全部判据。
    exploratory = [
        row for row in grid
        if row["current_multiplier"] != 1.0
        and row["current_phase_margin_deg"] is not None and row["current_phase_margin_deg"] >= 45.0
        and row["voltage_phase_margin_deg"] is not None and row["voltage_phase_margin_deg"] >= 45.0
    ]
    exploratory.sort(key=lambda row: (row["bandwidth_separation_ratio"] or 0.0), reverse=True)
    selected = (passing + [row for row in exploratory if row not in passing])[:2]
    spice_rows = [run_cc_case(overrides={}, charger=charger, controller=controller)]
    spice_rows[0]["label"] = "baseline_1.0"
    for index, candidate in enumerate(selected):
        overrides = {
            "current_kp_duty_per_a": candidate["current_kp"],
            "current_ki_duty_per_as": candidate["current_ki"],
            "voltage_kp_a_per_v": candidate["voltage_kp"],
            "voltage_ki_a_per_vs": candidate["voltage_ki"],
        }
        row = run_cc_case(overrides=overrides, charger=charger, controller=controller)
        row["label"] = f"candidate_{index + 1}"
        row["selection"] = "pre_registered_pass" if candidate in passing else "exploratory_not_all_criteria"
        row["current_multiplier"] = candidate["current_multiplier"]
        row["voltage_multiplier"] = candidate["voltage_multiplier"]
        spice_rows.append(row)
    write_csv(run / "pi_spice_validation.csv", spice_rows)
    write_json(run / "pi_selected.json", {
        "pre_registered_passing": passing,
        "exploratory": exploratory[:3],
        "selected": selected,
        "spice": spice_rows,
        "note": "0 个候选满足预先登记的 5× 带宽分离判据；探索性候选不改变该失败结论。",
    })
    pi_compare = [
        {
            "label": row["label"],
            "cc_mean_error_a": compare_performance(spice_rows[0]["cc_mean_error_a"], row["cc_mean_error_a"]),
            "cc_ripple_pp_a": compare_performance(spice_rows[0]["cc_ripple_pp_a"], row["cc_ripple_pp_a"]),
            "peak_current": compare_performance(spice_rows[0]["peak_charging_current_a"], row["peak_charging_current_a"]),
            "settling_time": compare_performance(spice_rows[0]["settling_time_s"], row["settling_time_s"])
            if row["settling_time_s"] is not None and spice_rows[0]["settling_time_s"] is not None else None,
        }
        for row in spice_rows[1:]
    ]

    # ---- 抗积分饱和：none / conditional / back_calculation（真实 SPICE C03 型工况） ----
    antiwindup = run_antiwindup(
        ("none", "conditional", "back_calculation", "back_calculation_tuned"),
        charger=charger, controller=controller,
    )
    for row in antiwindup:
        _dump_waveform(run / f"antiwindup_{row['method']}.csv.gz", row.pop("waveform"))
    write_csv(run / "antiwindup_comparison.csv", antiwindup)
    baseline_aw = next(row for row in antiwindup if row["method"] == "none")
    aw_compare = {}
    for row in antiwindup:
        if row["method"] == "none":
            continue
        aw_compare[row["method"]] = {
            "overshoot": compare_performance(baseline_aw["voltage_overshoot_v"], row["voltage_overshoot_v"]),
            "settling_time": compare_performance(baseline_aw["settling_time_to_20mv_s"], row["settling_time_to_20mv_s"])
            if row["settling_time_to_20mv_s"] is not None and baseline_aw["settling_time_to_20mv_s"] is not None else None,
            "integrator_peak": compare_performance(baseline_aw["integrator_peak_v"], row["integrator_peak_v"]),
            "cc_mean_error": compare_performance(baseline_aw["cc_mean_error_a"], row["cc_mean_error_a"]),
        }

    summary = {
        "run_id": run.name,
        "soft_start": soft_rows,
        "soft_start_extended": extended,
        "soft_start_improvement": soft_compare,
        "pi_grid_rows": len(grid),
        "pi_grid_passing": sum(1 for row in grid if row["passes"]),
        "pi_spice_validation": spice_rows,
        "pi_improvement": pi_compare,
        "antiwindup": antiwindup,
        "antiwindup_improvement": aw_compare,
        "engine_limits": {
            "step_s": 2.0e-8,
            "source": "真实开关级 ngspice 网表；PI 在网表内行为源实现",
        },
        "limitations": [
            "软启动只限制电流指令上升，电感本身已限制 di/dt，峰值电流改善有限。",
            "PI 网格先在频域筛选，再对 2 个候选做真实开关级复验，未穷举所有组合的 SPICE。",
            "抗积分饱和方法通过改写网表冻结项与 back-calculation 增益实现，未更换控制器结构。",
            "所有结论限于软件仿真，未做实物验证。",
        ],
    }
    write_json(run / "summary.json", summary)
    print(json.dumps({
        "run_id": run.name,
        "soft_start_rows": len(soft_rows) + 1,
        "pi_passing": summary["pi_grid_passing"],
        "pi_total": len(grid),
        "antiwindup_methods": [row["method"] for row in antiwindup],
        "antiwindup_overshoot": {row["method"]: row["voltage_overshoot_v"] for row in antiwindup},
        "soft_peak_current": {int(row["soft_start_time_s"] * 1e3): row["peak_charging_current_a"] for row in soft_rows},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
