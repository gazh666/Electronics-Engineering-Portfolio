"""Task 5/30：真实 CALCE 容量提取与积分曲线。

运行：conda run -n kaifa_battery python -m scripts.capacity_analysis_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from identification.capacity_estimator import compare_capacity_results, cumulative_charge_ah
from scripts.stage3_common import configs, load_record
from storage.result_store import RunDirectory, write_json
from visualization.plots import plot_dual_axis, plot_multi_series, plot_xy


def main() -> int:
    from scripts.stage3_common import capacity_bundle

    run = RunDirectory("capacity")
    settings = configs()
    capacities = capacity_bundle()
    run.write_metadata(
        {
            "script": "scripts/capacity_analysis_demo.py",
            "data_source": "public_experimental_data",
            "datasets": {
                "sp2": settings["split"]["datasets"]["capacity_reference"],
                "sp1": settings["split"]["datasets"]["capacity_cross_check"],
            },
        }
    )

    summary = {"script": "scripts/capacity_analysis_demo.py", "run_id": run.run_id, "results": {}}
    for key, result in capacities.items():
        summary["results"][key] = result.to_dict()
        record_name = "capacity_reference" if key == "sp2" else "capacity_cross_check"
        frame = load_record(record_name)
        step = frame[frame["step_index"] == result.step_index].sort_values("time_s")
        time_values = step["time_s"].to_numpy(dtype=float)
        current_values = step["current_a"].to_numpy(dtype=float)
        voltage_values = step["voltage_v"].to_numpy(dtype=float)
        charge = cumulative_charge_ah(time_values, current_values)
        plot_dual_axis(
            __import__("pandas").DataFrame({"time_s": time_values, "voltage_v": voltage_values, "current_a": current_values}),
            path=run.path / "plots" / f"{key}_discharge_voltage_current.png",
            x="time_s",
            y_left="voltage_v",
            y_right="current_a",
            xlabel="时间 (s)",
            left_label="端电压 (V)",
            right_label="电流 (A)",
            title=f"{key.upper()} 完整恒流放电（真实 CALCE 数据）",
            annotation=(
                f"来源: public_experimental_data | 文件: {result.source_file} | 条件: 25℃, 1 A 恒流放电"
                f" | 模型: 无（原始数据） | 角色: 容量参考 | Run: {run.run_id} | 单位: V / A"
            ),
        )
        plot_xy(
            charge,
            voltage_values,
            path=run.path / "plots" / f"{key}_capacity_integration.png",
            xlabel="累计放电容量 (Ah)",
            ylabel="端电压 (V)",
            title=f"{key.upper()} 容量积分结果 {result.integrated_capacity_ah:.4f} Ah",
            annotation=(
                f"ZOH 电流积分 | 采样 {len(step)} 点 | 来源: public_experimental_data | 文件: {result.source_file}"
                f" | 角色: 容量参考 | Run: {run.run_id} | 单位: Ah / V"
            ),
        )

    comparison = compare_capacity_results(list(capacities.values()))
    summary["comparison"] = comparison
    summary["note"] = (
        "容量由原始电流与时间积分得到；capacity_ratio 不等于已验证 SOH。"
        "SP1 与 SP2 是不同样品。"
    )
    write_json(run.path / "capacity_results.json", summary)
    run.write_summary(summary)
    plot_multi_series(
        [
            ("SP2 实测容量", [0, 1], [capacities["sp2"].integrated_capacity_ah] * 2),
            ("SP1 实测容量", [0, 1], [capacities["sp1"].integrated_capacity_ah] * 2),
            ("额定容量 2.0 Ah", [0, 1], [2.0, 2.0]),
        ],
        path=run.path / "plots" / "capacity_comparison.png",
        xlabel="",
        ylabel="容量 (Ah)",
        title="实测积分容量与额定容量对照",
        annotation=f"数据来源: public_experimental_data | Run: {run.run_id}",
    )
    run.log(
        f"SP2={capacities['sp2'].integrated_capacity_ah:.6f} Ah, "
        f"SP1={capacities['sp1'].integrated_capacity_ah:.6f} Ah"
    )
    run.flush_log()
    print(f"capacity run_id={run.run_id}")
    for key, result in capacities.items():
        print(
            f"{key}: integrated={result.integrated_capacity_ah:.6f} Ah, "
            f"recorded={result.recorded_capacity_ah}, diff={result.capacity_difference_ah}, "
            f"step={result.step_index}, points={result.points}"
        )
    print("comparison:", comparison)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
