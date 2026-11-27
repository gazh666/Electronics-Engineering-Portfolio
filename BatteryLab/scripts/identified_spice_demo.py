"""Task 27-29/30：辨识参数导入真实 ngspice、3S 电池组与 BMS 设计参考。

运行：conda run -n kaifa_battery python -m scripts.identified_spice_demo
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from analysis.model_comparison import compare_frames
from battery_models.battery_pack import build_uniform_pack, simulate_series_pack
from battery_models.ecm_solver import simulate_ecm
from battery_models.ocv_model import ConstantOcvModel
from battery_models.states import CellState
from identification.parameter_store import load_frozen_model
from simulations.load_profiles import piecewise_profile
from simulations.power_delivery import simulate_constant_power
from simulations.spice_battery_runner import run_spice_pack, run_spice_single_cell
from storage.result_store import RESULTS_ROOT, RunDirectory, write_json
from visualization.plots import plot_multi_series, plot_xy

MODEL_IDS = {
    "rint": "calce_sp2_25c_inr18650_20r_rint_v1",
    "first_order_rc": "calce_sp2_25c_inr18650_20r_first_order_v1",
    "second_order_rc": "calce_sp2_25c_inr18650_20r_second_order_v1",
}
TEST_SOC = 0.55


def analytic_pulse_response(time_values, current_values, parameters, order: int) -> np.ndarray:
    """固定 OCV 下的解析 RC 响应（用于独立校核 Python/SPICE 实现）。"""
    r0 = parameters["r0_ohm"]
    branches = []
    if order >= 1:
        branches.append((parameters["r1_ohm"], parameters["tau1_s"]))
    if order >= 2:
        branches.append((parameters["r2_ohm"], parameters["tau2_s"]))
    polarization = [0.0] * len(branches)
    ocv = parameters["ocv_v"]
    voltages = np.empty(len(time_values))
    for index in range(len(time_values) - 1):
        voltages[index] = ocv - current_values[index] * r0 - sum(polarization)
        dt = time_values[index + 1] - time_values[index]
        polarization = [
            value * math.exp(-dt / tau) + current_values[index] * resistance * (1.0 - math.exp(-dt / tau))
            for value, (resistance, tau) in zip(polarization, branches)
        ]
    voltages[-1] = ocv - current_values[-1] * r0 - sum(polarization)
    return voltages


def latest_run(category: str) -> Path | None:
    base = RESULTS_ROOT / category
    if not base.exists():
        return None
    runs = sorted([path for path in base.iterdir() if path.is_dir()])
    return runs[-1] if runs else None


def main() -> int:
    run = RunDirectory("identified_spice")
    frozen = {name: load_frozen_model(model_id) for name, model_id in MODEL_IDS.items()}
    second = frozen["second_order_rc"]
    parameters = second["parameters"]
    ocv_model = second["ocv_model"]
    ocv_value = ocv_model.voltage(TEST_SOC)
    profile = piecewise_profile(
        [(10.0, 0.0), (60.0, 2.0), (120.0, 0.0)],
        name="identified_parameter_pulse",
        description="固定 OCV 下的 2 A 脉冲，用于 Python/SPICE/解析三方对照",
    )

    run.write_metadata(
        {
            "script": "scripts/identified_spice_demo.py",
            "data_source": "spice_simulation",
            "frozen_models": {name: bundle["paths"] for name, bundle in frozen.items()},
            "test_soc": TEST_SOC,
            "fixed_ocv_v": ocv_value,
            "profile": profile.name,
            "note": "固定 OCV 局部脉冲只验证参数到网表的映射，不是完整 SOC 耦合仿真。",
        }
    )

    comparisons = {}
    for name, bundle in frozen.items():
        model_parameters = bundle["parameters"]
        definition = model_parameters.as_definition()
        spice = run_spice_single_cell(
            script="scripts/identified_spice_demo.py",
            model_name=name,
            parameters=definition.parameters,
            branches=definition.branches,
            ocv_v=ocv_value,
            profile=profile,
            step_s=0.05,
        )
        time_values, current_values = profile.sample(0.05)
        python_result = simulate_ecm(
            definition.parameters,
            definition.branches,
            CellState.initial(TEST_SOC, definition.order, 0.0),
            time_values,
            current_values,
            ConstantOcvModel(ocv_value),
            model_name=name,
            stop_on_limits=False,
        )
        analytic = analytic_pulse_response(
            time_values,
            current_values,
            {
                "ocv_v": ocv_value,
                "r0_ohm": model_parameters.r0_ohm,
                "r1_ohm": model_parameters.r1_ohm or 0.0,
                "tau1_s": model_parameters.tau1_s or 1.0,
                "r2_ohm": model_parameters.r2_ohm or 0.0,
                "tau2_s": model_parameters.tau2_s or 1.0,
            },
            definition.order,
        )
        python_spice = compare_frames(
            spice["frame"],
            python_result.frame,
            reference_name="ngspice",
            exclude_times_s=(10.0, 70.0),
            exclude_window_s=0.15,
        )
        analytic_max_error = float(
            np.max(np.abs(analytic - python_result.frame["terminal_voltage_v"].to_numpy(dtype=float)))
        )
        comparisons[name] = {
            "spice_run_id": spice["run_id"],
            "netlist_path": spice["summary"]["netlist_path"],
            "waveform_path": spice["summary"]["waveform_path"],
            "python_vs_spice": python_spice,
            "analytic_vs_python_max_v": analytic_max_error,
        }
        plot_multi_series(
            [
                ("ngspice 真实求解", spice["frame"]["time_s"], spice["frame"]["terminal_voltage_v"]),
                ("Python ECM", python_result.frame["time_s"], python_result.frame["terminal_voltage_v"]),
            ],
            path=run.path / "plots" / f"22_python_spice_{name}.png",
            xlabel="时间 (s)",
            ylabel="端电压 (V)",
            title=f"{name}: 辨识参数下的 Python 与 ngspice 对照",
            annotation=(
                f"固定 OCV={ocv_value:.4f} V, SOC={TEST_SOC} | 最大差异 "
                f"{python_spice['max_abs_error_v'] * 1000:.4f} mV | Run: {run.run_id}"
            ),
        )

    # 3S1P：使用辨识二阶参数与真实 OCV 曲线
    definition = parameters.as_definition()
    pack = build_uniform_pack(definition, ocv_model, count=3, initial_soc=TEST_SOC)
    sample_time, sample_current = profile.sample(0.1)
    pack_result = simulate_series_pack(pack, sample_time, sample_current, stop_on_limits=True)
    pack_frame = pack_result["pack_frame"]
    cell_frame = pack_result["cell_frame"]
    pack_frame.to_csv(run.path / "pack_waveform.csv", index=False)
    cell_frame.to_csv(run.path / "pack_cell_waveform.csv", index=False)

    power_pack = build_uniform_pack(parameters.as_definition(), ocv_model, count=3, initial_soc=0.9)
    constant_power = simulate_constant_power(power_pack, 20.0, duration_s=600.0, dt_s=0.1)
    constant_power["frame"].to_csv(run.path / "pack_constant_power_20w.csv", index=False)

    plot_multi_series(
        [
            ("组端电压", pack_frame["time_s"], pack_frame["pack_voltage_v"]),
            ("最大单体电压", pack_frame["time_s"], pack_frame["max_cell_voltage_v"]),
            ("最小单体电压", pack_frame["time_s"], pack_frame["min_cell_voltage_v"]),
        ],
        path=run.path / "plots" / "23_3s_pack_voltage.png",
        xlabel="时间 (s)",
        ylabel="电压 (V)",
        title="3S1P：辨识参数下的组端与单体电压",
        annotation=(
            f"来源: custom_ecm_simulation | 模型: 二阶 RC 辨识参数 | 初始 SOC {TEST_SOC}"
            f" | 角色: 工程演示（非实验验证） | Run: {run.run_id} | 单位: V"
        ),
    )
    if "cell_id" in cell_frame.columns:
        series = [
            (f"{cell_id} 单体电压", part["time_s"], part["terminal_voltage_v"])
            for cell_id, part in cell_frame.groupby("cell_id", sort=True)
        ]
        series.append(("组端电压 / 3", pack_frame["time_s"], pack_frame["pack_voltage_v"] / 3.0))
        plot_multi_series(
            series,
            path=run.path / "plots" / "23b_3s_individual_cell_voltage.png",
            xlabel="时间 (s)",
            ylabel="单体电压 (V)",
            title="3S1P：三节单体电压与组端电压折算对照",
            annotation=(
                f"来源: custom_ecm_simulation | 均匀参数下三节曲线重合 | Run: {run.run_id} | 单位: V"
            ),
        )

    validation_run = latest_run("dynamic_validation")
    fuds_rmse_mv = None
    fuds_mae_mv = None
    fuds_max_mv = None
    measured_voltage_range_v = None
    if validation_run is not None:
        metrics_path = validation_run / "validation_metrics.json"
        if metrics_path.exists():
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            fuds = [row for row in payload["validation_table"] if row["experiment"].startswith("fuds")]
            if fuds:
                fuds_rmse_mv = float(np.mean([row["rmse_mv"] for row in fuds]))
                fuds_mae_mv = float(np.mean([row["mae_mv"] for row in fuds]))
                fuds_max_mv = float(np.max([row["max_mv"] for row in fuds]))
        waveform_path = validation_run / "predicted_waveform_fuds_80_first_order_rc.csv.gz"
        if waveform_path.exists():
            waveform = pd.read_csv(waveform_path)
            measured = waveform["measured_voltage_v"].to_numpy(dtype=float)
            measured_voltage_range_v = float(np.max(measured) - np.min(measured))

    dynamic_range_text = (
        f"{measured_voltage_range_v:.4f}" if measured_voltage_range_v is not None else "NOT_VERIFIED"
    )
    fuds_error_text = f"{fuds_rmse_mv:.2f}" if fuds_rmse_mv is not None else "NOT_VERIFIED"
    fuds_max_text = f"{fuds_max_mv:.2f}" if fuds_max_mv is not None else "NOT_VERIFIED"
    ohmic_drop_mv = abs(parameters.r0_ohm * 4.0) * 1000.0
    polarization_drop_mv = abs((parameters.r1_ohm or 0.0) + (parameters.r2_ohm or 0.0)) * 4.0 * 1000.0
    rest_load_difference_mv = ohmic_drop_mv + polarization_drop_mv
    ocv_slope_mid_mv_per_soc = (ocv_model.voltage(0.55) - ocv_model.voltage(0.45)) * 1000 / 0.1
    ocv_difference_03_07_mv = (ocv_model.voltage(0.7) - ocv_model.voltage(0.3)) * 1000

    # BMS 硬件设计参考表：按 AFE 电压采集 / 电流采集 / MOSFET 保护 / 均衡 / CC-CV 五节组织
    bms_rows = [
        {
            "section": "AFE电压采集",
            "item": "实际单体电压范围",
            "value": "2.4034 – 4.2001",
            "unit": "V",
            "condition": "CALCE SP2 25℃ DST/FUDS/US06/BJDST",
            "source": "public_experimental_data",
            "note": "AFE 输入范围需覆盖该区间并留裕量，最终以电芯 datasheet 为准。",
        },
        {
            "section": "AFE电压采集",
            "item": "实际动态电压跌落（FUDS 80%）",
            "value": dynamic_range_text,
            "unit": "V",
            "condition": "FUDS 80% SOC 全程（实测端电压最大值减最小值）",
            "source": "public_experimental_data",
            "note": "用于估计动态范围与采样量程，不代表单一负载阶跃幅度。",
        },
        {
            "section": "AFE电压采集",
            "item": "一阶 RC 模型预测 RMSE",
            "value": fuds_error_text,
            "unit": "mV",
            "condition": "25℃ FUDS 50%/80% 独立验证平均",
            "source": "custom_ecm_simulation",
            "note": "模型误差，不是 AFE 测量误差；两者需分别进入误差预算。",
        },
        {
            "section": "AFE电压采集",
            "item": "建议电压采集分辨率（设计需求）",
            "value": "≤ 1",
            "unit": "mV",
            "condition": "目标 SOC 分辨率 0.01 时，按中段斜率反推",
            "source": "analytical_theory",
            "note": f"中段 OCV 斜率约 {ocv_slope_mid_mv_per_soc:.0f} mV/SOC，1 mV 采集误差约对应 0.0015 SOC。",
        },
        {
            "section": "电流采集",
            "item": "实际实验电流范围",
            "value": "−2.142 – +4.002",
            "unit": "A",
            "condition": "CALCE SP2 25℃ 动态工况",
            "source": "public_experimental_data",
            "note": "实验峰值不能直接作为允许充放电电流或保护阈值。",
        },
        {
            "section": "电流采集",
            "item": "电流方向约定",
            "value": "放电为正 / 充电为负",
            "unit": "—",
            "condition": "全项目统一归一化约定",
            "source": "educational_assumption",
            "note": "原始 CALCE 文件为充电为正，加载器统一转换为放电为正并做回归测试。",
        },
        {
            "section": "电流采集",
            "item": "建议电流采样误差（设计需求）",
            "value": f"≤ {5.0 / ohmic_drop_mv * 100:.2f}",
            "unit": "% FS",
            "condition": "按 4 A 满量程、R0 压降误差 ≤ 5 mV 估算",
            "source": "analytical_theory",
            "note": "采样电阻与 ADC 增益误差共同决定；需结合真实器件规格。",
        },
        {
            "section": "MOSFET保护",
            "item": "辨识欧姆内阻 R0",
            "value": f"{parameters.r0_ohm * 1000:.2f}",
            "unit": "mΩ",
            "condition": "25℃ DST 拟合",
            "source": "identified_parameters",
            "note": "含 1 s 尺度快极化的一部分，不是纯欧姆电阻。",
        },
        {
            "section": "MOSFET保护",
            "item": "4 A 峰值下 R0 压降",
            "value": f"{ohmic_drop_mv:.1f}",
            "unit": "mV",
            "condition": "4 A 峰值",
            "source": "identified_parameters",
            "note": "保护阈值与电压采集误差预算的关键量。",
        },
        {
            "section": "MOSFET保护",
            "item": "负载变化下端电压瞬变",
            "value": f"{rest_load_difference_mv:.1f}",
            "unit": "mV",
            "condition": "0 ↔ 4 A 阶跃，R0 + 稳态极化估算",
            "source": "identified_parameters",
            "note": "过流/短路保护去抖时间需大于真实负载阶跃引起的正常压降。",
        },
        {
            "section": "MOSFET保护",
            "item": "3S 单体一致性（仿真）",
            "value": "0.000",
            "unit": "mV",
            "condition": "3S1P 均匀参数、初始 SOC 0.55",
            "source": "custom_ecm_simulation",
            "note": "均匀参数下必然为 0，不能证明真实电芯一致性或均衡算法有效。",
        },
        {
            "section": "电池均衡",
            "item": "0.3 与 0.7 SOC 的 OCV 差",
            "value": f"{ocv_difference_03_07_mv:.1f}",
            "unit": "mV",
            "condition": "25℃，辨识 OCV 曲线",
            "source": "identified_parameters",
            "note": "均衡判定阈值需高于采集误差与迟滞。",
        },
        {
            "section": "电池均衡",
            "item": "OCV-SOC 中段斜率",
            "value": f"{ocv_slope_mid_mv_per_soc:.1f}",
            "unit": "mV/SOC",
            "condition": "SOC 45%–55%",
            "source": "identified_parameters",
            "note": "平台区斜率小，电压采集误差会被放大为 SOC 误差。",
        },
        {
            "section": "电池均衡",
            "item": "静置与负载状态电压差别",
            "value": f"{rest_load_difference_mv:.1f}",
            "unit": "mV",
            "condition": "4 A 负载相对静置",
            "source": "identified_parameters",
            "note": "均衡采样必须在静置或已知电流下进行，避免把极化压降当作 SOC 差。",
        },
        {
            "section": "CC-CV控制",
            "item": "实测容量",
            "value": "2.0281",
            "unit": "Ah",
            "condition": "SP2 25℃ 1 A 恒流放电",
            "source": "public_experimental_data",
            "note": "额定 2.0 Ah；比值不等于已验证 SOH。",
        },
        {
            "section": "CC-CV控制",
            "item": "充电方向内阻压升",
            "value": "NOT_VERIFIED",
            "unit": "mV",
            "condition": "当前公开数据缺少大电流充电阶跃",
            "source": "public_experimental_data",
            "note": "仅有 0.1 A 低电流充电，无法分离充电方向欧姆压升；不构造替代数据。",
        },
        {
            "section": "CC-CV控制",
            "item": "慢速极化时间常数",
            "value": f"{parameters.tau2_s:.1f}",
            "unit": "s",
            "condition": "25℃ 静置恢复拟合",
            "source": "identified_parameters",
            "note": "静置 3τ 以上才接近平衡，影响 CV 阶段终止与均衡延时。",
        },
        {
            "section": "CC-CV控制",
            "item": "CV 阶段极化恢复比例（3τ 后）",
            "value": "95.0",
            "unit": "%",
            "condition": "一阶指数近似，t = 3τ",
            "source": "analytical_theory",
            "note": "1 - exp(-3) ≈ 95%，用于估算 CV 保持时间下限。",
        },
        {
            "section": "CC-CV控制",
            "item": "FUDS 独立验证 MAE",
            "value": f"{fuds_mae_mv:.2f}" if fuds_mae_mv is not None else "NOT_VERIFIED",
            "unit": "mV",
            "condition": "25℃ FUDS 50%/80%",
            "source": "custom_ecm_simulation",
            "note": "模型误差预算，不是硬件测量误差。",
        },
        {
            "section": "CC-CV控制",
            "item": "FUDS 独立验证最大瞬时误差",
            "value": fuds_max_text,
            "unit": "mV",
            "condition": "25℃ FUDS 50%/80%",
            "source": "custom_ecm_simulation",
            "note": "空电区大电流末端误差，未达标项如实保留。",
        },
    ]
    bms_frame = pd.DataFrame(bms_rows)
    bms_frame.to_csv(run.path / "bms_design_reference.csv", index=False)

    summary = {
        "script": "scripts/identified_spice_demo.py",
        "run_id": run.run_id,
        "fixed_ocv_v": ocv_value,
        "test_soc": TEST_SOC,
        "spice_comparisons": comparisons,
        "spice_max_voltage_error_mv": {
            name: payload["python_vs_spice"]["max_abs_error_v"] * 1000 for name, payload in comparisons.items()
        },
        "spice_cross_validation_pass": bool(
            all(payload["python_vs_spice"]["max_abs_error_v"] <= 0.001 for payload in comparisons.values())
        ),
        "spice_solver_runs": 3,
        "pack": {
            "topology": pack_result["metadata"]["topology"],
            "pack_voltage_start_v": float(pack_frame["pack_voltage_v"].iloc[0]),
            "pack_voltage_end_v": float(pack_frame["pack_voltage_v"].iloc[-1]),
            "max_delta_cell_voltage_v": float(pack_frame["delta_cell_voltage_v"].max()),
            "first_limited_cell": pack_result["metadata"]["termination_cell"],
            "termination": pack_result["metadata"]["termination"],
            "constant_power_20w_termination": constant_power["metadata"]["termination"],
            "constant_power_20w_duration_s": float(constant_power["frame"]["time_s"].iloc[-1]),
        },
        "bms_reference": bms_rows,
        "bms_sections": sorted({row["section"] for row in bms_rows}),
        "note": "3S 仿真使用辨识单体参数，不等于真实 3S 电池组实验验证。",
    }
    write_json(run.path / "spice_pack_bms_summary.json", summary)
    run.write_summary(summary)
    run.log(f"SPICE max error mV: {summary['spice_max_voltage_error_mv']}")
    run.flush_log()

    print(f"identified_spice run_id={run.run_id}")
    print("fixed OCV:", round(ocv_value, 6), "V at SOC", TEST_SOC)
    for name, payload in comparisons.items():
        print(name, "python-spice max mV:", round(payload["python_vs_spice"]["max_abs_error_v"] * 1000, 6))
    print("3S pack:", summary["pack"])
    print("BMS rows:", len(bms_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
