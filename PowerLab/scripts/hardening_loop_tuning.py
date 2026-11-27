"""研发能力补强 · 任务三：闭环 PI 参数补强与 7 项扰动 + 软启动真实 SPICE 复验。

流程：
1) 在平均模型上对现有 Kp/Ki 做有限范围网格评估（裕度、穿越次数、闭环极点、带宽）。
2) 用平均模型对 7 个扰动 + 软启动做初筛。
3) 选一个候选，与原控制器在完全相同的功率级、限值、扰动与步长下做真实 SPICE 对照。
4) 不修改任何原有工程限值；改进不足或某些工况变差时如实记录。
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from analysis.startup_analysis import analyze_startup
from analysis.stability_analysis import (
    carrier_small_signal_gain,
    solve_operating_duty,
    stability_report,
)
from analysis.transient_metrics import analyze_events
from circuits.closed_loop_config import load_closed_loop_config
from experiments.load_step import load_events
from experiments.line_step import line_event
from simulations.averaged_model_runner import (
    averaged_metrics,
    averaged_parameters_from_config,
    run_averaged_closed_loop,
)
from simulations.closed_loop_runner import run_closed_loop_with_fallback, save_closed_loop_run
from storage.result_store import write_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = PROJECT_ROOT / "results" / "hardening" / "loop_tuning"
RUNS_ROOT = OUT_ROOT / "runs"

BASE_KP = 0.0585
BASE_KI = 117.66
LOAD_CASES = ("load_step_1a_to_2a", "load_step_2a_to_1a", "load_step_0p5a_to_2a")
LINE_CASES = (
    "vin_step_down_12_to_9",
    "vin_step_up_9_to_12",
    "vin_step_up_12_to_16",
    "vin_step_down_16_to_12",
)
SPICE_WAVEFORM_CASES = {"load_step_1a_to_2a", "vin_step_up_12_to_16"}
LIMITS = {
    # stage7_acceptance_checks.csv: load_step_worst_max_deviation_v 限值 0.3 V，
    # 对 1->2 A、2->1 A、0.5->2 A 三个负载阶跃统一适用。
    "load_step_1a_to_2a": {"dev": 0.3, "recovery": 0.010},
    "load_step_2a_to_1a": {"dev": 0.3, "recovery": 0.012},
    "load_step_0p5a_to_2a": {"dev": 0.3, "recovery": 0.012},
    "line_step": {"dev": 0.5, "recovery": 0.015},
    "soft_start": {"overshoot_percent": 10.0, "peak_il_a": 4.0, "peak_iin_a": 4.0},
}


class Budget:
    spice = 0
    averaged = 0

    def add_spice(self) -> None:
        Budget.spice += 1

    def add_averaged(self) -> None:
        Budget.averaged += 1


def grid() -> list[dict[str, Any]]:
    combos = [(1.0, 1.0), (0.5, 2.0)]
    for kp_factor in (1.0, 1.25, 1.5, 2.0, 2.5):
        for ki_factor in (1.0, 1.5, 2.0, 3.0):
            combos.append((kp_factor, ki_factor))
    unique = []
    for item in combos:
        if item not in unique:
            unique.append(item)
    return [{"kp_factor": kp, "ki_factor": ki} for kp, ki in unique]


def _report(params, duty, kp, ki, pwm_gain) -> dict[str, Any]:
    report = stability_report(
        params, kp, ki, target_v=5.0, pwm_gain=pwm_gain,
        limits={"phase_margin_deg": {"min": 45.0}, "finite_gain_margin_db": {"min": 6.0}},
    )
    return {
        "kp": kp,
        "ki": ki,
        "phase_margin_deg": report["phase_margin_deg"],
        "gain_margin_db": report["gain_margin_db"],
        "bandwidth_hz": report["bandwidth_hz"],
        "crossings": len(report["magnitude_crossings"]),
        "loop_status": report["status"],
        "poles": report["closed_loop_poles"],
        "messages": report["messages"],
    }


def _averaged_case(base, gains, case_name: str, kind: str) -> dict[str, Any]:
    config = base.with_gains(*gains)
    if kind == "load":
        config = config.with_named_load(case_name).with_name(f"tune_avg_{case_name}")
        event = load_events(config)[0]
        target_events = [event]
    elif kind == "line":
        config = config.with_named_line(case_name).with_name(f"tune_avg_{case_name}")
        config = config.with_timing(0.016)
        target_events = [line_event(config, case_name)]
    else:
        raise ValueError(kind)
    Budget.averaged += 1
    run = run_averaged_closed_loop(config)
    metrics = analyze_events(
        run.data["time_s"], run.data["vout_v"], target_events,
        target_v=config.target_voltage_v, tolerance_v=0.05, period_s=config.period_s,
        hold_cycles=20, pre_window_s=1e-3, data_source=run.data_source,
    )[0]
    return {
        "case": case_name,
        "model": "averaged_model",
        "run_id": run.run_id,
        "max_deviation_v": metrics.get("maximum_absolute_deviation_v"),
        "droop_v": metrics.get("droop_v"),
        "overshoot_v": metrics.get("overshoot_v"),
        "recovery_time_s": (metrics.get("recovery_strict") or {}).get("recovery_time_s"),
        "steady_state_error_v": metrics.get("steady_state_error_v"),
        "iae_vs": metrics.get("iae_vs"),
        "ise_v2s": metrics.get("ise_v2s"),
        "peak_inductor_a": metrics.get("peak_inductor_current_a"),
        "quality": averaged_metrics(run),
        "data_source": run.data_source,
    }


def _spice_case(base, gains, case_name: str, kind: str, *, duration_s: float = 0.0) -> dict[str, Any]:
    config = base.with_gains(*gains)
    if kind == "load":
        config = config.with_named_load(case_name).with_name(f"tune_spice_{case_name}")
        event = load_events(config)[0]
        events = [event]
    elif kind == "line":
        config = (
            config.with_named_line(case_name).with_name(f"tune_spice_{case_name}")
            .with_timing(0.016, step_time_s=50e-9, max_step_time_s=50e-9)
        )
        events = [line_event(config, case_name)]
    elif kind == "startup":
        config = (
            config.with_soft_start(duration_s, enabled=duration_s > 0)
            .with_name(f"tune_spice_soft_start_{int(round(duration_s * 1e3))}ms")
            .with_timing(max(0.012, duration_s + 0.006), step_time_s=50e-9, max_step_time_s=50e-9)
        )
        events = []
    else:
        raise ValueError(kind)

    Budget.spice += 1
    run = run_closed_loop_with_fallback(config, mode="closed_loop")
    record: dict[str, Any] = {
        "case": case_name,
        "kind": kind,
        "variant": run.variant,
        "run_id": run.run_id,
        "point_count": run.point_count,
        "duration_ms": run.duration_ms,
        "step_fallback": run.metadata.get("step_fallback"),
        "pwm_statistics_after_startup": run.metadata.get("pwm_statistics_after_startup"),
        "quality": run.metadata.get("quality"),
        "data_source": run.data_source,
        "kp": config.controller.kp,
        "ki": config.controller.ki,
        "peak_inductor_a": float(run.data["il_a"].max()),
        "minimum_duty": float(run.metadata.get("pwm_statistics_after_startup", {}).get("minimum_duty", math.nan)),
        "maximum_duty": float(run.metadata.get("pwm_statistics_after_startup", {}).get("maximum_duty", math.nan)),
    }
    if kind == "startup":
        metrics = analyze_startup(
            run.data["time_s"], run.data["vout_v"], run.data["vref_v"],
            run.data["il_a"], run.data["iin_a"],
            target_v=config.target_voltage_v, period_s=config.period_s,
            duty_raw=run.data["raw_v"], duty_limited=run.data["duty_cmd_v"],
            data_source=run.data_source,
        )
        record["startup"] = metrics
    else:
        metrics = analyze_events(
            run.data["time_s"], run.data["vout_v"], events,
            target_v=config.target_voltage_v, tolerance_v=0.05, period_s=config.period_s,
            hold_cycles=20, pre_window_s=1e-3, data_source=run.data_source,
        )[0]
        record["event"] = metrics
    save_waveform = case_name in SPICE_WAVEFORM_CASES and duration_s == 0.0
    directory = save_closed_loop_run(
        run, root=RUNS_ROOT, save_waveform=save_waveform,
        extra_metadata={"experiment": "hardening_loop_tuning", "case": case_name},
    )
    write_json(directory / "metrics.json", record)
    record["run_directory"] = str(directory)
    record["waveform"] = (
        str(directory / "waveform.csv.gz") if save_waveform else None
    )
    return record


def _event_view(record: dict[str, Any]) -> dict[str, Any]:
    if "event" not in record:
        return {"status": "ERROR", "error": record.get("error")}
    e = record["event"]
    return {
        "max_deviation_v": e.get("maximum_absolute_deviation_v"),
        "droop_v": e.get("droop_v"),
        "overshoot_v": e.get("overshoot_v"),
        "recovery_time_s": (e.get("recovery_strict") or {}).get("recovery_time_s"),
        "steady_state_error_v": e.get("steady_state_error_v"),
        "iae_vs": e.get("iae_vs"),
        "ise_v2s": e.get("ise_v2s"),
        "final_mean_v": e.get("final_mean_v"),
        "peak_inductor_a": record.get("peak_inductor_a"),
        "minimum_duty": record.get("minimum_duty"),
        "maximum_duty": record.get("maximum_duty"),
        "run_id": record.get("run_id"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="closed-loop PI tuning hardening")
    parser.add_argument("--screen-only", action="store_true", help="only run averaged screening")
    parser.add_argument(
        "--recompute-status",
        action="store_true",
        help="re-evaluate PASS/FAIL in existing tuning.json with the current limits",
    )
    args = parser.parse_args(argv)

    if args.recompute_status:
        payload = json.loads((OUT_ROOT / "tuning.json").read_text(encoding="utf-8"))
        comparison = payload["spice_comparison"]
        for case in LOAD_CASES + LINE_CASES:
            entry = comparison[case]
            limit = LIMITS.get(case, LIMITS["line_step"])
            for label in ("original", "conservative", "aggressive"):
                if label not in entry or entry[label].get("status") == "ERROR":
                    continue
                view = entry[label]
                entry[f"{label}_status"] = (
                    "PASS"
                    if view["max_deviation_v"] <= limit["dev"]
                    and view["recovery_time_s"] is not None
                    and view["recovery_time_s"] <= limit["recovery"]
                    else "FAIL"
                )
        payload["status_note"] = (
            "PASS/FAIL 按 stage7_acceptance_checks.csv 的 0.3 V 负载偏差限值与 0.5 V 线阶跃限值重算；"
            "原始仿真数值未改动"
        )
        write_json(OUT_ROOT / "tuning.json", payload)
        print("recomputed statuses with", {k: v["dev"] for k, v in LIMITS.items() if "dev" in v})
        return 0

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    base = load_closed_loop_config()
    params = averaged_parameters_from_config(base)
    duty = solve_operating_duty(params, 5.0)
    pwm_gain = carrier_small_signal_gain(duty)

    rows = []
    for item in grid():
        kp = BASE_KP * item["kp_factor"]
        ki = BASE_KI * item["ki_factor"]
        row = _report(params, duty, kp, ki, pwm_gain)
        row.update(item)
        rows.append(row)

    print("=== grid ===")
    for row in rows:
        print(
            f"kp_x{row['kp_factor']:<5} ki_x{row['ki_factor']:<4} kp={row['kp']:.5f} ki={row['ki']:.2f} "
            f"PM={row['phase_margin_deg']:.2f} GM={row['gain_margin_db']} BW={row['bandwidth_hz']:.1f} "
            f"cross={row['crossings']} poles={row['poles']['status']}"
        )

    screened = [
        row for row in rows
        if math.isfinite(row["phase_margin_deg"])
        and row["phase_margin_deg"] >= 45.0
        and row["poles"]["status"] == "STABLE"
        and row["crossings"] <= 2
        and 120.0 <= row["bandwidth_hz"] <= 450.0
    ]
    screened.sort(key=lambda row: row["bandwidth_hz"], reverse=True)
    conservative = screened[0] if screened else next(
        row for row in rows if row["kp_factor"] == 1.0 and row["ki_factor"] == 1.0
    )
    print("=== conservative (PM>=45) ===")
    print(conservative)

    original_gains = (BASE_KP, BASE_KI)
    averaged_rows = []
    for row in rows:
        gains = (row["kp"], row["ki"])
        for case in LOAD_CASES:
            averaged_rows.append({"gains": gains, **_averaged_case(base, gains, case, "load")})
        for case in LINE_CASES:
            averaged_rows.append({"gains": gains, **_averaged_case(base, gains, case, "line")})

    # 每个增益组合：与原始控制器比较 7 个工况的最大偏差比。
    summaries = []
    for row in rows:
        gains = (row["kp"], row["ki"])
        ratios = []
        worse = 0
        for case in LOAD_CASES + LINE_CASES:
            orig = next(
                item for item in averaged_rows
                if item["gains"] == original_gains and item["case"] == case
            )
            cand = next(
                item for item in averaged_rows if item["gains"] == gains and item["case"] == case
            )
            dev_orig = orig["max_deviation_v"]
            dev_cand = cand["max_deviation_v"]
            if dev_orig and dev_cand:
                ratio = dev_cand / dev_orig
                ratios.append(ratio)
                if ratio > 1.05:
                    worse += 1
        summaries.append(
            {
                "kp_factor": row["kp_factor"],
                "ki_factor": row["ki_factor"],
                "kp": row["kp"],
                "ki": row["ki"],
                "mean_deviation_ratio": sum(ratios) / len(ratios) if ratios else None,
                "worst_deviation_ratio": max(ratios) if ratios else None,
                "worse_cases": worse,
                "phase_margin_deg": row["phase_margin_deg"],
                "bandwidth_hz": row["bandwidth_hz"],
                "crossings": row["crossings"],
                "poles": row["poles"]["status"],
            }
        )
    by_gain = {(item["kp_factor"], item["ki_factor"]): item for item in summaries}

    # 激进候选：稳定性极点前提下，平均最大偏差最小（用于暴露 PI 结构的带宽/裕度取舍）。
    aggressive_pool = [
        item for item in summaries
        if item["poles"] == "STABLE"
        and math.isfinite(item["phase_margin_deg"])
        and item["phase_margin_deg"] >= 25.0
        and (item["kp_factor"], item["ki_factor"])
        != (conservative["kp_factor"], conservative["ki_factor"])
    ]
    aggressive_pool.sort(key=lambda item: item["mean_deviation_ratio"])
    aggressive = aggressive_pool[0] if aggressive_pool else None

    print("=== averaged screening (top 8 by mean deviation ratio) ===")
    for item in sorted(summaries, key=lambda x: x["mean_deviation_ratio"] or 99)[:8]:
        print(item)
    print("conservative:", by_gain[(conservative["kp_factor"], conservative["ki_factor"])])
    print("aggressive:", aggressive)

    payload: dict[str, Any] = {
        "task": "closed_loop_pi_hardening",
        "data_source": "averaged_model + spice_simulation",
        "design_point": {"duty": duty, "pwm_gain": pwm_gain, "target_v": 5.0},
        "original": {"kp": BASE_KP, "ki": BASE_KI, "report": _report(params, duty, BASE_KP, BASE_KI, pwm_gain)},
        "grid": rows,
        "conservative_candidate": by_gain[(conservative["kp_factor"], conservative["ki_factor"])],
        "aggressive_candidate": aggressive,
        "averaged_screening": averaged_rows,
        "averaged_summary": summaries,
        "limits_unchanged": LIMITS,
        "notes": [
            "平均模型只用于初筛，最终结论以真实 SPICE 为准",
            "原有工程限值未修改；未通过的工况保留",
            "PI 结构只有两个自由度，Kp 提高会压低相位裕度；激进候选用来说明这一取舍",
        ],
    }
    if args.screen_only:
        write_json(OUT_ROOT / "screening.json", payload)
        print("saved:", OUT_ROOT / "screening.json")
        return 0

    controllers = {
        "original": original_gains,
        "conservative": (conservative["kp"], conservative["ki"]),
    }
    if aggressive is not None:
        controllers["aggressive"] = (aggressive["kp"], aggressive["ki"])
    results: dict[str, dict[str, Any]] = {name: {} for name in controllers}
    for label, controller in controllers.items():
        for case in LOAD_CASES:
            try:
                results[label][case] = _spice_case(base, controller, case, "load")
            except Exception as exc:  # noqa: BLE001
                results[label][case] = {"case": case, "status": "ERROR", "error": str(exc)}
        for case in LINE_CASES:
            try:
                results[label][case] = _spice_case(base, controller, case, "line")
            except Exception as exc:  # noqa: BLE001
                results[label][case] = {"case": case, "status": "ERROR", "error": str(exc)}
        for duration in (0.0, 0.002):
            key = "soft_start_0ms" if duration == 0 else "soft_start_2ms"
            try:
                results[label][key] = _spice_case(base, controller, key, "startup", duration_s=duration)
            except Exception as exc:  # noqa: BLE001
                results[label][key] = {"case": key, "status": "ERROR", "error": str(exc)}

    comparison: dict[str, Any] = {}
    for case in LOAD_CASES + LINE_CASES:
        o = _event_view(results["original"][case])
        limit = LIMITS.get(case, LIMITS["line_step"])
        if o.get("status") == "ERROR":
            comparison[case] = {"original": o}
            continue
        entry: dict[str, Any] = {
            "original": o,
            "original_status": (
                "PASS" if o["max_deviation_v"] <= limit["dev"]
                and (o["recovery_time_s"] is not None and o["recovery_time_s"] <= limit["recovery"])
                else "FAIL"
            ),
        }
        for label in controllers:
            if label == "original":
                continue
            c = _event_view(results[label][case])
            entry[label] = c
            if c.get("status") == "ERROR":
                entry[f"{label}_status"] = "ERROR"
                continue
            entry[f"{label}_status"] = (
                "PASS" if c["max_deviation_v"] <= limit["dev"]
                and (c["recovery_time_s"] is not None and c["recovery_time_s"] <= limit["recovery"])
                else "FAIL"
            )
            entry[f"{label}_deviation_change_percent"] = (
                100.0 * (c["max_deviation_v"] - o["max_deviation_v"]) / o["max_deviation_v"]
                if o["max_deviation_v"] else None
            )
        comparison[case] = entry
    for key in ("soft_start_0ms", "soft_start_2ms"):
        entry = {}
        for label in controllers:
            record = results[label][key]
            if "startup" not in record:
                entry[label] = {"status": "ERROR", "error": record.get("error")}
                continue
            startup = record["startup"]
            entry[label] = {
                "overshoot_percent": startup.get("overshoot_percent"),
                "peak_inductor_current_a": startup.get("peak_inductor_current_a"),
                "peak_input_current_a": startup.get("peak_input_current_a"),
                "rise_time_s": startup.get("rise_time_s"),
                "settling_time_s": startup.get("settling_time_s"),
                "status": (
                    "PASS"
                    if (startup.get("overshoot_percent") or 0.0) <= LIMITS["soft_start"]["overshoot_percent"]
                    and (startup.get("peak_inductor_current_a") or 0.0) <= LIMITS["soft_start"]["peak_il_a"]
                    and (startup.get("peak_input_current_a") or 0.0) <= LIMITS["soft_start"]["peak_iin_a"]
                    else "FAIL"
                ),
            }
        comparison[key] = entry

    payload["spice_results"] = results
    payload["spice_comparison"] = comparison
    payload["controllers"] = {name: {"kp": gains[0], "ki": gains[1]} for name, gains in controllers.items()}
    payload["spice_budget"] = {"spice_runs": Budget.spice, "averaged_runs": Budget.averaged}
    write_json(OUT_ROOT / "tuning.json", payload)

    print("=== SPICE comparison ===")
    for case, item in comparison.items():
        print(case, item)
    print("saved:", OUT_ROOT / "tuning.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
