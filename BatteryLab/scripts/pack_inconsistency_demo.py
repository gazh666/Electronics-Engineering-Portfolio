"""电芯不一致性实验（Task 24）：SOC / 容量 / 内阻 / 综合。

使用教学 OCV-SOC 曲线，只实现模型运行边界与事件记录，不代表真实 BMS 保护电路。
运行：conda run -n kaifa_battery python -m scripts.pack_inconsistency_demo
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from analysis.pack_consistency import consistency_metrics
from battery_models.battery_pack import build_inconsistent_pack, simulate_series_pack
from battery_models.ocv_model import load_ocv_reference
from battery_models.parameters import load_ecm_models
from storage.result_store import RunDirectory, write_csv, write_json
from visualization.plots import plot_multi_series, plot_series_frame


def main() -> int:
    definition = load_ecm_models()["second_order_rc"]
    ocv = load_ocv_reference()
    times = np.arange(0.0, 2500.0, 1.0)
    currents = np.full(times.size, 2.0)

    specifications = [
        ("A_soc_mismatch", "初始 SOC 不一致", dict(socs=[0.70, 0.60, 0.50])),
        ("B_capacity_mismatch", "容量不一致", dict(socs=[0.6, 0.6, 0.6], capacities_ah=[2.0, 1.9, 1.8])),
        ("C_resistance_mismatch", "内阻不一致", dict(socs=[0.6, 0.6, 0.6], r0_ohm=[0.030, 0.040, 0.060])),
        (
            "D_combined_mismatch",
            "综合不一致",
            dict(socs=[0.70, 0.60, 0.50], capacities_ah=[2.0, 1.9, 1.8], r0_ohm=[0.030, 0.040, 0.060]),
        ),
    ]
    aggregate_rows = []
    runs = {}
    for experiment_id, description, overrides in specifications:
        pack = build_inconsistent_pack(definition, ocv, **overrides)
        result = simulate_series_pack(pack, times, currents)
        pack_frame: pd.DataFrame = result["pack_frame"]
        cell_frame: pd.DataFrame = result["cell_frame"]
        metrics = consistency_metrics(pack_frame, cell_frame)

        run = RunDirectory("battery_pack")
        pack_frame.to_csv(run.path / "pack_waveform.csv", index=False, float_format="%.12g", encoding="utf-8")
        cell_frame.to_csv(run.path / "cell_waveforms.csv", index=False, float_format="%.12g", encoding="utf-8")
        write_json(run.path / "cell_parameters.json", {"cells": result["metadata"]["cells"]})
        write_json(run.path / "consistency_metrics.json", metrics)
        write_csv(
            run.path / "event_log.csv",
            ["event_type", "time_s", "reason", "cell_id"],
            [[event.get("event_type"), event.get("time_s"), event.get("reason"), event.get("cell_id")] for event in result["events"]],
        )
        pivot = cell_frame.pivot_table(index="time_s", columns="cell_id", values="terminal_voltage_v")
        plot_multi_series(
            [(cell_id, pivot.index, pivot[cell_id]) for cell_id in pivot.columns],
            path=run.path / "plots" / "cell_voltages.png",
            xlabel="时间 (s)",
            ylabel="单体端电压 (V)",
            title=f"{experiment_id}：{description}",
            annotation=f"2A 恒流 | 来源: custom_ecm_simulation | Run: {run.run_id}",
        )
        plot_series_frame(
            pack_frame,
            path=run.path / "plots" / "delta_cell_voltage.png",
            x="time_s",
            y="delta_cell_voltage_v",
            xlabel="时间 (s)",
            ylabel="最大单体压差 (V)",
            title=f"{experiment_id}：最大单体压差",
            annotation=f"Run: {run.run_id} | 参数来源: educational_assumption",
        )
        plot_series_frame(
            pack_frame,
            path=run.path / "plots" / "soc_spread.png",
            x="time_s",
            y="delta_soc",
            xlabel="时间 (s)",
            ylabel="最大 SOC 差异",
            title=f"{experiment_id}：SOC 差异",
            annotation=f"Run: {run.run_id}",
        )
        summary = {
            "script": "scripts/pack_inconsistency_demo.py",
            "experiment_id": experiment_id,
            "description": description,
            "run_id": run.run_id,
            "data_source": "custom_ecm_simulation",
            "parameter_source": "educational_assumption",
            "consistency": metrics,
            "termination": result["metadata"]["termination"],
            "termination_time_s": result["metadata"]["termination_time_s"],
            "termination_reason": result["metadata"]["termination_reason"],
            "termination_cell": result["metadata"]["termination_cell"],
            "max_delta_cell_voltage_v": result["metadata"]["max_delta_cell_voltage_v"],
            "max_delta_soc": result["metadata"]["max_delta_soc"],
            "cell_parameters": result["metadata"]["cells"],
            "waveform_paths": {
                "pack": str(run.path / "pack_waveform.csv"),
                "cells": str(run.path / "cell_waveforms.csv"),
            },
        }
        write_json(run.path / "summary.json", summary)
        run.write_metadata({"script": "scripts/pack_inconsistency_demo.py", "case": experiment_id, "summary": summary})
        run.flush_log()
        runs[experiment_id] = run.run_id
        aggregate_rows.append(
            [
                experiment_id,
                result["metadata"]["max_delta_cell_voltage_v"],
                result["metadata"]["final_delta_cell_voltage_v"],
                result["metadata"]["max_delta_soc"],
                result["metadata"]["termination_cell"],
                result["metadata"]["termination_time_s"],
                result["metadata"]["termination_reason"],
                metrics["pack_voltage_start_v"],
                metrics["pack_voltage_end_v"],
                run.run_id,
            ]
        )

    combined = RunDirectory("battery_pack")
    write_csv(
        combined.path / "inconsistency_summary.csv",
        [
            "experiment_id",
            "max_delta_cell_voltage_v",
            "final_delta_cell_voltage_v",
            "max_delta_soc",
            "first_limited_cell",
            "termination_time_s",
            "termination_reason",
            "pack_voltage_start_v",
            "pack_voltage_end_v",
            "run_id",
        ],
        aggregate_rows,
    )
    summary = {
        "script": "scripts/pack_inconsistency_demo.py",
        "run_id": combined.run_id,
        "experiments": [specification[0] for specification in specifications],
        "runs": runs,
        "rows": aggregate_rows,
        "note": "模型停止事件不等于 MOSFET 保护动作，也不代表真实 BMS 保护完成。",
    }
    write_json(combined.path / "summary.json", summary)
    combined.write_metadata({"script": "scripts/pack_inconsistency_demo.py", "case": "inconsistency_suite", "summary": summary})
    combined.flush_log()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
