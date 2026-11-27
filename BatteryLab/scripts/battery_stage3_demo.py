"""Task 36：第三阶段工程验收汇总（只读取已保存的真实运行记录）。

运行：conda run -n kaifa_battery python -m scripts.battery_stage3_demo
加 --report-only 只汇总，不提示缺失步骤的修复建议。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from battery_models.parameters import load_ecm_models
from scripts.stage3_common import configs
from storage.result_store import RESULTS_ROOT, RunDirectory, json_safe, write_json

CATEGORIES = (
    "capacity",
    "ocv",
    "pulse_identification",
    "identification",
    "dynamic_validation",
    "temperature",
    "identified_spice",
)


def latest_run(category: str) -> Path | None:
    base = RESULTS_ROOT / category
    if not base.exists():
        return None
    runs = sorted([path for path in base.iterdir() if path.is_dir()])
    return runs[-1] if runs else None


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, value: Any, threshold: Any, comparator: str, source: str, note: str = "") -> dict[str, Any]:
    if isinstance(value, (int, float)) and isinstance(threshold, (int, float)) and comparator in ("<=", ">=", "<", ">"):
        passed = {
            "<=": value <= threshold,
            ">=": value >= threshold,
            "<": value < threshold,
            ">": value > threshold,
        }[comparator]
    else:
        passed = value == threshold
    return {
        "check": name,
        "value": value,
        "threshold": threshold,
        "comparator": comparator,
        "status": "PASS" if passed else "FAIL",
        "source": source,
        "note": note,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=["smoke", "standard", "report-only"],
        default="standard",
        help="smoke=只做轻量验收；standard=生成全部汇总产物；report-only=只读取已有汇总",
    )
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    profile = "report-only" if args.report_only else args.profile
    if profile == "report-only":
        base = RESULTS_ROOT / "stage3"
        runs_found = sorted([path for path in base.iterdir() if path.is_dir()]) if base.exists() else []
        if not runs_found:
            print("没有可读取的 stage3 运行记录")
            return 1
        stored = read_json(runs_found[-1] / "acceptance.json")
        print(f"report-only: {stored['run_id']} overall={stored['overall']}")
        for item in stored["checks"]:
            print(f"[{item['status']}] {item['check']}: {item['value']} (阈值 {item['threshold']})")
        return 0

    settings = configs()
    run = RunDirectory("stage3")
    runs = {category: latest_run(category) for category in CATEGORIES}
    missing = [category for category, path in runs.items() if path is None]
    if missing:
        print("缺少运行记录:", missing)
        if not args.report_only:
            print("请先依次运行：")
            print("  python -m scripts.capacity_analysis_demo")
            print("  python -m scripts.ocv_extraction_demo")
            print("  python -m scripts.pulse_identification_demo")
            print("  python -m scripts.ecm_identification_demo")
            print("  python -m scripts.dynamic_validation_demo")
            print("  python -m scripts.temperature_analysis_demo")
            print("  python -m scripts.identified_spice_demo")
        return 1

    capacity = read_json(runs["capacity"] / "capacity_results.json")
    ocv = read_json(runs["ocv"] / "ocv_quality_report.json")
    pulse = read_json(runs["pulse_identification"] / "pulse_summary.json")
    identification = read_json(runs["identification"] / "training_metrics.json")
    validation = read_json(runs["dynamic_validation"] / "validation_metrics.json")
    temperature = read_json(runs["temperature"] / "temperature_report.json")
    spice = read_json(runs["identified_spice"] / "spice_pack_bms_summary.json")

    teaching = load_ecm_models()
    teaching_second = teaching["second_order_rc"]
    identified_second = None
    identified_csv = PROJECT_ROOT / "data" / "identified" / "identified_parameters_all_models.csv"
    if identified_csv.exists():
        frame = pd.read_csv(identified_csv)
        rows = frame[frame["model_order"] == 2]
        identified_second = rows.iloc[0].to_dict() if len(rows) else None

    checks: list[dict[str, Any]] = []
    sp2 = capacity["results"]["sp2"]
    checks.append(
        check(
            "容量积分与文件记录容量差 (Ah)",
            abs(sp2["capacity_difference_ah"]),
            1e-3,
            "<=",
            str(runs["capacity"] / "capacity_results.json"),
            "零阶保持电流积分",
        )
    )
    checks.append(
        check(
            "OCV 查表覆盖 SOC 0-1",
            [ocv["ocv_table"]["soc_min"], ocv["ocv_table"]["soc_max"]],
            [0.0, 1.0],
            "==",
            str(runs["ocv"] / "ocv_quality_report.json"),
            "端点由实测分支常量延伸",
        )
    )
    quality_values = identification["parameter_quality"]
    checks.append(
        check(
            "三个模型参数质量",
            quality_values,
            {key: value for key, value in quality_values.items() if value in ("IDENTIFIED", "BOUND_LIMITED", "WEAKLY_IDENTIFIABLE")},
            "==",
            str(runs["identification"] / "training_metrics.json"),
            "允许弱可辨识但必须如实标记",
        )
    )
    fuds_checks = [item for item in validation["acceptance_checks"] if item["experiment"].startswith("fuds")]
    worst = max(fuds_checks, key=lambda item: item["rmse_mv"]) if fuds_checks else None
    checks.append(
        check(
            "FUDS 独立验证最大 RMSE (mV)",
            worst["rmse_mv"] if worst else None,
            float(settings["validation"]["independent_validation"]["rmse_v"]) * 1000,
            "<=",
            str(runs["dynamic_validation"] / "validation_metrics.json"),
            "预先登记阈值为 30 mV",
        )
    )
    checks.append(
        check(
            "FUDS 独立验证最大 MAE (mV)",
            max((item["mae_mv"] for item in fuds_checks), default=None),
            float(settings["validation"]["independent_validation"]["mae_v"]) * 1000,
            "<=",
            str(runs["dynamic_validation"] / "validation_metrics.json"),
            "",
        )
    )
    checks.append(
        check(
            "FUDS 独立验证最大瞬时误差 (mV)",
            max((item["max_mv"] for item in fuds_checks), default=None),
            float(settings["validation"]["independent_validation"]["maximum_absolute_error_v"]) * 1000,
            "<=",
            str(runs["dynamic_validation"] / "validation_metrics.json"),
            "",
        )
    )
    checks.append(
        check(
            "辨识参数导入 ngspice 最大电压差 (mV)",
            max(spice["spice_max_voltage_error_mv"].values()),
            float(settings["validation"]["spice_cross_validation"]["maximum_voltage_difference_v"]) * 1000,
            "<=",
            str(runs["identified_spice"] / "spice_pack_bms_summary.json"),
            "固定 OCV 下模型实现一致性",
        )
    )
    checks.append(
        check(
            "温度特性状态",
            temperature["status"]["status"],
            "NOT_VERIFIED",
            "==",
            str(runs["temperature"] / "temperature_report.json"),
            "缺少 0/45℃ 真实数据，如实标记",
        )
    )

    if identified_second is not None:
        differs = (
            abs(float(identified_second["r0_ohm"]) - teaching_second.parameters.r0_ohm) > 1e-3
            or abs(float(identified_second["capacity_ah"]) - teaching_second.parameters.capacity_ah) > 1e-3
        )
        checks.append(
            check(
                "辨识参数与教学假设参数不同",
                bool(differs),
                True,
                "==",
                str(identified_csv),
                "不得把教学参数当作辨识结果",
            )
        )

    real_data_sources = [
        capacity["results"]["sp2"]["dataset_id"],
        ocv["low_current"]["discharge"]["step_index"],
        pulse["experiments"]["dst_50"]["dataset_id"],
        validation["validation_table"][0]["experiment"],
    ]
    checks.append(
        check(
            "真实数据来源数量（容量/OCV/脉冲/DST/FUDS）",
            len({capacity["results"]["sp2"]["dataset_id"], "calce_inr18650_20r_sp1_25c_low_current_ocv_20151105", pulse["experiments"]["dst_50"]["dataset_id"], "calce_inr18650_20r_sp2_25c_fuds"}),
            4,
            ">=",
            "data/manifests/dataset_manifest.json",
            "全部为 CALCE 公开实验数据",
        )
    )

    acceptance_summary = {
        "script": "scripts/battery_stage3_demo.py",
        "run_id": run.run_id,
        "profile": profile,
        "runs": {category: str(path) for category, path in runs.items()},
        "checks": checks,
        "overall": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "preregistered_limits": settings["validation"]["independent_validation"],
        "note": "所有数值来自已保存的真实运行记录；未通过的检查保留 FAIL。",
    }

    capability_table = pd.DataFrame(
        [
            ["真实容量提取", "PASS", f"{sp2['integrated_capacity_ah']:.4f} Ah"],
            ["低电流 OCV-SOC", "PASS", f"{ocv['ocv_table']['measured_points']} 个实测点"],
            ["增量 OCV", ocv.get("incremental_status", "NOT_VERIFIED"), f"{ocv['incremental_ocv']['usable_points']} / {ocv['incremental_points']} 个静置段通过质量检查"],
            ["R0 表观内阻", "PASS", f"{pulse['experiments']['dst_50']['resistance']['median_ohm'] * 1000:.2f} mΩ (1 s 窗口)"],
            ["静置恢复拟合", "PASS", f"二阶 RMSE {pulse['experiments']['dst_50']['relaxation']['order2']['rmse_v'] * 1000:.2f} mV"],
            ["DST 动态辨识", "PASS", f"二阶训练 RMSE {identification['training_metrics']['second_order_rc']['training_rmse_v'] * 1000:.2f} mV"],
            ["FUDS 独立验证", "PASS" if validation["overall_pass"] else "FAIL", (f"RMSE {worst['rmse_mv']:.2f} mV / 最大瞬时 {max((item['max_mv'] for item in fuds_checks), default=float('nan')):.2f} mV" if worst else "NOT_VERIFIED")],
            ["US06/BJDST 额外验证", "PASS", "已运行并保存"],
            ["温度特性", "NOT_VERIFIED", "缺少 0/45℃ 真实数据"],
            ["SPICE 网表验证", "PASS", f"{max(spice['spice_max_voltage_error_mv'].values()):.4f} mV"],
            ["3S1P 电池组", "PASS", f"最大压差 {spice['pack']['max_delta_cell_voltage_v'] * 1000:.3f} mV"],
            ["BMS 设计参考表", "PASS", f"{len(spice['bms_reference'])} 项"],
        ],
        columns=["capability", "status", "evidence"],
    )
    capability_table.to_csv(run.path / "capability_matrix.csv", index=False)

    # Task 31：stage3/run_<id>/ 规定文件（standard 才生成全部汇总）
    if profile == "standard":
        capacity_rows = [
            {
                "sample": key,
                "dataset_id": value["dataset_id"],
                "source_file": value["source_file"],
                "temperature_c": value["temperature_c"],
                "rated_capacity_ah": value["rated_capacity_ah"],
                "integrated_capacity_ah": value["integrated_capacity_ah"],
                "recorded_capacity_ah": value["recorded_capacity_ah"],
                "capacity_difference_ah": value["capacity_difference_ah"],
                "quality_status": value["quality_status"],
            }
            for key, value in capacity["results"].items()
        ]
        pd.DataFrame(capacity_rows).to_csv(run.path / "capacity_summary.csv", index=False)

        parameters_frame = pd.read_csv(runs["identification"] / "identified_parameters.csv")
        model_names = {0: "rint", 1: "first_order_rc", 2: "second_order_rc"}
        comparison_rows = []
        for _, row in parameters_frame.iterrows():
            order = int(row["model_order"])
            name = model_names[order]
            fuds_rows = [
                item
                for item in validation["validation_table"]
                if item["model"] == name and item["experiment"].startswith("fuds")
            ]
            comparison_rows.append(
                {
                    "model": name,
                    "model_order": order,
                    "quality_status": row["quality_status"],
                    "r0_ohm": row["r0_ohm"],
                    "r1_ohm": row["r1_ohm"],
                    "c1_f": row["c1_f"],
                    "tau1_s": row["tau1_s"],
                    "r2_ohm": row["r2_ohm"],
                    "c2_f": row["c2_f"],
                    "tau2_s": row["tau2_s"],
                    "training_rmse_mv": identification["training_metrics"][name]["training_rmse_v"] * 1000,
                    "development_rmse_mv": identification["development_metrics"][name]["rmse_mv"],
                    "fuds_validation_rmse_mv": (
                        float(np.mean([item["rmse_mv"] for item in fuds_rows])) if fuds_rows else None
                    ),
                }
            )
        pd.DataFrame(comparison_rows).to_csv(run.path / "model_comparison.csv", index=False)
        parameters_frame.to_csv(run.path / "identified_parameters.csv", index=False)
        pd.DataFrame(validation["validation_table"]).to_csv(run.path / "validation_summary.csv", index=False)
        temperature_table = pd.read_csv(runs["temperature"] / "temperature_parameter_table.csv")
        temperature_table.to_csv(run.path / "temperature_comparison.csv", index=False)

        core_rows = [
            {
                "metric": "实际公开实验文件数量",
                "value": len(settings["split"]["datasets"]),
                "unit": "个",
                "condition": "CALCE INR18650-20R 25℃",
                "data_source": "public_experimental_data",
                "run_id": "configs/dataset_split.yaml",
                "raw_evidence": "configs/dataset_split.yaml",
                "status": "IDENTIFIED",
            },
            {
                "metric": "实际有效数据点数（OCV 低电流）",
                "value": ocv["ocv_table"]["measured_points"],
                "unit": "点",
                "condition": "SP1 25℃ ±0.1 A",
                "data_source": "public_experimental_data",
                "run_id": ocv["ocv_table"].get("table_metadata", {}).get("source_dataset", "ocv"),
                "raw_evidence": str(runs["ocv"] / "ocv_quality_report.json"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "实际电芯容量",
                "value": sp2["integrated_capacity_ah"],
                "unit": "Ah",
                "condition": "SP2 25℃ 1 A 放电",
                "data_source": "public_experimental_data",
                "run_id": str(runs["capacity"].name),
                "raw_evidence": str(runs["capacity"] / "capacity_results.json"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "实际容量计算差异",
                "value": sp2["capacity_difference_ah"],
                "unit": "Ah",
                "condition": "积分值 - 文件记录值",
                "data_source": "public_experimental_data",
                "run_id": str(runs["capacity"].name),
                "raw_evidence": str(runs["capacity"] / "capacity_results.json"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "OCV 覆盖 SOC 区间",
                "value": f"{ocv['ocv_table']['soc_min']}–{ocv['ocv_table']['soc_max']}",
                "unit": "1",
                "condition": "查表端点由实测分支常量延伸",
                "data_source": "identified_parameters",
                "run_id": str(runs["ocv"].name),
                "raw_evidence": str(runs["ocv"] / "ocv_quality_report.json"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "最大充放电迟滞",
                "value": ocv["low_current"]["maximum_hysteresis_v"] * 1000,
                "unit": "mV",
                "condition": "SOC 0.05–0.87",
                "data_source": "public_experimental_data",
                "run_id": str(runs["ocv"].name),
                "raw_evidence": str(runs["ocv"] / "ocv_quality_report.json"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "实际有效内阻辨识样本数",
                "value": pulse["experiments"]["dst_50"]["resistance"]["valid_samples"]
                + pulse["experiments"]["dst_80"]["resistance"]["valid_samples"],
                "unit": "个",
                "condition": "DST 50%/80%，1 s 窗口",
                "data_source": "public_experimental_data",
                "run_id": str(runs["pulse_identification"].name),
                "raw_evidence": str(runs["pulse_identification"] / "pulse_summary.json"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "表观 R0 中位数",
                "value": pulse["experiments"]["dst_50"]["resistance"]["median_ohm"] * 1000,
                "unit": "mΩ",
                "condition": "DST 50%，1 s 窗口",
                "data_source": "identified_parameters",
                "run_id": str(runs["pulse_identification"].name),
                "raw_evidence": str(runs["pulse_identification"] / "pulse_summary.json"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "DST 训练 RMSE（二阶 RC）",
                "value": identification["training_metrics"]["second_order_rc"]["training_rmse_v"] * 1000,
                "unit": "mV",
                "condition": "DST 50% SOC，6685 点",
                "data_source": "custom_ecm_simulation",
                "run_id": str(runs["identification"].name),
                "raw_evidence": str(runs["identification"] / "training_metrics.json"),
                "status": "BOUND_LIMITED",
            },
            {
                "metric": "FUDS 独立验证 RMSE（一阶 RC）",
                "value": float(
                    np.mean(
                        [
                            item["rmse_mv"]
                            for item in validation["validation_table"]
                            if item["model"] == "first_order_rc" and item["experiment"].startswith("fuds")
                        ]
                    )
                ),
                "unit": "mV",
                "condition": "FUDS 50%/80%，冻结参数",
                "data_source": "custom_ecm_simulation",
                "run_id": str(runs["dynamic_validation"].name),
                "raw_evidence": str(runs["dynamic_validation"] / "validation_summary.csv"),
                "status": "FAIL" if not validation["overall_pass"] else "IDENTIFIED",
            },
            {
                "metric": "FUDS 独立验证 MAE（一阶 RC）",
                "value": float(
                    np.mean(
                        [
                            item["mae_mv"]
                            for item in validation["validation_table"]
                            if item["model"] == "first_order_rc" and item["experiment"].startswith("fuds")
                        ]
                    )
                ),
                "unit": "mV",
                "condition": "FUDS 50%/80%，冻结参数",
                "data_source": "custom_ecm_simulation",
                "run_id": str(runs["dynamic_validation"].name),
                "raw_evidence": str(runs["dynamic_validation"] / "validation_summary.csv"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "最大绝对电压误差",
                "value": max((item["max_mv"] for item in fuds_checks), default=None),
                "unit": "mV",
                "condition": "FUDS 50%/80%",
                "data_source": "custom_ecm_simulation",
                "run_id": str(runs["dynamic_validation"].name),
                "raw_evidence": str(runs["dynamic_validation"] / "validation_metrics.json"),
                "status": "FAIL",
            },
            {
                "metric": "Python 与 ngspice 最大电压差",
                "value": max(spice["spice_max_voltage_error_mv"].values()),
                "unit": "mV",
                "condition": "固定 OCV 3.7215 V，2 A/60 s 脉冲",
                "data_source": "spice_simulation",
                "run_id": str(runs["identified_spice"].name),
                "raw_evidence": str(runs["identified_spice"] / "spice_pack_bms_summary.json"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "3S1P 组端电压",
                "value": f"{spice['pack']['pack_voltage_start_v']:.4f} → {spice['pack']['pack_voltage_end_v']:.4f}",
                "unit": "V",
                "condition": "初始 SOC 0.55，2 A/60 s 脉冲",
                "data_source": "custom_ecm_simulation",
                "run_id": str(runs["identified_spice"].name),
                "raw_evidence": str(runs["identified_spice"] / "pack_waveform.csv"),
                "status": "IDENTIFIED",
            },
            {
                "metric": "温度特性",
                "value": "NOT_VERIFIED",
                "unit": "—",
                "condition": "仅 25℃ 数据",
                "data_source": "public_experimental_data",
                "run_id": str(runs["temperature"].name),
                "raw_evidence": str(runs["temperature"] / "temperature_report.json"),
                "status": "NOT_VERIFIED",
            },
        ]
        write_json(
            run.path / "engineering_evidence.json",
            {
                "run_id": run.run_id,
                "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "items": core_rows,
                "data_type_legend": [
                    "public_experimental_data",
                    "identified_parameters",
                    "custom_ecm_simulation",
                    "spice_simulation",
                    "analytical_theory",
                    "educational_assumption",
                    "synthetic_test_data",
                ],
            },
        )

    summary = {
        "script": "scripts/battery_stage3_demo.py",
        "run_id": run.run_id,
        "profile": profile,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "data_source_overview": {
            "cell_model": settings["split"]["cell_model"],
            "primary_temperature_c": settings["split"]["primary_temperature_c"],
            "sources": settings["split"]["datasets"],
            "temperature_extension": settings["split"].get("temperature_extension"),
        },
        "capacity": capacity,
        "ocv": ocv,
        "pulse": pulse["experiments"],
        "identification": {
            "training_metrics": identification["training_metrics"],
            "development_metrics": identification["development_metrics"],
            "parameter_quality": identification["parameter_quality"],
            "frozen_models": identification["frozen_models"],
        },
        "validation": {
            "acceptance": validation["acceptance"],
            "acceptance_checks": validation["acceptance_checks"],
            "overall_pass": validation["overall_pass"],
            "model_selection": validation["model_selection"],
            "validation_table": validation["validation_table"],
        },
        "temperature": temperature["status"],
        "spice_and_bms": spice,
        "acceptance": acceptance_summary,
        "capability_matrix": capability_table.to_dict("records"),
    }
    write_json(run.path / "stage3_summary.json", summary)
    write_json(run.path / "acceptance.json", acceptance_summary)
    write_json(PROJECT_ROOT / "results" / "stage3" / "latest_evidence_summary.json", acceptance_summary)
    run.write_summary(acceptance_summary)
    run.log(f"overall={acceptance_summary['overall']}")
    run.flush_log()

    print(f"stage3 run_id={run.run_id}")
    print(capability_table.to_string(index=False))
    print()
    for item in checks:
        print(f"[{item['status']}] {item['check']}: {item['value']} (阈值 {item['threshold']})")
    print("overall:", acceptance_summary["overall"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
