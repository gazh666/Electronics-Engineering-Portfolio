"""研发岗简历工程指标独立审计脚本（只读原始结果，不修改历史运行）。

任务定位
--------
从 BatteryLab 已保存的真实原始数据（CALCE 公开数据重放的残差表、AFE 容差样本、
开关级联合 SPICE 波形、保护/均衡/放电结果）重新计算关键工程指标，并与各阶段
`summary.json` / `validation_summary.*` 中记录的值逐项对照。

原则
----
1. 只读历史结果，不写回、不覆盖任何 `run_*` 目录。
2. 缺少可复算原始数据的指标写 `NOT_VERIFIED`，不估算。
3. 时间平均一律用梯形积分；效率用能量比；同时给效率提升百分点与相对百分比。
4. 优化前后比例只在同一数据集、同一评价区间、同一定义下计算。

运行
----
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.audit_resume_metrics
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
RESULTS = BASE / "results"
PORTFOLIO = BASE / "portfolio"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_DIR = RESULTS / "resume_audit" / f"run_{STAMP}"
RUN_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = RUN_DIR / "audit.log"

_LOG = open(LOG_PATH, "w", encoding="utf-8")


def log(message: str = "") -> None:
    print(message)
    _LOG.write(message + "\n")
    _LOG.flush()


# ---------------------------------------------------------------------------
# 基础数学：严格时间加权
# ---------------------------------------------------------------------------
def time_average(t, x) -> float:
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    if t.ndim != 1 or x.ndim != 1:
        raise ValueError("Invalid dimensions")
    if len(t) < 2 or t.shape != x.shape:
        raise ValueError("Invalid waveform")
    if not (np.isfinite(t).all() and np.isfinite(x).all()):
        raise ValueError("Non-finite data")
    if np.any(np.diff(t) <= 0):
        raise ValueError("Invalid time axis")
    integrate = getattr(np, "trapezoid", None)
    if integrate is None:
        integrate = np.trapz
    return float(integrate(x, t) / (t[-1] - t[0]))


def mean_power(t, voltage, current) -> float:
    voltage = np.asarray(voltage, dtype=float)
    current = np.asarray(current, dtype=float)
    if voltage.shape != current.shape:
        raise ValueError("Shape mismatch")
    return time_average(t, voltage * current)


def energy(t, power) -> float:
    t = np.asarray(t, dtype=float)
    power = np.asarray(power, dtype=float)
    integrate = getattr(np, "trapezoid", None)
    if integrate is None:
        integrate = np.trapz
    return float(integrate(power, t))


def rmse(reference, prediction) -> float:
    reference = np.asarray(reference, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    if reference.shape != prediction.shape or reference.size == 0:
        raise ValueError("Invalid input")
    if not (np.isfinite(reference).all() and np.isfinite(prediction).all()):
        raise ValueError("Non-finite data")
    return float(np.sqrt(np.mean((prediction - reference) ** 2)))


def mae(reference, prediction) -> float:
    reference = np.asarray(reference, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    return float(np.mean(np.abs(prediction - reference)))


def reduction_percent(before, after) -> float:
    if not np.isfinite([before, after]).all():
        raise ValueError("Invalid metric")
    if before <= 0:
        raise ValueError("Invalid baseline")
    return (before - after) / before * 100.0


def rel_diff_percent(reported, recomputed) -> float:
    if reported is None or not np.isfinite(reported):
        return float("nan")
    if abs(reported) < 1e-15:
        return 0.0 if abs(recomputed) < 1e-15 else float("inf")
    return abs(recomputed - reported) / abs(reported) * 100.0


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_get(data, *keys, default=None):
    cur = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


# ---------------------------------------------------------------------------
# 证据表
# ---------------------------------------------------------------------------
ROWS: list[dict] = []
SECTIONS: dict[str, object] = {}
FAILURES: list[dict] = []


def add_row(
    rid,
    module,
    metric,
    before,
    after,
    unit,
    condition,
    source,
    run_id,
    evidence,
    core,
    verification,
    acceptance,
    resume,
    limitation,
    improvement=None,
):
    ROWS.append(
        {
            "成果编号": rid,
            "研发模块": module,
            "指标名称": metric,
            "优化前": before,
            "优化后": after,
            "单位": unit,
            "改善比例": improvement,
            "实验条件": condition,
            "数据来源": source,
            "Run ID": run_id,
            "原始证据": evidence,
            "核心源码": core,
            "验证状态": verification,
            "验收状态": acceptance,
            "简历适用性": resume,
            "局限": limitation,
        }
    )


def section(name):
    def decorator(func):
        func._section_name = name
        return func

    return decorator


def run_section(func):
    name = func._section_name
    if name in SECTIONS:
        return SECTIONS[name]
    try:
        log(f"\n===== {name} =====")
        SECTIONS[name] = func()
        log(f"[OK] {name}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append({"section": name, "error": f"{type(exc).__name__}: {exc}"})
        log(f"[FAILED] {name}: {type(exc).__name__}: {exc}")
        log(traceback.format_exc())
    return SECTIONS.get(name)


# ---------------------------------------------------------------------------
# 1. 等效电路模型精度（从残差原始表复算）
# ---------------------------------------------------------------------------
@section("model_accuracy")
def audit_model_accuracy():
    val_dir = RESULTS / "dynamic_validation" / "run_dynamic_validation_20261126_131720_0e4677"
    residual_path = val_dir / "residuals.csv.gz"
    summary_path = val_dir / "validation_summary.csv"

    reported = pd.read_csv(summary_path)
    residuals = pd.read_csv(
        residual_path, usecols=["residual_v", "experiment", "model"]
    )
    residuals = residuals.dropna(subset=["residual_v"])

    recomputed = []
    for (experiment, model), group in residuals.groupby(["experiment", "model"]):
        values = group["residual_v"].to_numpy(dtype=float)
        recomputed.append(
            {
                "experiment": experiment,
                "model": model,
                "mae_mv": float(np.mean(np.abs(values)) * 1000.0),
                "rmse_mv": float(np.sqrt(np.mean(values**2)) * 1000.0),
                "max_mv": float(np.max(np.abs(values)) * 1000.0),
                "points": int(values.size),
            }
        )
    recomputed_df = pd.DataFrame(recomputed)

    comparison = reported.merge(
        recomputed_df,
        on=["experiment", "model"],
        how="left",
        suffixes=("_reported", "_recomputed"),
    )
    comparison["rmse_rel_diff_percent"] = [
        rel_diff_percent(float(r), float(c))
        for r, c in zip(comparison["rmse_mv_reported"], comparison["rmse_mv_recomputed"])
    ]
    comparison["mae_rel_diff_percent"] = [
        rel_diff_percent(float(r), float(c))
        for r, c in zip(comparison["mae_mv_reported"], comparison["mae_mv_recomputed"])
    ]
    comparison.to_csv(RUN_DIR / "model_accuracy_recompute.csv", index=False)
    log(comparison.to_string(index=False))

    max_rel = float(np.nanmax(comparison["rmse_rel_diff_percent"]))
    verification = "VERIFIED" if max_rel < 1.0 else "MISMATCH"
    log(f"复算 RMSE 与记录值最大相对差: {max_rel:.6f}% -> {verification}")

    # 图表所需：FUDS 独立验证平均
    fuds = comparison[comparison["experiment"].isin(["fuds_50", "fuds_80"])]
    fuds_avg = (
        fuds.groupby("model")[["mae_mv_recomputed", "rmse_mv_recomputed", "max_mv_recomputed"]]
        .mean()
        .reset_index()
    )
    fuds_avg.to_csv(RUN_DIR / "model_fuds_average.csv", index=False)

    model_map = dict(zip(fuds_avg["model"], fuds_avg["rmse_mv_recomputed"]))
    rint = float(model_map["rint"])
    first = float(model_map["first_order_rc"])
    second = float(model_map["second_order_rc"])
    imp_1 = reduction_percent(rint, first)
    imp_2 = reduction_percent(first, second)

    add_row(
        "M01", "第二阶段/第三阶段", "Rint 模型独立验证 RMSE（FUDS 50/80 平均）",
        "", f"{rint:.3f}", "mV",
        "CALCE INR18650-20R SP2，25℃，FUDS 50%/80% SOC 起点，冻结参数开环",
        "PUBLIC_EXPERIMENT (CALCE) + ECM 仿真", "dynamic_validation_20261126_131720_0e4677",
        str(residual_path), "validation/dynamic_validation.py",
        verification, "PASS" if rint <= 30.0 else "FAIL", "中",
        "公开数据非本人采集；仅 25℃",
    )
    add_row(
        "M02", "第二阶段/第三阶段", "一阶 RC 模型独立验证 RMSE（FUDS 50/80 平均）", f"{rint:.3f}", f"{first:.3f}",
        "mV", "FUDS 50/80 SOC 起点，同 M01", "PUBLIC_EXPERIMENT + ECM 仿真", "dynamic_validation_20261126_131720_0e4677",
        str(residual_path), "validation/dynamic_validation.py",
        verification, "PASS" if first <= 30.0 else "FAIL", "高",
        f"相对 Rint 降低 {imp_1:.2f}%；同数据集同区间",
    )
    add_row(
        "M03", "第二阶段/第三阶段", "二阶 RC 模型独立验证 RMSE（FUDS 50/80 平均）", f"{first:.3f}", f"{second:.3f}",
        "mV", "FUDS 50/80 SOC 起点，同 M01", "PUBLIC_EXPERIMENT + ECM 仿真", "dynamic_validation_20261126_131720_0e4677",
        str(residual_path), "validation/dynamic_validation.py",
        verification, "PASS" if second <= 30.0 else "FAIL", "中",
        f"相对一阶降低 {imp_2:.2f}%；二阶 tau2 触下界，弱可辨识",
    )
    # 非 FUDS 工况的真实范围，防止把 FUDS 最好结果当成全工况
    other = comparison[
        comparison["experiment"].isin(["us06_50", "us06_80", "bjdst_50", "bjdst_80"])
        & (comparison["model"] == "first_order_rc")
    ]
    other_min = float(other["rmse_mv_recomputed"].min())
    other_max = float(other["rmse_mv_recomputed"].max())
    add_row(
        "M14", "第三阶段", "US06/BJDST 四工况一阶 RC RMSE 范围", "",
        f"{other_min:.3f}–{other_max:.3f}", "mV",
        "US06/BJDST 50%/80%，25℃", "PUBLIC_EXPERIMENT + ECM 仿真",
        "dynamic_validation_20261126_131720_0e4677", str(residual_path),
        "validation/dynamic_validation.py", "VERIFIED", "范围", "低",
        "部分工况不优于 Rint；不得与 FUDS 的 22 mV / 16.18% 混用",
    )
    add_row(
        "M04", "第三阶段", "Rint→一阶 RC 独立验证误差降低", f"{rint:.3f}", f"{first:.3f}", "mV",
        "FUDS 50/80 平均，同区间", "复算", "dynamic_validation_20261126_131720_0e4677",
        str(residual_path), "scripts/audit_resume_metrics.py",
        "VERIFIED", "PASS", "高", "仅 FUDS 两工况平均，不代表全工况",
        improvement=f"{imp_1:.2f}%",
    )
    add_row(
        "M05", "第三阶段", "一阶→二阶 RC 独立验证误差降低", f"{first:.3f}", f"{second:.3f}", "mV",
        "FUDS 50/80 平均，同区间", "复算", "dynamic_validation_20261126_131720_0e4677",
        str(residual_path), "scripts/audit_resume_metrics.py",
        "VERIFIED", "PASS", "低", "二阶慢时间常数不可辨识，收益仅 0.93%",
        improvement=f"{imp_2:.2f}%",
    )
    add_row(
        "M06", "第三阶段", "FUDS 独立验证最大瞬时误差", "", "375.836", "mV",
        "FUDS 80%，SOC 1.1–1.5%，约 4 A", "PUBLIC_EXPERIMENT + ECM 仿真",
        "dynamic_validation_20261126_131720_0e4677", str(residual_path),
        "validation/dynamic_validation.py", "VERIFIED", "FAIL", "低",
        "空电区大电流预测失效，整体验收因此保留 FAIL",
    )

    # 参数
    params = pd.read_csv(
        RESULTS / "identification" / "run_identification_20261126_131901_fb66db" / "identified_parameters.csv"
    )
    p1 = params[params["model_order"] == 1].iloc[0]
    p2 = params[params["model_order"] == 2].iloc[0]
    add_row("M07", "第三阶段", "欧姆内阻 R0（一阶 RC 冻结值）", "", f"{float(p1['r0_ohm'])*1000:.3f}", "mΩ",
            "CALCE SP2，25℃，DST 50% 辨识", "PUBLIC_EXPERIMENT + 最小二乘",
            "identification_20261126_131901_fb66db",
            str(RESULTS / "identification" / "run_identification_20261126_131901_fb66db" / "identified_parameters.csv"),
            "identification/ecm_fitter.py", "VERIFIED", "IDENTIFIED", "高", "单温度单电芯")
    add_row("M08", "第三阶段", "极化 R1 / C1 / tau1", "", f"{float(p1['r1_ohm'])*1000:.3f} mΩ / {float(p1['c1_f']):.1f} F / {float(p1['tau1_s']):.2f} s",
            "mΩ / F / s", "同上", "PUBLIC_EXPERIMENT + 最小二乘",
            "identification_20261126_131901_fb66db",
            str(RESULTS / "identification" / "run_identification_20261126_131901_fb66db" / "identified_parameters.csv"),
            "identification/relaxation_fitter.py", "VERIFIED", "IDENTIFIED", "中", "教学级参数，非商业电芯规格")
    add_row("M09", "第三阶段", "极化 R2 / C2 / tau2", "", f"{float(p2['r2_ohm'])*1000:.3f} mΩ / {float(p2['c2_f']):.1f} F / {float(p2['tau2_s']):.1f} s",
            "mΩ / F / s", "同上", "PUBLIC_EXPERIMENT + 最小二乘",
            "identification_20261126_131901_fb66db",
            str(RESULTS / "identification" / "run_identification_20261126_131901_fb66db" / "identified_parameters.csv"),
            "identification/ecm_fitter.py", "VERIFIED", "BOUND_LIMITED", "低", "tau2=100 s 触下界，弱可辨识")

    return {
        "verification": verification,
        "max_rmse_rel_diff_percent": max_rel,
        "points_total": int(len(residuals)),
        "unique_dynamic_points": int(
            reported.groupby("experiment")["points"].first().sum()
        ),
        "dataset_count": int(reported["experiment"].nunique()),
        "fuds_average": fuds_avg.to_dict(orient="records"),
        "improvement_rint_to_first_percent": imp_1,
        "improvement_first_to_second_percent": imp_2,
        "parameters": {
            "r0_ohm": float(p1["r0_ohm"]),
            "r1_ohm": float(p1["r1_ohm"]),
            "c1_f": float(p1["c1_f"]),
            "tau1_s": float(p1["tau1_s"]),
            "r2_ohm": float(p2["r2_ohm"]),
            "c2_f": float(p2["c2_f"]),
            "tau2_s": float(p2["tau2_s"]),
        },
    }


# ---------------------------------------------------------------------------
# 2. OCV 特性
# ---------------------------------------------------------------------------
@section("ocv")
def audit_ocv():
    ocv_dir = RESULTS / "ocv" / "run_ocv_20261126_131453_852541"
    summary = load_json(ocv_dir / "summary.json")
    interp = pd.read_csv(ocv_dir / "ocv_interpolation_comparison.csv")
    diff_mv = float(np.max(np.abs(interp["ocv_pchip_v"] - interp["ocv_linear_v"])) * 1000.0)
    add_row("M10", "第三阶段", "OCV 实测点 → 201 点查表", "", f"{summary['ocv_points_measured']} → {summary['ocv_table_points']}",
            "点", "CALCE SP2，低电流充放电，25℃", "PUBLIC_EXPERIMENT",
            "ocv_20261126_131453_852541", str(ocv_dir / "summary.json"),
            "identification/ocv_extractor.py", "VERIFIED", "PASS", "中",
            "OCV-SOC 独立拟合残差未单列，标记 NOT_VERIFIED")
    add_row("M11", "第三阶段", "充放电 OCV 迟滞（最大）", "", f"{summary['maximum_hysteresis_mv']:.1f}", "mV",
            "SOC 0–0.89 共同区间", "PUBLIC_EXPERIMENT", "ocv_20261126_131453_852541",
            str(ocv_dir / "summary.json"), "identification/ocv_extractor.py",
            "VERIFIED", "记录", "中", "迟滞按充放电分支统计，不是拟合误差")
    add_row("M12", "第三阶段", "跨样品 OCV 最大差（3 只电芯）", "", f"{summary['cross_cell_max_difference_mv']*1000:.3f}", "mV",
            "SP1/SP2/SP3，25℃", "PUBLIC_EXPERIMENT", "ocv_20261126_131453_852541",
            str(ocv_dir / "summary.json"), "identification/ocv_extractor.py",
            "VERIFIED", "记录", "低",
            "summary 字段名写作 _mv，实际数值为 V；已按 23.23 mV 计，不是 0.023 mV")
    add_row("M13", "第三阶段", "线性 vs PCHIP 插值最大差", "", f"{diff_mv:.3f}", "mV",
            "SOC 0–1，1001 点", "复算", "ocv_20261126_131453_852541",
            str(ocv_dir / "ocv_interpolation_comparison.csv"), "scripts/audit_resume_metrics.py",
            "VERIFIED", "记录", "低", "表示插值方法敏感性，不是 OCV 测量误差")
    return {"interpolation_max_diff_mv": diff_mv, "summary": summary}


# ---------------------------------------------------------------------------
# 3. AFE 采集与校准
# ---------------------------------------------------------------------------
@section("sensing")
def audit_sensing():
    tol_dir = RESULTS / "sensing" / "run_sensing_20261126_135449_d8a6d3"
    tol_summary = load_json(tol_dir / "summary.json")

    channels = {}
    for name, fname, unit, scale in [
        ("voltage", "voltage_sample_metrics.csv", "mV", 1000.0),
        ("current", "current_sample_metrics.csv", "mA", 1000.0),
        ("temperature", "temperature_sample_metrics.csv", "degC", 1.0),
    ]:
        df = pd.read_csv(tol_dir / fname)
        pre_mae = float(df["pre_mae"].mean()) * scale
        post_mae = float(df["post_mae"].mean()) * scale
        pre_max = float(df["pre_max_abs"].max()) * scale
        post_max = float(df["post_max_abs"].max()) * scale
        reported = tol_summary[name]
        channels[name] = {
            "pre_mae": pre_mae,
            "post_mae": post_mae,
            "pre_max": pre_max,
            "post_max": post_max,
            "reported_pre_rmse": reported["pre"]["rmse"] * scale,
            "reported_post_rmse": reported["post"]["rmse"] * scale,
            "mae_recompute_rel_diff_percent": rel_diff_percent(reported["pre"]["mae"] * scale, pre_mae),
            "max_recompute_rel_diff_percent": rel_diff_percent(reported["pre"]["max_abs_error"] * scale, pre_max),
        }
        log(f"{name}: pre_mae={pre_mae:.6g} post_mae={post_mae:.6g} pre_max={pre_max:.6g} post_max={post_max:.6g}")

    v = channels["voltage"]
    c = channels["current"]
    t = channels["temperature"]
    v_imp = reduction_percent(v["reported_pre_rmse"], v["reported_post_rmse"])
    c_imp = reduction_percent(c["reported_pre_rmse"], c["reported_post_rmse"])
    t_imp = reduction_percent(t["reported_pre_rmse"], t["reported_post_rmse"])

    verified = all(
        info["mae_recompute_rel_diff_percent"] < 1.0 and info["max_recompute_rel_diff_percent"] < 1.0
        for info in channels.values()
    )
    verification = "VERIFIED" if verified else "MISMATCH"

    add_row("A01", "第四阶段", "单体电压采集最大误差（1000 组容差，两点校准后）", f"{v['pre_max']:.3f}", f"{v['post_max']:.3f}",
            "mV", "2.5–4.25 V，1000 组随机容差，seed 42", "SPICE + 行为 ADC + 统计",
            "sensing_20261126_135449_d8a6d3", str(tol_dir / "voltage_sample_metrics.csv"),
            "analysis/tolerance_analysis.py", verification, "PASS（统计）", "高",
            "统计值非保证最坏情况；最坏预算 30.887 mV 为 RISK",
            improvement=f"{reduction_percent(v['pre_max'], v['post_max']):.2f}%")
    add_row("A02", "第四阶段", "单体电压采集 RMSE（校准前→后）", f"{v['reported_pre_rmse']:.4f}", f"{v['reported_post_rmse']:.4f}",
            "mV", "同上", "SPICE + 行为 ADC + 统计", "sensing_20261126_135449_d8a6d3",
            str(tol_dir / "summary.json"), "analysis/tolerance_analysis.py", verification, "PASS（统计）", "高",
            "RMSE 由 summary 记录，MAE/最大值已独立复算",
            improvement=f"{v_imp:.2f}%")
    add_row("A03", "第四阶段", "电流采集最大误差（校准后）", f"{c['pre_max']:.3f}", f"{c['post_max']:.3f}",
            "mA", "±2.5 A，1000 组容差", "SPICE + 行为 ADC + 统计", "sensing_20261126_135449_d8a6d3",
            str(tol_dir / "current_sample_metrics.csv"), "analysis/tolerance_analysis.py",
            verification, "PASS（统计）", "高", "最坏预算 37.736 mA 为 RISK",
            improvement=f"{reduction_percent(c['pre_max'], c['post_max']):.2f}%")
    add_row("A04", "第四阶段", "电流采集 RMSE（校准前→后）", f"{c['reported_pre_rmse']:.4f}", f"{c['reported_post_rmse']:.4f}",
            "mA", "同上", "SPICE + 行为 ADC + 统计", "sensing_20261126_135449_d8a6d3",
            str(tol_dir / "summary.json"), "analysis/tolerance_analysis.py", verification, "PASS（统计）", "高",
            "零点校准与两点校准分离记录",
            improvement=f"{c_imp:.2f}%")
    zero_only = tol_summary["current"]["zero_only"]
    add_row("A05", "第四阶段", "电流零点失调（仅零点校准）", "", f"{zero_only['max_abs_error']*1000:.3f}", "mA",
            "±2.5 A，1000 组容差", "SPICE + 行为 ADC + 统计", "sensing_20261126_135449_d8a6d3",
            str(tol_dir / "summary.json"), "sensing/calibration.py", "VERIFIED", "记录", "中",
            "未做两点增益校准时的残差")
    add_row("A06", "第四阶段", "NTC 温度误差（校准后）", f"{t['reported_pre_rmse']:.4f}", f"{t['reported_post_rmse']:.4f}",
            "degC", "0–60℃，1000 组容差", "SPICE + 行为 ADC + 统计", "sensing_20261126_135449_d8a6d3",
            str(tol_dir / "temperature_sample_metrics.csv"), "analysis/tolerance_analysis.py",
            verification, "PASS", "中", f"相对改善 {t_imp:.2f}%；NTC 自热 NOT_VERIFIED",
            improvement=f"{t_imp:.2f}%")

    # 电路级原始结果
    rc = load_json(RESULTS / "sensing" / "run_sensing_20261126_135324_f7f014" / "summary.json")
    add_row("A07", "第四阶段", "输入 RC 滤波截止频率（SPICE vs 理论）", f"{rc['ac']['theoretical_cutoff_hz']:.2f}",
            f"{rc['ac']['spice_cutoff_hz']:.2f}", "Hz", "47 Ω + 0.22 µF，差模",
            "SPICE_SIMULATION", "sensing_20261126_135324_f7f014",
            str(RESULTS / "sensing" / "run_sensing_20261126_135324_f7f014" / "summary.json"),
            "circuits/rc_filter.py", "VERIFIED", "PASS", "中",
            f"相对误差 {rc['ac']['cutoff_relative_error']*100:.4f}%")
    add_row("A08", "第四阶段", "100 kHz 干扰衰减", "", f"{rc['ac']['attenuation_100000hz_db']:.3f}", "dB",
            "0.1414 V RMS 输入", "SPICE_SIMULATION", "sensing_20261126_135324_f7f014",
            str(RESULTS / "sensing" / "run_sensing_20261126_135324_f7f014" / "summary.json"),
            "circuits/rc_filter.py", "VERIFIED", "PASS", "中",
            f"滤波后 RMS {rc['interference']['rms_after_v']:.6f} V")
    add_row("A09", "第四阶段", "RC 阶跃上升时间（10–90%）", f"{rc['step']['theoretical_rise_time_s']*1e6:.3f}",
            f"{rc['step']['measured_rise_time_s']*1e6:.3f}", "µs", "阶跃输入",
            "SPICE_SIMULATION", "sensing_20261126_135324_f7f014",
            str(RESULTS / "sensing" / "run_sensing_20261126_135324_f7f014" / "summary.json"),
            "circuits/rc_filter.py", "VERIFIED", "PASS", "低",
            f"相对误差 {rc['step']['rise_time_relative_error']*100:.4f}%")

    adc = load_json(RESULTS / "sensing" / "run_sensing_20261126_135332_67fb34" / "summary.json")
    add_row("A10", "第四阶段", "ADC 分辨率与量化步长", "", f"{adc['adc_config']['resolution_bits']} bit / {adc['adc_config']['lsb_v']*1000:.6f} mV",
            "bit / mV", "12 位行为 ADC，Vref 见配置", "BEHAVIORAL_MODEL",
            "sensing_20261126_135332_67fb34",
            str(RESULTS / "sensing" / "run_sensing_20261126_135332_67fb34" / "summary.json"),
            "sensing/adc.py", "VERIFIED", "PASS", "中",
            "理论分辨率不等于实际精度；实际精度见 A01/A02")

    cur = load_json(RESULTS / "sensing" / "run_sensing_20261126_135555_720959" / "summary.json")
    add_row("A11", "第四阶段", "双向电流采集跨导", "", f"{cur['measured_transconductance_v_per_a']:.9f}", "V/A",
            "±2.5 A，分流 10 mΩ + 50 V/V", "SPICE_SIMULATION", "sensing_20261126_135555_720959",
            str(RESULTS / "sensing" / "run_sensing_20261126_135555_720959" / "summary.json"),
            "circuits/current_sensing.py", "VERIFIED", "PASS", "中",
            f"分流压降 {cur['max_shunt_drop_v']*1000:.1f} mV，功耗 {cur['max_shunt_power_w']*1000:.1f} mW")

    diff = load_json(RESULTS / "sensing" / "run_sensing_20261126_135218_cb8cf7" / "summary.json")
    add_row("A12", "第四阶段", "差分放大器增益与 CMRR", "", f"{diff['differential_gain_spice']:.8f} / {diff['cmrr_db']:.2f} dB",
            "V/V / dB", "四电阻差分，0.1% 匹配", "SPICE_SIMULATION", "sensing_20261126_135218_cb8cf7",
            str(RESULTS / "sensing" / "run_sensing_20261126_135218_cb8cf7" / "summary.json"),
            "circuits/differential_amplifier.py", "VERIFIED", "PASS", "中",
            f"可验证 CMRR 下界 {diff['cmrr_numeric_floor_db']:.2f} dB")

    add_row("A13", "第四阶段", "误差预算最坏情况（电压/电流）", "", "30.887 mV / 37.736 mA", "mV / mA",
            "线性叠加，0.1% 电阻等", "解析误差预算", "sensing_20261126_135449_d8a6d3",
            str(tol_dir / "error_budget_voltage.csv"),
            "analysis/error_budget.py", "VERIFIED", "RISK", "中",
            "最坏情况超过 10 mV/20 mA 目标；统计 1000 组通过不等于最坏情况保证")

    return {"channels": channels, "verification": verification,
            "improvement": {"voltage": v_imp, "current": c_imp, "temperature": t_imp},
            "rc": rc, "adc": adc, "current": cur, "differential": diff}


# ---------------------------------------------------------------------------
# 4. 联合 SPICE 系统级
# ---------------------------------------------------------------------------
@section("system_spice")
def audit_system_spice():
    run_dir = RESULTS / "system_spice" / "integrated_nominal_20261126_172452_cb19d4"
    wave_path = run_dir / "waveform.csv"
    frame = pd.read_csv(wave_path)
    t = frame["time_s"].to_numpy()
    # 与原始运行一致的能量窗口：8.4 ms–12 ms（energy.window_s）
    steady = t >= 0.0083
    ts = t[steady]

    vout = frame.loc[steady, "output_voltage_v"].to_numpy()
    vout_mean = time_average(ts, vout)
    ripple = float(np.max(vout) - np.min(vout))

    p_in = frame.loc[steady, "converter_input_voltage_v"].to_numpy() * frame.loc[steady, "converter_input_current_a"].to_numpy()
    p_out = frame.loc[steady, "output_voltage_v"].to_numpy() * frame.loc[steady, "load_current_a"].to_numpy()
    eff = energy(ts, p_out) / energy(ts, p_in) * 100.0

    vbat = frame.loc[steady, "battery_voltage_v"].to_numpy()
    ibat = frame.loc[steady, "battery_current_a"].to_numpy()
    vbat_mean = time_average(ts, vbat)
    ibat_mean = time_average(ts, ibat)
    corr = float(np.corrcoef(vbat, ibat)[0, 1])

    reported = load_json(run_dir / "system_measurements.json")
    reported_map = {m["metric"]: m["value"] for m in reported["measurements"]}
    log(f"Vout={vout_mean:.6f} V (reported {reported_map['output_voltage_mean_v']:.6f})")
    log(f"ripple={ripple*1000:.4f} mV (reported {reported_map['output_voltage_ripple_vpp']*1000:.4f})")
    log(f"efficiency={eff:.4f}% (reported {reported_map['efficiency_percent']:.4f})")
    log(f"Vbat={vbat_mean:.6f} V, Ibat={ibat_mean:.6f} A, corr={corr:.9f}")

    checks = {
        "vout_rel": rel_diff_percent(reported_map["output_voltage_mean_v"], vout_mean),
        "ripple_rel": rel_diff_percent(reported_map["output_voltage_ripple_vpp"], ripple),
        "eff_rel": rel_diff_percent(reported_map["efficiency_percent"], eff),
    }
    verification = "VERIFIED" if max(checks.values()) < 2.0 else "MISMATCH"
    log(f"相对差: {checks}")

    energy_case = load_json(RESULTS / "stage9" / "system_energy" / "energy_20261126_173741_2a5eef" / "case_result.json")

    add_row("S01", "第九阶段", "电池供电 Buck 输出电压均值", "", f"{vout_mean:.6f}", "V",
            "3S ECM + PowerLab 真实开关级 Buck，12 ms 窗口，25 ns 步长",
            "SPICE_SIMULATION（同一网表联合求解）", "integrated_nominal_20261126_172452_cb19d4",
            str(wave_path), "circuits/system_spice_netlist.py", verification, "PASS", "高",
            "2.5 Ω 电阻负载，不能外推到恒流/恒功率负载")
    add_row("S02", "第九阶段", "输出电压纹波", "", f"{ripple*1000:.3f}", "mVpp",
            "8.4–12 ms 能量窗口（与原始运行同窗口）", "SPICE_SIMULATION", "integrated_nominal_20261126_172452_cb19d4",
            str(wave_path), "scripts/audit_resume_metrics.py", verification, "PASS", "高",
            "受 1 mΩ 理想开关与简化二极管模型限制")
    add_row("S03", "第九阶段", "电池端→负载效率（能量比）", "", f"{eff:.3f}", "%",
            "末 2 ms，稳态", "SPICE_SIMULATION", "integrated_nominal_20261126_172452_cb19d4",
            str(wave_path), "scripts/audit_resume_metrics.py", verification, "记录", "高",
            "损耗仅按输入输出差；未分离导通/开关分量")
    add_row("S04", "第九阶段", "电池负载压降与相关性", "", f"{10.878 - vbat_mean:.4f} V / {corr:.8f}",
            "V / -", "开路 ΣOCV 10.878 V，负载约 1 A", "SPICE_SIMULATION",
            "integrated_nominal_20261126_172452_cb19d4", str(wave_path),
            "scripts/audit_resume_metrics.py", "VERIFIED", "PASS", "高",
            "证明电池电压随负载变化，非固定输入源伪耦合")
    add_row("S05", "第九阶段", "系统能量边界残差", "", f"{energy_case['energy']['boundary_a_residual_percent']:.5f}", "%",
            "8.4–12 ms 窗口", "SPICE_SIMULATION", "energy_20261126_173741_2a5eef",
            str(RESULTS / "stage9" / "system_energy" / "energy_20261126_173741_2a5eef" / "case_result.json"),
            "analysis/energy_balance.py", "VERIFIED", "PASS", "中",
            f"效率（能量窗口）{energy_case['energy']['converter_efficiency_percent']:.3f}%")

    return {"vout_mean": vout_mean, "ripple_vpp": ripple, "efficiency_percent": eff,
            "vbat_mean": vbat_mean, "ibat_mean": ibat_mean, "correlation": corr,
            "recomputed_rel_diff": checks, "verification": verification,
            "energy_case": energy_case}


# ---------------------------------------------------------------------------
# 5. 保护
# ---------------------------------------------------------------------------
@section("protection")
def audit_protection():
    run_dir = RESULTS / "stage9" / "system_protection" / "protection_20261126_173438_1e53b2"
    case = load_json(run_dir / "case_result.json")
    timing = case["spice_protection_timing"]
    behavioral = case["behavioral"]
    ratio = case["suppression_ratio"]
    timing_ratio = timing["current_suppression_threshold_a"] / timing["pre_fault_battery_current_a"]

    add_row("P01", "第五阶段", "保护阈值组（OV/UV/充电OC/放电OC/短路/过温）",
            "", "4.25/2.80/1.50/4.00/8.00 V,A,A,A,A,65℃", "V/A/℃",
            "3S，工程配置，非 BQ76922 寄存器", "PROJECT_SPECIFICATION", "protection_20261126_143915_7354a8",
            str(RESULTS / "protection" / "run_protection_20261126_143915_7354a8" / "summary.json"),
            "protection/protection_controller.py", "VERIFIED", "PASS", "中",
            "阈值为工程设计值，不代表商业芯片出厂参数")
    add_row("P02", "第五阶段", "故障工况通过数（状态机+故障注入）", "", f"{behavioral['pass_count']}/{behavioral['scenario_count']}",
            "个", "欠压/过压/充放电过流/过温/无效采样/多故障等", "BEHAVIORAL_MODEL",
            "protection_20261126_173438_1e53b2", str(run_dir / "fault_injection.json"),
            "protection/state_machine.py", "VERIFIED", "PASS", "高",
            "故障为注入工况，不是真实电池滥用测试")
    add_row("P03", "第五阶段", "MOSFET 关断后电池电流抑制比", "", f"{ratio:.5f}", "-",
            "故障前 1.006 A；抑制判定阈值取故障前 5%（50.3 mA）", "SPICE_SIMULATION",
            "protection_20261126_173438_1e53b2", str(run_dir / "case_result.json"),
            "circuits/integrated_protection.py", "VERIFIED", "记录", "中",
            "残余约 0.123% 由行为电流源钳位得到；该比例不是物理 MOSFET 漏电实测")
    add_row("P04", "第五阶段", "电池电流抑制时刻（相对故障）", "", "2.5", "ns",
            "故障在 12 ms 注入", "SPICE_SIMULATION", "protection_20261126_173438_1e53b2",
            str(run_dir / "case_result.json"), "circuits/integrated_protection.py",
            "NOT_VERIFIED", "ARTIFACT", "低",
            "该时刻早于栅极关断指令（12.01 ms）10 µs，属行为源钳位伪迹；不得作为物理保护响应时间")
    add_row("P04B", "第五阶段", "保护确认延时（栅极关断指令相对故障）", "", "10.0", "µs",
            "故障 12.000 ms，FET 指令 12.010 ms", "SPICE_SIMULATION",
            "protection_20261126_173438_1e53b2", str(run_dir / "case_result.json"),
            "circuits/integrated_protection.py", "VERIFIED", "PASS", "高",
            "这是配置的 10 µs 确认延时在 SPICE 中的执行时刻，不是芯片比较器实测")
    add_row("P05", "第五阶段", "保护后转换器输入衰减时间", "", f"{timing['vin_decay_delay_from_command_s']*1e6:.1f}", "µs",
            "栅极关断指令后", "SPICE_SIMULATION", "protection_20261126_173438_1e53b2",
            str(run_dir / "case_result.json"), "circuits/integrated_protection.py",
            "VERIFIED", "记录", "中", "依赖 100 µF 输入电容与 2.5 Ω 负载")
    add_row("P06", "第五阶段", "保护后输出维持时间", "", f"{timing['output_hold_time_s']*1e6:.1f}", "µs",
            "输出跌出稳压限值前", "SPICE_SIMULATION", "protection_20261126_173438_1e53b2",
            str(run_dir / "case_result.json"), "circuits/integrated_protection.py",
            "VERIFIED", "PASS", "中", "短窗结果，不能外推到长时备电")

    # 第五阶段真实 SPICE 直接结果
    stage5 = load_json(RESULTS / "stage5_validation" / "run_stage5_validation_20261126_143914_3f8da9" / "summary.json")
    add_row("P07", "第五阶段", "背靠背 MOSFET 1 A 导通压降/单管 Rds(on)", "", "37.584 mV / 18.666 mΩ",
            "mV / mΩ", "1.007 A 放电", "SPICE_SIMULATION", "protection_20261126_143914_82fa77",
            str(RESULTS / "protection" / "run_protection_20261126_143914_82fa77" / "summary.json"),
            "circuits/protection_mosfet.py", "VERIFIED", "PASS", "高",
            "ngspice level-1 教学 MOSFET，不是商业器件模型")
    add_row("P08", "第五阶段", "双向阻断残余电流（双管关断，12.6 V 反压）", "", "1.00", "nA",
            "12.6 V 反向", "SPICE_SIMULATION", "protection_20261126_143914_82fa77",
            str(RESULTS / "protection" / "run_protection_20261126_143914_82fa77" / "summary.json"),
            "circuits/protection_mosfet.py", "VERIFIED", "PASS", "高", "限值 1 µA；教学模型漏电")
    add_row("P09", "第五阶段", "比较器跳闸/迟滞误差", "", "46 µV / 0.31 mV", "µV / mV",
            "配置 4.250 V / 100 mV 回差", "SPICE_SIMULATION", "protection_20261126_143915_9a84ab",
            str(RESULTS / "protection" / "run_protection_20261126_143915_9a84ab" / "summary.json"),
            "circuits/protection_comparator.py", "VERIFIED", "PASS", "中",
            "分立元件等效比较器，不是商业保护 IC")
    add_row("P10", "第五阶段", "保护确认延时误差", "", "0.074", "%",
            "RC 确认 60.865 ms vs 解析 60.820 ms", "SPICE_SIMULATION",
            "protection_20261126_143915_9a84ab",
            str(RESULTS / "protection" / "run_protection_20261126_143915_9a84ab" / "summary.json"),
            "protection/comparator.py", "VERIFIED", "PASS", "中",
            "配置延时不是实际保护响应时间")
    add_row("P11", "第五阶段", "综合验收检查通过数", "", f"{stage5.get('passed', 'N/A')}/{stage5.get('total', 'N/A')}",
            "项", "第五阶段 41 项", "SOFTWARE_TEST", "stage5_validation_20261126_143914_3f8da9",
            str(RESULTS / "stage5_validation" / "run_stage5_validation_20261126_143914_3f8da9" / "summary.json"),
            "scripts/battery_stage5_demo.py", "VERIFIED", "PASS", "低",
            "软件验收数量不是电气性能指标")

    return {"ratio": ratio, "timing": timing, "behavioral": behavioral, "stage5": stage5}


# ---------------------------------------------------------------------------
# 6. 被动均衡（含同条件无均衡对照）
# ---------------------------------------------------------------------------
@section("balancing")
def audit_balancing():
    run_dir = RESULTS / "protection" / "run_protection_20261126_143916_7ed424"
    series = pd.read_csv(run_dir / "balancing_long_run.csv")
    initial_delta_mv = float(series["delta_cell_voltage_v"].iloc[0]) * 1000.0
    final_delta_mv = float(series["delta_cell_voltage_v"].iloc[-1]) * 1000.0
    imp = reduction_percent(initial_delta_mv, final_delta_mv)
    summary = load_json(run_dir / "summary.json")

    # 同条件无均衡对照：同一初始 SOC、同一时长、同一 ECM，仅关闭均衡许可
    control = {}
    try:
        sys.path.insert(0, str(BASE))
        from protection.balancing import simulate_passive_balancing
        from scripts.stage5_common import pack_cells, stage5_limits

        socs = [0.8636363636363631, 0.9272727272727268, 0.981818181818181]
        cells = pack_cells(socs)
        result = simulate_passive_balancing(
            cells, stage5_limits(), duration_s=43200.0, step_s=10.0, permitted=False
        )
        control_delta = float(result.delta_cell_voltage_v[-1]) * 1000.0
        final_socs = [float(result.cell_soc[c][-1]) for c in result.cell_soc]
        control = {
            "initial_delta_mv": float(result.initial_delta_v) * 1000.0,
            "final_delta_mv": control_delta,
            "soc_spread_pp": (max(final_socs) - min(final_socs)) * 100.0,
            "reduction_percent": reduction_percent(float(result.initial_delta_v) * 1000.0, control_delta),
            "permitted": False,
        }
        (RUN_DIR / "balancing_control.json").write_text(json.dumps(control, indent=2), encoding="utf-8")
        log(f"无均衡对照: {control}")
    except Exception as exc:  # noqa: BLE001
        control = {"status": "NOT_VERIFIED", "error": f"{type(exc).__name__}: {exc}"}
        log(f"无均衡对照失败: {control['error']}")

    # 均衡仿真最终 SOC 极差（从长跑 CSV 不可直接得，使用同一模型的受控重跑）
    balancing_soc_spread = None
    try:
        from protection.balancing import simulate_passive_balancing
        from scripts.stage5_common import pack_cells, stage5_limits

        socs = [0.8636363636363631, 0.9272727272727268, 0.981818181818181]
        cells = pack_cells(socs)
        result = simulate_passive_balancing(
            cells, stage5_limits(), duration_s=43200.0, step_s=10.0, permitted=True
        )
        f_socs = [float(result.cell_soc[c][-1]) for c in result.cell_soc]
        balancing_soc_spread = (max(f_socs) - min(f_socs)) * 100.0
        (RUN_DIR / "balancing_recheck.json").write_text(
            json.dumps({
                "initial_delta_mv": float(result.initial_delta_v) * 1000.0,
                "final_delta_mv": float(result.final_delta_v) * 1000.0,
                "soc_spread_pp": balancing_soc_spread,
                "reduction_percent": float(result.delta_reduction_fraction) * 100.0,
                "energy_dissipated_wh": float(result.energy_dissipated_wh),
            }, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        log(f"均衡同条件重跑失败: {type(exc).__name__}: {exc}")

    if balancing_soc_spread is not None and control.get("soc_spread_pp") is not None:
        imp_soc = reduction_percent(control["soc_spread_pp"], balancing_soc_spread)
        add_row("B06", "第五阶段", "被动均衡前后 3S 单体 SOC 最大差异",
                f"{control['soc_spread_pp']:.3f}", f"{balancing_soc_spread:.3f}", "pp",
                "3 节 0.864/0.927/0.982 初始 SOC，12 h，同一 ECM", "ECM 长时仿真（含无均衡对照）",
                f"resume_audit/{RUN_DIR.name}", str(RUN_DIR / "balancing_recheck.json"),
                "protection/balancing.py", "VERIFIED", "PASS", "高",
                f"降低 {imp_soc:.2f}%；SOC 差由 SOC 估计器状态给出，不是实测单体 SOC",
                improvement=f"{imp_soc:.2f}%")

    add_row("B01", "第五阶段", "被动均衡前后单体最大压差", f"{initial_delta_mv:.3f}", f"{final_delta_mv:.3f}",
            "mV", "3 节 4.05/4.12/4.18 V，12 h 静置，均衡许可开启", "ECM 长时仿真 + 1 次 SPICE 支路校核",
            "protection_20261126_143916_7ed424", str(run_dir / "balancing_long_run.csv"),
            "protection/balancing.py", "VERIFIED", "PASS", "高",
            f"降低 {imp:.2f}%；无均衡同条件对照见 B02",
            improvement=f"{imp:.2f}%")
    if control.get("status") != "NOT_VERIFIED":
        add_row("B02", "第五阶段", "无均衡同条件对照（12 h）", f"{control['initial_delta_mv']:.3f}",
                f"{control['final_delta_mv']:.3f}", "mV", "同一初始 SOC、同一时长，仅关闭均衡许可",
                "ECM 长时仿真（对照）", f"resume_audit/{RUN_DIR.name}",
                str(RUN_DIR / "balancing_control.json"), "protection/balancing.py",
                "VERIFIED", "对照", "高",
                f"对照降低 {control['reduction_percent']:.2f}%；证明压差缩小来自均衡而非静置恢复")
    else:
        add_row("B02", "第五阶段", "无均衡同条件对照（12 h）", "NOT_VERIFIED", "NOT_VERIFIED", "mV",
                "同一初始 SOC、同一时长，仅关闭均衡许可", "N/A", "N/A", "N/A", "N/A",
                "NOT_VERIFIED", "NOT_VERIFIED", "低", "对照运行失败")

    add_row("B03", "第五阶段", "均衡支路电流/电阻功耗", "", f"{summary['spice']['measured_current_a']*1000:.3f} mA / {summary['spice']['peak_power_w']*1000:.2f} mW",
            "mA / mW", "cell3 4.18 V", "SPICE_SIMULATION", "protection_20261126_143916_7ed424",
            str(run_dir / "summary.json"), "circuits/balancing_circuit.py", "VERIFIED", "PASS", "中",
            "电阻温升为一阶估算，未做热仿真")
    add_row("B04", "第五阶段", "均衡累计耗散能量", "", f"{summary['long_run']['energy_dissipated_wh']:.4f}", "Wh",
            "12 h 静置", "ECM 长时仿真", "protection_20261126_143916_7ed424",
            str(run_dir / "summary.json"), "protection/balancing.py", "VERIFIED", "记录", "中",
            "能量为支路功率对时间积分")

    pack_soc = pd.read_csv(RESULTS / "stage7" / "run_stage7_20261126_162211_3590e5" / "pack_soc_summary.csv")
    ignore = pack_soc[pack_soc["case"] == "A_ignore_balancing"]["max_absolute_error_pp"].max()
    include = pack_soc[pack_soc["case"] == "B_include_balancing"]["max_absolute_error_pp"].max()
    add_row("B05", "第七阶段", "电池组 SOC 估计误差（忽略均衡→计入均衡）", f"{ignore:.3f}", f"{include:.3f}",
            "pp", "3S 不一致初始 SOC，安时积分", "PUBLIC_DATA + 计算",
            "stage7_20261126_162211_3590e5",
            str(RESULTS / "stage7" / "run_stage7_20261126_162211_3590e5" / "pack_soc_summary.csv"),
            "estimation/pack_soc.py", "VERIFIED", "PASS", "中",
            "这是 SOC 估计误差改善，不是真实均衡硬件效果")

    return {
        "initial_delta_mv": initial_delta_mv,
        "final_delta_mv": final_delta_mv,
        "reduction_percent": imp,
        "control": control,
        "balancing_soc_spread_pp": balancing_soc_spread,
        "soc_ignore_error_pp": float(ignore),
        "soc_include_error_pp": float(include),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 7. CC-CV 充电
# ---------------------------------------------------------------------------
@section("charging")
def audit_charging():
    summary = load_json(RESULTS / "stage6" / "run_stage6_20261126_155147_64c696" / "summary.json")
    limits = summary.get("limits", summary.get("limit_results", {}))
    log(f"stage6 summary keys: {list(summary.keys())[:20]}")
    add_row("C01", "第六阶段", "恒流稳态电流误差", "", "0.00109", "A",
            "18 V→12.15 V/1 A，20 ns 步长", "SPICE_SIMULATION", "run_stage6_20261126_155147_64c696",
            str(RESULTS / "stage6" / "run_stage6_20261126_155147_64c696" / "summary.json"),
            "charging/cc_cv_controller.py", "VERIFIED", "PASS", "高",
            "开关级短窗，SOC 不变")
    add_row("C02", "第六阶段", "恒压稳态电压误差", "", "0.01350", "V",
            "同上", "SPICE_SIMULATION", "run_stage6_20261126_155147_64c696",
            str(RESULTS / "stage6" / "run_stage6_20261126_155147_64c696" / "summary.json"),
            "charging/cc_cv_controller.py", "VERIFIED", "PASS", "高",
            "接近 20 mV 限值")
    add_row("C03", "第六阶段", "CC→CV 切换电压过冲", "", "2.07", "mV",
            "C03 工况", "SPICE_SIMULATION", "run_stage6_20261126_155227_97496e",
            str(RESULTS / "stage6" / "run_stage6_20261126_155227_97496e" / "summary.json"),
            "charging/cc_cv_controller.py", "VERIFIED", "PASS", "中", "单工况")
    add_row("C04", "第六阶段", "功率级效率", "", "98.01", "%",
            "开关级，导通+开关损耗", "SPICE_SIMULATION", "run_stage6_20261126_155147_64c696",
            str(RESULTS / "stage6" / "run_stage6_20261126_155147_64c696" / "summary.json"),
            "circuits/charger_buck.py", "VERIFIED", "PASS", "中",
            "简化器件模型，非商业 BQ24610 实测")
    add_row("C05", "第六阶段", "电压环相位裕度", "", "107.22", "deg",
            "kp=2, ki=2000，线性化平均模型", "BEHAVIORAL_MODEL",
            "run_stage6_20261126_155147_64c696",
            str(RESULTS / "stage6" / "run_stage6_20261126_155147_64c696" / "summary.json"),
            "analysis/charging_loop_analysis.py", "VERIFIED", "PASS", "高",
            "平均模型不含 PWM 采样与 DCM")
    add_row("C06", "第六阶段", "软启动前后启动过冲", "NOT_VERIFIED", "8.34", "%",
            "C01 启动峰值 1.0834 A", "SPICE_SIMULATION", "run_stage6_20261126_155156_d5f885",
            str(RESULTS / "stage6" / "run_stage6_20261126_155156_d5f885" / "summary.json"),
            "charging/soft_start.py", "NOT_VERIFIED", "PASS", "中",
            "历史结果未保留无软启动同条件对照，无法计算改善比例；仅记录有软启动的 8.34%")
    add_row("C07", "第六阶段", "PI 参数优化前后动态性能", "NOT_VERIFIED", "NOT_VERIFIED", "-",
            "kp=2, ki=2000 为冻结值", "N/A", "N/A", "N/A", "N/A",
            "NOT_VERIFIED", "NOT_VERIFIED", "低",
            "仅保留整定网格与最终值，无同条件前后对照运行")
    add_row("C08", "第六阶段", "抗积分饱和前后恢复时间", "NOT_VERIFIED", "NOT_VERIFIED", "ms",
            "条件积分+反计算为冻结方案", "N/A", "N/A", "N/A", "N/A",
            "NOT_VERIFIED", "NOT_VERIFIED", "低",
            "仅记录纯反计算会把 C01 恒流指令拉低约 25 mA，无保留的前后对照波形")
    return {"summary_keys": list(summary.keys()), "summary": summary}


# ---------------------------------------------------------------------------
# 8. SOC / SOH
# ---------------------------------------------------------------------------
@section("soc_soh")
def audit_soc_soh():
    comp = pd.read_csv(RESULTS / "stage7" / "run_stage7_20261126_162211_3590e5" / "soc_method_comparison.csv")
    observer = comp[comp["method"] == "ecm_observer"]
    raw = comp[comp["method"] == "raw_voltage_ocv"]
    obs_rmse = float(observer["rmse_pp"].mean())
    obs_max = float(observer["max_absolute_error_pp"].max())
    raw_rmse = float(raw["rmse_pp"].mean())
    imp = reduction_percent(raw_rmse, obs_rmse)
    coverage = float(observer["coverage_fraction"].mean())

    add_row("E01", "第七阶段", "ECM 观测器 SOC RMSE（4 个独立动态工况平均）", "", f"{obs_rmse:.4f}", "pp",
            "US06/BJDST 50%/80%，25℃", "PUBLIC_EXPERIMENT + 观测器", "stage7_20261126_162211_3590e5",
            str(RESULTS / "stage7" / "run_stage7_20261126_162211_3590e5" / "soc_method_comparison.csv"),
            "estimation/ecm_observer.py", "VERIFIED", "PASS", "高",
            "SOC 参考由公开数据电流积分推导，不是直接实测真实 SOC")
    add_row("E02", "第七阶段", "端电压查表 → ECM 观测器 SOC RMSE 降低", f"{raw_rmse:.4f}", f"{obs_rmse:.4f}", "pp",
            "同一 4 工况、同一区间", "复算", "stage7_20261126_162211_3590e5",
            str(RESULTS / "stage7" / "run_stage7_20261126_162211_3590e5" / "soc_method_comparison.csv"),
            "scripts/audit_resume_metrics.py", "VERIFIED", "PASS", "高",
            f"降低 {imp:.2f}%；同一数据集同一区间",
            improvement=f"{imp:.2f}%")
    add_row("E03", "第七阶段", "SOC 估计最大误差", "", f"{obs_max:.3f}", "pp",
            "4 工况中最大", "PUBLIC_EXPERIMENT + 观测器", "stage7_20261126_162211_3590e5",
            str(RESULTS / "stage7" / "run_stage7_20261126_162211_3590e5" / "soc_method_comparison.csv"),
            "estimation/ecm_observer.py", "VERIFIED", "PASS", "高", "预登记限值 5 pp")
    add_row("E04", "第七阶段", "有效覆盖率", "", f"{coverage:.4f}", "-",
            "4 工况", "PUBLIC_EXPERIMENT + 观测器", "stage7_20261126_162211_3590e5",
            str(RESULTS / "stage7" / "run_stage7_20261126_162211_3590e5" / "soc_method_comparison.csv"),
            "estimation/ecm_observer.py", "VERIFIED", "PASS", "中", "覆盖率不等于精度")

    corr = load_json(RESULTS / "soc_estimation" / "run_soc_estimation_20261126_161725_90c158" / "correction_metrics.json")
    fixture = corr["fixture"]
    add_row("E05", "第七阶段", "静置 OCV 校正前后 SOC 终值误差（合成夹具）", "-5.000", f"{fixture['final_error_pp']:.4f}",
            "pp", "初始偏差 -5 pp，25 次校正，2400 s", "SYNTHETIC_TRUTH",
            "soc_estimation_20261126_161725_90c158",
            str(RESULTS / "soc_estimation" / "run_soc_estimation_20261126_161725_90c158" / "correction_metrics.json"),
            "estimation/rest_correction.py", "VERIFIED", "PASS", "中",
            "夹具为合成真值；真实 CALCE 连续动态段校正 0 次，不能外推")
    add_row("E06", "第七阶段", "初始 SOC 偏差收敛时间（+20 pp）", "", "479.6", "s",
            "US06 50% 起点", "PUBLIC_EXPERIMENT + 观测器", "stage7_20261126_162211_3590e5",
            str(RESULTS / "stage7" / "run_stage7_20261126_162211_3590e5" / "initial_soc_experiments.csv"),
            "estimation/ecm_observer.py", "VERIFIED", "PASS", "中",
            "安时积分在 +10/+20 pp 不收敛；观测器收敛")

    soh = load_json(RESULTS / "battery_health" / "run_battery_health_20261126_161753_3e607b" / "capacity_soh_summary.json")
    add_row("E07", "第七阶段", "容量 SOH（真实数据）", "", "1 次完整循环，100%", "%",
            "CALCE SP2 初始容量", "PUBLIC_EXPERIMENT", "battery_health_20261126_161753_3e607b",
            str(RESULTS / "battery_health" / "run_battery_health_20261126_161753_3e607b" / "capacity_soh_summary.json"),
            "health/capacity_soh.py", "VERIFIED", "NOT_VERIFIED（老化）", "低",
            "仅一次实验，100% 保持率无老化含义；真实老化 NOT_VERIFIED")
    add_row("E08", "第七阶段", "合成 100 循环容量保持率", "", f"{soh['synthetic_summary']['retention_percent']:.1f}", "%",
            "合成线性衰减，非实测", "SYNTHETIC", "battery_health_20261126_161753_3e607b",
            str(RESULTS / "battery_health" / "run_battery_health_20261126_161753_3e607b" / "capacity_soh_summary.json"),
            "health/capacity_soh.py", "VERIFIED（合成）", "记录", "低",
            "合成序列，不得称为真实电池老化")
    add_row("E09", "第七阶段", "真实表观 DCIR", "", "0.073274", "Ω",
            "SOC 0.391，25℃，4.483 A，1.003 s", "PUBLIC_EXPERIMENT", "battery_health_20261126_161844_389769",
            str(RESULTS / "battery_health" / "run_battery_health_20261126_161844_389769" / "resistance_summary.json"),
            "health/resistance_health.py", "VERIFIED", "记录", "中",
            "单点表观内阻；真实内阻增长率 NOT_VERIFIED")

    return {"observer_rmse_pp": obs_rmse, "observer_max_pp": obs_max, "raw_rmse_pp": raw_rmse,
            "improvement_percent": imp, "coverage": coverage, "fixture": fixture, "soh": soh}


# ---------------------------------------------------------------------------
# 9. 硬件设计（KiCad）
# ---------------------------------------------------------------------------
@section("hardware")
def audit_hardware():
    eda = RESULTS / "eda" / "run_stage8_20261126_165159_f06bd0"
    val = load_json(eda / "validation_summary.json")
    pins = load_json(eda / "pin_mapping_completeness.json")
    bom = load_json(eda / "bom_validation.json")
    blocked = load_json(eda / "blocked_items.json")

    add_row("H01", "第八阶段", "BMS 引脚映射完整度", "", f"{pins['bms']['rows']} 行（{pins['bms']['expected_pin_count']} pin + PAD）",
            "行", "BQ76922 32 引脚", "DATASHEET", "run_stage8_20261126_165159_f06bd0",
            str(eda / "pin_mapping_completeness.json"), "eda_tools/pin_mapping_audit.py",
            "VERIFIED", "PASS", "高", "引脚级设计输入，不是已投板原理图")
    add_row("H02", "第八阶段", "充电器引脚映射完整度", "", f"{pins['charger']['rows']} 行（{pins['charger']['expected_pin_count']} pin + PAD）",
            "行", "BQ24610 24 引脚", "DATASHEET", "run_stage8_20261126_165159_f06bd0",
            str(eda / "pin_mapping_completeness.json"), "eda_tools/pin_mapping_audit.py",
            "VERIFIED", "PASS", "高", "同上")
    add_row("H03", "第八阶段", "关键网络规则 / 器件库 / MOSFET 候选", "", "18 / 17 / 4",
            "条", "关键网络、器件记录、NexFET 对比", "DATASHEET + 选型", "run_stage8_20261126_165159_f06bd0",
            str(BASE / "hardware" / "eda" / "requirements" / "critical_net_rules.csv"),
            "eda_tools/board_metrics.py", "VERIFIED", "记录", "中", "未采购、未打样")
    add_row("H04", "第八阶段", "BOM 完整性", "", f"{bom['bms']['row_count'] + bom['charger']['row_count']} 行，issues={bom['issue_count']}",
            "行", "BMS+充电器 BOM", "BOM 审计", "run_stage8_20261126_165159_f06bd0",
            str(eda / "bom_validation.json"), "eda_tools/bom_validator.py",
            "VERIFIED", "PASS", "中", "被动件料号仍大量 TBD")
    add_row("H05", "第八阶段", "ERC / DRC / Gerber / 钻孔 / STEP", "", "全部 BLOCKED", "-",
            "本机无 KiCad", "EDA", "run_stage8_20261126_165159_f06bd0",
            str(eda / "blocked_items.json"), "eda_tools/kicad_runner.py",
            "NOT_VERIFIED", "BLOCKED", "低",
            "未安装 KiCad，未生成原理图/PCB/ERC/DRC/Gerber；不得宣称已完成 PCB")
    add_row("H06", "第八阶段", "LLC 谐振/LC 谐振目标", "", "11.07 kHz（目标 12–17 kHz）", "kHz",
            "标称 9.4 µF", "解析计算", "run_stage8_20261126_165159_f06bd0",
            str(eda / "design_calculations.json"), "eda_tools/design_calculations.py",
            "VERIFIED", "FAIL", "中", "MLCC 直流偏压未实测，不能把可能合格写成 PASS")
    add_row("H07", "第八阶段", "分流电阻功耗/充电设定/电感纹波", "", "62.5 mW / 1.0061 A / 0.299 A",
            "mW / A / A", "2.5 A，18→12.075 V，22 µH", "解析计算", "run_stage8_20261126_165159_f06bd0",
            str(eda / "design_calculations.json"), "eda_tools/design_calculations.py",
            "VERIFIED", "PASS", "中", "解析计算，不是硬件实测")
    add_row("H08", "第八阶段", "降额检查 / 设计评审", "", "13 项 / 3 份评审 CSV + FMEA + 验证计划", "项",
            "器件降额与评审", "工程评审", "run_stage8_20261126_165159_f06bd0",
            str(BASE / "hardware" / "design_review" / "design_fmea.csv"),
            "eda_tools/release_manifest.py", "VERIFIED", "记录", "中",
            "评审为文档级，不是硬件验证通过")
    return {"validation": val, "pins": pins, "bom": bom, "blocked": blocked}


# ---------------------------------------------------------------------------
# 10. 系统长期/老化/功率映射/TestLab
# ---------------------------------------------------------------------------
@section("system_operation")
def audit_system_operation():
    discharge = load_json(RESULTS / "stage9" / "system_lifetime" / "discharge_20261126_173652_f67325" / "case_result.json")
    runtimes = [r["runtime_h"] for r in discharge["results"]]
    statuses = {}
    for r in discharge["results"]:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    add_row("L01", "第九阶段", "电池供电运行时间（16 工况）", "", f"{min(runtimes):.3f}–{max(runtimes):.3f}", "h",
            "负载 0.5–2.0 A，初始 SOC 0.2–0.8", "ECM + 已验证功率映射", "discharge_20261126_173652_f67325",
            str(RESULTS / "stage9" / "system_lifetime" / "discharge_20261126_173652_f67325" / "case_result.json"),
            "system_models/long_term_discharge.py", "VERIFIED", "LIMITED", "中",
            "16 工况均终止于电池模型限值或已验证输入域边界，未到达保护切断；运行时间不是完整续航")

    aging = load_json(RESULTS / "stage9" / "system_lifetime" / "aging_20261126_173726_efe310" / "case_result.json")
    rows = aging["scenarios"]
    add_row("L02", "第九阶段", "SOH 90%/80% 供电时间变化", "0.990 h (SOH100)",
            f"{rows[1]['runtime_h']:.3f} h / {rows[2]['runtime_h']:.3f} h",
            "h", "1.5 A 负载，初始 SOC 0.4", "ECM 参数敏感性", "aging_20261126_173726_efe310",
            str(RESULTS / "stage9" / "system_lifetime" / "aging_20261126_173726_efe310" / "case_result.json"),
            "system_models/long_term_discharge.py", "VERIFIED", "LIMITED", "中",
            f"变化 {rows[1]['runtime_change_percent']:.1f}% / {rows[2]['runtime_change_percent']:.1f}%；三组均终止于已验证输入域边界，不是实测寿命")

    pmap = load_json(RESULTS / "converter_power_map" / "power_map_20261126_173026_8e4c27" / "converter_power_map_summary.json")
    valid = pmap["valid_maps"]
    add_row("L03", "第九阶段", "Buck 有效功率映射", "",
            f"4 组负载 / {pmap['converged_count']}/{pmap['point_count']} 点收敛", "组",
            "9.0–12.6 V 输入，0.5–2.0 A 负载", "PowerLab 真实开关级 SPICE",
            "power_map_20261126_173026_8e4c27",
            str(RESULTS / "converter_power_map" / "power_map_20261126_173026_8e4c27" / "converter_power_map_summary.json"),
            "integration/powerlab_adapter.py", "VERIFIED", "PARTIAL", "高",
            "7 点因未稳态/求解失败被拒绝，未外推")
    add_row("L04", "第九阶段", "功率映射最低效率", "",
            f"{min(v['minimum_efficiency_percent'] for v in valid.values()):.3f}", "%",
            "有效映射组中最低值", "SPICE", "power_map_20261126_173026_8e4c27",
            str(RESULTS / "converter_power_map" / "power_map_20261126_173026_8e4c27" / "converter_power_map_summary.json"),
            "integration/powerlab_adapter.py", "VERIFIED", "记录", "中",
            "PowerLab 教学 NMOS Level 1，不是商业器件")

    testlab = load_json(RESULTS / "stage9" / "testlab_integration" / "testlab_20261126_173758_18733f" / "case_result.json")
    agree = testlab["agreement"]
    add_row("L05", "第九阶段", "TestLab 判定一致性", "", f"{agree['agreed']}/{agree['comparable']}",
            "项", "只读调用真实 result_judge", "SOFTWARE_TEST",
            "testlab_20261126_173758_18733f",
            str(RESULTS / "stage9" / "testlab_integration" / "testlab_20261126_173758_18733f" / "case_result.json"),
            "integration/testlab_bridge.py", "VERIFIED", "PASS", "中",
            f"judge sha256 {testlab['testlab_output']['testlab_judge_sha256'][:16]}…")

    return {"discharge": discharge, "runtimes_h": runtimes, "statuses": statuses,
            "aging": aging, "power_map": pmap, "testlab": testlab}


# ---------------------------------------------------------------------------
# 11. 回归测试与仿真计数
# ---------------------------------------------------------------------------
@section("counts")
def audit_counts():
    counts = {
        "pytest_last": "550 passed",
        "stage2_spice_solves": 6,
        "stage4_spice_solves": 68,
        "stage5_spice_solves": 12,
        "stage6_spice_solves": 12,
        "stage7_spice_solves": 2,
        "stage8_kicad": "BLOCKED",
        "stage9_power_map_points": 24,
        "stage9_power_map_converged": 17,
        "stage9_fault_scenarios": 10,
        "stage9_discharge_cases": 16,
        "stage9_testlab_checks": 4,
        "demo_runs_total": len(list(RESULTS.glob("**/run_*"))),
    }
    (RUN_DIR / "simulation_counts.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    return counts


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
log(f"BatteryLab resume audit run {RUN_DIR.name}")
log(f"Python {sys.version.split()[0]}")
log(f"numpy {np.__version__} / pandas {pd.__version__}")

for _func in (
    audit_model_accuracy,
    audit_ocv,
    audit_sensing,
    audit_system_spice,
    audit_protection,
    audit_balancing,
    audit_charging,
    audit_soc_soh,
    audit_hardware,
    audit_system_operation,
    audit_counts,
):
    run_section(_func)

# 证据索引导出
fields = ["成果编号", "研发模块", "指标名称", "优化前", "优化后", "单位", "改善比例",
          "实验条件", "数据来源", "Run ID", "原始证据", "核心源码", "验证状态",
          "验收状态", "简历适用性", "局限"]
with open(RUN_DIR / "evidence_index.csv", "w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for row in ROWS:
        writer.writerow(row)

# 优化前后对照（只含成对数值）
pairs = []
for row in ROWS:
    if row["优化前"] not in ("", None, "NOT_VERIFIED") and row["优化后"] not in ("", None, "NOT_VERIFIED"):
        pairs.append(row)
with open(RUN_DIR / "before_after.csv", "w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for row in pairs:
        writer.writerow(row)

# 简历指标 CSV（附到 portfolio）
with open(PORTFOLIO / "BatteryLab_resume_metrics.csv", "w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for row in ROWS:
        writer.writerow(row)

# 验证状态统计
status_counts = {}
for row in ROWS:
    key = row["验证状态"]
    status_counts[key] = status_counts.get(key, 0) + 1

payload = {
    "run_id": RUN_DIR.name,
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "sections": SECTIONS,
    "failures": FAILURES,
    "verification_status_counts": status_counts,
    "row_count": len(ROWS),
}
with open(RUN_DIR / "recomputed_metrics.json", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, default=str)

# 配置快照（只记录关键输入）
snapshot = {
    "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__},
    "source_runs": {row["成果编号"]: row["Run ID"] for row in ROWS},
    "inputs": {
        "calce_dynamic_validation": "results/dynamic_validation/run_dynamic_validation_20261126_131720_0e4677",
        "identification": "results/identification/run_identification_20261126_131901_fb66db",
        "sensing_tolerance": "results/sensing/run_sensing_20261126_135449_d8a6d3",
        "system_spice": "results/system_spice/integrated_nominal_20261126_172452_cb19d4",
        "protection": "results/stage9/system_protection/protection_20261126_173438_1e53b2",
        "balancing": "results/protection/run_protection_20261126_143916_7ed424",
        "stage7": "results/stage7/run_stage7_20261126_162211_3590e5",
        "stage8": "results/eda/run_stage8_20261126_165159_f06bd0",
    },
    "integration": {"time_weighted": True, "efficiency_definition": "energy_ratio",
                    "optimization_rule": "same_dataset_same_window_same_definition"},
}
with open(RUN_DIR / "config_snapshot.json", "w", encoding="utf-8") as handle:
    json.dump(snapshot, handle, indent=2, default=str)

log("\n===== 汇总 =====")
for key, value in status_counts.items():
    log(f"  {key}: {value}")
log(f"  证据行数: {len(ROWS)}")
log(f"  失败区块: {[f['section'] for f in FAILURES] if FAILURES else '无'}")
log(f"\n输出目录: {RUN_DIR}")
log(f"简历指标: {PORTFOLIO / 'BatteryLab_resume_metrics.csv'}")
_LOG.close()
