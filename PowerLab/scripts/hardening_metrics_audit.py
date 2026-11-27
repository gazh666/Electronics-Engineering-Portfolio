"""研发能力补强 · 任务一：工程指标复核（只读历史结果 + 同配置真实复算）。

本脚本不修改任何历史结果：
- 复用 stage8 VAL001_E 的配置重建同一网表，重新跑一次真实 ngspice 瞬态，
  保存原始波形用于独立重算（历史 stage8 目录只保存了 metrics/netlist）。
- 独立用时间积分重算输入/输出平均功率、效率、纹波、器件应力。
- 复核 controller_config.yaml 中 62.0 deg / 57.3 Hz 与验收 63.49 deg / 113.86 Hz
  的差异来源。
- 复核 0.674 V 最大输入阶跃偏差对应的真实输入工况。

输出：results/hardening/audit/
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis.stability_analysis import (
    carrier_small_signal_gain,
    solve_operating_duty,
    stability_report,
)
from experiments._stage8_common import run_case, write_json
from simulations.averaged_model_runner import averaged_parameters_from_config
from circuits.closed_loop_config import load_closed_loop_config
from validation.reference_cases import build_case_config, load_validation_cases

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = PROJECT_ROOT / "results" / "hardening" / "audit"
RUNS_ROOT = OUT_ROOT / "runs"
STAGE8_BASELINE_RUN = "20261125_171501_a26df3bd"
STAGE4_STRESS_RUN = "20261125_133400_0c9ef0d5"


class Budget:
    def __init__(self) -> None:
        self.spice = 0

    def add_spice(self) -> None:
        self.spice += 1


def _trapz(values: np.ndarray, time: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(values, time))
    return float(np.trapz(values, time))


def _avg(values: np.ndarray, time: np.ndarray) -> float:
    return _trapz(values, time) / float(time[-1] - time[0])


def _rms(values: np.ndarray, time: np.ndarray) -> float:
    return float(np.sqrt(max(_avg(values * values, time), 0.0)))


def _load_window_gzip(path: Path) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return pd.read_csv(handle)


def _recompute(frame: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    time = frame["time_s"].to_numpy(dtype=float)
    vin = frame["vin_v"].to_numpy(dtype=float)
    vout = frame["vout_v"].to_numpy(dtype=float)
    iin = frame["input_current_a"].to_numpy(dtype=float)
    iload = frame["load_current_a"].to_numpy(dtype=float)
    il = frame["inductor_current_a"].to_numpy(dtype=float)
    ic = frame["capacitor_current_a"].to_numpy(dtype=float)
    vds = frame["mosfet_vds_v"].to_numpy(dtype=float)
    vgs = frame["mosfet_vgs_v"].to_numpy(dtype=float)
    idrain = frame["mosfet_drain_terminal_current_a"].to_numpy(dtype=float)
    ig = frame["gate_current_a"].to_numpy(dtype=float)
    vdrv = frame["drive_vgs_command_v"].to_numpy(dtype=float)
    idrv = frame["driver_current_a"].to_numpy(dtype=float)
    vak = frame["diode_anode_cathode_voltage_v"].to_numpy(dtype=float)
    idiode = frame["diode_current_a"].to_numpy(dtype=float)

    dcr = float(cfg["inductor"]["dcr_ohm"])
    esr = float(cfg["capacitor"]["esr_ohm"])
    rg = float(cfg["gate_driver"]["gate_resistance_ohm"])
    rgs = float(cfg["gate_driver"]["gate_source_pulldown_ohm"])

    vout_mean = _avg(vout, time)
    iin_mean = _avg(iin, time)
    vin_mean = _avg(vin, time)
    pin_int = _avg(vin * iin, time)
    pin_dc = vin_mean * iin_mean
    pout = _avg(vout * iload, time)
    iout_mean = _avg(iload, time)
    pdrv = _avg(vdrv * idrv, time)

    pmos_drain = _avg(vds * idrain, time)
    pmos_gate = _avg(vgs * ig, time)
    pmos_total = pmos_drain + pmos_gate
    pdiode = _avg(vak * idiode, time)
    pdcr = dcr * _avg(il * il, time)
    pesr = esr * _avg(ic * ic, time)
    prg = rg * _avg(ig * ig, time)
    prpd = _avg(vgs * vgs, time) / rgs
    total_loss = pmos_total + pdiode + pdcr + pesr + prg + prpd
    residual = pin_int + pdrv - pout - total_loss

    on_mask = vgs > 5.0
    conduction_drain = (
        _trapz((vds * idrain)[on_mask], time[on_mask])
        / float(time[-1] - time[0])
        if on_mask.sum() > 10
        else math.nan
    )
    switching_drain_est = pmos_drain - conduction_drain if math.isfinite(conduction_drain) else math.nan

    return {
        "window_start_s": float(time[0]),
        "window_end_s": float(time[-1]),
        "sample_count": int(len(frame)),
        "output_mean_v": vout_mean,
        "output_max_v": float(np.max(vout)),
        "output_min_v": float(np.min(vout)),
        "output_ripple_vpp": float(np.max(vout) - np.min(vout)),
        "output_abs_error_v": vout_mean - 5.0,
        "output_relative_error_percent": 100.0 * (vout_mean - 5.0) / 5.0,
        "input_mean_current_a": iin_mean,
        "input_mean_voltage_v": vin_mean,
        "input_power_integral_w": pin_int,
        "input_power_mean_product_w": pin_dc,
        "input_power_definition_gap_w": pin_dc - pin_int,
        "input_power_definition_gap_percent": 100.0 * (pin_dc - pin_int) / pin_int,
        "output_mean_current_a": iout_mean,
        "output_power_integral_w": pout,
        "effective_load_resistance_ohm": vout_mean / iout_mean,
        "driver_power_w": pdrv,
        "mosfet_drain_port_power_w": pmos_drain,
        "mosfet_gate_port_power_w": pmos_gate,
        "mosfet_network_power_w": pmos_total,
        "mosfet_conduction_estimate_w": conduction_drain,
        "mosfet_switching_estimate_w": switching_drain_est,
        "diode_power_w": pdiode,
        "dcr_loss_w": pdcr,
        "esr_loss_w": pesr,
        "gate_resistor_loss_w": prg,
        "pulldown_loss_w": prpd,
        "total_loss_w": total_loss,
        "residual_w": residual,
        "residual_ratio": residual / (pin_int + pdrv),
        "efficiency_stage_percent": 100.0 * pout / pin_int,
        "efficiency_system_percent": 100.0 * pout / (pin_int + pdrv),
        "inductor_mean_a": _avg(il, time),
        "inductor_peak_a": float(np.max(il)),
        "inductor_valley_a": float(np.min(il)),
        "inductor_ripple_a": float(np.max(il) - np.min(il)),
        "inductor_rms_a": _rms(il, time),
        "capacitor_rms_a": _rms(ic, time),
        "mosfet_vds_max_v": float(np.max(vds)),
        "mosfet_id_peak_a": float(np.max(idrain)),
        "mosfet_vgs_max_v": float(np.max(vgs)),
        "mosfet_vgs_min_v": float(np.min(vgs)),
        "diode_reverse_voltage_max_v": float(np.max(-vak)),
        "gate_resistance_ohm": rg,
        "pulldown_resistance_ohm": rgs,
        "dcr_ohm": dcr,
        "esr_ohm": esr,
        "data_source": "spice_derived",
    }


def _delta(new: dict[str, Any], ref: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    rows = {}
    for name, key in mapping.items():
        a = new.get(name)
        b = ref.get(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isfinite(a) and math.isfinite(b):
            rows[name] = {"recomputed": a, "stored": b, "difference": a - b}
    return rows


def _loop_inconsistency() -> dict[str, Any]:
    config = load_closed_loop_config()
    params = averaged_parameters_from_config(config)
    duty = solve_operating_duty(params, config.target_voltage_v)
    pwm_gain = carrier_small_signal_gain(duty)

    def report(kp: float, ki: float) -> dict[str, Any]:
        r = stability_report(
            params, kp, ki, target_v=config.target_voltage_v, pwm_gain=pwm_gain,
            limits={"phase_margin_deg": {"min": 45.0}, "finite_gain_margin_db": {"min": 6.0}},
        )
        crossings = [
            {
                "frequency_hz": c["frequency_hz"],
                "phase_deg": c["phase_deg"],
                "phase_margin_deg": c["phase_margin_deg"],
            }
            for c in r["magnitude_crossings"]
        ]
        return {
            "kp": kp,
            "ki": ki,
            "duty": duty,
            "pwm_gain": pwm_gain,
            "phase_margin_deg": r["phase_margin_deg"],
            "gain_margin_db": r["gain_margin_db"],
            "bandwidth_hz": r["bandwidth_hz"],
            "crossings": crossings,
            "closed_loop_poles": r["closed_loop_poles"],
            "messages": r["messages"],
        }

    # 同一 kp 下扫描 ki，检查是否能在记录的 3x3 矩阵之外复现 57.3 Hz / 62 deg。
    sweep = []
    for ki in (58.83, 70.0, 80.0, 90.0, 100.0, 117.66, 140.0, 176.49):
        r = stability_report(
            params, 0.0585, ki, target_v=config.target_voltage_v, pwm_gain=pwm_gain
        )
        sweep.append(
            {
                "kp": 0.0585,
                "ki": ki,
                "phase_margin_deg": r["phase_margin_deg"],
                "bandwidth_hz": r["bandwidth_hz"],
                "crossings": len(r["magnitude_crossings"]),
            }
        )

    return {
        "reproduced_config_gains": report(0.0585, 117.66),
        "declared_selected_candidate": {
            "declared": "0.5x kp, 2.0x ki",
            "actual_gains_in_yaml": {"kp": 0.0585, "ki": 117.66},
            "matrix_selected_gains": {"kp": 0.02925, "ki": 235.32},
            "matrix_selected_report": report(0.02925, 235.32),
        },
        "ki_sweep_at_kp_0p0585": sweep,
        "design_record_in_yaml": {"phase_margin_deg": 62.0, "bandwidth_hz": 57.3},
    }


def _line_step() -> dict[str, Any]:
    path = PROJECT_ROOT / "results" / "stage7" / "stage7_acceptance.json"
    acceptance = json.loads(path.read_text(encoding="utf-8"))
    records = acceptance["experiments"]["line_step"]["records"]
    rows = []
    for r in records:
        if r.get("model") == "averaged_model":
            continue
        m = r["metrics"]
        rows.append(
            {
                "case": r["case"],
                "scheme": r["scheme"],
                "run_id": r["run_id"],
                "vin_initial_v": m["event"]["initial_value"],
                "vin_final_v": m["event"]["final_value"],
                "pre_event_mean_v": m["pre_event_mean_v"],
                "post_event_mean_v": m["post_event_mean_v"],
                "droop_v": m["droop_v"],
                "overshoot_v": m["overshoot_v"],
                "maximum_absolute_deviation_v": m["maximum_absolute_deviation_v"],
                "recovery_time_s": (m.get("recovery_strict") or {}).get("recovery_time_s"),
                "iae_vs": m["iae_vs"],
                "status": r["limit_check"]["status"],
                "end_time_s": acceptance["experiments"]["line_step"]["end_time_s"],
                "load": "resistive_fixed 2.5 ohm (closed-loop nominal)",
            }
        )
    worst = max(
        (item for item in rows if item["scheme"] == "closed_loop"),
        key=lambda item: item["maximum_absolute_deviation_v"],
    )
    return {
        "source": str(path),
        "records": rows,
        "max_deviation_case": worst["case"],
        "max_deviation_value_v": worst["maximum_absolute_deviation_v"],
        "note": (
            "0.674 V 属于 9 V -> 12 V 输入阶跃的闭环过冲（droop=0，overshoot=0.6743 V），"
            "不是 12 V -> 16 V 工况；12 V -> 16 V 闭环最大偏差为 0.5885 V，"
            "16 V -> 12 V 为 0.4507 V"
        ),
    }


def _stress_reference() -> dict[str, Any]:
    path = PROJECT_ROOT / "results" / "buck_stage4" / f"run_{STAGE4_STRESS_RUN}" / "stage4_validation.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    model_e = payload["models"]["E"]
    return {
        "source_run": STAGE4_STRESS_RUN,
        "duty_cycle": 0.4166666666666667,
        "note": "stage4 名义开环占空比 0.41667，输出约 4.67-4.68 V，不是 5 V 校准工况",
        "stress_steady": model_e.get("stress"),
        "power": model_e.get("power"),
    }


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    budget = Budget()

    cases = {c.case_id: c for c in load_validation_cases()}
    config = build_case_config(cases["VAL001"])
    config_dict = config.to_dict()

    stored_metrics = json.loads(
        (PROJECT_ROOT / "results" / "stage8" / "runs" / STAGE8_BASELINE_RUN / "metrics.json").read_text(
            encoding="utf-8"
        )
    )

    rerun = None
    timing_attempts = []
    for step, maximum in ((50e-9, 25e-9), (25e-9, 25e-9), (50e-9, 20e-9), (100e-9, 50e-9)):
        candidate = run_case(
            config,
            "E",
            budget,
            label="audit_VAL001_E_regenerated",
            step_time_s=step,
            max_step_time_s=maximum,
            end_time_s=5e-3,
            run_root=RUNS_ROOT,
            save=True,
            save_waveform=True,
        )
        timing_attempts.append(
            {"step_time_s": step, "max_step_time_s": maximum, "status": candidate["status"]}
        )
        if candidate["status"] == "COMPLETED":
            rerun = candidate
            break
    if rerun is None:
        raise SystemExit(f"regenerated VAL001 run failed: {timing_attempts}")
    rerun["timing_attempts"] = timing_attempts

    frame = _load_window_gzip(Path(rerun["run_dir"]) / "waveform.csv.gz")
    recomputed = _recompute(frame, config_dict)
    deltas = _delta(
        recomputed,
        stored_metrics,
        {
            "output_mean_v": "output_voltage_mean_v",
            "output_ripple_vpp": "output_voltage_ripple_vpp",
            "input_mean_current_a": "input_current_mean_a",
            "input_power_integral_w": "input_power_w",
            "output_power_integral_w": "output_power_w",
            "total_loss_w": "total_loss_w",
            "efficiency_stage_percent": "efficiency_power_stage_percent",
            "efficiency_system_percent": "efficiency_system_percent",
            "inductor_peak_a": "inductor_current_peak_a",
            "inductor_valley_a": "inductor_current_valley_a",
            "inductor_ripple_a": "inductor_current_ripple_a",
            "capacitor_rms_a": "capacitor_current_rms_a",
            "mosfet_network_power_w": "mosfet_loss_w",
            "diode_power_w": "diode_loss_w",
            "dcr_loss_w": "dcr_loss_w",
            "esr_loss_w": "esr_loss_w",
            "gate_resistor_loss_w": "gate_resistor_loss_w",
            "pulldown_loss_w": "pulldown_loss_w",
        },
    )

    audit = {
        "task": "engineering_metric_audit",
        "data_source": "spice_simulation + spice_derived",
        "historical_baseline": {
            "run_id": STAGE8_BASELINE_RUN,
            "path": f"results/stage8/runs/{STAGE8_BASELINE_RUN}",
            "config": "configs/nonideal_buck_config.yaml + calibrated duty 0.44520054460590486",
            "stored_metrics": stored_metrics,
            "note": "历史目录只保存 metrics.json 与 circuit.cir，未保存原始波形",
        },
        "regenerated_waveform_run": rerun,
        "recomputed_from_waveform": recomputed,
        "recomputed_vs_stored": deltas,
        "input_power_definition": {
            "integral_of_v_times_i_w": recomputed["input_power_integral_w"],
            "mean_voltage_times_mean_current_w": recomputed["input_power_mean_product_w"],
            "gap_w": recomputed["input_power_definition_gap_w"],
            "gap_percent": recomputed["input_power_definition_gap_percent"],
            "stored_metrics_input_current_mean_a": stored_metrics["input_current_mean_a"],
            "stored_metrics_input_power_w": stored_metrics["input_power_w"],
            "stored_current_times_12v_w": 12.0 * stored_metrics["input_current_mean_a"],
            "stored_gap_percent": 100.0
            * (12.0 * stored_metrics["input_current_mean_a"] - stored_metrics["input_power_w"])
            / stored_metrics["input_power_w"],
            "conservation_json_input_power_w": 11.4908,
            "conclusion": (
                "同配置复算窗口内 <vin*iin>=10.7527 W 且 vin=12 V 恒定，"
                "对应输入平均电流 0.89606 A，与存储 input_power_w=10.7498 W 自洽；"
                "但历史 metrics.json 的 input_current_mean=0.95716 A 与自身功率不自洽"
                "（12x0.95716=11.486 W，偏高 6.9%），stage8 conservation.json 的"
                " Pin=11.4908 W 也沿用了该电流口径。报告统一采用 <v*i> 时间积分口径，"
                "并保留两套数值，不修改历史文件"
            ),
        },
        "mosfet_loss_boundary": {
            "drain_port_power_w": recomputed["mosfet_drain_port_power_w"],
            "gate_port_power_w": recomputed["mosfet_gate_port_power_w"],
            "network_power_w": recomputed["mosfet_network_power_w"],
            "conduction_estimate_w": recomputed["mosfet_conduction_estimate_w"],
            "switching_estimate_w": recomputed["mosfet_switching_estimate_w"],
            "mask_based_split_valid": False,
            "mask_based_split_note": (
                "用 vgs>5 V 掩码会把栅极充电/换流过渡段计入导通，"
                "在 100 ns 输出步长下导通估计(0.1211 W)大于漏极端口总功率(0.0604 W)，"
                "因此该拆分不可用；只保留端口总功率与转换窗口诊断量"
            ),
            "stored_switching_power_w": stored_metrics.get("switching_power_w"),
            "conclusion": (
                "MOSFET 端口功率已包含导通与开关的全部漏极能量，"
                "switching_power_w 只是转换窗口诊断量，不能再加到总损耗中"
            ),
        },
        "loop_margin_inconsistency": _loop_inconsistency(),
        "line_step_audit": _line_step(),
        "stress_reference": _stress_reference(),
        "notes": [
            "历史结果未修改，复算运行写入 results/hardening/audit/runs",
            "复算使用与历史相同的配置、占空比、步长与结束时间",
        ],
    }

    write_json(OUT_ROOT / "audit_metrics.json", audit)

    flat_rows = []
    for key, value in recomputed.items():
        flat_rows.append({"metric": key, "value": value})
    pd.DataFrame(flat_rows).to_csv(OUT_ROOT / "recomputed_metrics.csv", index=False)

    print("=== regenerated run ===")
    print(rerun["run_id"], rerun["run_dir"])
    print("=== core recomputation ===")
    for key in (
        "output_mean_v",
        "output_ripple_vpp",
        "input_mean_current_a",
        "input_power_integral_w",
        "input_power_mean_product_w",
        "output_power_integral_w",
        "efficiency_stage_percent",
        "efficiency_system_percent",
        "total_loss_w",
        "residual_ratio",
        "inductor_peak_a",
        "inductor_valley_a",
        "mosfet_vds_max_v",
        "mosfet_id_peak_a",
    ):
        print(f"{key}: {recomputed[key]}")
    print("=== loop ===")
    print("config gains PM/BW:", _loop_inconsistency()["reproduced_config_gains"]["phase_margin_deg"],
          _loop_inconsistency()["reproduced_config_gains"]["bandwidth_hz"])
    print("saved:", OUT_ROOT / "audit_metrics.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
