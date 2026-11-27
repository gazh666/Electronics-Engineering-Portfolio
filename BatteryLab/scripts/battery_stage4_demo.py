"""Task 33/34/36/39：汇总第四阶段全部采集实验并做工程限值验收。

运行前置：先执行下列 demo，本脚本只读取它们已落盘的真实结果，不重新运行
隐藏计算，也不把缺失试验默认判为 PASS。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from analysis.sensing_validation import (
    adc_checks,
    check,
    current_checks,
    filter_checks,
    summarize_checks,
    temperature_checks,
    voltage_checks,
)
from scripts.stage4_common import limits
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame
from storage.result_store import RESULTS_ROOT, read_json, write_json

DEMO_KEYWORDS = {
    "cell_voltage": "cell_voltage_sensing_demo",
    "differential_amplifier": "differential_amplifier_demo",
    "current_sensing": "current_sensing_demo",
    "rc_filter": "rc_filter_demo",
    "adc": "adc_demo",
    "ntc": "ntc_sensing_demo",
    "calibration": "calibration_demo",
    "tolerance": "sensing_tolerance_demo",
    "afe": "afe_system_demo",
}


def find_latest_run(keyword: str) -> tuple[dict, Path] | None:
    candidates = []
    for metadata_path in RESULTS_ROOT.glob("sensing/run_*/metadata.json"):
        try:
            metadata = read_json(metadata_path)
        except Exception:  # noqa: BLE001
            continue
        script = str(metadata.get("script", "")).replace(".", "/")
        if keyword in script:
            candidates.append((str(metadata.get("created_at", "")), metadata_path.parent))
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: item[0])
    summary_path = latest[1] / "summary.json"
    summary = read_json(summary_path) if summary_path.exists() else {}
    return summary, latest[1]


def main() -> int:
    run = new_sensing_run("stage4")
    composed = {name: find_latest_run(keyword) for name, keyword in DEMO_KEYWORDS.items()}
    missing = [name for name, value in composed.items() if value is None]

    def summary_of(name: str) -> dict:
        value = composed.get(name)
        return value[0] if value else {}

    differential = summary_of("differential_amplifier")
    current = summary_of("current_sensing")
    rc = summary_of("rc_filter")
    adc = summary_of("adc")
    ntc = summary_of("ntc")
    calibration = summary_of("calibration")
    tolerance = summary_of("tolerance")
    afe = summary_of("afe")

    ideal_diff_error = max((abs(row["error_v"]) for row in differential.get("experiment_a", [])), default=float("nan"))
    ideal_current_error = float(current.get("max_theory_error_v", float("nan")))
    cutoff_error = float(rc.get("ac", {}).get("cutoff_relative_error", float("nan")))
    attenuation_100k = float(rc.get("interference", {}).get("attenuation_db", float("nan")))
    rise_error = float(rc.get("step", {}).get("rise_time_relative_error", float("nan")))
    max_quantization = float(adc.get("max_quantization_error_lsb", float("nan")))
    monotonic = bool(adc.get("monotonic", False))

    voltage_post = tolerance.get("voltage", {}).get("post", {})
    current_post = tolerance.get("current", {}).get("post", {})
    temperature_post = tolerance.get("temperature", {}).get("post", {})
    voltage_pre = tolerance.get("voltage", {}).get("pre", {})
    current_pre = tolerance.get("current", {}).get("pre", {})
    current_zero = tolerance.get("current", {}).get("zero_only", {})
    temperature_pre = tolerance.get("temperature", {}).get("pre", {})

    afe_voltage_metrics = afe.get("voltage_metrics", [])
    afe_invalid_total = int(sum(float(row.get("invalid_count", 0)) for row in afe_voltage_metrics))
    afe_status_cases = afe.get("status_cases", [])
    status_ok = all(row.get("status") in {"SENSOR_OPEN", "SENSOR_SHORT"} for row in afe_status_cases) and bool(afe_status_cases)

    limit_config = limits()
    checks = []
    checks += voltage_checks(
        ideal_error_v=ideal_diff_error,
        calibrated_max_error_v=float(voltage_post.get("max_abs_error", float("nan"))),
        calibrated_rmse_v=float(voltage_post.get("rmse", float("nan"))),
        saturation_ratio=0.0 if afe_invalid_total == 0 else 1.0,
        limits=limit_config,
    )
    checks += current_checks(
        ideal_error_v=ideal_current_error,
        calibrated_max_error_a=float(current_post.get("max_abs_error", float("nan"))),
        calibrated_rmse_a=float(current_post.get("rmse", float("nan"))),
        limits=limit_config,
    )
    checks += filter_checks(
        cutoff_relative_error=cutoff_error,
        attenuation_100khz_db=attenuation_100k,
        rise_time_relative_error=rise_error,
        limits=limit_config,
    )
    checks += adc_checks(max_quantization_error_lsb=max_quantization, monotonic=monotonic, limits=limit_config)
    checks += temperature_checks(
        calibrated_max_error_c=float(temperature_post.get("max_abs_error", float("nan"))),
        calibrated_rmse_c=float(temperature_post.get("rmse", float("nan"))),
        limits=limit_config,
    )
    checks.append(check("无效测量必须具备明确状态", status_ok, True, "==", source="scripts/afe_system_demo.py"))
    checks.append(check("缺失实验数", len(missing), 0, "==", source="scripts/battery_stage4_demo.py", note=",".join(missing)))
    validation = summarize_checks(checks)

    voltage_summary = [
        {
            "channel": "cell1/2/3",
            "ideal_theory_vs_spice_mv": ideal_diff_error * 1000.0,
            "pre_cal_max_mv": float(voltage_pre.get("max_abs_error", float("nan"))) * 1000.0,
            "post_cal_max_mv": float(voltage_post.get("max_abs_error", float("nan"))) * 1000.0,
            "post_cal_rmse_mv": float(voltage_post.get("rmse", float("nan"))) * 1000.0,
        }
    ]
    current_summary = [
        {
            "channel": "pack_current",
            "ideal_theory_vs_spice_mv": ideal_current_error * 1000.0,
            "pre_cal_max_ma": float(current_pre.get("max_abs_error", float("nan"))) * 1000.0,
            "zero_cal_max_ma": float(current_zero.get("max_abs_error", float("nan"))) * 1000.0,
            "post_cal_max_ma": float(current_post.get("max_abs_error", float("nan"))) * 1000.0,
            "post_cal_rmse_ma": float(current_post.get("rmse", float("nan"))) * 1000.0,
        }
    ]
    filter_summary = [
        {
            "cutoff_relative_error": cutoff_error,
            "attenuation_100khz_db": attenuation_100k,
            "rise_time_relative_error": rise_error,
            "theoretical_cutoff_hz": rc.get("filter", {}).get("theoretical_cutoff_hz"),
            "theoretical_tau_s": rc.get("filter", {}).get("tau_s"),
        }
    ]
    adc_summary = [
        {
            "resolution_bits": adc.get("adc_config", {}).get("resolution_bits"),
            "lsb_v": adc.get("adc_config", {}).get("lsb_v"),
            "max_quantization_error_lsb": max_quantization,
            "monotonic": monotonic,
        }
    ]
    temperature_summary = [
        {
            "channel": "ntc",
            "pre_cal_max_c": float(temperature_pre.get("max_abs_error", float("nan"))),
            "post_cal_max_c": float(temperature_post.get("max_abs_error", float("nan"))),
            "post_cal_rmse_c": float(temperature_post.get("rmse", float("nan"))),
            "max_spice_vs_theory_v": ntc.get("max_spice_vs_theory_voltage_error_v"),
            "self_heating_status": ntc.get("self_heating", {}).get("status"),
        }
    ]
    calibration_summary = [
        {
            "channel": "voltage",
            "pre_max": calibration.get("voltage", {}).get("metrics", {}).get("pre", {}).get("max_abs_error"),
            "post_max": calibration.get("voltage", {}).get("metrics", {}).get("post", {}).get("max_abs_error"),
        },
        {
            "channel": "current",
            "pre_max": calibration.get("current", {}).get("metrics", {}).get("pre", {}).get("max_abs_error"),
            "zero_max": calibration.get("current", {}).get("metrics", {}).get("zero", {}).get("max_abs_error"),
            "two_point_max": calibration.get("current", {}).get("metrics", {}).get("two_point", {}).get("max_abs_error"),
        },
        {
            "channel": "temperature",
            "pre_max": calibration.get("temperature", {}).get("metrics", {}).get("pre", {}).get("max_abs_error"),
            "post_max": calibration.get("temperature", {}).get("metrics", {}).get("post", {}).get("max_abs_error"),
        },
    ]
    tolerance_summary = [
        {
            "channel": "voltage",
            "pre_rmse_mv": float(voltage_pre.get("rmse", float("nan"))) * 1000.0,
            "post_rmse_mv": float(voltage_post.get("rmse", float("nan"))) * 1000.0,
            "pre_max_mv": float(voltage_pre.get("max_abs_error", float("nan"))) * 1000.0,
            "post_max_mv": float(voltage_post.get("max_abs_error", float("nan"))) * 1000.0,
        },
        {
            "channel": "current",
            "pre_rmse_ma": float(current_pre.get("rmse", float("nan"))) * 1000.0,
            "post_rmse_ma": float(current_post.get("rmse", float("nan"))) * 1000.0,
            "pre_max_ma": float(current_pre.get("max_abs_error", float("nan"))) * 1000.0,
            "post_max_ma": float(current_post.get("max_abs_error", float("nan"))) * 1000.0,
        },
        {
            "channel": "temperature",
            "pre_rmse_c": float(temperature_pre.get("rmse", float("nan"))),
            "post_rmse_c": float(temperature_post.get("rmse", float("nan"))),
            "pre_max_c": float(temperature_pre.get("max_abs_error", float("nan"))),
            "post_max_c": float(temperature_post.get("max_abs_error", float("nan"))),
        },
    ]

    write_frame(run, "voltage_sensing_summary.csv", pd.DataFrame(voltage_summary))
    write_frame(run, "current_sensing_summary.csv", pd.DataFrame(current_summary))
    write_frame(run, "filter_summary.csv", pd.DataFrame(filter_summary))
    write_frame(run, "adc_summary.csv", pd.DataFrame(adc_summary))
    write_frame(run, "temperature_summary.csv", pd.DataFrame(temperature_summary))
    write_frame(run, "calibration_summary.csv", pd.DataFrame(calibration_summary))
    write_frame(run, "tolerance_summary.csv", pd.DataFrame(tolerance_summary))
    write_json(run.path / "validation_summary.json", validation)
    write_json(
        run.path / "coupled_experiments.json",
        {
            "runs": {name: (str(value[1]) if value else None) for name, value in composed.items()},
            "missing": missing,
        },
    )
    run.log(f"验收检查: {validation['passed']} PASS / {validation['failed']} FAIL")

    summary = {
        "validation": validation,
        "missing_experiments": missing,
        "runs": {name: (str(value[1]) if value else None) for name, value in composed.items()},
        "afe_voltage_metrics": afe_voltage_metrics,
        "afe_current_metrics": afe.get("current_metrics", {}),
    }
    payload = finalize_run(
        run,
        script="scripts/battery_stage4_demo.py",
        summary=summary,
        metadata={"note": "汇总读取各 demo 已落盘结果；不重复计算或修改限值。"},
    )

    print(f"run_id={run.run_id}")
    print(pd.DataFrame(checks)[["check", "value", "threshold", "status"]].to_string(index=False))
    print(f"总体验收={validation['overall']}（PASS {validation['passed']} / FAIL {validation['failed']}）")
    if missing:
        print(f"缺失实验: {missing}")
    print(f"本汇总脚本真实 SPICE 求解次数={payload['real_spice_solves']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
