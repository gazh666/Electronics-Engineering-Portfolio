"""Task 7-9/30：低电流与增量 OCV 提取、真实 OCV 查表模型。

运行：conda run -n kaifa_battery python -m scripts.ocv_extraction_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from battery_models.ocv_model import IdentifiedOcvModel
from identification.ocv_extractor import extract_low_current_ocv, relaxation_points
from scripts.stage3_common import configs, load_record, ocv_bundle, write_ocv_artifacts
from storage.result_store import RunDirectory, write_json
from visualization.plots import plot_multi_series, plot_xy


def _cross_cell_comparison(primary_model: IdentifiedOcvModel, secondary_frame: pd.DataFrame, grid_points: int) -> dict:
    try:
        secondary = extract_low_current_ocv(
            secondary_frame,
            capacity_ah=2.0,
            current_tolerance_a=0.20,
            grid_points=grid_points,
        )
    except Exception as exc:  # 真实数据缺失方向时如实记录，不构造替代曲线
        return {
            "status": "NOT_VERIFIED",
            "reason": f"SP3 低电流 OCV 提取失败: {exc}",
        }
    grid = secondary["average"]["soc"].to_numpy(dtype=float)
    primary = np.asarray([primary_model.voltage(float(soc)) for soc in grid])
    secondary_values = secondary["average"]["ocv_v"].to_numpy(dtype=float)
    mask = np.isfinite(secondary_values) & (grid >= 0.05) & (grid <= 0.85)
    difference = primary[mask] - secondary_values[mask]
    return {
        "secondary_dataset": "calce_inr18650_20r_sp3_25c_low_current_ocv_20151116",
        "common_points": int(mask.sum()),
        "mean_absolute_difference_v": float(np.mean(np.abs(difference))) if mask.sum() else None,
        "maximum_absolute_difference_v": float(np.max(np.abs(difference))) if mask.sum() else None,
        "difference_at_soc": {
            f"{soc:.1f}": float(primary_model.voltage(soc) - np.interp(soc, grid, secondary_values))
            for soc in (0.1, 0.3, 0.5, 0.7, 0.8)
        },
        "curves": secondary,
        "note": "SP1 与 SP3 为同型号不同样品，差异属于样品间 OCV 差异，不是测量噪声。",
    }


def main() -> int:
    run = RunDirectory("ocv")
    settings = configs()
    bundle = ocv_bundle()
    model = bundle["model"]
    curves = bundle["curves"]
    metrics = curves["metrics"]
    paths = write_ocv_artifacts(bundle, run.path / "ocv")
    run.write_metadata(
        {
            "script": "scripts/ocv_extraction_demo.py",
            "data_source": "public_experimental_data",
            "source_datasets": [
                settings["split"]["datasets"]["ocv_low_current_primary"],
                settings["split"]["datasets"]["ocv_low_current_cross_cell"],
                settings["split"]["datasets"]["ocv_incremental"],
            ],
        }
    )

    # 增量 OCV：SP3 文件时间轴跨工作表不连续，先做真实质量检查。
    ic_frame = load_record("ocv_incremental")
    ic_points, ic_report = relaxation_points(
        ic_frame,
        initial_soc=1.0,
        capacity_ah=2.0,
        rest_tolerance_a=0.01,
        minimum_rest_s=settings["identification"]["incremental_ocv"]["minimum_rest_s"],
        end_window_s=settings["identification"]["incremental_ocv"]["end_window_s"],
        maximum_drift_v_per_h=settings["identification"]["incremental_ocv"]["maximum_end_drift_v_per_h"],
        temperature_c=25.0,
    )
    if not ic_points.empty:
        ic_points.to_csv(run.path / "ocv_relaxation_points.csv", index=False)

    # SP1 低电流实验中的静置段（满充后 / 放空后）作为增量静置点核对
    primary_frame = load_record("ocv_low_current_primary")
    primary_points, primary_report = relaxation_points(
        primary_frame,
        initial_soc=1.0,
        capacity_ah=bundle["capacities"]["sp1"].integrated_capacity_ah,
        minimum_rest_s=settings["identification"]["incremental_ocv"]["minimum_rest_s"],
        end_window_s=settings["identification"]["incremental_ocv"]["end_window_s"],
        maximum_drift_v_per_h=settings["identification"]["incremental_ocv"]["maximum_end_drift_v_per_h"],
        temperature_c=25.0,
    )

    cross = _cross_cell_comparison(model, load_record("ocv_low_current_cross_cell"), settings["identification"]["ocv"]["soc_grid_points"])
    cross_ok = cross.get("status") != "NOT_VERIFIED"

    # 插值方式对照（同一批实测点，不是新增测量）
    pchip_model = IdentifiedOcvModel(
        model.soc_table, model.ocv_table, metadata_info=model.metadata_info, interpolation="pchip"
    )
    check_soc = np.linspace(0.0, 1.0, 1001)
    interpolation_difference = np.asarray(
        [abs(model.voltage(float(soc)) - pchip_model.voltage(float(soc))) for soc in check_soc]
    )

    quality = {
        "low_current": metrics,
        "ocv_table": {
            "points": int(len(model.soc_table)),
            "measured_points": int(metrics["charge"]["valid_points"] + metrics["discharge"]["valid_points"]),
            "interpolation": model.interpolation,
            "pchip_max_difference_v": float(np.max(interpolation_difference)),
            "soc_min": 0.0,
            "soc_max": 1.0,
            "table_metadata": bundle["table_metadata"],
        },
        "incremental_ocv": ic_report,
        "incremental_points": int(len(ic_points)),
        "primary_rest_points": primary_report,
        "cross_cell": {key: value for key, value in cross.items() if key != "curves"},
        "status": "IDENTIFIED",
        "note": (
            "OCV 曲线由低电流充放电平均得到；增量 OCV 仅在静置质量通过时使用。"
            "1000 点插值不等于 1000 个独立实测点。"
        ),
    }
    usable_incremental = int(ic_report.get("usable_points", 0))
    quality["incremental_status"] = (
        "IDENTIFIED" if len(ic_points) > 0 and usable_incremental >= 3 else "NOT_VERIFIED"
    )

    write_json(run.path / "ocv_quality_report.json", quality)
    write_json(
        run.path / "ocv_soc.csv",
        pd.DataFrame({"soc": model.soc_table, "ocv_v": model.ocv_table}).to_dict("records"),
    )
    pd.DataFrame({"soc": check_soc, "ocv_linear_v": [model.voltage(float(s)) for s in check_soc],
                  "ocv_pchip_v": [pchip_model.voltage(float(s)) for s in check_soc]}).to_csv(
        run.path / "ocv_interpolation_comparison.csv", index=False
    )

    grid = curves["average"]["soc"].to_numpy(dtype=float)
    plot_multi_series(
        [
            ("充电方向", grid, curves["charge"]["ocv_v"]),
            ("放电方向", grid, curves["discharge"]["ocv_v"]),
            ("平均 OCV", grid, curves["average"]["ocv_v"]),
        ],
        path=run.path / "plots" / "04_05_low_current_ocv_soc.png",
        xlabel="SOC",
        ylabel="端电压近似 OCV (V)",
        title="SP1 低电流 OCV-SOC 曲线（真实 CALCE 数据）",
        annotation=(
            "来源: public_experimental_data | 文件: SP1_25C_LC_OCV_11_5_2015.zip | 条件: 25℃, ±0.1 A"
            f" | 模型: 辨识 OCV 查表 | 角色: 拟合输入 | Run: {run.run_id} | 单位: V"
        ),
    )
    plot_xy(
        curves["charge"]["soc"],
        curves["charge"]["ocv_v"],
        path=run.path / "plots" / "04_low_current_charge_ocv.png",
        xlabel="SOC",
        ylabel="充电方向端电压近似 OCV (V)",
        title="低电流充电 OCV-SOC（真实 CALCE SP1）",
        annotation=(
            "来源: public_experimental_data | 文件: SP1_25C_LC_OCV_11_5_2015.zip | 条件: 25℃, 0.1 A 充电"
            f" | 模型: 辨识 OCV 查表输入 | 角色: 拟合输入 | Run: {run.run_id} | 单位: V"
        ),
        color="#2ca02c",
    )
    plot_xy(
        curves["discharge"]["soc"],
        curves["discharge"]["ocv_v"],
        path=run.path / "plots" / "05_low_current_discharge_ocv.png",
        xlabel="SOC",
        ylabel="放电方向端电压近似 OCV (V)",
        title="低电流放电 OCV-SOC（真实 CALCE SP1）",
        annotation=(
            "来源: public_experimental_data | 文件: SP1_25C_LC_OCV_11_5_2015.zip | 条件: 25℃, 0.1 A 放电"
            f" | 模型: 辨识 OCV 查表输入 | 角色: 拟合输入 | Run: {run.run_id} | 单位: V"
        ),
        color="#d62728",
    )
    plot_xy(
        grid,
        curves["hysteresis"]["hysteresis_v"],
        path=run.path / "plots" / "08_ocv_hysteresis.png",
        xlabel="SOC",
        ylabel="迟滞电压 (V)",
        title="充放电迟滞（OCV_charge - OCV_discharge）",
        annotation=(
            f"最大迟滞 {metrics.get('maximum_hysteresis_v', float('nan')) * 1000:.1f} mV | "
            f"来源: public_experimental_data | 文件: SP1_25C_LC_OCV_11_5_2015.zip | 条件: 25℃"
            f" | 角色: 拟合输入 | Run: {run.run_id} | 单位: V"
        ),
    )
    plot_multi_series(
        [
            ("分段线性", check_soc, [model.voltage(float(s)) for s in check_soc]),
            ("PCHIP", check_soc, [pchip_model.voltage(float(s)) for s in check_soc]),
        ],
        path=run.path / "plots" / "07_ocv_table_interpolation.png",
        xlabel="SOC",
        ylabel="OCV (V)",
        title="OCV 查表模型插值对照",
        annotation=f"最大差异 {np.max(interpolation_difference) * 1000:.2f} mV | Run: {run.run_id}",
    )
    if not primary_points.empty:
        plot_xy(
            primary_points["soc_reference"],
            primary_points["end_window_mean_v"],
            path=run.path / "plots" / "06_relaxation_points.png",
            xlabel="SOC 参考值",
            ylabel="静置末端电压 (V)",
            title="低电流实验静置末端点",
            annotation=(
                f"来源: public_experimental_data | 文件: SP1_25C_LC_OCV_11_5_2015.zip | 条件: 25℃ 静置"
                f" | 角色: 拟合输入 | Run: {run.run_id} | 单位: V"
            ),
        )
    if not ic_points.empty:
        plot_xy(
            ic_points["soc_reference"],
            ic_points["end_window_mean_v"],
            path=run.path / "plots" / "06b_incremental_ocv_points.png",
            xlabel="SOC 参考值",
            ylabel="静置末端电压 (V)",
            title=f"增量 OCV 静置点（22 段中 {usable_incremental} 段通过质量检查）",
            annotation=(
                "来源: public_experimental_data | 文件: SP3_25C_IC_OCV_12_2_2015.zip | 条件: 25℃ 静置"
                f" | 角色: 独立核对（不参与拟合） | Run: {run.run_id} | 单位: V"
            ),
            color="#9467bd",
        )

    secondary = cross.get("curves")
    if cross_ok and secondary is not None:
        plot_multi_series(
            [
                ("SP1 平均 OCV", curves["average"]["soc"], curves["average"]["ocv_v"]),
                ("SP3 平均 OCV", secondary["average"]["soc"], secondary["average"]["ocv_v"]),
            ],
            path=run.path / "plots" / "ocv_cross_cell_comparison.png",
            xlabel="SOC",
            ylabel="OCV (V)",
            title="同型号不同样品 OCV 对照",
            annotation=f"最大差异 {cross['maximum_absolute_difference_v'] * 1000:.1f} mV | Run: {run.run_id}",
        )

    summary = {
        "script": "scripts/ocv_extraction_demo.py",
        "run_id": run.run_id,
        "ocv_points_measured": quality["ocv_table"]["measured_points"],
        "ocv_table_points": quality["ocv_table"]["points"],
        "common_soc_range": [metrics["common_soc_min"], metrics["common_soc_max"]],
        "maximum_hysteresis_v": metrics.get("maximum_hysteresis_v"),
        "maximum_hysteresis_mv": (
            float(metrics["maximum_hysteresis_v"]) * 1000.0 if metrics.get("maximum_hysteresis_v") is not None else None
        ),
        "maximum_hysteresis_soc": metrics.get("maximum_hysteresis_soc"),
        "incremental_points": int(len(ic_points)),
        "incremental_status": quality.get("incremental_status", "IDENTIFIED"),
        "cross_cell_max_difference_mv": cross.get("maximum_absolute_difference_v"),
        "artifacts": paths,
        "plots": sorted(str(path) for path in (run.path / "plots").glob("*.png")),
    }
    run.write_summary(summary)
    run.log(f"OCV table points={len(model.soc_table)}, measured={summary['ocv_points_measured']}")
    run.flush_log()

    print(f"ocv run_id={run.run_id}")
    print("discharge branch:", metrics["discharge"])
    print("charge branch:", metrics["charge"])
    print("hysteresis max V:", metrics.get("maximum_hysteresis_v"), "at soc", metrics.get("maximum_hysteresis_soc"))
    print("incremental report:", ic_report)
    print("primary rest report:", primary_report)
    print("cross-cell:", {key: value for key, value in cross.items() if key != "curves"})
    print("pchip max diff V:", float(np.max(interpolation_difference)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
