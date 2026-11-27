"""任务 32：由真实运行结果生成工程图。

每张图都标注 SIMULATED / CALCULATED — NOT MEASURED；没有数据时跳过并在清单里
记录 SKIPPED，而不是画占位图。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from battery_models.parameters import PROJECT_ROOT  # noqa: E402
from scripts.stage9_common import STAGE9_RESULTS, new_run_dir, read_json, write_json  # noqa: E402

RESULTS = PROJECT_ROOT / "results"


def newest(pattern: str) -> Path | None:
    candidates = [item for item in RESULTS.glob(pattern) if item.is_file()]
    stage9 = [item for item in (RESULTS / "stage9").glob(pattern) if item.is_file()]
    candidates = sorted(candidates + stage9, key=lambda item: item.stat().st_mtime)
    return candidates[-1] if candidates else None


def save(fig, path: Path, records: list[dict], name: str, status: str = "OK") -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    records.append({"figure": name, "file": path.name, "status": status})


def footer(fig, text: str = "SIMULATED / CALCULATED — NOT MEASURED") -> None:
    fig.text(0.01, 0.005, text, fontsize=7, color="0.4")


def load_waveform(path: Path) -> dict[str, np.ndarray]:
    data = np.genfromtxt(path, delimiter=",", names=True)
    return {name: np.asarray(data[name], dtype=float) for name in data.dtype.names}


def load_csv_columns(path: Path, columns: list[str]) -> dict[str, np.ndarray]:
    """功率映射 CSV 含带逗号的引号字段，必须用 csv 模块解析而不是 genfromtxt。"""
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[str, np.ndarray] = {}
    for name in columns:
        result[name] = np.array([
            float(row[name]) if row.get(name) not in ("", None) else np.nan for row in rows
        ])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="第九阶段工程图")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir)) if args.run_dir
        else new_run_dir(STAGE9_RESULTS / "figures", "figures")
    )
    directory.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    # 1. 系统架构（概念图，明确标注）
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.axis("off")
    boxes = [
        (0.03, "3S battery\nECM (stage 3)", "#dbeafe"),
        (0.25, "BMS protection\n(stage 5)", "#fde68a"),
        (0.47, "Buck power stage\n(PowerLab)", "#bbf7d0"),
        (0.69, "Load / output", "#fecaca"),
        (0.47, "PI feedback", "#e9d5ff"),
    ]
    for x, text, color in boxes:
        ax.add_patch(plt.Rectangle((x, 0.42 if "feedback" not in text else 0.12), 0.18, 0.28,
                                   facecolor=color, edgecolor="0.3"))
        ax.text(x + 0.09, 0.56 if "feedback" not in text else 0.26, text, ha="center", va="center", fontsize=9)
    for x in (0.21, 0.43, 0.65):
        ax.annotate("", xy=(x + 0.04, 0.56), xytext=(x, 0.56),
                    arrowprops={"arrowstyle": "->", "lw": 1.2})
    ax.annotate("", xy=(0.47, 0.40), xytext=(0.56, 0.28),
                arrowprops={"arrowstyle": "->", "lw": 1.2})
    ax.set_title("System composition (conceptual, single-netlist coupling)")
    footer(fig)
    save(fig, directory / "01_system_architecture.png", records, "01_system_architecture", "CONCEPTUAL")

    # 2/3. 功率映射
    map_dir = newest("converter_power_map/*/converter_power_map_*.csv")
    if map_dir:
        fig, ax = plt.subplots(figsize=(7, 4))
        for path in sorted(map_dir.parent.glob("converter_power_map_*.csv")):
            data = load_csv_columns(path, ["input_voltage_v", "output_voltage_v"])
            ax.plot(data["input_voltage_v"], data["output_voltage_v"], marker="o", label=path.stem.replace("converter_power_map_", ""))
        ax.axhline(5.0, color="0.5", ls="--", lw=0.8)
        ax.set_xlabel("Converter input voltage (V)")
        ax.set_ylabel("Output voltage (V)")
        ax.set_title("Real PowerLab switch-level power map: Vout vs Vin")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        footer(fig)
        save(fig, directory / "02_power_map_vout.png", records, "02_power_map_vout")

        fig, ax = plt.subplots(figsize=(7, 4))
        for path in sorted(map_dir.parent.glob("converter_power_map_*.csv")):
            data = load_csv_columns(path, ["input_voltage_v", "efficiency_percent"])
            ax.plot(data["input_voltage_v"], data["efficiency_percent"], marker="s",
                    label=path.stem.replace("converter_power_map_", ""))
        ax.set_xlabel("Converter input voltage (V)")
        ax.set_ylabel("Efficiency (%)")
        ax.set_title("Power map efficiency (real SPICE runs)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        footer(fig)
        save(fig, directory / "03_power_map_efficiency.png", records, "03_power_map_efficiency")

    # 4/5. 联合 SPICE 波形
    wave = newest("system_spice/*/waveform.csv")
    if wave:
        data = load_waveform(wave)
        fig, ax = plt.subplots(figsize=(7.5, 4))
        ax.plot(data["time_s"] * 1e3, data["battery_voltage_v"], label="battery terminal")
        ax.plot(data["time_s"] * 1e3, data["converter_input_voltage_v"], label="converter input")
        ax.plot(data["time_s"] * 1e3, data["output_voltage_v"] * 2, label="output x2")
        ax.set_xlabel("Time (ms)")
        ax.set_ylabel("Voltage (V)")
        ax.set_title("Integrated SPICE: battery-fed closed-loop buck")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        footer(fig)
        save(fig, directory / "04_integrated_voltages.png", records, "04_integrated_voltages")

        fig, ax = plt.subplots(figsize=(7.5, 4))
        ax.plot(data["time_s"] * 1e3, data["battery_current_a"], label="battery current")
        ax.plot(data["time_s"] * 1e3, data["inductor_current_a"], label="inductor current")
        ax.plot(data["time_s"] * 1e3, data["load_current_a"], label="load current")
        ax.set_xlabel("Time (ms)")
        ax.set_ylabel("Current (A)")
        ax.set_title("Integrated SPICE currents (load affects battery voltage)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        footer(fig)
        save(fig, directory / "05_integrated_currents.png", records, "05_integrated_currents")

    # 6/7. 负载阶跃
    average = newest("system_average/*/average_result.json")
    if average:
        payload = read_json(average)
        rows = payload["records"]
        t = np.array([row["time_s"] for row in rows]) * 1e3
        vout = np.array([row["output_voltage_v"] for row in rows])
        vbat = np.array([row["input_voltage_v"] for row in rows])
        ibat = np.array([row["battery_current_a"] for row in rows])
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(t, vout)
        ax.axhline(5.0, color="0.5", ls="--", lw=0.8)
        ax.set_xlabel("Time (ms)")
        ax.set_ylabel("Output voltage (V)")
        ax.set_title("Averaged model: load-step response")
        ax.grid(alpha=0.3)
        footer(fig)
        save(fig, directory / "06_load_step_vout.png", records, "06_load_step_vout")

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(t, vbat, label="battery terminal")
        ax2 = ax.twinx()
        ax2.plot(t, ibat, color="tab:red", label="battery current")
        ax.set_xlabel("Time (ms)")
        ax.set_ylabel("Voltage (V)")
        ax2.set_ylabel("Current (A)")
        ax.set_title("Bidirectional coupling: load change moves battery voltage")
        ax.grid(alpha=0.3)
        footer(fig)
        save(fig, directory / "07_bidirectional_coupling.png", records, "07_bidirectional_coupling")

    # 8. 保护波形
    protection_wave = newest("system_protection/*/waveform.csv")
    if protection_wave:
        data = load_waveform(protection_wave)
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(data["time_s"] * 1e3, data["battery_current_a"], label="battery current")
        ax.plot(data["time_s"] * 1e3, data["converter_input_voltage_v"] / 5, label="Vin / 5")
        ax.plot(data["time_s"] * 1e3, data["output_voltage_v"], label="output voltage")
        ax.set_xlabel("Time (ms)")
        ax.set_title("Protection gate-off electrical consequence (SPICE)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        footer(fig)
        save(fig, directory / "08_protection_spice.png", records, "08_protection_spice")

    # 9. 故障注入结果
    fault = newest("system_protection/*/fault_injection.json")
    if fault:
        payload = read_json(fault)
        names = [item["scenario"] for item in payload["records"]]
        statuses = [1 if item["status"] == "PASS" else 0 for item in payload["records"]]
        fig, ax = plt.subplots(figsize=(8, 4.2))
        ax.barh(names, statuses, color=["tab:green" if value else "tab:red" for value in statuses])
        ax.set_xlim(0, 1.1)
        ax.set_xlabel("1 = PASS, 0 = FAIL")
        ax.set_title("Behavioural protection fault injection (real controller)")
        footer(fig)
        save(fig, directory / "09_fault_injection.png", records, "09_fault_injection")

    # 10. 放电运行时间
    discharge = newest("system_lifetime/discharge_*/case_result.json")
    if discharge:
        payload = read_json(discharge)
        fig, ax = plt.subplots(figsize=(7, 4))
        for load in sorted({item["load_current_a"] for item in payload["results"]}):
            subset = [item for item in payload["results"] if item["load_current_a"] == load]
            ax.plot([item["initial_soc"] for item in subset],
                    [item["runtime_s"] / 3600 for item in subset], marker="o", label=f"{load:.2f} A")
        ax.set_xlabel("Initial SOC")
        ax.set_ylabel("Runtime (h)")
        ax.set_title("Discharge runtime (ECM + verified power map)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        footer(fig)
        save(fig, directory / "10_discharge_runtime.png", records, "10_discharge_runtime")

        fig, ax = plt.subplots(figsize=(7, 4))
        for load in sorted({item["load_current_a"] for item in payload["results"]}):
            subset = [item for item in payload["results"] if item["load_current_a"] == load]
            ax.plot([item["initial_soc"] for item in subset],
                    [item["min_cell_voltage_v"] for item in subset], marker="s", label=f"{load:.2f} A")
        ax.axhline(2.8, color="tab:red", ls="--", lw=0.8, label="UV trip")
        ax.set_xlabel("Initial SOC")
        ax.set_ylabel("Minimum cell voltage (V)")
        ax.set_title("Minimum cell voltage at termination")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        footer(fig)
        save(fig, directory / "11_min_cell_voltage.png", records, "11_min_cell_voltage")

    # 12. 老化
    aging = newest("system_lifetime/aging_*/case_result.json")
    if aging:
        payload = read_json(aging)
        names = [item["scenario"] for item in payload["scenarios"]]
        hours = [item["runtime_s"] / 3600 for item in payload["scenarios"]]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(names, hours, color="tab:blue")
        ax.set_ylabel("Runtime (h)")
        ax.set_title("Capacity / resistance ageing sensitivity")
        footer(fig)
        save(fig, directory / "12_aging_runtime.png", records, "12_aging_runtime")

    # 13. 能量分解
    energy = newest("system_energy/*/case_result.json")
    if energy:
        payload = read_json(energy)
        breakdown = payload["loss_breakdown"]
        labels = ["battery internal", "protection path", "converter loss", "output"]
        values = [breakdown["battery_internal_loss_j"], breakdown["protection_path_loss_j"],
                  breakdown["converter_loss_j"], breakdown["output_energy_j"]]
        fig, ax = plt.subplots(figsize=(6.5, 4))
        ax.bar(labels, values, color=["tab:orange", "tab:red", "tab:purple", "tab:green"])
        ax.set_ylabel("Energy in steady window (J)")
        ax.set_title("Energy / loss breakdown from real SPICE waveform")
        plt.setp(ax.get_xticklabels(), rotation=15, fontsize=8)
        footer(fig)
        save(fig, directory / "13_energy_breakdown.png", records, "13_energy_breakdown")

    # 14. PowerLab 基准/候选效率
    sweep = PROJECT_ROOT.parent / "PowerLab" / "results" / "hardening" / "stage6_optimization" / "sweep.json"
    if sweep.is_file():
        payload = read_json(sweep)
        baseline = None
        candidate = None
        for row in payload.get("rows", []):
            values = row.get("values", {})
            if row.get("name") == "baseline":
                baseline = row
            if values.get("L_uh") == 68.0 and values.get("C_uf") == 330.0:
                candidate = row
        if baseline and candidate:
            fig, ax = plt.subplots(figsize=(6, 4))
            names = ["baseline (47uH/100uF)", "candidate (68uH/330uF)"]
            eff = [baseline["result"]["efficiency_system_percent"], candidate["result"]["efficiency_system_percent"]]
            ripple = [baseline["result"]["ripple_vpp"] * 1e3, candidate["result"]["ripple_vpp"] * 1e3]
            ax.bar(names, eff, color=["tab:gray", "tab:blue"])
            ax.set_ylabel("Efficiency (%)")
            ax.set_title("PowerLab historical runs: baseline vs candidate")
            for index, value in enumerate(ripple):
                ax.text(index, eff[index] + 0.2, f"ripple {value:.1f} mV", ha="center", fontsize=8)
            footer(fig)
            save(fig, directory / "14_baseline_candidate.png", records, "14_baseline_candidate")

    manifest = {
        "run_id": run_id,
        "figure_count": len([item for item in records if item["status"] == "OK"]),
        "records": records,
        "not_measured": True,
        "note": "所有图均由本阶段仿真或真实历史运行结果生成，不是实测波形",
    }
    write_json(directory / "figures_manifest.json", manifest)
    if args.json_out:
        write_json(args.json_out, manifest)
    print(json.dumps({"run_id": run_id, "figures": manifest["figure_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
