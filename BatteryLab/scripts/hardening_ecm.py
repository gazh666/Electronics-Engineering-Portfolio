"""Task 9：ECM 低 SOC 分区误差审计入口。

运行：
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.hardening_ecm
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
from hardening.low_soc_model_analysis import (  # noqa: E402
    BANDS,
    band_metrics,
    identification_metrics,
    load_residuals,
    low_soc_dominant,
    model_comparison,
    plot,
    temperature_and_pack_availability,
    upgrade_improvement,
)


def main() -> int:
    run = new_run("ecm")
    frame = load_residuals()
    bands = band_metrics(frame, BANDS)
    comparisons = model_comparison(frame)
    upgrades = upgrade_improvement(frame)
    write_csv(run / "low_soc_error_by_band.csv", bands)
    write_csv(run / "model_comparison_by_experiment.csv", comparisons)
    write_csv(run / "model_upgrade_improvement.csv", [
        {
            "experiment": row["experiment"],
            "status": row["status"],
            "rint_rmse_mv": row.get("rint_rmse_mv"),
            "first_order_rmse_mv": row.get("first_order_rmse_mv"),
            "second_order_rmse_mv": row.get("second_order_rmse_mv"),
            "rint_to_first_percent": (row.get("rint_to_first") or {}).get("improvement_percent"),
            "first_to_second_percent": (row.get("first_to_second") or {}).get("improvement_percent"),
        }
        for row in upgrades
    ])
    plots = plot(frame, bands, run / "plots")

    summary = {
        "run_id": run.name,
        "source": str(Path("results/dynamic_validation/run_dynamic_validation_20261126_131720_0e4677/residuals.csv.gz")),
        "bands": BANDS,
        "points": int(frame.shape[0]),
        "experiments": sorted(frame["experiment"].unique().tolist()),
        "models": sorted(frame["model"].unique().tolist()),
        "model_comparison": comparisons,
        "upgrade_improvement": upgrades,
        "low_soc_dominant": low_soc_dominant(frame, bands),
        "identification": identification_metrics(),
        "availability": temperature_and_pack_availability(),
        "preserved_failures": {
            "low_soc_max_error_mv": 375.836,
            "note": "历史低 SOC 最大误差 375.836 mV 永久保留；本任务不通过删点或降低限值改善该值。",
        },
        "leakage_control": {
            "refit_on_validation": False,
            "note": "未使用验证数据重新拟合；未提出未经独立验证的低 SOC 改进。",
        },
        "plots": plots,
        "limitations": [
            "残差来自 CALCE 公开数据重放，参考 SOC 由电流积分推导，不是直接实测真实 SOC。",
            "低 SOC 区间样本少且 OCV 平台平坦，参数外推误差大。",
            "无多温度实测与 3S 组电压参考，相关指标 NOT_VERIFIED。",
        ],
    }
    write_json(run / "low_soc_analysis_summary.json", summary)
    worst = summary["low_soc_dominant"]["low_soc_worst"]
    print(json.dumps({
        "run_id": run.name,
        "points": summary["points"],
        "low_soc_worst": {key: worst[key] for key in ("experiment", "model", "band_low", "band_high", "rmse_mv", "max_abs_mv")},
        "experiments": summary["experiments"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
