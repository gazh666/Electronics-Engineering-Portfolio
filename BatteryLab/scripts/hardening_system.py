"""Task 10：系统 LC 与控制器候选闭环验证入口。

运行：
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.hardening_system
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hardening.common import new_run, write_csv, write_json  # noqa: E402
from hardening.system_candidate_validation import run_all  # noqa: E402


def _dump(path: Path, waveform: dict, stride: int = 20) -> None:
    names = ["time_s", "output_voltage_v", "converter_input_voltage_v", "battery_voltage_v",
             "battery_current_a", "inductor_current_a", "load_current_a", "gate_source_v"]
    length = len(waveform["time_s"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(names)
        for index in range(0, length, stride):
            writer.writerow([f"{float(waveform[name][index]):.9g}" for name in names])


def main() -> int:
    run = new_run("system")
    result = run_all()
    write_csv(run / "average_controller_sweep.csv", result["average_sweep"])
    write_csv(run / "controller_screening.csv", result["controller_screening"])
    write_csv(run / "system_candidate_comparison.csv", [
        {
            "group": metrics["group"],
            "inductance_h": metrics["lc"]["inductance_h"],
            "capacitance_f": metrics["lc"]["capacitance_f"],
            "inductor_dcr_ohm": metrics["lc"]["inductor_dcr_ohm"],
            "capacitor_esr_ohm": metrics["lc"]["capacitor_esr_ohm"],
            "kp": metrics["controller"]["kp"],
            "ki": metrics["controller"]["ki"],
            "steady_voltage_v": metrics["steady_voltage_v"],
            "steady_error_mv": metrics["steady_error_mv"],
            "ripple_vpp": metrics["ripple_vpp"],
            "efficiency_percent": metrics["efficiency_percent"],
            "step_deviation_v": metrics["step_deviation_v"],
            "recovery_time_s": metrics["recovery_time_s"],
            "inductor_peak_a": metrics["inductor_peak_a"],
            "path_loss_w": metrics["path_loss_w"],
            "battery_current_mean_a": metrics["battery_current_mean_a"],
            "samples": metrics["samples"],
        }
        for metrics in result["groups"].values()
    ])
    for name, waveform in result["waveforms"].items():
        _dump(run / "waveforms" / f"{name}.csv.gz", waveform)

    groups = result["groups"]
    summary = {
        "run_id": run.name,
        "selected_controller": result["selected_controller"],
        "controller_screening": result["controller_screening"],
        "groups": groups,
        "comparisons": result["comparisons"],
        "status": "VERIFIED" if all(metrics["finite"] for metrics in groups.values()) else "NOT_VERIFIED",
        "model_note": "真实开关级 ngspice 联合仿真；电池为 3S 一阶 RC ECM（初始 SOC 0.4），Buck 为 100 kHz 理想开关 + 物理保护 MOSFET 级。",
        "limitations": [
            "负载阶跃 2.5 Ω → 1.25 Ω，故障时刻 6 ms，仿真窗口 10 ms；非长时间热效应验证。",
            "优化控制器由平均模型筛选，仅用真实 SPICE 做一次确认，不做全网格开关级扫描。",
            "未做实物验证；效率为仿真能量比，不含驱动与辅助电源损耗。",
            "保护 MOSFET 级引入约 31 mΩ 通路电阻，三组共享同一保护级。",
        ],
    }
    write_json(run / "system_candidate_summary.json", summary)
    print(json.dumps({
        "run_id": run.name,
        "status": summary["status"],
        "selected_controller": summary["selected_controller"],
        "groups": {name: {
            "steady_v": round(metrics["steady_voltage_v"], 4),
            "ripple_mv": round(metrics["ripple_vpp"] * 1e3, 2),
            "eff_pct": round(metrics["efficiency_percent"], 3),
            "dev_mv": round(metrics["step_deviation_v"] * 1e3, 2),
            "recovery_us": None if metrics["recovery_time_s"] is None else round(metrics["recovery_time_s"] * 1e6, 1),
        } for name, metrics in groups.items()},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
