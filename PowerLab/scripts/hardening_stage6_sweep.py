"""研发能力补强 · 任务二：第六阶段参数优化（真实 SPICE 扫描 + 约束 + Pareto + 复验）。

基准：第四阶段变体 E 非理想 MOSFET Buck，12 V -> 5 V / 约 2 A，2.5 ohm 恒阻负载。
每个工况都用平均模型重新校准占空比到 5 V 目标，再用真实 ngspice 瞬态复核。

说明（必须保留）：L/C/fs/DCR/ESR 在这里是独立教学参数扫描，不是商业器件选型；
DCR 与 L 不绑定为同一器件系列。基准与候选使用相同目标、负载、模型边界与分析步长。
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.stability_analysis import solve_operating_duty
from circuits.nonideal_config import NonidealBuckConfig, load_nonideal_buck_config
from experiments._stage8_common import run_case, write_json
from scripts.hardening_metrics_audit import _load_window_gzip, _recompute
from validation.reference_cases import averaged_parameters_for_case

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = PROJECT_ROOT / "results" / "hardening" / "stage6_optimization"
RUNS_ROOT = OUT_ROOT / "runs"

BASELINE = {"L_uh": 47.0, "C_uf": 100.0, "fs_khz": 100.0, "dcr_ohm": 0.05, "esr_ohm": 0.03}

#: 共享 ngspice 实例在进程内复用，个别工况会触发 "timestep too small"；
#: 只调整数值步长重试，不改变功率级、占空比、负载或输出目标。
STEP_CANDIDATES = (
    (100e-9, 50e-9),
    (50e-9, 12.5e-9),
    (50e-9, 25e-9),
    (200e-9, 50e-9),
)
VERIFY_STEP_CANDIDATES = (
    (50e-9, 25e-9),
    (50e-9, 12.5e-9),
    (100e-9, 50e-9),
)
END_TIME_S = 5e-3


class Budget:
    def __init__(self) -> None:
        self.spice = 0

    def add_spice(self) -> None:
        self.spice += 1


def make_config(values: dict[str, float], *, name: str) -> NonidealBuckConfig:
    base = load_nonideal_buck_config()
    config = replace(
        base,
        circuit_name=name,
        switching_frequency_hz=float(values["fs_khz"]) * 1e3,
        inductor=replace(base.inductor, inductance_h=float(values["L_uh"]) * 1e-6, dcr_ohm=float(values["dcr_ohm"])),
        capacitor=replace(base.capacitor, capacitance_f=float(values["C_uf"]) * 1e-6, esr_ohm=float(values["esr_ohm"])),
    )
    # 用同一平均模型口径把稳态占空比校准到 5 V，使不同 DCR 的设计仍工作在同一输出点。
    parameters = averaged_parameters_for_case(config)
    duty = solve_operating_duty(parameters, config.target_output_voltage_v)
    return config.with_duty(duty)


def cases() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(name: str, **overrides: float) -> None:
        values = dict(BASELINE)
        values.update(overrides)
        rows.append({"name": name, "values": values, "changed": overrides})

    add("baseline", **{})
    for L in (22, 33, 47, 56, 68, 82, 100):
        add(f"L_{L}uH", L_uh=L)
    for C in (47, 100, 150, 220, 330):
        add(f"C_{C}uF", C_uf=C)
    for fs in (50, 100, 150, 200, 300):
        add(f"fs_{fs}kHz", fs_khz=fs)
    for dcr in (0.02, 0.035, 0.05, 0.07, 0.10, 0.20):
        add(f"dcr_{int(round(dcr * 1000))}mOhm", dcr_ohm=dcr)
    for esr in (0.005, 0.02, 0.03, 0.06, 0.10):
        add(f"esr_{int(round(esr * 1000))}mOhm", esr_ohm=esr)
    add("combo_A", L_uh=68, C_uf=220, fs_khz=100, dcr_ohm=0.02, esr_ohm=0.01)
    add("combo_B", L_uh=100, C_uf=220, fs_khz=200, dcr_ohm=0.02, esr_ohm=0.01)
    add("combo_C", L_uh=68, C_uf=330, fs_khz=100, dcr_ohm=0.02, esr_ohm=0.005)
    add("combo_D", L_uh=100, C_uf=330, fs_khz=200, dcr_ohm=0.02, esr_ohm=0.005)
    add("combo_E", L_uh=47, C_uf=100, fs_khz=200, dcr_ohm=0.05, esr_ohm=0.03)
    add("combo_F", L_uh=33, C_uf=220, fs_khz=300, dcr_ohm=0.02, esr_ohm=0.01)
    return rows


def _extract(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "vout_v": metrics.get("output_voltage_mean_v"),
        "ripple_vpp": metrics.get("output_voltage_ripple_vpp"),
        "efficiency_stage_percent": metrics.get("efficiency_power_stage_percent"),
        "efficiency_system_percent": metrics.get("efficiency_system_percent"),
        "total_loss_w": metrics.get("total_loss_w"),
        "inductor_peak_a": metrics.get("inductor_current_peak_a"),
        "inductor_valley_a": metrics.get("inductor_current_valley_a"),
        "inductor_ripple_a": metrics.get("inductor_current_ripple_a"),
        "duty_cycle": metrics.get("pwm_duty_cycle"),
        "switching_power_w": metrics.get("switching_power_w"),
        "mosfet_loss_w": metrics.get("mosfet_loss_w"),
        "diode_loss_w": metrics.get("diode_loss_w"),
        "dcr_loss_w": metrics.get("dcr_loss_w"),
        "esr_loss_w": metrics.get("esr_loss_w"),
        "residual_ratio": metrics.get("power_residual_ratio"),
        "data_source": "spice_derived",
    }


def _feasible(row: dict[str, Any]) -> bool:
    values = row["result"]
    if values is None:
        return False
    return bool(
        values["vout_v"] is not None
        and 4.95 <= values["vout_v"] <= 5.05
        and values["ripple_vpp"] <= 0.030
        and values["inductor_peak_a"] <= 3.5
        and values["inductor_valley_a"] > 0.0
        and values["efficiency_stage_percent"] >= 93.0
        and abs(values["residual_ratio"]) <= 1.0e-2
    )


def _pareto(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feasible = [item for item in rows if item["feasible"]]
    front = []
    for item in feasible:
        ripple = item["result"]["ripple_vpp"]
        loss = item["result"]["total_loss_w"]
        dominated = False
        for other in feasible:
            if other is item:
                continue
            oripple = other["result"]["ripple_vpp"]
            oloss = other["result"]["total_loss_w"]
            if (oripple <= ripple and oloss <= loss) and (oripple < ripple or oloss < loss):
                dominated = True
                break
        if not dominated:
            front.append(item)
    return sorted(front, key=lambda item: item["result"]["ripple_vpp"])


def _run_with_fallback(
    config: NonidealBuckConfig,
    label: str,
    budget: Budget,
    *,
    step_candidates: tuple[tuple[float, float], ...],
    save_waveform: bool = False,
) -> dict[str, Any]:
    attempts = []
    for step, maximum in step_candidates:
        result = run_case(
            config,
            "E",
            budget,
            label=label,
            step_time_s=step,
            max_step_time_s=maximum,
            end_time_s=END_TIME_S,
            run_root=RUNS_ROOT,
            save=True,
            save_waveform=save_waveform,
        )
        attempts.append(
            {"step_time_s": step, "max_step_time_s": maximum, "status": result["status"]}
        )
        if result["status"] == "COMPLETED":
            result["timing_attempts"] = attempts
            if save_waveform:
                frame = _load_window_gzip(Path(result["run_dir"]) / "waveform.csv.gz")
                result["waveform_recomputed"] = _recompute(frame, config.to_dict())
            return result
    return {
        "status": "ERROR",
        "label": label,
        "timing_attempts": attempts,
        "failure_reason": "all step candidates failed",
    }


def _verify_pair(
    baseline: NonidealBuckConfig,
    candidate: NonidealBuckConfig,
    budget: Budget,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """基准与候选必须使用同一组数值步长，保证可比。"""
    fallback = None
    for step, maximum in VERIFY_STEP_CANDIDATES:
        for _attempt in range(2):
            b = _run_with_fallback(
                baseline, "stage6_verify_baseline", budget,
                step_candidates=((step, maximum),), save_waveform=True,
            )
            c = _run_with_fallback(
                candidate, "stage6_verify_candidate", budget,
                step_candidates=((step, maximum),), save_waveform=True,
            )
            fallback = (b, c)
            if b["status"] == "COMPLETED" and c["status"] == "COMPLETED":
                return b, c
    return fallback  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="stage 6 parameter optimization sweep")
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="reuse existing sweep.json rows, only redo feasibility/Pareto/verification",
    )
    args = parser.parse_args(argv)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    budget = Budget()
    rows: list[dict[str, Any]] = []

    if args.reuse:
        payload = json.loads((OUT_ROOT / "sweep.json").read_text(encoding="utf-8"))
        rows = payload["rows"]
        for item in rows:
            item["feasible"] = _feasible(item)
        print(f"[reuse] loaded {len(rows)} rows from {OUT_ROOT / 'sweep.json'}")
    else:
        for case in cases():
            config = make_config(case["values"], name=f"stage6_sweep_{case['name']}")
            result = _run_with_fallback(
                config,
                f"stage6_sweep_{case['name']}",
                budget,
                step_candidates=STEP_CANDIDATES,
            )
            extracted = _extract(result.get("metrics", {})) if result["status"] == "COMPLETED" else None
            rows.append(
                {
                    "name": case["name"],
                    "changed": case["changed"],
                    "values": case["values"],
                    "duty_cycle": config.duty_cycle,
                    "config": config.to_dict(),
                    "run_id": result.get("run_id"),
                    "run_dir": result.get("run_dir"),
                    "status": result["status"],
                    "used_step_time_s": (
                        result.get("timing_attempts", [{}])[-1].get("step_time_s")
                        if result.get("timing_attempts")
                        else None
                    ),
                    "result": extracted,
                    "failure_reason": result.get("failure_reason"),
                    "duration_s": result.get("duration_s"),
                }
            )
            if extracted:
                rows[-1]["feasible"] = _feasible(rows[-1])
                print(
                    f"{case['name']:>18} run={result['run_id']} "
                    f"Vout={extracted['vout_v']:.4f} ripple={extracted['ripple_vpp']*1e3:.2f}mV "
                    f"eta={extracted['efficiency_stage_percent']:.3f}% loss={extracted['total_loss_w']:.4f}W "
                    f"Ipk={extracted['inductor_peak_a']:.3f}A feasible={rows[-1]['feasible']}"
                )
            else:
                rows[-1]["feasible"] = False
                print(f"{case['name']:>18} ERROR {result.get('failure_reason')}")

    sweep_runs = (
        int(payload.get("sweep_spice_runs", payload.get("spice_runs", 0)))
        if args.reuse
        else budget.spice
    )
    front = _pareto(rows)

    # 选一个工程意义上的候选：在可行域内、纹波 <= 15 mV 的方案中总损耗最小。
    low_ripple = [
        item for item in rows
        if item["feasible"] and item["result"]["ripple_vpp"] <= 0.015
    ]
    candidate = min(low_ripple, key=lambda item: item["result"]["total_loss_w"]) if low_ripple else None

    # 独立复验：基准与候选使用同一组数值步长重新跑一次。
    baseline_config = make_config(BASELINE, name="stage6_verify_baseline")
    candidate_config = (
        make_config(candidate["values"], name="stage6_verify_candidate")
        if candidate is not None
        else None
    )
    if candidate_config is not None:
        baseline_verify, candidate_verify = _verify_pair(baseline_config, candidate_config, budget)
    else:
        baseline_verify = _run_with_fallback(
            baseline_config, "stage6_verify_baseline", budget,
            step_candidates=VERIFY_STEP_CANDIDATES, save_waveform=True,
        )
        candidate_verify = None
    comparison = None
    if candidate_verify is not None:
        if (
            baseline_verify.get("status") == "COMPLETED"
            and candidate_verify.get("status") == "COMPLETED"
        ):
            b = baseline_verify["waveform_recomputed"]
            c = candidate_verify["waveform_recomputed"]
            comparison = {
                "baseline_run_id": baseline_verify["run_id"],
                "candidate_run_id": candidate_verify["run_id"],
                "same_conditions": {
                    "input_voltage_v": 12.0,
                    "target_output_voltage_v": 5.0,
                    "load_resistance_ohm": 2.5,
                    "model_variant": "E",
                    "step_time_s": baseline_verify["timing_attempts"][-1]["step_time_s"],
                    "max_step_time_s": baseline_verify["timing_attempts"][-1]["max_step_time_s"],
                    "end_time_s": END_TIME_S,
                },
                "baseline": b,
                "candidate": c,
                "delta": {
                    "ripple_vpp": c["output_ripple_vpp"] - b["output_ripple_vpp"],
                    "ripple_reduction_percent": 100.0
                    * (b["output_ripple_vpp"] - c["output_ripple_vpp"])
                    / b["output_ripple_vpp"],
                    "efficiency_stage_pp": c["efficiency_stage_percent"] - b["efficiency_stage_percent"],
                    "efficiency_system_pp": c["efficiency_system_percent"] - b["efficiency_system_percent"],
                    "total_loss_w": c["total_loss_w"] - b["total_loss_w"],
                    "loss_reduction_percent": 100.0
                    * (b["total_loss_w"] - c["total_loss_w"])
                    / b["total_loss_w"],
                    "inductor_peak_a": c["inductor_peak_a"] - b["inductor_peak_a"],
                    "vout_v": c["output_mean_v"] - b["output_mean_v"],
                },
            }

    payload = {
        "task": "stage6_parameter_optimization",
        "data_source": "spice_simulation + spice_derived",
        "baseline_design": BASELINE,
        "sweep_dimensions": ["L", "C", "fs", "DCR", "ESR"],
        "case_count": len(rows),
        "spice_runs": sweep_runs + budget.spice,
        "sweep_spice_runs": sweep_runs,
        "verification_spice_runs": budget.spice,
        "simulation_window_s": END_TIME_S,
        "step_candidates": [list(item) for item in STEP_CANDIDATES],
        "independence_note": (
            "L/C/fs/DCR/ESR 为独立教学参数扫描；DCR 未与具体电感器件绑定，"
            "不代表任何真实商业器件选型或许可"
        ),
        "constraints": {
            "output_voltage_v": [4.95, 5.05],
            "ripple_vpp_max": 0.030,
            "inductor_peak_a_max": 3.5,
            "ccm": "inductor valley current > 0",
            "efficiency_stage_percent_min": 93.0,
            "power_residual_ratio_abs_max": 1e-2,
            "residual_basis": (
                "project threshold in configs/nonideal_validation.yaml is 0.15; "
                "this optimization uses a stricter 1% screen without changing project limits"
            ),
        },
        "rows": rows,
        "pareto_front": [
            {
                "name": item["name"],
                "values": item["values"],
                "ripple_vpp": item["result"]["ripple_vpp"],
                "total_loss_w": item["result"]["total_loss_w"],
                "efficiency_stage_percent": item["result"]["efficiency_stage_percent"],
                "inductor_peak_a": item["result"]["inductor_peak_a"],
                "run_id": item["run_id"],
            }
            for item in front
        ],
        "selected_candidate": (
            {
                "name": candidate["name"],
                "values": candidate["values"],
                "run_id": candidate["run_id"],
                "result": candidate["result"],
                "selection_rule": "可行域内 ripple<=15 mV 时总损耗最小",
            }
            if candidate
            else None
        ),
        "independent_verification": {
            "baseline": baseline_verify,
            "candidate": candidate_verify,
            "comparison": comparison,
        },
        "notes": [
            "所有指标来自真实 ngspice 瞬态波形，占空比由平均模型校准后再由 SPICE 复核",
            "未修改任何历史结果；扫描与复验写入 results/hardening/stage6_optimization",
            "效率改善是百分点差，不是相对百分比",
        ],
    }
    write_json(OUT_ROOT / "sweep.json", payload)

    table = pd.DataFrame(
        [
            {
                "name": item["name"],
                **{f"value_{k}": v for k, v in item["values"].items()},
                "run_id": item["run_id"],
                "status": item["status"],
                "used_step_time_s": item["used_step_time_s"],
                "feasible": item["feasible"],
                **(item["result"] or {}),
            }
            for item in rows
        ]
    )
    table.to_csv(OUT_ROOT / "sweep.csv", index=False)
    pd.DataFrame(payload["pareto_front"]).to_csv(OUT_ROOT / "pareto.csv", index=False)

    print("=== pareto front ===")
    for item in payload["pareto_front"]:
        print(item)
    print("=== selected ===")
    print(payload["selected_candidate"]["name"] if candidate else None)
    if comparison:
        print("comparison delta:", comparison["delta"])
    print("saved:", OUT_ROOT / "sweep.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
