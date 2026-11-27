"""生成第八阶段工程图（全部来自解析计算，不是 EDA 导出，也不是实测）。

每张图右上角标注 "CALCULATED — NOT MEASURED"，避免被误读为硬件测试结果。
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from eda_tools.design_calculations import (  # noqa: E402
    calculate_balancing_branch,
    calculate_shunt,
    calculate_shunt_scale,
)
from eda_tools.inductor_design import (  # noqa: E402
    calculate_lc_resonance,
    calculate_ripple_for_inductance,
)
from eda_tools.thermal_calculations import estimate_rds_on_at_temperature  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150

FETS = {
    "CSD18540Q5B": 0.0022,
    "CSD18532Q5B": 0.0032,
    "CSD17578Q5A": 0.0069,
    "CSD17581Q5A": 0.0034,
}
SHUNT_TC = {0.001: 275, 0.002: 275, 0.005: 110, 0.010: 75}
CALC_NOTE = "CALCULATED — NOT MEASURED"


def finish(fig, path: Path, title: str) -> None:
    fig.text(0.99, 0.01, CALC_NOTE, ha="right", va="bottom", fontsize=7, color="#b00")
    fig.suptitle(title, fontsize=11)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(path)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    out = Path(args.output) if args.output else Path("results/eda") / f"run_figures_{run_id}"
    out.mkdir(parents=True, exist_ok=True)
    figures = []

    # 01 分流电阻：功耗与分辨率
    resistances = [0.001, 0.002, 0.005, 0.010]
    powers = [calculate_shunt(2.5, r, 0.5)["power_loss_w"] * 1000 for r in resistances]
    res_ma = [calculate_shunt_scale(r, 0.2, 7.568e-6)["current_lsb_a"] * 1000 for r in resistances]
    fig, ax1 = plt.subplots(figsize=(6.4, 4.2))
    ax1.bar([str(int(r * 1000)) for r in resistances], powers, color="#4a7ebb")
    ax1.set_xlabel("分流电阻 (mΩ)")
    ax1.set_ylabel("2.5 A 功耗 (mW)", color="#4a7ebb")
    ax2 = ax1.twinx()
    ax2.plot([str(int(r * 1000)) for r in resistances], res_ma, "o-", color="#c0504d")
    ax2.set_ylabel("电流分辨率 (mA/LSB)", color="#c0504d")
    finish(fig, out / "01_shunt_power_vs_resolution.png", "01 分流电阻权衡（BQ76922 ±200 mV, 1 LSB=7.568 µV）")
    figures.append("01_shunt_power_vs_resolution.png")

    # 02 RDS(on) 随结温
    temps = list(range(25, 126, 5))
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for name, r25 in FETS.items():
        ax.plot(temps, [estimate_rds_on_at_temperature(r25, t)["rds_on_ohm"] * 1000 for t in temps], label=name)
    ax.set_xlabel("结温 (℃)")
    ax.set_ylabel("RDS(on) 线性近似 (mΩ)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    finish(fig, out / "02_rds_on_vs_temperature.png", "02 RDS(on) 一阶温度外推（+0.5%/℃，仅初筛）")
    figures.append("02_rds_on_vs_temperature.png")

    # 03 BMS 功率路径损耗 vs 电流
    currents = [i / 10 for i in range(0, 51)]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.plot(currents, [i ** 2 * 0.0044 * 1000 for i in currents], color="#4a7ebb")
    ax.set_xlabel("电流 (A)")
    ax.set_ylabel("双管导通损耗 (mW)")
    ax.grid(alpha=0.3)
    finish(fig, out / "03_bms_path_loss_vs_current.png", "03 BMS 保护路径损耗（2×CSD18540Q5B, 4.4 mΩ）")
    figures.append("03_bms_path_loss_vs_current.png")

    # 04 均衡：外部电阻功耗 vs Rint
    rints = list(range(15, 47))
    ext_power = [calculate_balancing_branch(4.05, 47.0, r)["resistor_power_w"] * 1000 for r in rints]
    chip_power = [calculate_balancing_branch(4.05, 47.0, r)["switch_power_w"] * 1000 for r in rints]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.plot(rints, ext_power, label="外部 47 Ω 电阻")
    ax.plot(rints, chip_power, label="芯片内部均衡电阻")
    ax.axhline(250, color="#c0504d", linestyle="--", linewidth=1, label="1206 0.25 W 额定")
    ax.set_xlabel("芯片内部均衡电阻 (Ω)")
    ax.set_ylabel("功耗 (mW)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    finish(fig, out / "04_balancing_power_vs_internal_r.png", "04 均衡功耗（Vcell=4.05 V, Rext=47 Ω）")
    figures.append("04_balancing_power_vs_internal_r.png")

    # 05 均衡电流 vs 外部电阻
    rexts = list(range(10, 201, 5))
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.plot(rexts, [calculate_balancing_branch(4.05, r, 28.0)["balancing_current_a"] * 1000 for r in rexts])
    ax.axvline(47, color="#c0504d", linestyle="--", linewidth=1, label="本设计 47 Ω")
    ax.set_xlabel("外部滤波/均衡电阻 (Ω)")
    ax.set_ylabel("均衡电流 (mA)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    finish(fig, out / "05_balancing_current_vs_external_r.png", "05 均衡电流（Vcell=4.05 V, Rint=28 Ω）")
    figures.append("05_balancing_current_vs_external_r.png")

    # 06 充电电压误差预算
    from eda_tools.feedback_design import calculate_divider_error_budget

    budget = calculate_divider_error_budget(2.1, 0.5, 475_000.0, 100_000.0, 0.5, 0.0)
    labels = ["标称", "最坏下限", "最坏上限"]
    nominal = budget["nominal_voltage_v"]
    low = budget["worst_case_low_v"]
    high = budget["worst_case_high_v"]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.bar(labels, [nominal, low, high], color=["#4a7ebb", "#9bbb59", "#c0504d"])
    ax.axhline(12.15, color="k", linestyle="--", linewidth=1, label="目标 12.15 V")
    ax.set_ylabel("充电电压 (V)")
    ax.set_ylim(11.7, 12.4)
    ax.legend(fontsize=7)
    finish(fig, out / "06_charge_voltage_budget.png", "06 充电电压设定与容差（解析预算，非实测）")
    figures.append("06_charge_voltage_budget.png")

    # 07 充电电流 vs ISET1 电压
    isets = [i / 100 for i in range(10, 31)]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.plot(isets, [v / (20 * 0.01) for v in isets])
    ax.axvline(0.20122, color="#c0504d", linestyle="--", linewidth=1, label="本设计 0.2012 V → 1.006 A")
    ax.set_xlabel("ISET1 电压 (V)")
    ax.set_ylabel("充电电流 (A)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    finish(fig, out / "07_charge_current_vs_iset1.png", "07 充电电流设定（I=V_ISET1/(20×10 mΩ)）")
    figures.append("07_charge_current_vs_iset1.png")

    # 08 纹波 vs 电感
    inds = [i / 1e6 for i in range(4700, 47001, 1000)]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.plot([i * 1e6 for i in inds], [calculate_ripple_for_inductance(18.0, 12.075, i, 600e3)["estimated_ripple_a"] for i in inds])
    ax.axvline(22, color="#c0504d", linestyle="--", linewidth=1, label="本设计 22 µH")
    ax.set_xlabel("电感 (µH)")
    ax.set_ylabel("峰峰值纹波 (A)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    finish(fig, out / "08_inductor_ripple_vs_inductance.png", "08 Buck 纹波（18 V→12.075 V, 600 kHz, 1 A）")
    figures.append("08_inductor_ripple_vs_inductance.png")

    # 09 LC 谐振 vs 电容
    caps = [i / 1e6 for i in range(1, 41)]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.plot([c * 1e6 for c in caps], [calculate_lc_resonance(22e-6, c) / 1000 for c in caps])
    ax.axhspan(12, 17, color="#9bbb59", alpha=0.25, label="12–17 kHz 目标带")
    ax.axvline(9.4, color="#c0504d", linestyle="--", linewidth=1, label="标称 9.4 µF → 11.07 kHz")
    ax.set_xlabel("输出电容 (µF, 标称)")
    ax.set_ylabel("LC 谐振 (kHz)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    finish(fig, out / "09_lc_resonance_vs_capacitance.png", "09 LC 谐振（22 µH；标称 9.4 µF 落在目标带外）")
    figures.append("09_lc_resonance_vs_capacitance.png")

    # 10 铜箔电阻与损耗 vs 线宽
    widths = [i / 10 for i in range(2, 51)]
    rho = 1.724e-8
    resistance = [rho * 0.02 / (w * 1e-3 * 35e-6) * 1000 for w in widths]
    fig, ax1 = plt.subplots(figsize=(6.4, 4.2))
    ax1.plot(widths, resistance, color="#4a7ebb")
    ax1.set_xlabel("线宽 (mm)")
    ax1.set_ylabel("20 mm 走线电阻 (mΩ)", color="#4a7ebb")
    ax2 = ax1.twinx()
    ax2.plot(widths, [2.5 ** 2 * r for r in resistance], color="#c0504d")
    ax2.set_ylabel("2.5 A 损耗 (mW)", color="#c0504d")
    finish(fig, out / "10_copper_trace_vs_width.png", "10 理想铜箔（35 µm, 20 mm, 20 ℃）")
    figures.append("10_copper_trace_vs_width.png")

    # 11 充电器导通损耗分解
    duty = 12.075 / 18.0
    high = duty * 1.0 ** 2 * 0.0069 * 1000
    low = (1 - duty) * 1.0 ** 2 * 0.0034 * 1000
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    ax.bar(["高边 Q3", "低边 Q4", "合计"], [high, low, high + low], color=["#4a7ebb", "#9bbb59", "#8064a2"])
    ax.set_ylabel("导通损耗 (mW)")
    finish(fig, out / "11_charger_conduction_loss.png", "11 充电器导通损耗（1 A；未含开关损耗）")
    figures.append("11_charger_conduction_loss.png")

    # 12 分流电阻 TC 与 BQ76922 建议
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.bar([str(int(r * 1000)) for r in resistances], [SHUNT_TC[r] for r in resistances], color="#4a7ebb")
    ax.axhline(50, color="#c0504d", linestyle="--", linewidth=1, label="BQ76922 建议 ≤50 ppm/°C")
    ax.set_xlabel("分流电阻 (mΩ)")
    ax.set_ylabel("TC (ppm/°C)")
    ax.legend(fontsize=7)
    finish(fig, out / "12_shunt_tc_vs_limit.png", "12 分流电阻温度系数（Vishay WSL）")
    figures.append("12_shunt_tc_vs_limit.png")

    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_source": "analytic calculations (eda_tools)",
        "not_eda_exports": True,
        "not_measured": True,
        "figure_count": len(figures),
        "figures": figures,
    }
    (out / "figures_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"生成 {len(figures)} 张工程图：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
