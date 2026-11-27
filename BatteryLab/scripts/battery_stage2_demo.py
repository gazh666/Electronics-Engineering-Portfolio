"""第二阶段综合验收入口：复用已有运行证据，不重复完全相同的实验。

运行：conda run -n kaifa_battery python -m scripts.battery_stage2_demo
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from analysis.energy_balance import energy_balance
from battery_models.parameters import load_ecm_models, load_yaml
from storage.result_store import RunDirectory, utc_now, write_csv, write_json

SCRIPTS = {
    "pulse": "scripts/battery_pulse_demo.py",
    "first_order": "scripts/first_order_rc_demo.py",
    "second_order": "scripts/second_order_rc_demo.py",
    "pack": "scripts/battery_pack_demo.py",
    "inconsistency": "scripts/pack_inconsistency_demo.py",
    "spice": "scripts/spice_battery_demo.py",
    "comparison": "scripts/model_comparison_demo.py",
}


def latest_run(script: str) -> dict | None:
    candidates = []
    for metadata_path in (PROJECT_ROOT / "results").glob("*/run_*/metadata.json"):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("script") == script:
            candidates.append((metadata_path.stat().st_mtime, metadata_path.parent, payload))
    if not candidates:
        return None
    _, path, payload = max(candidates, key=lambda item: item[0])
    return {"path": path, "metadata": payload}


def main() -> int:
    acceptance = load_yaml(PROJECT_ROOT / "configs" / "stage2_cases.yaml")["acceptance"]
    models = load_ecm_models()
    available = {key: latest_run(script) for key, script in SCRIPTS.items()}
    missing = [key for key, value in available.items() if value is None]
    if missing:
        raise RuntimeError(f"以下演示尚未运行，请先执行对应脚本: {missing}")

    run = RunDirectory("stage2")
    validation: dict = {
        "script": "scripts/battery_stage2_demo.py",
        "run_id": run.run_id,
        "generated_at": utc_now(),
        "acceptance_targets": acceptance,
        "evidence_runs": {key: str(value["path"]) for key, value in available.items()},
        "checks": [],
        "notes": [
            "所有数值来自实际保存的波形或真实 ngspice/PyBaMM 运行记录。",
            "CALCE 重放为未辨识参数基线，不得宣称为标定后精度。",
        ],
    }

    def add_check(name: str, value, threshold, comparator: str, status: str, source: str) -> None:
        validation["checks"].append(
            {
                "check": name,
                "value": value,
                "threshold": threshold,
                "comparator": comparator,
                "status": status,
                "source": source,
            }
        )

    pulse_summary = json.loads((available["pulse"]["path"] / "summary.json").read_text(encoding="utf-8"))
    max_rc_error = max(
        pulse_summary["theory_errors"][name]["max_abs_error_v"] for name in ("first_order_rc", "second_order_rc")
    )
    add_check(
        "RC 解析公式最大端电压误差 (V)",
        max_rc_error,
        acceptance["rint_absolute_error_v"],
        "<=",
        "PASS" if max_rc_error <= acceptance["rint_absolute_error_v"] else "FAIL",
        str(available["pulse"]["path"] / "summary.json"),
    )
    rint_error = pulse_summary["theory_errors"]["rint"]["max_abs_error_v"]
    add_check(
        "Rint 解析公式最大端电压误差 (V)",
        rint_error,
        acceptance["rint_absolute_error_v"],
        "<=",
        "PASS" if rint_error <= acceptance["rint_absolute_error_v"] else "FAIL",
        str(available["pulse"]["path"] / "summary.json"),
    )

    pulse_frame = pd.read_csv(PROJECT_ROOT / "results/ecm" / f"run_{pulse_summary['runs']['second_order_rc']}" / "waveform.csv")
    soc_at_release = float(pulse_frame.loc[pulse_frame["time_s"] == 70.0, "soc"].iloc[0])
    expected_soc = 0.6 - 2.0 * 60.0 / 3600.0 / 2.0
    soc_error = abs(soc_at_release - expected_soc)
    add_check(
        "60s 脉冲 SOC 误差",
        soc_error,
        acceptance["soc_absolute_error"],
        "<=",
        "PASS" if soc_error <= acceptance["soc_absolute_error"] else "FAIL",
        str(PROJECT_ROOT / "results/ecm" / f"run_{pulse_summary['runs']['second_order_rc']}" / "waveform.csv"),
    )

    energy_rows = []
    for key, name in (("first_order", "first_order_rc"), ("second_order", "second_order_rc")):
        summary = json.loads((available[key]["path"] / "summary.json").read_text(encoding="utf-8"))
        waveform_path = PROJECT_ROOT / "results/ecm" / f"run_{summary['run_id']}" / "waveform.csv"
        frame = pd.read_csv(waveform_path)
        definition = models[name]
        balance = energy_balance(frame, definition.parameters, definition.branches, start_s=10.0, end_s=70.0)
        energy_rows.append(
            [
                name,
                balance["source_energy_j"],
                balance["terminal_energy_j"],
                balance["ohmic_energy_j"],
                balance["polarization_energy_j"],
                balance["stored_energy_change_j"],
                balance["residual_j"],
                balance["relative_residual"],
                balance["status"],
                str(waveform_path),
            ]
        )
        add_check(
            f"{name} 能量平衡相对残差",
            abs(balance["relative_residual"]),
            acceptance["energy_balance_relative_residual"],
            "<=",
            "PASS" if balance["status"] in ("PASS_RELATIVE", "PASS_ABSOLUTE") else "FAIL",
            str(waveform_path),
        )
    write_csv(
        run.path / "energy_balance_summary.csv",
        [
            "model",
            "source_energy_j",
            "terminal_energy_j",
            "ohmic_energy_j",
            "polarization_energy_j",
            "stored_energy_change_j",
            "residual_j",
            "relative_residual",
            "status",
            "waveform_path",
        ],
        energy_rows,
    )

    pack_summary = json.loads((available["pack"]["path"] / "summary.json").read_text(encoding="utf-8"))
    consistency = pack_summary["consistency"]
    write_csv(
        run.path / "pack_consistency.csv",
        ["metric", "value"],
        [[key, value] for key, value in consistency.items() if not isinstance(value, dict)],
    )
    add_check(
        "3S 电池组电压求和误差 (V)",
        consistency["max_voltage_sum_error_v"],
        acceptance["series_voltage_absolute_error_v"],
        "<=",
        "PASS" if consistency["max_voltage_sum_error_v"] <= acceptance["series_voltage_absolute_error_v"] else "FAIL",
        str(available["pack"]["path"] / "summary.json"),
    )
    add_check(
        "3S 一致电芯最大压差 (V)",
        consistency["max_delta_cell_voltage_v"],
        0.0,
        "==",
        "PASS" if consistency["max_delta_cell_voltage_v"] <= 1e-9 else "FAIL",
        str(available["pack"]["path"] / "summary.json"),
    )

    pulse_metrics_rows = []
    for name, metrics in pulse_summary["pulse_metrics"].items():
        pulse_metrics_rows.append(
            [
                name,
                metrics["pre_step_voltage_v"],
                metrics["instantaneous_voltage_after_step_v"],
                metrics["instantaneous_drop_v"],
                metrics["end_of_pulse_voltage_v"],
                metrics["recovery_jump_v"],
                metrics["r0_estimate_ohm"],
                metrics["recovery_time_s"],
                metrics["recovery_status"],
            ]
        )
    write_csv(
        run.path / "pulse_response_metrics.csv",
        [
            "model",
            "pre_step_voltage_v",
            "voltage_after_step_v",
            "instantaneous_drop_v",
            "end_of_pulse_voltage_v",
            "recovery_jump_v",
            "r0_estimate_ohm",
            "recovery_time_s",
            "recovery_status",
        ],
        pulse_metrics_rows,
    )

    spice_summary = json.loads((available["spice"]["path"] / "summary.json").read_text(encoding="utf-8"))
    spice_errors = {name: spice_summary["single_cell"][name]["comparison"]["max_abs_error_v"] for name in spice_summary["single_cell"]}
    spice_errors["pack"] = spice_summary["pack"]["comparison"]["max_abs_error_v"]
    worst_spice = max(spice_errors.values())
    add_check(
        "Python 与 ngspice 最大电压误差 (V)",
        worst_spice,
        acceptance["python_spice_max_voltage_error_v"],
        "<=",
        "PASS" if worst_spice <= acceptance["python_spice_max_voltage_error_v"] else "FAIL",
        str(available["spice"]["path"] / "summary.json"),
    )

    comparison_summary = json.loads((available["comparison"]["path"] / "summary.json").read_text(encoding="utf-8"))
    pybamm_error = comparison_summary["pybamm"]["comparison"]["max_abs_error_v"]
    add_check(
        "PyBaMM Thevenin 与自研 ECM 最大电压差 (V)",
        pybamm_error,
        2e-3,
        "<=",
        "PASS" if pybamm_error <= 2e-3 else "FAIL",
        str(available["comparison"]["path"] / "summary.json"),
    )
    case_energy_ok = all(
        case["models"][model]["energy_balance_status"] in ("PASS_RELATIVE", "PASS_ABSOLUTE")
        for case in comparison_summary["cases"].values()
        for model in case["models"]
    )
    add_check(
        "6 个动态工况 × 3 模型能量平衡",
        "all_pass" if case_energy_ok else "some_fail",
        "all_pass",
        "==",
        "PASS" if case_energy_ok else "FAIL",
        str(available["comparison"]["path"] / "summary.json"),
    )

    write_json(run.path / "model_comparison.csv.json", comparison_summary["cases"])
    pd.DataFrame(
        [
            [case_id, name, values["end_voltage_v"], values["soc_end"], values["terminal_energy_j"], values["energy_balance_status"]]
            for case_id, case in comparison_summary["cases"].items()
            for name, values in case["models"].items()
        ],
        columns=["case_id", "model", "end_voltage_v", "soc_end", "terminal_energy_j", "energy_balance_status"],
    ).to_csv(run.path / "model_comparison.csv", index=False, float_format="%.12g", encoding="utf-8")

    validation["pack_benchmark"] = {
        "pack_voltage_open_circuit_v": pack_summary["pack_voltage_open_circuit_v"],
        "pack_voltage_at_step_v": pack_summary["pack_voltage_at_step_v"],
        "pack_voltage_before_release_v": pack_summary["pack_voltage_before_release_v"],
    }
    validation["spice_max_voltage_error_v"] = spice_errors
    validation["pybamm_max_voltage_error_v"] = pybamm_error
    validation["calce_status"] = comparison_summary["calce"].get("status", "NOT_VERIFIED")
    validation["overall"] = "PASS" if all(check["status"] == "PASS" for check in validation["checks"]) else "FAIL"
    write_json(run.path / "validation_summary.json", validation)

    portfolio_dir = PROJECT_ROOT / "portfolio"
    portfolio_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# BatteryLab 第二阶段工程证据",
        "",
        f"- 生成时间：{validation['generated_at']}",
        f"- 综合运行编号：{run.run_id}",
        f"- 总体验收：**{validation['overall']}**",
        "",
        "## 验收检查",
        "",
        "| 检查项 | 数值 | 阈值 | 结论 | 证据 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in validation["checks"]:
        value = check["value"]
        value_text = f"{value:.6g}" if isinstance(value, (int, float)) else str(value)
        lines.append(
            f"| {check['check']} | {value_text} | {check['comparator']} {check['threshold']} | {check['status']} | `{check['source']}` |"
        )
    lines.extend(
        [
            "",
            "## 基准数值（3S1P，一致电芯）",
            "",
            f"- 开路：{validation['pack_benchmark']['pack_voltage_open_circuit_v']:.6f} V",
            f"- 2A 接入后：{validation['pack_benchmark']['pack_voltage_at_step_v']:.6f} V",
            f"- 60s 放电结束：{validation['pack_benchmark']['pack_voltage_before_release_v']:.6f} V",
            "",
            "## 数据来源说明",
            "",
            "- 所有单体/电池组波形来自 `custom_ecm_simulation`，不是真实硬件测量。",
            "- ngspice 结果为真实 SPICE 瞬态求解；PyBaMM 结果来自官方 Thevenin 模型交叉验证。",
            "- CALCE 重放使用教学参数与教学初始 SOC，状态为 `UNCALIBRATED_BASELINE`。",
            "",
            "## 主要运行目录",
            "",
        ]
    )
    for key, value in available.items():
        lines.append(f"- {key}: `{value['path']}`")
    (portfolio_dir / "stage2_engineering_evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    run.write_metadata({"script": "scripts/battery_stage2_demo.py", "case": "stage2_acceptance", "summary": validation})
    run.log(f"综合验收完成: {validation['overall']}")
    run.flush_log()
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
