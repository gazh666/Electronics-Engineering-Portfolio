"""第二阶段综合演示：一次串行执行 11 项真实 ngspice 分析。

运行::

    python -m scripts.basic_circuits_demo

顺序：
1. 分压电路直流工作点（OP）
2. 分压电路直流扫描（DC）
3. RC 充放电瞬态（TRAN）
4. RC 低通交流分析（AC）
5. RL 阶跃瞬态（TRAN）
6. RLC 欠阻尼瞬态（R=10 Ohm）
7. RLC 临界阻尼瞬态（R=200 Ohm）
8. RLC 过阻尼瞬态（R=400 Ohm）
9. RLC 串联谐振交流分析（AC）
10. 二极管伏安特性直流扫描（DC）
11. 半波整流瞬态（TRAN）

任何一项抛异常都会被如实记录为 FAILED，整体退出码非零；
不会用理论公式或历史数据伪造通过结果。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from scripts import (
    dc_analysis_demo,
    diode_iv_demo,
    rc_ac_demo,
    rc_transient_demo,
    rectifier_demo,
    rl_transient_demo,
    rlc_demo,
)
from simulations.config import load_basic_circuits_config
from storage.result_store import (
    BASIC_RESULTS_ROOT,
    ResultStore,
    new_run_id,
    write_dataframe,
    write_json,
)

SUMMARY_JSON_NAME = "summary_{run_id}.json"
SUMMARY_CSV_NAME = "summary_{run_id}.csv"


def _summarize(name: str, analysis_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """把单个脚本的返回值压缩成一行汇总。"""
    keys_of_interest = (
        "vout_v",
        "theoretical_vout_v",
        "slope_dvout_dvin",
        "max_absolute_error_v",
        "simulated_cutoff_hz",
        "theoretical_cutoff_hz",
        "gain_at_cutoff_db",
        "phase_at_cutoff_deg",
        "tau_s",
        "current_at_one_tau_simulated_a",
        "current_at_one_tau_theory_a",
        "final_current_a",
        "steady_state_current_a",
        "inductor_energy_at_final_j",
        "simulated_average_voltage_v",
        "ideal_average_voltage_v",
        "simulated_rms_voltage_v",
        "ideal_rms_voltage_v",
        "simulated_average_load_power_w",
        "ideal_average_load_power_w",
        "forward_current_at_0p8v_a",
        "voltage_at_1ma_v",
        "voltage_at_10ma_v",
        "max_absolute_difference_a",
        "points",
        "duration_ms",
    )
    key_results = {key: payload[key] for key in keys_of_interest if key in payload}
    return {
        "analysis": name,
        "analysis_type": analysis_type,
        "status": payload.get("status", "UNKNOWN"),
        "run_dir": payload.get("run_dir")
        or (payload.get("run_dirs") or {}).get("dc_sweep")
        or (payload.get("run_dirs") or {}).get("operating_point"),
        "key_results": key_results,
        "checks": payload.get("checks", {}),
    }


def _rlc_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """RLC 汇总拆分为三条阻尼曲线 + 一条交流分析。"""
    rows: list[dict[str, Any]] = []
    for case in payload.get("transient_cases", []):
        label = str(case.get("label", "unknown"))
        rows.append(
            {
                "analysis": f"rlc_transient_{label}_R{case.get('resistance_ohm'):g}ohm",
                "analysis_type": "TRANSIENT",
                "status": "PASS",
                "run_dir": case.get("run_dir"),
                "key_results": {
                    "resistance_ohm": case.get("resistance_ohm"),
                    "damping_ratio": case.get("damping_ratio"),
                    "quality_factor": case.get("quality_factor"),
                    "final_value_v": case.get("final_value_v"),
                    "final_value_error_v": case.get("final_value_error_v"),
                    "overshoot_percent": (case.get("overshoot") or {}).get("overshoot_percent"),
                    "theoretical_overshoot_percent": case.get("theoretical_overshoot_percent"),
                    "oscillation_hz": (case.get("oscillation") or {}).get("frequency_hz"),
                    "theoretical_oscillation_hz": case.get("theoretical_oscillation_hz"),
                    "settling_time_s": (case.get("settling") or {}).get("settling_time_s"),
                    "points": case.get("points"),
                    "duration_ms": case.get("duration_ms"),
                },
                "checks": {
                    "settled": bool((case.get("settling") or {}).get("settled", False)),
                    "final_near_5v": abs(float(case.get("final_value_error_v", 0.0))) < 0.05,
                },
            }
        )
    ac = payload.get("ac", {})
    capacitor_peak = ac.get("capacitor_voltage_peak") or {}
    rows.append(
        {
            "analysis": "rlc_ac_resonance",
            "analysis_type": "AC",
            "status": ac.get("status", "UNKNOWN"),
            "run_dir": ac.get("run_dir"),
            "key_results": {
                "peak_frequency_hz": capacitor_peak.get("peak_frequency_hz"),
                "peak_magnitude_v": capacitor_peak.get("peak_value"),
                "theoretical_peak_frequency_hz": ac.get("theoretical_peak_frequency_hz"),
                "theoretical_peak_magnitude_v": ac.get("theoretical_peak_magnitude"),
                "points": ac.get("points"),
                "duration_ms": ac.get("duration_ms"),
            },
            "checks": ac.get("checks", {}),
        }
    )
    return rows


def run_all(
    config: Any | None = None,
    store: ResultStore | None = None,
) -> dict[str, Any]:
    """串行执行 11 项分析并返回汇总（不写汇总文件）。"""
    config = config or load_basic_circuits_config()
    store = store or ResultStore()

    tasks: list[tuple[str, str, Callable[[], dict[str, Any]]]] = [
        ("voltage_divider_op_dc", "OP+DC", lambda: dc_analysis_demo.analyze(config, store)),
        (
            "rc_charge_discharge",
            "TRANSIENT",
            lambda: rc_transient_demo.analyze_charge_discharge(config, store),
        ),
        ("rc_lowpass_ac", "AC", lambda: rc_ac_demo.analyze(config, store)),
        ("rl_step_transient", "TRANSIENT", lambda: rl_transient_demo.analyze(config, store)),
        ("rlc_transient_and_ac", "TRANSIENT+AC", lambda: rlc_demo.analyze(config, store)),
        ("diode_iv", "DC", lambda: diode_iv_demo.analyze(config, store)),
        ("half_wave_rectifier", "TRANSIENT", lambda: rectifier_demo.analyze(config, store)),
    ]

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for name, analysis_type, task in tasks:
        try:
            payload = task()
        except Exception as exc:  # noqa: BLE001 - 汇总必须记录真实异常
            errors.append(
                {
                    "analysis": name,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            rows.append(
                {
                    "analysis": name,
                    "analysis_type": analysis_type,
                    "status": "FAILED",
                    "run_dir": None,
                    "key_results": {},
                    "checks": {},
                }
            )
            continue

        if name == "voltage_divider_op_dc":
            op = payload.get("op", {})
            dc = payload.get("dc", {})
            rows.append(
                {
                    "analysis": "voltage_divider_operating_point",
                    "analysis_type": "OP",
                    "status": op.get("status", payload.get("status", "UNKNOWN")),
                    "run_dir": (payload.get("run_dirs") or {}).get("operating_point"),
                    "key_results": {
                        "vout_v": op.get("vout_v"),
                        "theoretical_vout_v": op.get("theoretical_vout_v"),
                        "supply_current_a": op.get("supply_current_a"),
                        "theoretical_current_a": op.get("theoretical_current_a"),
                        "point_count": op.get("point_count"),
                        "duration_ms": op.get("duration_ms"),
                    },
                    "checks": payload.get("checks", {}),
                }
            )
            rows.append(
                {
                    "analysis": "voltage_divider_dc_sweep",
                    "analysis_type": "DC",
                    "status": dc.get("status", payload.get("status", "UNKNOWN")),
                    "run_dir": (payload.get("run_dirs") or {}).get("dc_sweep"),
                    "key_results": {
                        "points": dc.get("points"),
                        "slope_dvout_dvin": dc.get("slope_dvout_dvin"),
                        "theoretical_slope": dc.get("theoretical_slope"),
                        "max_absolute_error_v": dc.get("max_absolute_error_v"),
                        "kcl_max_residual_a": dc.get("kcl_max_residual_a"),
                        "kvl_max_residual_v": dc.get("kvl_max_residual_v"),
                        "duration_ms": dc.get("duration_ms"),
                    },
                    "checks": payload.get("checks", {}),
                }
            )
        elif name == "rlc_transient_and_ac":
            rows.extend(_rlc_rows(payload))
            if payload.get("status") != "PASS":
                for row in rows[-4:]:
                    if row["status"] == "PASS":
                        row["status"] = "FAIL"
        else:
            rows.append(_summarize(name, analysis_type, payload))

    overall = "PASS" if not errors and all(row["status"] == "PASS" for row in rows) else "FAIL"
    return {
        "run_id": new_run_id(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "overall_status": overall,
        "total_items": len(rows),
        "passed_items": sum(1 for row in rows if row["status"] == "PASS"),
        "failed_items": sum(1 for row in rows if row["status"] != "PASS"),
        "errors": errors,
        "items": rows,
        "data_source": {"waveform": "spice_simulation", "theory": "analytical_theory"},
        "note": "All waveforms come from real ngspice runs; failures are never replaced by theory data.",
    }


def _flatten_rows(items: list[dict[str, Any]]) -> pd.DataFrame:
    flattened: list[dict[str, Any]] = []
    for item in items:
        row: dict[str, Any] = {
            "analysis": item["analysis"],
            "analysis_type": item["analysis_type"],
            "status": item["status"],
            "run_dir": item.get("run_dir"),
        }
        row.update({f"key.{key}": value for key, value in item.get("key_results", {}).items()})
        row.update({f"check.{key}": value for key, value in item.get("checks", {}).items()})
        flattened.append(row)
    return pd.DataFrame(flattened)


def main() -> int:
    try:
        summary = run_all()
    except Exception as exc:  # noqa: BLE001 - 配置加载等前置失败也要如实上报
        ResultStore().save_failure(analysis_name="basic_circuits_demo", error=exc)
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    BASIC_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = summary["run_id"]
    json_path = BASIC_RESULTS_ROOT / SUMMARY_JSON_NAME.format(run_id=run_id)
    csv_path = BASIC_RESULTS_ROOT / SUMMARY_CSV_NAME.format(run_id=run_id)
    write_json(json_path, summary)
    write_dataframe(csv_path, _flatten_rows(summary["items"]))

    print(f"Overall: {summary['overall_status']}")
    print(f"Items:   {summary['passed_items']}/{summary['total_items']} passed")
    for item in summary["items"]:
        print(f"  [{item['status']:>6}] {item['analysis']}")
    for error in summary["errors"]:
        print(
            f"  [FAILED] {error['analysis']}: {error['error_type']}: {error['message']}",
            file=sys.stderr,
        )
    print(f"Summary JSON: {json_path}")
    print(f"Summary CSV:  {csv_path}")
    return 0 if summary["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
