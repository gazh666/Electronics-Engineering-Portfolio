"""Task 10-13/30：脉冲检测、R0 表观内阻与静置恢复拟合。

运行：conda run -n kaifa_battery python -m scripts.pulse_identification_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from identification.pulse_detector import DetectionConfig, detect_events, detect_steps_within_dynamic
from identification.relaxation_fitter import fit_relaxation
from identification.resistance_estimator import estimate_from_steps, soc_binned_resistance
from scripts.stage3_common import capacity_bundle, configs, load_record
from storage.result_store import RunDirectory, write_json
from visualization.plots import plot_histogram, plot_multi_series, plot_xy
from validation.dataset_split import build_experiment


def rest_before_dynamic(frame: pd.DataFrame, dynamic_start_time_s: float) -> tuple[pd.DataFrame, dict]:
    """取动态工步之前最近的长静置段及其之前的恒流脉冲。"""
    best = None
    for step, part in frame.groupby("step_index", sort=False):
        part = part.sort_values("time_s")
        if part["time_s"].iloc[-1] >= dynamic_start_time_s:
            continue
        if len(part) < 30:
            continue
        mean_current = float(np.nanmean(part["current_a"]))
        duration = float(part["time_s"].iloc[-1] - part["time_s"].iloc[0])
        if abs(mean_current) <= 0.01 and duration >= 1800:
            if best is None or part["time_s"].iloc[-1] > best[1]["time_s"].iloc[-1]:
                best = (step, part)
    if best is None:
        return pd.DataFrame(), {}
    rest_step, rest_part = best
    pulse = None
    for step, part in frame.groupby("step_index", sort=False):
        if step >= rest_step or len(part) < 10:
            continue
        mean_current = float(np.nanmean(part["current_a"]))
        std_current = float(np.std(part["current_a"]))
        if abs(mean_current) >= 0.2 and std_current < 0.2 * abs(mean_current):
            if pulse is None or part["time_s"].iloc[-1] > pulse[1]["time_s"].iloc[-1]:
                pulse = (step, part)
    info = {
        "rest_step": float(rest_step),
        "rest_start_s": float(rest_part["time_s"].iloc[0]),
        "rest_end_s": float(rest_part["time_s"].iloc[-1]),
        "rest_duration_s": float(rest_part["time_s"].iloc[-1] - rest_part["time_s"].iloc[0]),
        "pulse_step": float(pulse[0]) if pulse else None,
        "pulse_current_a": float(np.nanmean(pulse[1]["current_a"])) if pulse else None,
        "pulse_duration_s": float(pulse[1]["time_s"].iloc[-1] - pulse[1]["time_s"].iloc[0]) if pulse else None,
    }
    return rest_part, info


def main() -> int:
    run = RunDirectory("pulse_identification")
    settings = configs()
    capacities = capacity_bundle()
    capacity_ah = capacities["sp2"].integrated_capacity_ah
    split_config = settings["split"]
    detection = settings["identification"]["pulse_detection"]
    relaxation_config = settings["identification"]["relaxation"]

    config = DetectionConfig(
        rest_current_tolerance_a=detection["rest_current_tolerance_a"],
        minimum_current_step_a=detection["minimum_current_step_a"],
        minimum_pulse_s=detection["minimum_pulse_s"],
        stability_window_s=detection["stability_window_s"],
    )
    run.write_metadata(
        {
            "script": "scripts/pulse_identification_demo.py",
            "data_source": "public_experimental_data",
            "capacity_ah": capacity_ah,
            "detection_config": detection,
            "relaxation_config": relaxation_config,
        }
    )

    summary: dict = {
        "script": "scripts/pulse_identification_demo.py",
        "run_id": run.run_id,
        "capacity_ah": capacity_ah,
        "experiments": {},
    }
    resistance_tables = []
    relaxation_rows = []
    fit_curves = []

    for name, record_name in (("dst_50", "dst_50"), ("dst_80", "dst_80")):
        record = split_config["datasets"][record_name]
        experiment = build_experiment(name, record, capacity_ah=capacity_ah)
        frame = experiment.frame
        time_values = frame["time_s"].to_numpy(dtype=float)
        current_values = frame["current_a"].to_numpy(dtype=float)
        voltage_values = frame["voltage_v"].to_numpy(dtype=float)
        soc_values = frame["soc_reference"].to_numpy(dtype=float)

        events, event_table = detect_events(
            time_values,
            current_values,
            voltage_values,
            config=config,
            soc_reference=soc_values,
            temperature_c=25.0,
            segment_id=name,
        )
        steps = detect_steps_within_dynamic(time_values, current_values, config=config)
        resistance, stats = estimate_from_steps(
            frame,
            steps,
            window_s=1.0,
            minimum_current_change_a=detection["minimum_current_step_a"],
            temperature_c=25.0,
        )
        if not resistance.empty:
            resistance["experiment"] = name
            resistance_tables.append(resistance)
        bins = soc_binned_resistance(resistance) if not resistance.empty else pd.DataFrame()

        python_record = load_record(record_name)
        rest_part, rest_info = rest_before_dynamic(python_record, float(time_values[0]))
        relaxation_payload = {}
        if not rest_part.empty:
            rest_time = rest_part["time_s"].to_numpy(dtype=float)
            rest_voltage = rest_part["voltage_v"].to_numpy(dtype=float)
            for order in (1, 2):
                fit = fit_relaxation(
                    rest_time,
                    rest_voltage,
                    order=order,
                    tau1_bounds_s=tuple(relaxation_config["tau1_bounds_s"]),
                    tau2_bounds_s=tuple(relaxation_config["tau2_bounds_s"]),
                    maximum_relative_rmse=relaxation_config["maximum_relative_rmse"],
                )
                payload = fit.to_dict()
                payload.update(
                    {
                        "experiment": name,
                        "rest_start_s": rest_info["rest_start_s"],
                        "rest_end_s": rest_info["rest_end_s"],
                        "rest_duration_s": rest_info["rest_duration_s"],
                        "pulse_current_a": rest_info["pulse_current_a"],
                        "pulse_duration_s": rest_info["pulse_duration_s"],
                    }
                )
                if rest_info["pulse_current_a"] and rest_info["pulse_duration_s"]:
                    try:
                        r_value, c_value = fit.derive_rc(
                            rest_info["pulse_current_a"], rest_info["pulse_duration_s"], 0
                        )
                        payload["derived_r1_ohm"] = r_value
                        payload["derived_c1_f"] = c_value
                    except Exception as exc:
                        payload["derived_note"] = str(exc)
                relaxation_rows.append(payload)
                relaxation_payload[f"order{order}"] = payload
                if fit.time_s is not None and fit.residual is not None:
                    prediction = rest_voltage[: len(fit.time_s)] + fit.residual
                    fit_curves.append(
                        (f"{name} 实测", fit.time_s, rest_voltage[: len(fit.time_s)])
                    )
                    fit_curves.append((f"{name} {order}阶拟合", fit.time_s, prediction))
                    plot_multi_series(
                        [
                            (f"{name} 实测静置", fit.time_s, rest_voltage[: len(fit.time_s)]),
                            (f"{order} 阶指数拟合", fit.time_s, prediction),
                        ],
                        path=run.path / "plots" / f"{'12' if order == 1 else '13'}_relaxation_fit_{order}order_{name}.png",
                        xlabel="静置时间 (s)",
                        ylabel="端电压 (V)",
                        title=f"{name}: {order} 阶 RC 静置恢复拟合",
                        annotation=(
                            f"来源: public_experimental_data | 文件: {record['source_file']}"
                            f" | 条件: 25℃ 长静置 | 模型: {order} 阶指数 | 角色: 参数提取（非验证）"
                            f" | RMSE {fit.rmse_v * 1000:.3f} mV | Run: {run.run_id} | 单位: V"
                        ),
                    )

        summary["experiments"][name] = {
            "dataset_id": experiment.dataset_id,
            "soc0": experiment.soc0,
            "soc0_method": experiment.soc0_method,
            "points": int(len(frame)),
            "detected_events": int(len(events)),
            "detected_steps": int(len(steps)),
            "resistance": stats,
            "soc_binned": bins.to_dict("records") if not bins.empty else [],
            "relaxation": relaxation_payload,
            "rest_info": rest_info,
        }
        if not event_table.empty:
            event_table.to_csv(run.path / f"detected_events_{name}.csv", index=False)
        if not resistance.empty:
            resistance.to_csv(run.path / f"resistance_results_{name}.csv", index=False)
            plot_xy(
                resistance["soc_reference"],
                resistance["r0_apparent_ohm"] * 1000.0,
                path=run.path / "plots" / f"10_r0_vs_soc_{name}.png",
                xlabel="SOC 参考值",
                ylabel="表观 R0 (mΩ)",
                title=f"{name}: 1 s 窗口表观内阻与 SOC",
                annotation=(
                    f"来源: public_experimental_data | 文件: {record['source_file']} | 条件: 25℃"
                    f" | 模型: 无（实测阶跃） | 角色: 参数提取 | 有效样本 {len(resistance)} | Run: {run.run_id} | 单位: mΩ"
                ),
            )
            plot_histogram(
                resistance["r0_apparent_ohm"] * 1000.0,
                path=run.path / "plots" / f"11_r0_histogram_{name}.png",
                xlabel="表观 R0 (mΩ)",
                title=f"{name}: R0 分布直方图",
                annotation=(
                    f"中位数 {stats['median_ohm'] * 1000:.2f} mΩ | 来源: public_experimental_data"
                    f" | 条件: 25℃, 1 s 窗口 | 模型: 无（实测阶跃） | 角色: 参数提取 | Run: {run.run_id} | 单位: mΩ"
                ),
            )
            # 局部阶跃波形
            index = int(np.argmin(np.abs(time_values - float(resistance["time_s"].iloc[len(resistance) // 2]))))
            window = (time_values >= time_values[index] - 5) & (time_values <= time_values[index] + 5)
            plot_multi_series(
                [
                    ("端电压", time_values[window] - time_values[index], voltage_values[window]),
                    ("电流", time_values[window] - time_values[index], current_values[window]),
                ],
                path=run.path / "plots" / f"09_current_step_zoom_{name}.png",
                xlabel="相对阶跃时间 (s)",
                ylabel="电压 (V) / 电流 (A)",
                title=f"{name}: 真实电流阶跃局部波形",
                annotation=(
                    f"来源: public_experimental_data | 文件: {record['source_file']} | 条件: 25℃"
                    f" | 模型: 无（实测阶跃） | 角色: 参数提取 | Run: {run.run_id} | 单位: V / A"
                ),
            )

    if resistance_tables:
        combined = pd.concat(resistance_tables, ignore_index=True)
        combined.to_csv(run.path / "resistance_results.csv", index=False)
    if relaxation_rows:
        pd.DataFrame(relaxation_rows).to_csv(run.path / "relaxation_fits.csv", index=False)
    if fit_curves:
        for name in ("dst_50", "dst_80"):
            series = [(label, t, v) for label, t, v in fit_curves if label.startswith(name)]
            if series:
                plot_multi_series(
                    series,
                    path=run.path / "plots" / f"12_13_relaxation_fit_{name}.png",
                    xlabel="静置时间 (s)",
                    ylabel="端电压 (V)",
                    title=f"{name}: 静置恢复一阶/二阶指数拟合",
                    annotation=(
                        f"来源: public_experimental_data | 条件: 25℃ 长静置 | 模型: 一阶/二阶指数"
                        f" | 角色: 参数提取（非验证） | Run: {run.run_id} | 单位: V"
                    ),
                )

    # Task 25：SOC 相关参数探索（可选工程扩展，仅用训练/DST 数据，不使用验证集）
    r0_bins = []
    for name, payload in summary["experiments"].items():
        for row in payload.get("soc_binned", []):
            r0_bins.append({"experiment": name, **row})
    usable_bins = [row for row in r0_bins if row["samples"] >= 30 and row["median_r0_ohm"] is not None]
    relaxation_points_summary = []
    for name, payload in summary["experiments"].items():
        order2 = payload.get("relaxation", {}).get("order2")
        if order2:
            relaxation_points_summary.append(
                {
                    "experiment": name,
                    "rest_soc": payload.get("soc0"),
                    "r1_ohm": order2.get("derived_r1_ohm"),
                    "tau1_s": order2["time_constants_s"][0] if order2.get("time_constants_s") else None,
                    "r2_ohm": order2.get("derived_r1_ohm"),
                    "tau2_s": order2["time_constants_s"][1] if len(order2.get("time_constants_s") or []) > 1 else None,
                    "status": order2.get("status"),
                }
            )
    soc_exploration = {
        "temperature_c": 25.0,
        "data_role": "training_only",
        "r0_soc": {
            "bins": r0_bins,
            "usable_bin_count": len(usable_bins),
            "total_valid_samples": int(
                sum(payload["resistance"].get("valid_samples", 0) for payload in summary["experiments"].values())
            ),
            "median_range_ohm": [
                float(min(row["median_r0_ohm"] for row in usable_bins)),
                float(max(row["median_r0_ohm"] for row in usable_bins)),
            ]
            if usable_bins
            else None,
            "classification": (
                "分段常数 R0(SOC) 可探索（每个区间有效样本 >= 30）"
                if len(usable_bins) >= 3
                else "INSUFFICIENT_DATA：保留全局常参数 R0"
            ),
            "note": "R0 为 1 s 窗口表观内阻，含快速极化；样本集中在 0–0.6 SOC，0.6 以上不足以分箱。",
        },
        "r1_tau_soc": {
            "segments": relaxation_points_summary,
            "segment_count": len(relaxation_points_summary),
            "classification": (
                "分段常数 R1/tau(SOC) 可探索"
                if len(relaxation_points_summary) >= 3
                else "INSUFFICIENT_DATA：独立静置段不足，保留全局常参数 R1/tau1/R2/tau2"
            ),
            "note": "现有真实数据仅在 2 个静置段可做二阶指数拟合，无法按 SOC 分箱，不做无记录外推。",
        },
        "rule": "查表值仅由 DST 训练段决定；验证集不参与查表参数选择。",
    }
    summary["soc_parameter_exploration"] = soc_exploration
    write_json(run.path / "soc_parameter_exploration.json", soc_exploration)

    write_json(run.path / "pulse_summary.json", summary)
    run.write_summary(summary)
    run.flush_log()
    print(f"pulse run_id={run.run_id}")
    for name, payload in summary["experiments"].items():
        print(name, "events", payload["detected_events"], "steps", payload["detected_steps"])
        print("  resistance:", payload["resistance"])
        print("  rest:", payload["rest_info"])
        for order in ("order1", "order2"):
            fit = payload["relaxation"].get(order)
            if fit:
                print(
                    f"  {order}: rmse={fit['rmse_v']:.5f} V, A={fit['amplitudes_v']}, tau={fit['time_constants_s']}, "
                    f"status={fit['status']}, derived R1={fit.get('derived_r1_ohm')}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
