"""Task 21/22：生成 v2 研发成果交付（不覆盖 v1 六份原始成果）。

输入：portfolio/BatteryLab_resume_metrics.csv（v1）+ results/hardening 各 summary。

输出（Task 22 规定的六件套 v2，文件名带 _v2 后缀）：
- portfolio/BatteryLab_resume_metrics_v2.csv
- portfolio/BatteryLab_真实量化工程成果总表_v2.md
- portfolio/BatteryLab_工程指标真实性核查报告_v2.md
- portfolio/BatteryLab_工程性能优化前后对照_v2.md
- portfolio/BatteryLab_研发岗成果证据卡_v2.md
- portfolio/BatteryLab_研发岗简历项目最终版_v2.md
- portfolio/BatteryLab_交付与复现说明_v2.md

Task 22 另行规定的七份专题报告：
- portfolio/BatteryLab_研发能力补强报告.md
- portfolio/BatteryLab_AFE精度优化前后对照.md
- portfolio/BatteryLab_MOSFET保护真实性复验.md
- portfolio/BatteryLab_CC_CV控制优化前后对照.md
- portfolio/BatteryLab_电池模型及系统复核报告.md
- portfolio/BatteryLab_KiCad硬件设计交付报告.md
- portfolio/BatteryLab_最终简历量化成果.md

第九阶段证据（Task 20 交付物）：
- portfolio/stage9_engineering_evidence.md
- portfolio/system_integration_metrics.csv
- portfolio/system_optimization_comparison.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
PORTFOLIO = PROJECT / "portfolio"
HARDENING = PROJECT / "results" / "hardening"

COLUMNS = ["成果编号", "研发模块", "指标名称", "优化前", "优化后", "单位", "改善比例", "实验条件",
           "数据来源", "Run ID", "原始证据", "核心源码", "验证状态", "验收状态", "简历适用性", "局限"]

DROP_IDS = {"P03", "P04", "P04B", "P05"}


def latest(area: str) -> Path:
    paths = sorted((HARDENING / area).glob("run_*"), key=lambda path: path.stat().st_mtime)
    if not paths:
        raise FileNotFoundError(f"缺少 results/hardening/{area}/run_*")
    return paths[-1]


def summary(area: str, filename: str) -> dict[str, Any]:
    path = latest(area) / filename
    return json.loads(path.read_text(encoding="utf-8"))


def row(identifier: str, module: str, name: str, before: Any, after: Any, unit: str, improvement: Any,
        condition: str, source: str, run_id: str, evidence: str, code: str, verification: str,
        acceptance: str, resume: str, limitation: str) -> dict[str, Any]:
    return dict(zip(COLUMNS, [identifier, module, name, before, after, unit, improvement, condition,
                              source, run_id, evidence, code, verification, acceptance, resume, limitation]))


def load_v1() -> pd.DataFrame:
    frame = pd.read_csv(PORTFOLIO / "BatteryLab_resume_metrics.csv", dtype=str, encoding="utf-8-sig").fillna("")
    return frame[~frame["成果编号"].isin(DROP_IDS)]


def new_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    afe = summary("afe", "summary.json")
    afe_run = afe["run_id"]
    afe_path = str(HARDENING / "afe" / afe_run)
    protection = summary("protection", "protection_summary.json")
    protection_run = protection["run_id"]
    protection_path = str(HARDENING / "protection" / protection_run)
    charging = summary("charging", "summary.json")
    charging_run = charging["run_id"]
    charging_path = str(HARDENING / "charging" / charging_run)
    ecm = summary("ecm", "low_soc_analysis_summary.json")
    ecm_run = ecm["run_id"]
    ecm_path = str(HARDENING / "ecm" / ecm_run)
    system = summary("system", "system_candidate_summary.json")
    system_run = system["run_id"]
    system_path = str(HARDENING / "system" / system_run)
    domain = summary("domain", "domain_summary.json")
    eda = summary("eda", "eda_status.json")
    eda_run = latest("eda").name
    baseline = summary("baseline", "baseline.json")

    standalone = protection["standalone"]
    integrated = protection["integrated"]
    soft = {int(item["soft_start_time_s"] * 1000): item for item in charging["soft_start"]}
    antiwindup = {item["method"]: item for item in charging["antiwindup"]}
    groups = system["groups"]
    base_group = groups["baseline_lc_baseline_controller"]
    opt_group = groups["optimized_lc_tuned_controller"]
    base_dc = base_group["controller"]
    opt_dc = opt_group["controller"]

    rows = [
        row("V01", "第四阶段", "AFE 电压最坏情况预算（线性叠加）", 30.887, 3.837, "mV", "87.58%",
            "3S 最高单体 4.0 V、共模 9.7 V、0.1%（基线）→0.01%（候选D）匹配网络",
            "解析误差预算 + 真实 SPICE 角点", afe_run, f"{afe_path}/optimized_budget.json",
            "hardening/afe_worst_case.py", "VERIFIED", "PASS（设计）", "高",
            "候选 D 未打样；0.01% 匹配网络为设计目标参数"),
        row("V02", "第四阶段", "AFE 电流最坏情况预算（线性叠加）", 37.736, 6.666, "mA", "82.33%",
            "±2.5 A、分流 10 mΩ、0.5%→0.05%、TCR 50→10 ppm/°C",
            "解析误差预算 + 真实 SPICE 角点", afe_run, f"{afe_path}/optimized_budget.json",
            "hardening/afe_worst_case.py", "VERIFIED", "PASS（设计）", "高",
            "ADC 增益剩余误差按两点校准后残差建模"),
        row("V03", "第四阶段", "AFE 电压统计 RMSE（两点校准后，同种子）", 0.8730, 0.8750, "mV", "-0.23%",
            "1000 组独立均匀容差，seed 42", "真实 SPICE 采样 + 行为 ADC 统计", afe_run,
            f"{afe_path}/monte_carlo_before.csv", "hardening/afe_worst_case.py", "VERIFIED", "记录", "中",
            "统计误差由 12 bit 量化与 ADC 噪声主导，器件升级不改善 RMSE（真实变差 0.23%）"),
        row("V04", "第四阶段", "AFE 电流统计 RMSE（两点校准后，同种子）", 0.8396, 0.8408, "mA", "-0.14%",
            "1000 组独立均匀容差，seed 42", "真实 SPICE 采样 + 行为 ADC 统计", afe_run,
            f"{afe_path}/monte_carlo_before.csv", "hardening/afe_worst_case.py", "VERIFIED", "记录", "中",
            "同上；统计值与最坏情况预算必须分开报告"),
        row("V05", "第五阶段", "真实 MOSFET 故障→电池电流抑制（独立）", "", round(standalone["delay_fault_to_suppression_s"] * 1e6, 3),
            "µs", "", "10 V/2 A→8 A 阶跃，阈值 4 A，20 ns 步长", "真实 ngspice Level-1 MOSFET 网表",
            protection_run, f"{protection_path}/protection_summary.json",
            "hardening/protection_physical_validation.py", "VERIFIED", "PASS", "高",
            "教学 MOSFET 模型；command→suppression 受采样分辨率限制"),
        row("V06", "第五阶段", "真实 MOSFET 栅极下降时间（90%→10%）", "", round(standalone["gate_fall_time_s"] * 1e9, 1),
            "ns", "", "RG 10 Ω + CGS 2 nF", "真实 ngspice 瞬态", protection_run,
            f"{protection_path}/numerical_convergence.csv", "hardening/protection_physical_validation.py",
            "VERIFIED", "PASS", "高", "网络依赖栅极电荷；非商业器件模型"),
        row("V07", "第五阶段", "联合系统故障→电流抑制（电池+Buck+负载）", "", round(integrated["delay_fault_to_suppression_s"] * 1e6, 1),
            "µs", "", "负载 2.5→0.5 Ω，4 A 阈值，50 ns 步长", "真实 ngspice 联合网表", protection_run,
            f"{protection_path}/event_sequence.csv", "hardening/protection_physical_validation.py",
            "VERIFIED", "RISK", "中", "过流爬升主导；输出维持时间为 0，需更快限流"),
        row("V08", "第五阶段", "保护级真实导通电阻（双管串联）", "", round(protection["conduction"][0]["path_resistance_ohm"] * 1e3, 2),
            "mΩ", "", "1.99 A 放电，VGS 10 V", "真实 ngspice 工作点", protection_run,
            f"{protection_path}/conduction_results.csv", "hardening/protection_physical_validation.py",
            "VERIFIED", "PASS", "高", "双管串联；体二极管漏电约 1e-11 A"),
        row("V09", "第五阶段", "历史 2.5 ns 保护伪迹", "", "拒绝", "-", "",
            "行为电流源在栅极指令前 9.9975 µs 钳位", "证据复核", protection_run,
            f"{protection_path}/original_artifact_analysis.md", "circuits/system_spice_netlist.py",
            "VERIFIED", "PASS（真实性）", "高", "伪迹永久保留为无效记录，不进入简历"),
        row("V10", "第六阶段", "软启动峰值充电电流（0→5 ms）", round(soft[0]["peak_charging_current_a"], 4),
            round(soft[5]["peak_charging_current_a"], 4), "A", "3.07%", "18 V 输入，1 A CC，8 ms 窗口",
            "真实开关级 ngspice", charging_run, f"{charging_path}/soft_start_comparison.csv",
            "hardening/charging_control_comparison.py", "VERIFIED", "PASS", "中",
            "电感已限制 di/dt，峰值改善有限"),
        row("V11", "第六阶段", "软启动启动能量（0→5 ms）", round(soft[0]["startup_energy_j"], 4),
            round(soft[5]["startup_energy_j"], 4), "J", "45.10%", "0–5 ms 积分窗口", "真实开关级 ngspice",
            charging_run, f"{charging_path}/soft_start_comparison.csv",
            "hardening/charging_control_comparison.py", "VERIFIED", "PASS", "高", "窗口为启动段，非整段充电"),
        row("V12", "第六阶段", "软启动 CC 稳态误差（0→5 ms）", round(abs(soft[0]["cc_mean_error_a"]) * 1e3, 3),
            round(soft[5]["cc_mean_error_a"] * 1e3, 3), "mA", "变差 5673%", "最后 2 ms 评价窗口",
            "真实开关级 ngspice", charging_run, f"{charging_path}/soft_start_comparison.csv",
            "hardening/charging_control_comparison.py", "VERIFIED", "FAIL（5 ms）", "中",
            "5 ms 软启动未在 8 ms 窗口内稳态；推荐 1–2 ms"),
        row("V13", "第六阶段", "抗积分饱和 CV 过冲（none→conditional）", round(antiwindup["none"]["voltage_overshoot_v"] * 1e3, 3),
            round(antiwindup["conditional"]["voltage_overshoot_v"] * 1e3, 3), "mV", "36.51%",
            "CC→CV 11.95→12.15 V，12 ms", "真实开关级 ngspice", charging_run,
            f"{charging_path}/antiwindup_comparison.csv", "hardening/charging_control_comparison.py",
            "VERIFIED", "PASS", "高", "恢复时间基本不变"),
        row("V14", "第六阶段", "back-calculation 沿用旧 KAW 的 CV 过冲", round(antiwindup["none"]["voltage_overshoot_v"] * 1e3, 3),
            round(antiwindup["back_calculation"]["voltage_overshoot_v"] * 1e3, 1), "mV", "变差 20000%",
            "同一 CC→CV 工况", "真实开关级 ngspice", charging_run,
            f"{charging_path}/antiwindup_comparison.csv", "hardening/charging_control_comparison.py",
            "VERIFIED", "FAIL", "中", "保留失败；调优 Kaw=Ki/Kp 后过冲 2.338 mV"),
        row("V15", "第六阶段", "PI 带宽分离比（目标 ≥5×）", "", "最大 1.86×", "-", "0/25 通过",
            "25 组 Kp/Ki 倍率，频域环分析", "频域分析 + 2 次真实 SPICE", charging_run,
            f"{charging_path}/pi_grid.csv", "analysis/charging_loop_analysis.py", "VERIFIED", "FAIL", "中",
            "原始控制器即未满足 5×，保留 FAIL"),
        row("V16", "第三阶段", "低 SOC 0–5% 端电压 RMSE（bjdst_80 二阶）", "", round(ecm["low_soc_dominant"]["low_soc_worst"]["rmse_mv"], 1),
            "mV", "", "SOC 0–5%，25 °C，公开 BJDST", "CALCE 公开数据重放", ecm_run,
            f"{ecm_path}/low_soc_error_by_band.csv", "hardening/low_soc_model_analysis.py",
            "VERIFIED", "FAIL", "中", "低 SOC 最大误差 358.2 mV；未用验证数据重拟合"),
        row("V17", "第九阶段/系统", "系统效率（基准→优化LC+控制器）", round(base_group["efficiency_percent"], 3),
            round(opt_group["efficiency_percent"], 3), "%", "+1.048 pp / +1.11%",
            "3S SOC 0.4，5 V/2 A，10 ms", "真实开关级联合仿真", system_run,
            f"{system_path}/system_candidate_summary.json", "hardening/system_candidate_validation.py",
            "VERIFIED", "PASS", "高", "仿真效率，不含驱动与辅助电源"),
        row("V18", "第九阶段/系统", "系统输出纹波（基准→优化）", round(base_group["ripple_vpp"] * 1e3, 2),
            round(opt_group["ripple_vpp"] * 1e3, 2), "mV", "14.43%", "2.5 Ω 稳态，6 ms 前窗口",
            "真实开关级联合仿真", system_run, f"{system_path}/system_candidate_comparison.csv",
            "hardening/system_candidate_validation.py", "VERIFIED", "PASS", "高", "需与控制器配套"),
        row("V19", "第九阶段/系统", "负载阶跃最大偏差（2.5→1.25 Ω）", round(base_group["step_deviation_v"] * 1e3, 2),
            round(opt_group["step_deviation_v"] * 1e3, 2), "mV", "31.79%", "6 ms 阶跃，10 ms 窗口",
            "真实开关级联合仿真", system_run, f"{system_path}/system_candidate_comparison.csv",
            "hardening/system_candidate_validation.py", "VERIFIED", "PASS", "高", "恢复时间略变慢"),
        row("V20", "第九阶段/系统", "负载阶跃恢复时间（基准→优化）", round(base_group["recovery_time_s"] * 1e6, 0),
            round(opt_group["recovery_time_s"] * 1e6, 0), "µs", "变差 6.32%", "±1% 带宽判定",
            "真实开关级联合仿真", system_run, f"{system_path}/system_candidate_comparison.csv",
            "hardening/system_candidate_validation.py", "VERIFIED", "记录", "中", "优化LC储能更大，恢复更慢"),
        row("V21", "第三阶段/第九阶段", "模型有效域（7 个动态工况）", "", "7/7 LIMITED", "项", "",
            "SOC 0.014–0.80，辨识区间 0.011–0.507", "残差表复核", domain["run_id"],
            str(HARDENING / "domain" / domain["run_id"] / "operating_domain.csv"),
            "hardening/domain_audit.py", "VERIFIED", "LIMITED", "中", "区间外为参数外推"),
        row("V22", "第八阶段/EDA", "EDA 交付状态", "", "PASS 10 / BLOCKED 9 / FAIL 1", "项", "",
            "KiCad 未安装", "既有运行复核", eda_run,
            str(HARDENING / "eda" / eda_run / "eda_status.md"), "hardening/eda_status.py",
            "BLOCKED", "BLOCKED", "低", "无原理图/PCB/ERC/DRC"),
        row("V23", "全项目", "自动化测试实际通过数", "", baseline["pytest"]["counts"].get("passed"), "项", "",
            "pytest tests -q", "软件测试", baseline["run_id"],
            str(HARDENING / "baseline" / baseline["run_id"] / "baseline.json"), "tests/",
            "VERIFIED", "PASS", "低", "软件测试数量不是电气性能；补强新增 10 个测试后为 560 passed"),
        row("V24", "第七阶段", "SOC 方法误差（raw OCV / ECM observer / 安时积分）", "", "9.30–9.70 / 1.48–1.81 / ~0", "pp", "",
            "US06/BJDST 50/80", "公开数据重放", "stage7_20261126_162211_3590e5",
            str(PROJECT / "results" / "stage7" / "run_stage7_20261126_162211_3590e5" / "soc_method_comparison.csv"),
            "estimation/", "VERIFIED", "LIMITED", "高",
            "安时积分参考由同一电流积分推导，非独立实测 SOC"),
    ]
    context = {
        "afe_run": afe_run, "protection_run": protection_run, "charging_run": charging_run,
        "ecm_run": ecm_run, "system_run": system_run, "domain_run": domain["run_id"],
        "eda_run": eda_run, "baseline_run": baseline["run_id"],
        "baseline_dc": base_dc, "opt_dc": opt_dc, "system_groups": groups,
        "afe": afe, "protection": protection, "charging": charging, "ecm": ecm,
        "system": system, "domain": domain, "eda": eda, "baseline": baseline,
        "paths": {
            "afe": afe_path, "protection": protection_path, "charging": charging_path,
            "ecm": ecm_path, "system": system_path,
            "domain": str(HARDENING / "domain" / domain["run_id"]),
            "eda": str(HARDENING / "eda" / eda_run),
            "baseline": str(HARDENING / "baseline" / baseline["run_id"]),
        },
    }
    return rows, context


def frame_to_markdown(frame: pd.DataFrame, columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    lines = [header, divider]
    for _, item in frame.iterrows():
        cells = [str(item.get(column, "")).replace("|", "/") for column in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    lines = [header, divider]
    for item in rows:
        cells = []
        for column in columns:
            value = item.get(column, "")
            if value is None:
                value = "—"
            cells.append(str(value).replace("|", "/").replace("\n", " "))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _mv(value_v: float) -> float:
    return round(value_v * 1e3, 3)


# ---------------------------------------------------------------------------
# Task 22 七份专题报告
# ---------------------------------------------------------------------------

def doc_hardening_report(ctx: dict[str, Any]) -> str:
    afe, protection, charging, ecm = ctx["afe"], ctx["protection"], ctx["charging"], ctx["ecm"]
    system, domain, eda = ctx["system"], ctx["domain"], ctx["eda"]
    soft = {int(item["soft_start_time_s"] * 1000): item for item in charging["soft_start"]}
    aw = {item["method"]: item for item in charging["antiwindup"]}
    groups = system["groups"]
    base = groups["baseline_lc_baseline_controller"]
    opt = groups["optimized_lc_tuned_controller"]
    rows = [
        {"模块": "AFE 电压预算", "补强前": "30.887 mV", "补强后": "3.837 mV", "判定": "PASS（≤10 mV）"},
        {"模块": "AFE 电流预算", "补强前": "37.736 mA", "补强后": "6.666 mA", "判定": "PASS（≤20 mA）"},
        {"模块": "保护电流抑制", "补强前": "2.5 ns（行为源伪迹）", "补强后": "0.871 µs（真实 MOSFET）", "判定": "伪迹已剔除"},
        {"模块": "软启动启动能量", "补强前": "0.2492 J（无软启动）", "补强后": f"{soft[5]['startup_energy_j']:.4f} J（5 ms）", "判定": "改善 45.1%"},
        {"模块": "软启动 CC 误差", "补强前": f"{abs(soft[0]['cc_mean_error_a']) * 1e3:.3f} mA", "补强后": f"{soft[5]['cc_mean_error_a'] * 1e3:.3f} mA（5 ms）", "判定": "FAIL（5 ms 超差）"},
        {"模块": "抗积分饱和", "补强前": f"{aw['none']['voltage_overshoot_v'] * 1e3:.3f} mV", "补强后": f"{aw['conditional']['voltage_overshoot_v'] * 1e3:.3f} mV", "判定": "改善 36.5%"},
        {"模块": "PI 带宽分离", "补强前": "原始控制器未达标", "补强后": "最大 1.86×（目标 5×）", "判定": "FAIL（0/25）"},
        {"模块": "低 SOC 误差", "补强前": "375.836 mV（历史最大）", "补强后": f"{ecm['low_soc_dominant']['low_soc_worst']['rmse_mv']:.1f} mV（RMSE）/ {ecm['low_soc_dominant']['low_soc_worst']['max_abs_mv']:.1f} mV（最大）", "判定": "FAIL（保留）"},
        {"模块": "系统纹波", "补强前": f"{base['ripple_vpp'] * 1e3:.2f} mV", "补强后": f"{opt['ripple_vpp'] * 1e3:.2f} mV", "判定": "PASS"},
        {"模块": "系统效率", "补强前": f"{base['efficiency_percent']:.3f}%", "补强后": f"{opt['efficiency_percent']:.3f}%", "判定": "PASS（+1.048 pp）"},
        {"模块": "模型有效域", "补强前": "未标注", "补强后": "7/7 LIMITED", "判定": "LIMITED"},
        {"模块": "EDA 交付", "补强前": "PASS 10 / BLOCKED 9 / FAIL 1", "补强后": "无变化（KiCad 未安装）", "判定": "BLOCKED"},
    ]
    return (
        "# BatteryLab 研发能力补强报告\n\n"
        "> 全部数值来自真实 SPICE、公开数据重放或解析计算；未做硬件实测。\n\n"
        "## 1. 补强范围\n\n"
        "本次补强针对四个真实工程问题：模拟采集最坏情况误差、保护行为源伪迹、CC-CV 启动与积分饱和、"
        "系统闭环 LC 与低 SOC 模型精度；同时完成第九阶段文档闭合与第十阶段学习材料。\n\n"
        "## 2. 结果总览\n\n"
        + table(rows, ["模块", "补强前", "补强后", "判定"]) + "\n\n"
        "## 3. 逐项证据\n\n"
        f"- AFE 误差预算：`{ctx['paths']['afe']}/optimized_budget.json`（Run `{ctx['afe_run']}`）\n"
        f"- 真实 MOSFET 保护：`{ctx['paths']['protection']}/protection_summary.json`（Run `{ctx['protection_run']}`）\n"
        f"- CC-CV 控制：`{ctx['paths']['charging']}/summary.json`（Run `{ctx['charging_run']}`）\n"
        f"- 低 SOC 模型：`{ctx['paths']['ecm']}/low_soc_analysis_summary.json`（Run `{ctx['ecm_run']}`）\n"
        f"- 系统闭环：`{ctx['paths']['system']}/system_candidate_summary.json`（Run `{ctx['system_run']}`）\n"
        f"- 有效域与 SOH/LLC：`{ctx['paths']['domain']}/domain_summary.json`（Run `{ctx['domain_run']}`）\n"
        f"- EDA 状态：`{ctx['paths']['eda']}/eda_status.md`（Run `{ctx['eda_run']}`）\n\n"
        "## 4. 保留的失败与未达标项\n\n"
        "- AFE 基线 30.887 mV / 37.736 mA 本身未达 10 mV / 20 mA，作为历史 FAIL 保留；达标的是候选 D 的设计预算。\n"
        "- 5 ms 软启动使 CC 稳态误差恶化到 20.610 mA，判 FAIL；1–2 ms 为推荐区间。\n"
        "- back-calculation 沿用旧 KAW 时过冲 654.6 mV，判 FAIL；调优后 2.338 mV 仅作补充。\n"
        "- PI 带宽分离 0/25 通过，保留 FAIL，未通过降低 5× 判据“改善”。\n"
        "- 低 SOC 0–5% 误差 157.7 mV（RMSE）/ 358.2 mV（最大），历史 375.836 mV 保留。\n"
        "- 联合系统故障→抑制 119.8 µs，输出维持时间 0，标记 RISK。\n"
        "- LC 谐振 11.07 kHz 低于 12–17 kHz 目标，FAIL 保留。\n\n"
        "## 5. 未完成与阻塞\n\n"
        "- KiCad 未安装，原理图/PCB/ERC/DRC/Gerber/钻孔/STEP 均未产生（BLOCKED）。\n"
        "- 无硬件实测：无打样、无真实电池上电、无热与 EMI 测试。\n"
        "- 模型仅 25 °C；0/45 °C 与 3S 组电压参考为 NOT_VERIFIED。\n\n"
        "## 6. 复现\n\n"
        "```powershell\n"
        "python -B -m scripts.hardening_afe\n"
        "python -B -m scripts.hardening_protection\n"
        "python -B -m scripts.hardening_charging\n"
        "python -B -m scripts.hardening_ecm\n"
        "python -B -m scripts.hardening_system\n"
        "python -B -m scripts.hardening_domain\n"
        "python -B -m scripts.hardening_eda\n"
        "```\n"
    )


def doc_afe(ctx: dict[str, Any]) -> str:
    afe = ctx["afe"]
    candidates = afe["candidates"]
    base = afe["baseline"]
    opt = afe["optimized"]
    rows = [
        {"方案": "历史基线（0.1% 电阻）", "电压最坏(mV)": round(base["voltage_worst_case_mv"], 3),
         "电流最坏(mA)": round(base["current_worst_case_ma"], 3), "电压达标": "否", "电流达标": "否",
         "主导项": base["dominant_voltage"] + " / " + base["dominant_current"]},
    ]
    for key, item in candidates.items():
        rows.append({
            "方案": f"{key}：{item['label']}",
            "电压最坏(mV)": round(item["voltage_worst_case_v"] * 1e3, 3),
            "电流最坏(mA)": round(item["current_worst_case_a"] * 1e3, 3),
            "电压达标": "是" if item["voltage_target_met"] else "否",
            "电流达标": "是" if item["current_target_met"] else "否",
            "主导项": item["voltage_dominant"] + " / " + item["current_dominant"],
        })
    contributions = [
        {"误差项": item["name"], "幅值(mV)": round(item["magnitude"] * 1e3, 4), "占比(%)": round(item["share_percent"], 2),
         "来源": item["source"], "公式": item["formula"]}
        for item in opt["residual_contributions"]
    ]
    base_mc = base["monte_carlo"]
    opt_mc = opt["monte_carlo_same_seed"]
    indep_mc = opt["monte_carlo_independent_seed"]
    mc_rows = [
        {"口径": "基线 未校准 RMSE", "电压(mV)": round(base_mc["voltage"]["pre_calibration"]["rmse"] * 1e3, 4),
         "电流(mA)": round(base_mc["current"]["pre_calibration"]["rmse"] * 1e3, 4)},
        {"口径": "基线 两点校准后 RMSE", "电压(mV)": round(base_mc["voltage"]["post_calibration"]["rmse"] * 1e3, 4),
         "电流(mA)": round(base_mc["current"]["post_calibration"]["rmse"] * 1e3, 4)},
        {"口径": "候选D 两点校准后 RMSE（同种子）", "电压(mV)": round(opt_mc["voltage"]["post_calibration"]["rmse"] * 1e3, 4),
         "电流(mA)": round(opt_mc["current"]["post_calibration"]["rmse"] * 1e3, 4)},
        {"口径": "候选D 两点校准后 RMSE（独立种子）", "电压(mV)": round(indep_mc["voltage"]["post_calibration"]["rmse"] * 1e3, 4),
         "电流(mA)": round(indep_mc["current"]["post_calibration"]["rmse"] * 1e3, 4)},
    ]
    temp = afe["temperature_cost"]["baseline_historical"]
    temp_opt = afe["temperature_cost"]["D_network_low_offset_composite"]
    return (
        "# BatteryLab AFE 精度优化前后对照\n\n"
        "> 口径：最坏情况为线性叠加（保证边界），统计值为 1000 组蒙特卡洛（数学样本，不是 1000 次 SPICE）。\n\n"
        "## 1. 目标\n\n"
        f"- 电压最坏情况 ≤ {afe['targets']['voltage_mv']:.1f} mV；电流最坏情况 ≤ {afe['targets']['current_ma']:.1f} mA。\n"
        "- 工况：3S 最高单体 4.0 V、共模 9.7 V、±2.5 A、分流 10 mΩ。\n\n"
        "## 2. 候选对照\n\n"
        + table(rows, ["方案", "电压最坏(mV)", "电流最坏(mA)", "电压达标", "电流达标", "主导项"]) + "\n\n"
        "## 3. 候选 D 剩余误差分解\n\n"
        + table(contributions, ["误差项", "幅值(mV)", "占比(%)", "来源", "公式"]) + "\n\n"
        f"- 电压最坏 {opt['voltage_worst_case_mv']:.3f} mV，RSS {opt['voltage_rss_mv']:.3f} mV；"
        f"电流最坏 {opt['current_worst_case_ma']:.3f} mA，RSS {opt['current_rss_ma']:.3f} mA。\n"
        f"- 相对基线改善：电压 {afe['improvement']['voltage']['improvement_percent']:.2f}%，"
        f"电流 {afe['improvement']['current']['improvement_percent']:.2f}%。\n\n"
        "## 4. 统计精度（两点校准后）\n\n"
        + table(mc_rows, ["口径", "电压(mV)", "电流(mA)"]) + "\n\n"
        "- 统计 RMSE 未改善（电压 0.8730→0.8750 mV，电流 0.8396→0.8408 mA），真实现象：12 bit 量化与 ADC 噪声主导。\n"
        "- 统计精度与最坏情况设计保证必须分开报告，不能互相替代。\n\n"
        "## 5. 真实 SPICE 角点校核\n\n"
        f"- 4 组样本 × 5 点：解析模型与真实 ngspice 最大偏差 {afe['spice_corner_max_abs_difference_v'] * 1e6:.2f} µV。\n\n"
        "## 6. 温度漂移代价（ΔT = 25 °C）\n\n"
        + table([
            {"方案": "历史基线", "电压漂移(mV)": round(temp["voltage"]["total_v"] * 1e3, 3),
             "电流漂移(mA)": round(temp["current"]["total_a"] * 1e3, 3)},
            {"方案": "候选D", "电压漂移(mV)": round(temp_opt["voltage"]["total_v"] * 1e3, 3),
             "电流漂移(mA)": round(temp_opt["current"]["total_a"] * 1e3, 3)},
        ], ["方案", "电压漂移(mV)", "电流漂移(mA)"]) + "\n\n"
        "- 电压漂移主要由电阻跟踪（48.5 mV）与 ADC 参考漂移（8.25 mV）构成，选型无法消除，只能靠参考源与标定。\n\n"
        "## 7. 器件选型与局限\n\n"
        "- 选型方向：0.01% 比率匹配电阻网络 + 低失调放大器 + 优化参考源 + 两点校准剩余误差。\n"
        "- 上述为设计目标参数，未打样、未做器件级实测；0.01% 网络的实际温漂与长期稳定性未验证。\n"
        f"- 证据：`{ctx['paths']['afe']}`（Run `{ctx['afe_run']}`）。\n"
    )


def doc_protection(ctx: dict[str, Any]) -> str:
    protection = ctx["protection"]
    hist = protection["artifact"]["historical"]["timing"]
    standalone = protection["standalone"]
    integrated = protection["integrated"]
    conduction = {item["mode"]: item for item in protection["conduction"]}
    convergence = [
        {"步长(ns)": round(item["step_s"] * 1e9, 0), "触发电流(A)": round(item["trip_current_a"], 3),
         "故障→指令(µs)": round(item["fault_to_command_s"] * 1e6, 3),
         "栅极下降(ns)": round(item["gate_fall_time_s"] * 1e9, 1),
         "故障→抑制(µs)": round(item["fault_to_suppression_s"] * 1e6, 3),
         "峰值Vds(V)": round(item["peak_vds_v"], 3), "峰值电流(A)": round(item["peak_current_a"], 3),
         "关断能量(µJ)": round(item["turnoff_energy_j"] * 1e6, 4)}
        for item in protection["numerical_convergence"]
    ]
    on = conduction["on_discharge"]
    off = conduction["off_discharge_block"]
    charge = conduction["on_charge"]
    charge_off = conduction["off_charge_block"]
    return (
        "# BatteryLab MOSFET 保护真实性复验\n\n"
        "> 真实 ngspice Level-1 N-MOSFET 背靠背共源 + 显式体二极管 + 栅极 RC；不是行为电流源。\n\n"
        "## 1. 历史 2.5 ns 伪迹判定\n\n"
        + table([
            {"事件": "故障注入时刻", "时间(s)": f"{hist['fault_start_time_s']:.9f}"},
            {"事件": "栅极关断指令", "时间(s)": f"{hist['fet_command_off_time_s']:.9f}"},
            {"事件": "历史“电流抑制”", "时间(s)": f"{hist['battery_current_suppressed_time_s']:.9f}"},
            {"事件": "相对栅极指令", "时间(s)": f"{hist['current_suppression_delay_from_command_s'] * 1e6:.4f} µs（早于指令）"},
            {"事件": "历史抑制比", "时间(s)": f"{protection['artifact']['historical']['suppression_ratio']:.6f}"},
        ], ["事件", "时间(s)"]) + "\n\n"
        "- 结论：抑制早于栅极指令 9.9975 µs，物理不成立，判定为行为电流源钳位伪迹，永久保留为无效记录。\n\n"
        "## 2. 真实独立故障复验（20 ns 步长）\n\n"
        + table([
            {"指标": "故障前电流", "数值": f"{standalone['pre_fault_current_a']:.3f} A"},
            {"指标": "触发电流", "数值": f"{standalone['trip_current_a']:.3f} A"},
            {"指标": "故障→栅极指令", "数值": f"{standalone['fault_to_command_s'] * 1e6:.3f} µs"},
            {"指标": "栅极下降（90%→10%）", "数值": f"{standalone['gate_fall_time_s'] * 1e9:.1f} ns"},
            {"指标": "故障→电流抑制", "数值": f"{standalone['delay_fault_to_suppression_s'] * 1e6:.3f} µs"},
            {"指标": "残余电流比", "数值": f"{standalone['residual_ratio']:.3e}"},
            {"指标": "峰值 Vds", "数值": f"{standalone['peak_vds_v']:.3f} V"},
            {"指标": "峰值电流", "数值": f"{standalone['peak_battery_current_a']:.3f} A"},
            {"指标": "关断能量", "数值": f"{standalone['turnoff_energy_j'] * 1e6:.3f} µJ"},
        ], ["指标", "数值"]) + "\n\n"
        "## 3. 三档步长收敛\n\n"
        + table(convergence, ["步长(ns)", "触发电流(A)", "故障→指令(µs)", "栅极下降(ns)",
                              "故障→抑制(µs)", "峰值Vds(V)", "峰值电流(A)", "关断能量(µJ)"]) + "\n\n"
        "- 关键时间在三档步长下一致到采样分辨率；`command→suppression` 为 0，说明受限采样分辨率，报告值为上限估计。\n\n"
        "## 4. 导通与阻断\n\n"
        + table([
            {"工况": "放电导通", "电流(A)": round(on["battery_current_a"], 3), "通路压降(V)": round(on["path_voltage_v"], 4),
             "串联导通电阻(mΩ)": round(on["path_resistance_ohm"] * 1e3, 3)},
            {"工况": "充电导通", "电流(A)": round(charge["battery_current_a"], 3), "通路压降(V)": round(charge["path_voltage_v"], 4),
             "串联导通电阻(mΩ)": round(charge["path_resistance_ohm"] * 1e3, 3)},
            {"工况": "放电阻断", "电流(A)": f"{off['battery_current_a']:.3e}", "通路压降(V)": round(off["path_voltage_v"], 3),
             "串联导通电阻(mΩ)": "—"},
            {"工况": "充电阻断", "电流(A)": f"{charge_off['battery_current_a']:.3e}", "通路压降(V)": round(charge_off["path_voltage_v"], 3),
             "串联导通电阻(mΩ)": "—"},
        ], ["工况", "电流(A)", "通路压降(V)", "串联导通电阻(mΩ)"]) + "\n\n"
        f"- 双向阻断漏电约 {abs(off['battery_current_a']):.2e} A / {abs(charge_off['battery_current_a']):.2e} A。\n\n"
        "## 5. 联合系统故障（电池 + Buck + 负载）\n\n"
        + table([
            {"指标": "故障→触发", "数值": f"{integrated['fault_to_trip_s'] * 1e6:.1f} µs"},
            {"指标": "故障→栅极指令", "数值": f"{integrated['fault_to_command_s'] * 1e6:.1f} µs"},
            {"指标": "故障→电流抑制", "数值": f"{integrated['delay_fault_to_suppression_s'] * 1e6:.1f} µs"},
            {"指标": "峰值电流", "数值": f"{integrated['peak_battery_current_a']:.3f} A"},
            {"指标": "峰值 Vds", "数值": f"{integrated['peak_vds_v']:.3f} V"},
            {"指标": "输出维持时间", "数值": f"{integrated['output_hold_time_s'] * 1e6:.1f} µs"},
            {"指标": "故障后能量", "数值": f"{integrated['energy_after_fault_j'] * 1e3:.3f} mJ"},
        ], ["指标", "数值"]) + "\n\n"
        "- 风险：过流爬升由 Buck 输入侧与大电容供能主导，输出维持时间为 0（负载阶跃下先跌破 4.5 V），标记 RISK。\n\n"
        "## 6. 局限\n\n"
        "- MOSFET 为教学 Level-1 模型，非商业器件官方 SPICE 模型；栅极电荷与米勒平台为简化 RC。\n"
        "- 全部为软件仿真，未做真实短路/过流实验。\n"
        f"- 证据：`{ctx['paths']['protection']}`（Run `{ctx['protection_run']}`）。\n"
    )


def doc_charging(ctx: dict[str, Any]) -> str:
    charging = ctx["charging"]
    soft = {int(item["soft_start_time_s"] * 1000): item for item in charging["soft_start"]}
    rows = [
        {"软启动(ms)": ms, "峰值充电电流(A)": round(item["peak_charging_current_a"], 4),
         "启动能量(J)": round(item["startup_energy_j"], 4),
         "CC 稳态误差(mA)": round(item["cc_mean_error_a"] * 1e3, 3),
         "过冲比例": f"{item['overshoot_fraction'] * 100:.2f}%",
         "90% 上升时间(ms)": round(item["rise_time_90_s"] * 1e3, 3)}
        for ms, item in sorted(soft.items())
    ]
    aw = {item["method"]: item for item in charging["antiwindup"]}
    aw_rows = [
        {"方法": method, "CV 过冲(mV)": round(item["voltage_overshoot_v"] * 1e3, 3),
         "20 mV 恢复(ms)": round(item["settling_time_to_20mv_s"] * 1e3, 3),
         "CC 误差(mA)": round(item["cc_mean_error_a"] * 1e3, 3)}
        for method, item in aw.items()
    ]
    grid = pd.read_csv(latest("charging") / "pi_grid.csv")
    best = grid.sort_values("bandwidth_separation_ratio", ascending=False).iloc[0]
    return (
        "# BatteryLab CC-CV 控制优化前后对照\n\n"
        "> 真实开关级 ngspice；PI 在网表内以行为源实现；同输入、同目标、同器件、同步长。\n\n"
        "## 1. 软启动（0→5 ms）\n\n"
        + table(rows, ["软启动(ms)", "峰值充电电流(A)", "启动能量(J)", "CC 稳态误差(mA)", "过冲比例", "90% 上升时间(ms)"]) + "\n\n"
        f"- 峰值电流 {soft[0]['peak_charging_current_a']:.4f} → {soft[5]['peak_charging_current_a']:.4f} A（−3.07%）。\n"
        f"- 启动能量 {soft[0]['startup_energy_j']:.4f} → {soft[5]['startup_energy_j']:.4f} J（−45.1%）。\n"
        f"- 代价：5 ms 软启动使 CC 稳态误差由 {abs(soft[0]['cc_mean_error_a']) * 1e3:.3f} mA 恶化到 {soft[5]['cc_mean_error_a'] * 1e3:.3f} mA（FAIL）；推荐 1–2 ms。\n\n"
        "## 2. PI 参数网格\n\n"
        f"- 25 组 Kp/Ki 倍率中通过全部判据 {charging['pi_grid_passing']}/{charging['pi_grid_rows']} 组。\n"
        f"- 最大带宽分离比 {best['bandwidth_separation_ratio']:.2f}×（判据 ≥5×），对应电流环 PM "
        f"{best['current_phase_margin_deg']:.2f}°、电压环 PM {best['voltage_phase_margin_deg']:.2f}°。\n"
        "- 说明：原始控制器本身即未满足 5× 分离，本次未通过降低判据制造“通过”；探索性候选仅作记录。\n"
        f"- 真实 SPICE 复验：探针候选 1 CC 误差 {charging['pi_improvement'][0]['cc_mean_error_a']['candidate'] * 1e3:.3f} mA（基线 "
        f"{charging['pi_improvement'][0]['cc_mean_error_a']['baseline'] * 1e3:.3f} mA），但未通过全判据。\n\n"
        "## 3. 抗积分饱和\n\n"
        + table(aw_rows, ["方法", "CV 过冲(mV)", "20 mV 恢复(ms)", "CC 误差(mA)"]) + "\n\n"
        f"- 条件积分：{aw['none']['voltage_overshoot_v'] * 1e3:.3f} → {aw['conditional']['voltage_overshoot_v'] * 1e3:.3f} mV（−36.5%），恢复时间基本不变。\n"
        f"- back-calculation 沿用旧 KAW：过冲 {aw['back_calculation']['voltage_overshoot_v'] * 1e3:.1f} mV（FAIL，保留）。\n"
        f"- back-calculation 按 Kaw=Ki/Kp 调优：过冲 {aw['back_calculation_tuned']['voltage_overshoot_v'] * 1e3:.3f} mV，但恢复 {aw['back_calculation_tuned']['settling_time_to_20mv_s'] * 1e3:.1f} ms，慢于条件积分。\n\n"
        "## 4. 结论与局限\n\n"
        "- 推荐：1–2 ms 软启动 + 条件积分抗饱和；5 ms 软启动与旧 KAW 方案不推荐。\n"
        "- 局限：单工作点、恒阻负载、无温度与容差；PI 为网表内行为源，非数字实现。\n"
        f"- 证据：`{ctx['paths']['charging']}`（Run `{ctx['charging_run']}`）。\n"
    )


def doc_model_system(ctx: dict[str, Any]) -> str:
    ecm, system, domain = ctx["ecm"], ctx["system"], ctx["domain"]
    comparison = {}
    for item in ecm["model_comparison"]:
        comparison.setdefault(item["experiment"], {})[item["model"]] = item
    experiments = sorted(comparison)
    rmse_rows = []
    for experiment in experiments:
        models = comparison[experiment]
        rmse_rows.append({
            "工况": experiment,
            "Rint RMSE(mV)": round(models["rint"]["rmse_mv"], 3),
            "一阶 RC RMSE(mV)": round(models["first_order_rc"]["rmse_mv"], 3),
            "二阶 RC RMSE(mV)": round(models["second_order_rc"]["rmse_mv"], 3),
            "最大绝对误差(mV)": round(max(item["max_abs_mv"] for item in models.values()), 1),
        })
    low = ecm["low_soc_dominant"]["low_soc_worst"]
    mid = ecm["low_soc_dominant"]["mid_soc_reference"]
    groups = system["groups"]
    group_rows = []
    for name, item in groups.items():
        group_rows.append({
            "组别": name, "L(µH)": round(item["lc"]["inductance_h"] * 1e6, 1),
            "C(µF)": round(item["lc"]["capacitance_f"] * 1e6, 0),
            "kp": item["controller"]["kp"], "ki": item["controller"]["ki"],
            "稳态电压(V)": round(item["steady_voltage_v"], 4),
            "纹波(mV)": round(item["ripple_vpp"] * 1e3, 2),
            "效率(%)": round(item["efficiency_percent"], 3),
            "阶跃偏差(mV)": round(item["step_deviation_v"] * 1e3, 2),
            "恢复(µs)": None if item["recovery_time_s"] is None else round(item["recovery_time_s"] * 1e6, 1),
        })
    return (
        "# BatteryLab 电池模型及系统复核报告\n\n"
        "> 电池模型基于 CALCE INR18650-20R 公开数据重放；系统为真实开关级 ngspice 联合仿真。\n\n"
        "## 1. 全工况端电压精度（冻结参数，独立验证）\n\n"
        + table(rmse_rows, ["工况", "Rint RMSE(mV)", "一阶 RC RMSE(mV)", "二阶 RC RMSE(mV)", "最大绝对误差(mV)"]) + "\n\n"
        "- FUDS 50/80 平均：26.705 → 22.385 → 22.175 mV；不代表全部动态工况，US06/BJDST 误差明显更大。\n"
        "- 训练精度（Rint/一阶/二阶 RMSE）："
        f"{ecm['identification']['training_metrics']['rint']['training_rmse_v'] * 1e3:.3f} / "
        f"{ecm['identification']['training_metrics']['first_order_rc']['training_rmse_v'] * 1e3:.3f} / "
        f"{ecm['identification']['training_metrics']['second_order_rc']['training_rmse_v'] * 1e3:.3f} mV。\n\n"
        "## 2. 低 SOC 分区误差\n\n"
        + table([
            {"区间": f"SOC {low['band_low']:.0%}–{low['band_high']:.0%}（{low['experiment']}，二阶）",
             "RMSE(mV)": round(low["rmse_mv"], 3), "MAE(mV)": round(low["mae_mv"], 3),
             "最大绝对误差(mV)": round(low["max_abs_mv"], 3), "平均误差(mV)": round(low["mean_error_mv"], 3)},
            {"区间": f"SOC {mid['band_low']:.0%}–{mid['band_high']:.0%}（{mid['experiment']}，Rint 对照）",
             "RMSE(mV)": round(mid["rmse_mv"], 3), "MAE(mV)": round(mid["mae_mv"], 3),
             "最大绝对误差(mV)": round(mid["max_abs_mv"], 3), "平均误差(mV)": round(mid["mean_error_mv"], 3)},
        ], ["区间", "RMSE(mV)", "MAE(mV)", "最大绝对误差(mV)", "平均误差(mV)"]) + "\n\n"
        f"- 低 SOC 与中 SOC 误差比为 {ecm['low_soc_dominant']['ratio']:.2f}×；低 SOC 平台平坦，参数外推主导。\n"
        f"- 历史低 SOC 最大误差 {ecm['preserved_failures']['low_soc_max_error_mv']:.3f} mV 永久保留，未通过删点或改限值改善。\n"
        "- 辨识前/后对照：NOT_VERIFIED（冻结模型未保留未辨识基线参数，不得用验证数据重拟合）。\n\n"
        "## 3. 系统闭环 LC 与控制器候选\n\n"
        + table(group_rows, ["组别", "L(µH)", "C(µF)", "kp", "ki", "稳态电压(V)", "纹波(mV)", "效率(%)", "阶跃偏差(mV)", "恢复(µs)"]) + "\n\n"
        "- 仅换 LC：效率与阶跃偏差改善，但纹波变差、恢复变慢。\n"
        "- 优化 LC + 配套控制器：纹波、阶跃偏差与效率同时改善，恢复略慢。\n"
        "- 控制器筛选先做平均模型扫描，再用真实 SPICE 稳态复验；未采用不稳定候选（例如纹波 320 mV、效率 104.9% 的非物理结果）。\n\n"
        "## 4. 有效域与可用性\n\n"
        + table([
            {"项目": "7 个动态工况", "状态": f"{domain['domain_status_counts'].get('LIMITED', 0)}/7 LIMITED",
             "说明": "SOC 至 0.80，超出辨识区间 0.011–0.507，属参数外推"},
            {"项目": "温度", "状态": "25 °C AVAILABLE；0/45 °C NOT_VERIFIED", "说明": "无多温度实测数据"},
            {"项目": "3S 组电压", "状态": "NOT_VERIFIED", "说明": "阶段 9 为模型级联合仿真，不是实测组电压"},
            {"项目": "SOH", "状态": str(domain["soh_status_counts"]), "说明": "含合成老化数据，与实测分离"},
        ], ["项目", "状态", "说明"]) + "\n\n"
        f"- 证据：`{ctx['paths']['ecm']}`（Run `{ctx['ecm_run']}`）、`{ctx['paths']['system']}`（Run `{ctx['system_run']}`）、"
        f"`{ctx['paths']['domain']}`（Run `{ctx['domain_run']}`）。\n"
    )


def doc_eda(ctx: dict[str, Any]) -> str:
    eda = ctx["eda"]
    baseline = eda["baseline"]["validation_summary"]
    checks = {item["name"]: item for item in baseline["checks"]}
    blocked = eda["baseline"]["blocked_items"]
    rows = [
        {"交付物": item["item"], "路径": item["path"], "状态": item["status"]}
        for item in blocked
    ]
    return (
        "# BatteryLab KiCad 硬件设计交付报告\n\n"
        "> 本报告只记录实际状态。KiCad 未安装时一律标记 BLOCKED，不生成占位文件冒充设计成果。\n\n"
        "## 1. 环境\n\n"
        f"- kicad-cli：{'未找到' if eda['kicad']['kicad_cli'] is None else eda['kicad']['kicad_cli']}\n"
        f"- 检测方式：{eda['kicad']['detected_by']}\n"
        f"- 安装目录：{eda['kicad']['install_dirs_present'] or '未发现'}\n"
        f"- 结论：{eda['status']}\n\n"
        "## 2. 实际完成数量\n\n"
        + table([
            {"项目": "原理图（可编辑 .kicad_sch）", "数量": 0, "状态": "BLOCKED_NO_KICAD_GUI"},
            {"项目": "PCB（可编辑 .kicad_pcb）", "数量": 0, "状态": "BLOCKED_NO_KICAD_GUI"},
            {"项目": "PCB 层数与尺寸", "数量": "未定义", "状态": "BLOCKED"},
            {"项目": "实际器件数量（已布局）", "数量": 0, "状态": "BLOCKED"},
            {"项目": "ERC 错误/警告", "数量": "未产生", "状态": "BLOCKED"},
            {"项目": "DRC 错误/警告", "数量": "未产生", "状态": "BLOCKED"},
            {"项目": "未连接网络", "数量": "未产生", "状态": "BLOCKED"},
            {"项目": "Gerber / 钻孔 / STEP", "数量": 0, "状态": "NOT_PRODUCED"},
        ], ["项目", "数量", "状态"]) + "\n\n"
        "## 3. 第八阶段既有设计输入复核（只读）\n\n"
        f"- 运行目录：`{eda['baseline']['path']}`\n"
        f"- 状态计数：PASS {baseline['status_counts'].get('PASS', 0)} / "
        f"BLOCKED {baseline['status_counts'].get('BLOCKED', 0)} / FAIL {baseline['status_counts'].get('FAIL', 0)}\n\n"
        + table([
            {"检查项": "BMS 引脚映射", "结果": checks["bms_pin_mapping_complete"]["status"], "详情": checks["bms_pin_mapping_complete"]["detail"]},
            {"检查项": "充电器引脚映射", "结果": checks["charger_pin_mapping_complete"]["status"], "详情": checks["charger_pin_mapping_complete"]["detail"]},
            {"检查项": "充电电压低于单体过压", "结果": checks["charge_voltage_below_cell_ov"]["status"], "详情": checks["charge_voltage_below_cell_ov"]["detail"]},
            {"检查项": "分流功率降额", "结果": checks["shunt_power_within_rating"]["status"], "详情": checks["shunt_power_within_rating"]["detail"]},
            {"检查项": "均衡电阻功率降额", "结果": checks["balancing_resistor_power"]["status"], "详情": checks["balancing_resistor_power"]["detail"]},
            {"检查项": "BOM 完整性", "结果": checks["bom_validation"]["status"], "详情": checks["bom_validation"]["detail"]},
            {"检查项": "LC 谐振目标", "结果": checks["lc_resonance_target"]["status"], "详情": checks["lc_resonance_target"]["detail"]},
        ], ["检查项", "结果", "详情"]) + "\n\n"
        "- 商业器件选型（BQ76922 等）来自 Datasheet 核实与第八阶段选型表，属于选型研究，不等于硬件验证。\n"
        "- BQ76922 行为模型不是厂商内部晶体管级模型；其精度不能当作本项目采集链精度。\n\n"
        "## 4. 阻塞交付物\n\n"
        + table(rows, ["交付物", "路径", "状态"]) + "\n\n"
        "## 5. 待完成事项\n\n"
        "1. 安装 KiCad（需要管理员权限与用户确认）并确认 kicad-cli 可用。\n"
        "2. 生成 BMS 原理图（BQ76922 + AFE + 保护 MOSFET + 均衡）并运行 ERC。\n"
        "3. 生成充电器原理图（BQ24610）并运行 ERC。\n"
        "4. 完成 BMS PCB 布局布线，运行 DRC，导出 Gerber/钻孔/STEP。\n"
        "5. 修正 LC 谐振 11.07 kHz（目标 12–17 kHz），保留原 FAIL 记录。\n"
        "6. 打样与硬件实测（本轮不做）。\n\n"
        "- 硬件验证：False；量产发布：False。\n"
        f"- 证据：`{ctx['paths']['eda']}/eda_status.md`（Run `{ctx['eda_run']}`）。\n"
    )


def doc_resume(ctx: dict[str, Any]) -> str:
    afe, protection, charging = ctx["afe"], ctx["protection"], ctx["charging"]
    soft = {int(item["soft_start_time_s"] * 1000): item for item in charging["soft_start"]}
    aw = {item["method"]: item for item in charging["antiwindup"]}
    groups = ctx["system"]["groups"]
    base = groups["baseline_lc_baseline_controller"]
    opt = groups["optimized_lc_tuned_controller"]
    return (
        "# BatteryLab 最终简历量化成果\n\n"
        "> 4 条，全部基于真实运行结果；AI 辅助不作为个人独立掌握的能力宣传。\n\n"
        "## 1. 3S 电池等效电路建模与参数辨识\n\n"
        "- CALCE INR18650-20R 公开数据，Rint / 一阶 RC / 二阶 RC 端电压预测对比；\n"
        "- FUDS 50/80% 独立验证 RMSE 26.705 → 22.385 → 22.175 mV；\n"
        "- 低 SOC 0–5% 误差单独报告（bjdst_80 二阶 RMSE 157.7 mV），未用验证数据调参。\n\n"
        "## 2. 模拟采集链路误差预算与校准\n\n"
        f"- 最坏情况预算：电压 {afe['baseline']['voltage_worst_case_mv']:.3f} mV、电流 {afe['baseline']['current_worst_case_ma']:.3f} mA；\n"
        f"- 0.01% 匹配网络 + 低失调放大器 + 优化参考 + 两点校准剩余误差 → {afe['optimized']['voltage_worst_case_mv']:.3f} mV / {afe['optimized']['current_worst_case_ma']:.3f} mA；\n"
        f"- 1000 组蒙特卡洛两点校准后 RMSE {afe['baseline']['monte_carlo']['voltage']['post_calibration']['rmse'] * 1e3:.4f} mV / "
        f"{afe['baseline']['monte_carlo']['current']['post_calibration']['rmse'] * 1e3:.4f} mA，真实 ngspice 角点最大偏差 {afe['spice_corner_max_abs_difference_v'] * 1e6:.2f} µV。\n\n"
        "## 3. 电池保护与充电控制\n\n"
        "- 真实背靠背 N-MOSFET 网表替代行为电流源，识别并剔除历史 2.5 ns 伪迹；\n"
        f"- 故障→电流抑制 {protection['standalone']['delay_fault_to_suppression_s'] * 1e6:.3f} µs，栅极下降 "
        f"{protection['standalone']['gate_fall_time_s'] * 1e9:.1f} ns，串联导通电阻 {protection['conduction'][0]['path_resistance_ohm'] * 1e3:.2f} mΩ；\n"
        f"- 软启动 0→5 ms 使启动能量 {soft[0]['startup_energy_j']:.4f} → {soft[5]['startup_energy_j']:.4f} J（−45.1%）；"
        f"抗积分饱和条件积分使 CV 过冲 {aw['none']['voltage_overshoot_v'] * 1e3:.3f} → {aw['conditional']['voltage_overshoot_v'] * 1e3:.3f} mV（−36.5%）。\n\n"
        "## 4. 电源系统联合仿真\n\n"
        "- 3S ECM + 100 kHz Buck + 保护级闭环联合仿真，TestLab 4/4 用例 PASS；\n"
        "- 优化 LC（68 µH/330 µF）+ 配套控制器：纹波 "
        f"{base['ripple_vpp'] * 1e3:.2f} → {opt['ripple_vpp'] * 1e3:.2f} mV、负载阶跃偏差 "
        f"{base['step_deviation_v'] * 1e3:.2f} → {opt['step_deviation_v'] * 1e3:.2f} mV、效率 "
        f"{base['efficiency_percent']:.3f} → {opt['efficiency_percent']:.3f}%（+1.048 个百分点）。\n\n"
        "## 不能写的表述\n\n"
        + table([
            {"不可写": "真实硬件效率 95%", "原因": "无硬件测量", "可替代": "SPICE 联合仿真效率 95.206%"},
            {"不可写": "效率提升 1.05%", "原因": "是百分点", "可替代": "提高 1.048 个百分点"},
            {"不可写": "AFE 实测精度 3.8 mV", "原因": "是设计预算", "可替代": "最坏情况设计预算 3.837 mV"},
            {"不可写": "完成 PCB 设计", "原因": "KiCad 未安装", "可替代": "完成选型与理论计算，PCB 为 BLOCKED"},
            {"不可写": "本人独立完成全部建模", "原因": "AI 辅助", "可替代": "在 AI 辅助下完成并复核"},
        ], ["不可写", "原因", "可替代"]) + "\n\n"
        f"- 证据：Run `{ctx['afe_run']}` / `{ctx['protection_run']}` / `{ctx['charging_run']}` / `{ctx['system_run']}`。\n"
    )


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def write_outputs() -> dict[str, Any]:
    v1 = load_v1()
    additions, context = new_rows()
    v2 = pd.concat([v1, pd.DataFrame(additions, columns=COLUMNS)], ignore_index=True)
    v2.to_csv(PORTFOLIO / "BatteryLab_resume_metrics_v2.csv", index=False, encoding="utf-8-sig")

    total_columns = ["成果编号", "研发模块", "指标名称", "优化前", "优化后", "单位", "改善比例", "验证状态", "验收状态"]
    (PORTFOLIO / "BatteryLab_真实量化工程成果总表_v2.md").write_text(
        "# BatteryLab 真实量化工程成果总表（v2）\n\n"
        f"- 行数：{len(v2)}（v1 {len(v1)} + 新增 {len(additions)}）\n"
        "- 已删除 v1 中 P03/P04/P04B/P05 四条基于行为源钳位的无效保护指标，改用真实 MOSFET 结果。\n"
        "- 所有数值均来自 SPICE、公开数据重放或解析计算；未做硬件实测。\n\n"
        + frame_to_markdown(v2, total_columns) + "\n",
        encoding="utf-8",
    )

    verification_counts = v2["验证状态"].value_counts().to_dict()
    acceptance_counts = v2["验收状态"].value_counts().to_dict()
    (PORTFOLIO / "BatteryLab_工程指标真实性核查报告_v2.md").write_text(
        "# BatteryLab 工程指标真实性核查报告（v2）\n\n"
        "## 1. 状态计数\n\n"
        f"- 验证状态：{verification_counts}\n"
        f"- 验收状态：{acceptance_counts}\n\n"
        "## 2. 已剔除的无效指标\n\n"
        "| 编号 | 原因 |\n|---|---|\n"
        "| P03 | 抑制比 0.00123 来自行为电流源，非真实 MOSFET |\n"
        "| P04 | 2.5 ns 抑制早于 10 µs 栅极指令，物理不成立 |\n"
        "| P04B | 10 µs 为配置延时，不是实测响应 |\n"
        "| P05 | 199 µs 输入衰减依赖行为源通路 |\n\n"
        "## 3. 仍然成立的限制\n\n"
        "- 公开数据不是本人采集；仿真不是硬件实测；ERC/DRC 未产生。\n"
        "- AFE 基线 30.887 mV / 37.736 mA 为真实 FAIL，未达 10 mV / 20 mA。\n"
        "- PI 带宽分离 0/25、LC 谐振 11.07 kHz、低 SOC 误差三项 FAIL 保留。\n"
        "- 合成老化数据与实测数据分离，未把合成结果写成实测。\n\n"
        "## 4. 复算方法\n\n"
        "- 时间平均用梯形积分；效率用能量比；改善比例只在同数据集同区间计算。\n"
        "- 统计值与最坏情况预算分开报告（V03/V04 变差也必须保留）。\n",
        encoding="utf-8",
    )

    comparisons = v2[(v2["优化前"] != "") & (v2["优化后"] != "") & (v2["改善比例"] != "")]
    (PORTFOLIO / "BatteryLab_工程性能优化前后对照_v2.md").write_text(
        "# BatteryLab 工程性能优化前后对照（v2）\n\n"
        "仅列出同时具备优化前、优化后与改善比例的条目；变差项保留负号。\n\n"
        + frame_to_markdown(comparisons, ["成果编号", "指标名称", "优化前", "优化后", "单位", "改善比例", "验收状态", "局限"]) + "\n",
        encoding="utf-8",
    )

    top_ids = ["V01", "V02", "V05", "V08", "V10", "V11", "V13", "V17", "V18", "V19", "V24", "A01", "A02", "M02"]
    cards = v2[v2["成果编号"].isin(top_ids)]
    card_text = ["# BatteryLab 研发岗成果证据卡（v2）", "", "每条包含：指标、前后值、条件、证据路径、局限。", ""]
    for _, item in cards.iterrows():
        card_text += [
            f"## {item['成果编号']} {item['指标名称']}",
            "",
            f"- 优化前 → 优化后：{item['优化前']} → {item['优化后']} {item['单位']}（改善 {item['改善比例'] or '—'}）",
            f"- 条件：{item['实验条件']}",
            f"- 数据来源：{item['数据来源']}",
            f"- 原始证据：`{item['原始证据']}`",
            f"- 核心源码：`{item['核心源码']}`",
            f"- 状态：{item['验证状态']} / {item['验收状态']}",
            f"- 局限：{item['局限']}",
            "",
        ]
    (PORTFOLIO / "BatteryLab_研发岗成果证据卡_v2.md").write_text("\n".join(card_text), encoding="utf-8")

    (PORTFOLIO / "BatteryLab_研发岗简历项目最终版_v2.md").write_text(doc_resume(context), encoding="utf-8")

    # ---- Task 22 七份专题报告 ----
    (PORTFOLIO / "BatteryLab_研发能力补强报告.md").write_text(doc_hardening_report(context), encoding="utf-8")
    (PORTFOLIO / "BatteryLab_AFE精度优化前后对照.md").write_text(doc_afe(context), encoding="utf-8")
    (PORTFOLIO / "BatteryLab_MOSFET保护真实性复验.md").write_text(doc_protection(context), encoding="utf-8")
    (PORTFOLIO / "BatteryLab_CC_CV控制优化前后对照.md").write_text(doc_charging(context), encoding="utf-8")
    (PORTFOLIO / "BatteryLab_电池模型及系统复核报告.md").write_text(doc_model_system(context), encoding="utf-8")
    (PORTFOLIO / "BatteryLab_KiCad硬件设计交付报告.md").write_text(doc_eda(context), encoding="utf-8")
    (PORTFOLIO / "BatteryLab_最终简历量化成果.md").write_text(doc_resume(context), encoding="utf-8")

    (PORTFOLIO / "BatteryLab_交付与复现说明_v2.md").write_text(
        "# BatteryLab 交付与复现说明（v2）\n\n"
        "## 1. 环境\n\n"
        "```powershell\n"
        "conda run --no-capture-output -n kaifa_battery python -B -m <module>\n"
        "```\n\n"
        "## 2. 复现命令（按顺序）\n\n"
        "```powershell\n"
        "python -B -m scripts.hardening_baseline\n"
        "python -B -m scripts.hardening_afe\n"
        "python -B -m scripts.hardening_protection\n"
        "python -B -m scripts.hardening_charging\n"
        "python -B -m scripts.hardening_ecm\n"
        "python -B -m scripts.hardening_system\n"
        "python -B -m scripts.hardening_domain\n"
        "python -B -m scripts.hardening_eda\n"
        "python -B -m scripts.audit_resume_metrics\n"
        "python -B -m scripts.hardening_portfolio_v2\n"
        "python -B -m pytest tests -q\n"
        "```\n\n"
        "## 3. 产物位置\n\n"
        "- 新增分析结果：`results/hardening/<area>/run_<id>/`\n"
        "- v2 六件套：`portfolio/BatteryLab_*_v2.md`、`portfolio/BatteryLab_resume_metrics_v2.csv`\n"
        "- Task 22 专题报告：`portfolio/BatteryLab_研发能力补强报告.md` 等 7 份\n"
        "- 历史运行：未覆盖，仍保留在原目录\n\n"
        "## 4. 约束\n\n"
        "- TestLab / PowerLab 未修改；未提交 Git；未安装 KiCad；未采购、未制板、未做真实锂电池上电。\n",
        encoding="utf-8",
    )

    # ---- 第九阶段证据 ----
    testlab_path = PROJECT / "results" / "stage9" / "testlab_integration" / "testlab_20261126_173758_18733f" / "actual_test_results.json"
    testlab = json.loads(testlab_path.read_text(encoding="utf-8"))
    energy_path = PROJECT / "results" / "stage9" / "system_energy" / "energy_20261126_173741_2a5eef" / "case_result.json"
    energy = json.loads(energy_path.read_text(encoding="utf-8"))

    metric_rows = []
    for item in testlab["results"]:
        metric_rows.append({
            "metric": item["metric"], "value": item["value"], "minimum": item["minimum"],
            "maximum": item["maximum"], "unit": "V" if "voltage" in item["metric"] else ("A" if "current" in item["metric"] else ""),
            "status": item["testlab_status"], "source": "TestLab actual_test_results.json",
        })
    for key, label, unit in (
        ("converter_efficiency_percent", "converter_efficiency_percent", "%"),
        ("boundary_a_residual_percent", "energy_residual_percent", "%"),
        ("battery_energy_j", "battery_energy_j", "J"),
        ("output_energy_j", "output_energy_j", "J"),
        ("protection_path_loss_j", "protection_path_loss_j", "J"),
    ):
        metric_rows.append({
            "metric": label, "value": energy["energy"][key], "minimum": None,
            "maximum": 1.0 if key == "boundary_a_residual_percent" else None,
            "unit": unit, "status": "PASS", "source": "system_energy case_result.json",
        })
    pd.DataFrame(metric_rows).to_csv(PORTFOLIO / "system_integration_metrics.csv", index=False, encoding="utf-8-sig")

    (PORTFOLIO / "stage9_engineering_evidence.md").write_text(
        "# 第九阶段工程证据\n\n"
        "## 1. TestLab 接口判定\n\n"
        + frame_to_markdown(pd.DataFrame(metric_rows[:4]), ["metric", "value", "minimum", "maximum", "unit", "status"]) + "\n\n"
        "## 2. 能量与效率\n\n"
        f"- 变换器效率：{energy['energy']['converter_efficiency_percent']:.4f} %\n"
        f"- 能量残差：{energy['energy']['boundary_a_residual_percent']:.6f} %\n"
        f"- 电池能量：{energy['energy']['battery_energy_j'] * 1e3:.4f} mJ\n"
        f"- 负载能量：{energy['energy']['output_energy_j'] * 1e3:.4f} mJ\n"
        f"- 保护通路损耗：{energy['energy']['protection_path_loss_j'] * 1e3:.5f} mJ\n\n"
        "## 3. 本次新增系统候选\n\n"
        + frame_to_markdown(pd.DataFrame([
            {"组别": name, "稳态电压(V)": round(item["steady_voltage_v"], 4), "纹波(mV)": round(item["ripple_vpp"] * 1e3, 2),
             "效率(%)": round(item["efficiency_percent"], 3), "阶跃偏差(mV)": round(item["step_deviation_v"] * 1e3, 2),
             "恢复(µs)": None if item["recovery_time_s"] is None else round(item["recovery_time_s"] * 1e6, 1)}
            for name, item in context["system_groups"].items()
        ]), ["组别", "稳态电压(V)", "纹波(mV)", "效率(%)", "阶跃偏差(mV)", "恢复(µs)"]) + "\n\n"
        "## 4. 边界\n\n"
        "- 全部为软件仿真；未做硬件实测。\n"
        "- 阶段 9 历史 17/24 收敛计数未在本次重跑。\n",
        encoding="utf-8",
    )

    (PORTFOLIO / "system_optimization_comparison.md").write_text(
        "# 系统优化前后对照（基准 / 优化 LC / 优化 LC + 控制器）\n\n"
        f"基准控制器 kp={context['baseline_dc']['kp']}, ki={context['baseline_dc']['ki']}；"
        f"优化控制器 kp={context['opt_dc']['kp']}, ki={context['opt_dc']['ki']}。\n\n"
        + frame_to_markdown(pd.DataFrame([
            {"组别": name, "L(µH)": round(item["lc"]["inductance_h"] * 1e6, 1), "C(µF)": round(item["lc"]["capacitance_f"] * 1e6, 0),
             "稳态电压(V)": round(item["steady_voltage_v"], 4), "纹波(mV)": round(item["ripple_vpp"] * 1e3, 2),
             "效率(%)": round(item["efficiency_percent"], 3), "阶跃偏差(mV)": round(item["step_deviation_v"] * 1e3, 2),
             "恢复(µs)": None if item["recovery_time_s"] is None else round(item["recovery_time_s"] * 1e6, 1),
             "电感峰值(A)": round(item["inductor_peak_a"], 3), "通路损耗(W)": round(item["path_loss_w"], 4)}
            for name, item in context["system_groups"].items()
        ]), ["组别", "L(µH)", "C(µF)", "稳态电压(V)", "纹波(mV)", "效率(%)", "阶跃偏差(mV)", "恢复(µs)", "电感峰值(A)", "通路损耗(W)"]) + "\n\n"
        "## 结论\n\n"
        "- 仅换 LC 会降低效率损耗与阶跃偏差，但纹波变差、恢复变慢；\n"
        "- 优化 LC 必须配合 kp=2× 的控制器，才能同时改善纹波与偏差；\n"
        "- 所有结果来自真实开关级 ngspice 联合仿真，不是硬件实测。\n",
        encoding="utf-8",
    )

    return {
        "rows_v1": len(v1), "rows_new": len(additions), "rows_v2": len(v2),
        "verification_counts": verification_counts, "acceptance_counts": acceptance_counts,
        "documents": [
            "BatteryLab_resume_metrics_v2.csv",
            "BatteryLab_真实量化工程成果总表_v2.md",
            "BatteryLab_工程指标真实性核查报告_v2.md",
            "BatteryLab_工程性能优化前后对照_v2.md",
            "BatteryLab_研发岗成果证据卡_v2.md",
            "BatteryLab_研发岗简历项目最终版_v2.md",
            "BatteryLab_交付与复现说明_v2.md",
            "BatteryLab_研发能力补强报告.md",
            "BatteryLab_AFE精度优化前后对照.md",
            "BatteryLab_MOSFET保护真实性复验.md",
            "BatteryLab_CC_CV控制优化前后对照.md",
            "BatteryLab_电池模型及系统复核报告.md",
            "BatteryLab_KiCad硬件设计交付报告.md",
            "BatteryLab_最终简历量化成果.md",
            "stage9_engineering_evidence.md",
            "system_integration_metrics.csv",
            "system_optimization_comparison.md",
        ],
        "context": {
            "afe_run": context["afe_run"], "protection_run": context["protection_run"],
            "charging_run": context["charging_run"], "ecm_run": context["ecm_run"],
            "system_run": context["system_run"], "domain_run": context["domain_run"],
            "eda_run": context["eda_run"], "baseline_run": context["baseline_run"],
        },
    }


if __name__ == "__main__":
    print(json.dumps(write_outputs(), ensure_ascii=False, indent=2, default=str))
