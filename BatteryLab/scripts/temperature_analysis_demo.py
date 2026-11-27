"""Task 26/30：温度特性分析（真实数据仅 25℃，其余如实标记 NOT_VERIFIED）。

运行：conda run -n kaifa_battery python -m scripts.temperature_analysis_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from identification.parameter_store import load_frozen_model
from scripts.stage3_common import configs
from storage.result_store import RunDirectory, write_json
from validation.temperature_validation import (
    cross_temperature_validation,
    per_temperature_identification,
    temperature_analysis_status,
    temperature_parameter_table,
)

MODEL_IDS = {
    "rint": "calce_sp2_25c_inr18650_20r_rint_v1",
    "first_order_rc": "calce_sp2_25c_inr18650_20r_first_order_v1",
    "second_order_rc": "calce_sp2_25c_inr18650_20r_second_order_v1",
}


def main() -> int:
    run = RunDirectory("temperature")
    settings = configs()
    frozen = {name: load_frozen_model(model_id) for name, model_id in MODEL_IDS.items()}
    available = [25.0]
    status = temperature_analysis_status(available, tuple(settings["validation"]["temperature"]["target_temperatures_c"]))
    table = temperature_parameter_table({25.0: frozen["second_order_rc"]})

    experiment_a = cross_temperature_validation(frozen, experiments_by_temperature={})
    experiment_b = per_temperature_identification({}, fit_function=lambda temperature, experiments: {"status": "NOT_VERIFIED"})

    summary = {
        "script": "scripts/temperature_analysis_demo.py",
        "run_id": run.run_id,
        "data_source": "public_experimental_data",
        "available_temperatures_c": available,
        "status": status,
        "experiment_a_cross_temperature": experiment_a,
        "experiment_b_per_temperature_identification": experiment_b,
        "temperature_parameter_table": table.to_dict("records"),
        "parameter_source_25c": {name: bundle["paths"] for name, bundle in frozen.items()},
        "note": (
            "已下载的 CALCE 公开数据只包含 25℃ 标称环境温度。"
            "未获取 0℃/45℃ 真实实验文件，因此不给出温度-参数结论，也不使用人工数据填补。"
        ),
    }
    table.to_csv(run.path / "temperature_parameter_table.csv", index=False)
    write_json(run.path / "temperature_report.json", summary)
    run.write_metadata({"script": "scripts/temperature_analysis_demo.py", "data_source": "public_experimental_data"})
    run.write_summary(summary)
    run.log(f"temperature status={status['status']}")
    run.flush_log()

    print(f"temperature run_id={run.run_id}")
    print("status:", status)
    print("experiment A:", experiment_a)
    print("experiment B:", experiment_b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
