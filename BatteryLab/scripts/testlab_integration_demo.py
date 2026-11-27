"""任务 24/26：用 TestLab 真实限值判定模块处理 BatteryLab 系统结果。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from battery_models.parameters import PROJECT_ROOT  # noqa: E402
from integration.measurement_exchange import SystemMeasurement  # noqa: E402
from integration.testlab_adapter import inspect_testlab_api, judge_measurements  # noqa: E402
from scripts.stage9_common import STAGE9_RESULTS, new_run_dir, validation_limits, write_json  # noqa: E402
from validation.system_result_judge import judge  # noqa: E402


def latest_case_result() -> Path | None:
    base = PROJECT_ROOT / "results" / "system_spice"
    candidates = sorted(base.glob("integrated_*/case_result.json"), key=lambda item: item.stat().st_mtime)
    return candidates[-1] if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(description="TestLab 真实判定调用")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--case-result", default=None)
    args = parser.parse_args()

    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir))
        if args.run_dir
        else new_run_dir(STAGE9_RESULTS / "testlab_integration", "testlab")
    )
    directory.mkdir(parents=True, exist_ok=True)

    case_path = Path(args.case_result) if args.case_result else latest_case_result()
    if case_path is None or not case_path.is_file():
        payload = {"run_id": run_id, "status": "BLOCKED", "reason": "缺少联合仿真结果"}
        write_json(directory / "case_result.json", payload)
        if args.json_out:
            write_json(args.json_out, payload)
        print(json.dumps({"run_id": run_id, "status": "BLOCKED"}, ensure_ascii=False))
        return 1

    integrated_case = json.loads(case_path.read_text(encoding="utf-8"))
    metrics = integrated_case.get("metrics") or {}
    limits = validation_limits()["nominal"]

    measurement_specs = [
        ("output_voltage_mean_v", "output_voltage_mean_v", "V", limits["output_voltage_mean_v"]),
        ("output_voltage_ripple_vpp", "output_voltage_ripple_vpp", "V", limits["output_ripple_vpp"]),
        ("inductor_peak_current_a", "inductor_peak_current_a", "A", limits["inductor_peak_current_a"]),
        ("converter_input_voltage_v", "input_voltage_mean_v", "V", limits["converter_input_voltage_v"]),
    ]
    measurements = []
    convert_limits: dict[str, dict[str, float]] = {}
    for metric, source_key, unit, limit in measurement_specs:
        value = metrics.get(source_key)
        measurements.append(
            SystemMeasurement(metric, value, unit, "spice_coupled_simulation",
                              integrated_case["run_id"], str(case_path),
                              "VERIFIED" if value is not None else "NOT_VERIFIED", "SYS029")
        )
        convert_limits[metric] = {key: float(value_limit) for key, value_limit in limit.items()}

    testlab_root = PROJECT_ROOT.parent / "TestLab"
    api = inspect_testlab_api(testlab_root)
    judge_result = judge_measurements(
        testlab_root, measurements, limits=convert_limits,
        output_directory=directory, timeout_s=180,
    )
    actual = judge_result.get("actual_test_results") or {}
    rows = []
    agreement = 0
    comparable = 0
    for item, spec in zip(actual.get("results", []), measurement_specs):
        local = judge(item["metric"], item["value"],
                      minimum=spec[3].get("min"), maximum=spec[3].get("max"), unit=spec[2])
        consistent = None
        if item["testlab_status"] in ("PASS", "FAIL"):
            comparable += 1
            consistent = (item["testlab_status"] == "PASS") == (local.status == "PASS")
            agreement += int(bool(consistent))
        rows.append({
            "metric": item["metric"],
            "value": item["value"],
            "testlab_status": item["testlab_status"],
            "testlab_detail": item["testlab_detail"],
            "local_status": local.status,
            "consistent": consistent,
        })

    status = "PASS" if actual.get("status") == "JUDGED" and agreement == comparable and comparable > 0 else "FAIL"
    if actual.get("status") != "JUDGED":
        status = "BLOCKED"
    payload = {
        "run_id": run_id,
        "status": status,
        "testlab_api": api,
        "testlab_execution": judge_result["execution"],
        "testlab_output": actual,
        "agreement": {"comparable": comparable, "agreed": agreement},
        "rows": rows,
        "source_case": str(case_path),
        "note": "TestLab 没有外部测量导入接口；本次为只读导入其真实判定函数",
    }
    write_json(directory / "case_result.json", payload)
    if args.json_out:
        write_json(args.json_out, payload)
    print(json.dumps({"run_id": run_id, "status": status,
                      "agreed": agreement, "comparable": comparable}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
