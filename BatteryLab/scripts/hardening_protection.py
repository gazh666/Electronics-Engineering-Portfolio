"""Task 5：MOSFET 保护真实性复验入口。

运行：
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.hardening_protection
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hardening.common import new_run, write_csv, write_json  # noqa: E402
from hardening.protection_physical_validation import (  # noqa: E402
    MosfetProtectionSpec,
    analyze_ocp,
    build_conduction_circuit,  # noqa: F401
    run_conduction,
    run_integrated_transient,
    run_ocp_transient,
)

HISTORICAL_RUN = PROJECT_ROOT / "results" / "stage9" / "system_protection" / "protection_20261126_173438_1e53b2"


def artifact_analysis(run: Path) -> dict:
    historical = {}
    case_path = HISTORICAL_RUN / "case_result.json"
    if case_path.is_file():
        payload = json.loads(case_path.read_text(encoding="utf-8"))
        historical = {
            "timing": payload.get("spice_protection_timing"),
            "suppression_ratio": payload.get("suppression_ratio"),
            "status": payload.get("status"),
        }
    source_line = None
    source_path = PROJECT_ROOT / "circuits" / "system_spice_netlist.py"
    for number, line in enumerate(source_path.read_text(encoding="utf-8").splitlines(), start=1):
        if "BPROT" in line and "current_expression" in line:
            source_line = {"file": str(source_path), "line": number, "code": line.strip()}
    text = [
        "# 历史保护伪迹分析（2.5 ns 电流抑制无效）",
        "",
        "## 1. 原始证据",
        "",
        f"- 历史运行：`{HISTORICAL_RUN}`",
        f"- 历史状态：`{historical.get('status')}`",
        "",
        "```json",
        json.dumps(historical.get("timing"), ensure_ascii=False, indent=2),
        "```",
        "",
        "## 2. 伪迹根因",
        "",
        "历史网表用行为电流源 `BPROT` 直接按 `V(prot_ctrl)` 改写电池到 Buck 之间的等效电阻：",
        "",
        "```python",
        (source_line or {}).get("code", "未找到"),
        "```",
        "",
        "- 该支路电流是电压的代数函数，不含任何栅极电荷、栅源电容或驱动能力；",
        "- 因此控制电压一变化，电流立即被改写，与真实 MOSFET 的关断过程无关；",
        "- 历史记录中 `battery_current_suppressed_time_s = 12.0000025 ms`，早于",
        "  `fet_command_off_time_s = 12.010 ms` 约 9.9975 µs，即电流在栅极指令之前就被“抑制”，",
        "  物理上不成立；",
        "- 该 2.5 ns 结果永久保留为无效伪迹，不进入简历与工程指标。",
        "",
        "## 3. 本次替代方案",
        "",
        "- 背靠背 N 沟道 MOSFET（共源）+ 显式体二极管 + 栅极串联电阻与栅源/栅漏电容；",
        "- 过流检测：真实 0 V 电流探针 → 二极管-电容峰值保持（故障锁存）→ 回差开关",
        "  → RC 确认延时 → 栅极驱动；",
        "- 故障注入：改变负载电阻使真实电池电流上升，不再直接钳位电流；",
        "- 报告的电流抑制时间按波形采样间隔给出，不超出分辨率。",
        "",
        "## 4. 局限",
        "",
        "- MOSFET 为教学 Level-1 模型，不是商业器件官方 SPICE 模型；",
        "- 未做实物验证，所有结论限于软件仿真；",
        "- 短路等故障仅限软件仿真，不做真实锂电池实验。",
    ]
    (run / "original_artifact_analysis.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return {"historical": historical, "source": source_line}


def _write_waveform(path: Path, waveform: dict) -> None:
    import csv
    import gzip

    columns = {
        "time_s": waveform["time_s"],
        "battery_current_a": waveform["battery_current_a"],
        "battery_voltage_v": waveform["battery_voltage_v"],
        "converter_input_voltage_v": waveform["converter_input_voltage_v"],
        "output_voltage_v": waveform["output_voltage_v"],
        "gate_source_v": waveform["gate_source_v"],
        "drive_voltage_v": waveform["drive_voltage_v"],
        "hold_v": waveform["hold_v"],
    }
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        names = list(columns)
        writer.writerow(names)
        for index in range(len(columns["time_s"])):
            writer.writerow([f"{float(columns[name][index]):.9g}" for name in names])


def main() -> int:
    run = new_run("protection")
    spec = MosfetProtectionSpec()
    artifact = artifact_analysis(run)

    conduction = run_conduction(spec)
    write_csv(run / "conduction_results.csv", conduction)

    convergence_rows = []
    analyses = {}
    finest_waveform = None
    for step in (1.0e-7, 5.0e-8, 2.0e-8):
        waveform = run_ocp_transient(spec, fault_time_s=2.0e-4, end_time_s=4.0e-4, step_s=step)
        analysis = analyze_ocp(waveform, spec, hold_time_s=5e-6, maximum_sample_gap_s=2e-6)
        analyses[f"{step:.0e}"] = analysis
        convergence_rows.append({
            "step_s": step,
            "trip_current_a": analysis["trip_current_a"],
            "fault_to_command_s": analysis["fault_to_command_s"],
            "gate_fall_time_s": analysis["gate_fall_time_s"],
            "fault_to_suppression_s": analysis["delay_fault_to_suppression_s"],
            "command_to_suppression_s": analysis["delay_command_to_suppression_s"],
            "peak_vds_v": analysis["peak_vds_v"],
            "peak_current_a": analysis["peak_battery_current_a"],
            "turnoff_energy_j": analysis["turnoff_energy_j"],
            "residual_ratio": analysis["residual_ratio"],
            "resolution_limited": analysis["resolution_limited"],
        })
        if step == 2.0e-8:
            finest_waveform = waveform
            from hardening.protection_physical_validation import build_ocp_circuit

            ocp_circuit, _ = build_ocp_circuit(spec, fault_time_s=2.0e-4, end_time_s=4.0e-4)
            (run / "physical_protection.cir").write_text(str(ocp_circuit), encoding="utf-8")
    write_csv(run / "numerical_convergence.csv", convergence_rows)

    # 联合：电池 ECM + 保护 MOSFET + Buck + 负载阶跃
    from integration.battery_port_adapter import build_battery_port, cell_ecm_parameters

    port = build_battery_port(initial_soc=[0.4, 0.4, 0.4])
    cells = cell_ecm_parameters(port)
    integrated_wave = run_integrated_transient(
        spec, cells=cells, fault_time_s=4.0e-3, end_time_s=4.6e-3, step_s=5.0e-8
    )
    integrated = analyze_ocp(integrated_wave, spec, hold_time_s=5e-6, maximum_sample_gap_s=2e-6)
    time = integrated_wave["time_s"]
    vout = integrated_wave["output_voltage_v"]
    pre_mask = (time > 3.4e-3) & (time < 4.0e-3)
    pre_voltage = float(np.mean(vout[pre_mask]))
    gate_off = integrated["gate_off_time_s"] or 4.0e-3
    below = time[(time >= gate_off) & (vout < 4.5)]
    output_hold_time = float(below[0] - gate_off) if below.size else None
    post_mask = time >= 4.0e-3
    integrate = getattr(np, "trapezoid", None)
    if integrate is None:
        integrate = np.trapz
    post_energy = float(integrate(
        integrated_wave["battery_voltage_v"][post_mask] * np.abs(integrated_wave["battery_current_a"][post_mask]),
        time[post_mask],
    ))
    integrated.update({
        "pre_fault_output_voltage_v": pre_voltage,
        "pre_fault_output_ripple_vpp": float(np.max(vout[pre_mask]) - np.min(vout[pre_mask])),
        "output_hold_time_s": output_hold_time,
        "final_battery_current_a": float(np.mean(integrated_wave["battery_current_a"][-10:])),
        "energy_after_fault_j": post_energy,
    })
    _write_waveform(run / "waveform.csv.gz", integrated_wave)

    event_rows = []
    for label, analysis in (("ocp_standalone", analyses["2e-08"]), ("integrated", integrated)):
        event_rows.append({
            "case": label,
            "fault_time_s": 2.0e-4 if label == "ocp_standalone" else 4.0e-3,
            "trip_time_s": analysis["trip_time_s"],
            "trip_current_a": analysis["trip_current_a"],
            "command_time_s": analysis["command_time_s"],
            "gate_off_time_s": analysis["gate_off_time_s"],
            "suppression_time_s": analysis["suppression"]["suppression_time_s"],
            "fault_to_suppression_s": analysis["delay_fault_to_suppression_s"],
            "command_to_suppression_s": analysis["delay_command_to_suppression_s"],
            "residual_current_a": analysis["residual_current_a"],
            "resolution_limited": analysis["resolution_limited"],
        })
    write_csv(run / "event_sequence.csv", event_rows, [
        "case", "fault_time_s", "trip_time_s", "trip_current_a", "command_time_s", "gate_off_time_s",
        "suppression_time_s", "fault_to_suppression_s", "command_to_suppression_s",
        "residual_current_a", "resolution_limited",
    ])

    write_json(run / "mosfet_stress.json", {
        "standalone": {
            "peak_vds_v": analyses["2e-08"]["peak_vds_v"],
            "peak_current_a": analyses["2e-08"]["peak_battery_current_a"],
            "turnoff_energy_j": analyses["2e-08"]["turnoff_energy_j"],
        },
        "integrated": {
            "peak_vds_v": integrated["peak_vds_v"],
            "peak_current_a": integrated["peak_battery_current_a"],
            "turnoff_energy_j": integrated["turnoff_energy_j"],
            "pre_fault_output_voltage_v": integrated["pre_fault_output_voltage_v"],
            "pre_fault_output_ripple_vpp": integrated["pre_fault_output_ripple_vpp"],
            "output_hold_time_s": integrated["output_hold_time_s"],
        },
        "model": "Level-1 MOSFET + explicit body diode; 教学模型，不是商业器件实测。",
    })
    write_json(run / "switching_energy.json", {
        "standalone_turnoff_energy_j": analyses["2e-08"]["turnoff_energy_j"],
        "integrated_turnoff_energy_j": integrated["turnoff_energy_j"],
        "standalone_window_s": analyses["2e-08"]["turnoff_energy_window_s"],
        "integrated_window_s": integrated["turnoff_energy_window_s"],
    })

    summary = {
        "run_id": run.name,
        "artifact": artifact,
        "conduction": conduction,
        "numerical_convergence": convergence_rows,
        "standalone": analyses["2e-08"],
        "integrated": integrated,
        "status": "VERIFIED" if analyses["2e-08"]["suppression"]["status"] == "THRESHOLD_REACHED" else "NOT_VERIFIED",
        "verdict": {
            "artifact_rejected": True,
            "physical_current_path": True,
            "behavioral_current_clamp": False,
            "latest_step_used_s": 2.0e-8,
            "integrated_step_used_s": 5.0e-8,
            "note": "2.5 ns 历史结果为无效伪迹；本次结果为真实器件网表求解，受采样分辨率限制。",
        },
        "limitations": [
            "MOSFET 为教学 Level-1 模型，未使用商业器件官方 SPICE 模型。",
            "全部为软件仿真，未做实物验证。",
            "command→suppression 时间为采样分辨率下限，报告为上限估计。",
            "短路故障仅限软件仿真。",
        ],
    }
    write_json(run / "protection_summary.json", summary)
    print(json.dumps({
        "run_id": run.name,
        "status": summary["status"],
        "standalone_fault_to_suppression_s": summary["standalone"]["delay_fault_to_suppression_s"],
        "gate_fall_time_s": summary["standalone"]["gate_fall_time_s"],
        "integrated_fault_to_suppression_s": summary["integrated"]["delay_fault_to_suppression_s"],
        "conduction_on_resistance_ohm": next(row["path_resistance_ohm"] for row in conduction if row["mode"] == "on_discharge"),
        "blocking_leakage_a": next(row["abs_current_a"] for row in conduction if row["mode"] == "off_discharge_block"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
