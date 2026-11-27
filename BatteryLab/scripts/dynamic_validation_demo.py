"""Task 21-24/30：FUDS 独立验证、额外动态工况、模型选择与残差分析。

运行：conda run -n kaifa_battery python -m scripts.dynamic_validation_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml

from analysis.fitting_metrics import soc_bucket_metrics
from analysis.residual_analysis import residual_correlations, steady_state_bias, worst_error_windows
from identification.parameter_store import load_frozen_model
from scripts.stage3_common import capacity_bundle, configs
from storage.result_store import RunDirectory, write_json
from validation.dataset_split import build_experiment
from validation.dynamic_validation import run_open_loop_validation, validation_table
from validation.model_selection import aggregate_validation_rmse, select_model
from visualization.plots import plot_multi_series, plot_xy

MODEL_IDS = {
    "rint": "calce_sp2_25c_inr18650_20r_rint_v1",
    "first_order_rc": "calce_sp2_25c_inr18650_20r_first_order_v1",
    "second_order_rc": "calce_sp2_25c_inr18650_20r_second_order_v1",
}
EXPERIMENTS = ("fuds_50", "fuds_80", "us06_50", "us06_80", "bjdst_50", "bjdst_80", "dst_80")


def main() -> int:
    run = RunDirectory("dynamic_validation")
    settings = configs()
    acceptance = settings["validation"]["independent_validation"]
    capacities = capacity_bundle()
    capacity_ah = capacities["sp2"].integrated_capacity_ah
    frozen = {name: load_frozen_model(model_id) for name, model_id in MODEL_IDS.items()}
    experiments = {
        name: build_experiment(name, settings["split"]["datasets"][name], capacity_ah=capacity_ah)
        for name in EXPERIMENTS
    }

    run.write_metadata(
        {
            "script": "scripts/dynamic_validation_demo.py",
            "data_source": "public_experimental_data",
            "capacity_ah": capacity_ah,
            "frozen_models": {name: bundle["paths"] for name, bundle in frozen.items()},
            "experiments": {name: experiment.summary() for name, experiment in experiments.items()},
            "acceptance": acceptance,
            "note": "验证只读取冻结参数；未在验证集上调参或修正状态。",
        }
    )

    results: dict[str, dict] = {}
    for experiment_name, experiment in experiments.items():
        results[experiment_name] = {}
        for model_name, bundle in frozen.items():
            payload = run_open_loop_validation(experiment, bundle, model_name=model_name)
            results[experiment_name][model_name] = payload
            waveform = payload["waveform"]
            waveform.to_csv(
                run.path / f"predicted_waveform_{experiment_name}_{model_name}.csv.gz",
                index=False,
                compression="gzip",
            )

    table = validation_table(results)
    table.to_csv(run.path / "validation_summary.csv", index=False)

    # Task 31：验证运行规定文件
    (run.path / "frozen_parameters.yaml").write_text(
        yaml.safe_dump(
            {name: bundle["parameters"].to_dict() for name, bundle in frozen.items()},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manifest = {
        "frozen_models": {name: bundle["model_id"] for name, bundle in frozen.items()},
        "frozen_parameter_files": {name: bundle["paths"]["parameters"] for name, bundle in frozen.items()},
        "experiments": {
            "independent_validation": ["fuds_50", "fuds_80"],
            "additional_validation": ["us06_50", "us06_80", "bjdst_50", "bjdst_80"],
            "development_only": ["dst_80"],
        },
        "experiment_details": {name: experiment.summary() for name, experiment in experiments.items()},
        "datasets": {name: settings["split"]["datasets"][name] for name in EXPERIMENTS},
        "capacity_ah": capacity_ah,
        "acceptance": acceptance,
        "rule": "参数在 DST 训练集冻结；验证阶段不调参、不使用验证电压修正状态。",
    }
    write_json(run.path / "validation_manifest.json", manifest)
    pd.concat(
        [
            payload["waveform"].assign(experiment=name, model=model)[
                [
                    "time_s",
                    "current_a",
                    "measured_voltage_v",
                    "predicted_voltage_v",
                    "soc_reference",
                    "soc_model",
                    "residual_v",
                    "experiment",
                    "model",
                ]
            ]
            for name, per_model in results.items()
            for model, payload in per_model.items()
        ],
        ignore_index=True,
    ).to_csv(run.path / "predicted_waveform.csv.gz", index=False, compression="gzip")

    fuds = table[table["experiment"].str.startswith("fuds")]
    rint_rmse = fuds[fuds["model"] == "rint"]["rmse_mv"].mean()
    checks = []
    for _, row in fuds.iterrows():
        checks.append(
            {
                "experiment": row["experiment"],
                "model": row["model"],
                "rmse_mv": row["rmse_mv"],
                "mae_mv": row["mae_mv"],
                "max_mv": row["max_mv"],
                "rmse_pass": bool(row["rmse_mv"] <= acceptance["rmse_v"] * 1000),
                "mae_pass": bool(row["mae_mv"] <= acceptance["mae_v"] * 1000),
                "max_pass": bool(row["max_mv"] <= acceptance["maximum_absolute_error_v"] * 1000),
            }
        )
    overall_pass = bool(checks) and all(
        item["rmse_pass"] and item["mae_pass"] and item["max_pass"] for item in checks
    )

    # 训练与开发误差（来自冻结模型的记录）
    training_metrics = {}
    development_metrics = {}
    for name, bundle in frozen.items():
        quality = bundle.get("quality", {})
        summary = quality.get("fitting_summary", {})
        training_metrics[name] = {
            "model_order": bundle["parameters"].model_order,
            "training_rmse_v": summary.get("training_rmse_v"),
            "training_mae_v": summary.get("training_mae_v"),
        }
        dev = results.get("dst_80", {}).get(name)
        development_metrics[name] = {"rmse_v": dev["metrics"]["rmse_v"]} if dev else {}

    selection = select_model(
        training_metrics=training_metrics,
        development_metrics=development_metrics,
        validation_rmse=aggregate_validation_rmse(table, experiment_prefix="fuds"),
        quality={name: bundle["parameters"].quality_status for name, bundle in frozen.items()},
        acceptance_rmse_v=float(acceptance["rmse_v"]),
        prefer_lower_order_within_percent=float(settings["validation"]["model_selection"]["prefer_lower_order_if_rmse_within_percent"]),
    )
    selection["table"].to_csv(run.path / "model_selection.csv", index=False)

    residual_summary = {}
    for experiment_name, per_model in results.items():
        residual_summary[experiment_name] = {}
        for model_name, payload in per_model.items():
            waveform = payload["waveform"]
            residual_summary[experiment_name][model_name] = {
                "correlations": residual_correlations(waveform),
                "steady_state": steady_state_bias(waveform),
                "worst_windows": worst_error_windows(waveform).to_dict("records"),
                "soc_buckets": payload["soc_buckets"].to_dict("records"),
            }
            if experiment_name in ("fuds_50", "fuds_80"):
                plot_multi_series(
                    [
                        ("实测电压", waveform["time_s"], waveform["measured_voltage_v"]),
                        (f"{model_name} 预测", waveform["time_s"], waveform["predicted_voltage_v"]),
                    ],
                    path=run.path / "plots" / f"17_18_{experiment_name}_{model_name}_voltage.png",
                    xlabel="时间 (s)",
                    ylabel="端电压 (V)",
                    title=f"{experiment_name}: {model_name} 独立开环预测",
                    annotation=(
                        f"来源: public_experimental_data | 文件: {experiment.source_file} | 条件: 25℃, {experiment_name}"
                        f" | 模型: {model_name}（冻结参数） | 角色: 独立验证 | RMSE {payload['metrics']['rmse_mv']:.2f} mV"
                        f" | Run: {run.run_id} | 单位: V"
                    ),
                )
                plot_xy(
                    waveform["time_s"],
                    waveform["residual_v"] * 1000.0,
                    path=run.path / "plots" / f"18_residual_{experiment_name}_{model_name}.png",
                    xlabel="时间 (s)",
                    ylabel="残差 (mV)",
                    title=f"{experiment_name}: {model_name} 电压残差",
                    annotation=f"Run: {run.run_id}",
                )
            if experiment_name == "fuds_50":
                buckets = payload["soc_buckets"]
                valid = buckets[buckets["status"] != "NOT_VERIFIED"]
                if not valid.empty:
                    plot_multi_series(
                        [
                            (
                                "SOC 区间",
                                valid["soc_low"],
                                valid["rmse_mv"],
                            )
                        ],
                        path=run.path / "plots" / f"20_soc_bucket_rmse_{model_name}.png",
                        xlabel="SOC 区间下界",
                        ylabel="RMSE (mV)",
                        title=f"FUDS 50%: {model_name} 各 SOC 区间误差",
                        annotation=f"来源: public_experimental_data | Run: {run.run_id}",
                    )

    plot_multi_series(
        [
            (
                "FUDS 平均 RMSE",
                [0, 1, 2],
                [
                    float(fuds[fuds["model"] == model]["rmse_mv"].mean())
                    for model in ("rint", "first_order_rc", "second_order_rc")
                ],
            )
        ],
        path=run.path / "plots" / "19_validation_rmse_comparison.png",
        xlabel="模型序号（0=Rint, 1=一阶RC, 2=二阶RC）",
        ylabel="独立验证 RMSE (mV)",
        title="三种模型 FUDS 独立验证误差对照",
        annotation=f"数据来源: public_experimental_data | Run: {run.run_id}",
    )

    summary = {
        "script": "scripts/dynamic_validation_demo.py",
        "run_id": run.run_id,
        "capacity_ah": capacity_ah,
        "acceptance": acceptance,
        "validation_table": table.to_dict("records"),
        "acceptance_checks": checks,
        "overall_pass": overall_pass,
        "model_selection": {
            "recommendation": selection["recommendation"],
            "reason": selection["reason"],
            "meets_acceptance": selection["meets_acceptance"],
            "table": selection["table"].to_dict("records"),
        },
        "residual_summary": residual_summary,
        "note": (
            "FUDS 结果来自参数冻结后的开环预测；未使用验证电压修正模型状态。"
            "未达到限值时保留 FAIL。"
        ),
    }
    write_json(run.path / "validation_metrics.json", summary)
    pd.concat(
        [
            payload["waveform"].assign(experiment=name, model=model)
            for name, per_model in results.items()
            for model, payload in per_model.items()
        ],
        ignore_index=True,
    ).to_csv(run.path / "residuals.csv.gz", index=False, compression="gzip")
    run.write_summary(summary)
    run.log(f"FUDS overall_pass={overall_pass}, recommendation={selection['recommendation']}")
    run.flush_log()

    print(f"dynamic_validation run_id={run.run_id}")
    print(table.to_string(index=False))
    print("acceptance checks:", checks)
    print("overall_pass:", overall_pass)
    print("recommendation:", selection["recommendation"], "|", selection["reason"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
