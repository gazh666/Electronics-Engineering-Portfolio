"""充电过程 SOC 监测演示（Task 31 / Task 40）。

复用第六阶段长时 ECM 充电包络（``simulations.long_duration_charge``）。
符号转换：第六阶段控制器**充电为正**，第七阶段安时积分**放电为正**，
因此 ``I_ecm = -I_charge``（``charging.battery_adapter.to_ecm_current``）。

关键约束：进入 COMPLETE 不等于 SOC=100%。12.15 V 教学充电目标本身不代表
充满，本脚本**不强制**把终止 SOC 设为 100%。
"""

from __future__ import annotations

import numpy as np

from analysis.soc_metrics import calculate_soc_metrics
from charging.battery_adapter import to_ecm_current
from estimation.coulomb_counter import CoulombCounter
from experiments.common import frozen_capacity_ah, load_bundle
from scripts.stage7_common import (
    finish,
    open_run,
    plot_series,
    write_metadata,
    write_payload,
    write_rows,
)
from simulations.long_duration_charge import LongChargeParameters, simulate_long_charge


def _estimate(
    time_s: np.ndarray,
    charging_current_a: np.ndarray,
    truth_mean_soc: np.ndarray,
    *,
    initial_soc: float,
    offset_a: float = 0.0,
) -> dict[str, object]:
    counter = CoulombCounter(capacity_ah=frozen_capacity_ah(), soc=float(initial_soc))
    estimated = [counter.soc]
    for index in range(1, time_s.size):
        dt = float(time_s[index] - time_s[index - 1])
        measured_charging = float(charging_current_a[index - 1]) + float(offset_a)
        counter.step(to_ecm_current(measured_charging), dt)
        estimated.append(counter.soc)
    estimated_array = np.asarray(estimated, dtype=float)
    metrics = calculate_soc_metrics(truth_mean_soc, estimated_array, time_s)
    return {
        "initial_soc": float(initial_soc),
        "offset_ma": float(offset_a) * 1000.0,
        "estimated_soc": estimated_array,
        "final_estimated_soc": float(estimated_array[-1]),
        "metrics": metrics,
        "bound_event_count": len(counter.bound_events),
    }


def main() -> None:
    run = open_run("soc_estimation")
    bundle = load_bundle()
    parameters = LongChargeParameters(
        initial_socs=(0.30, 0.30, 0.30),
        current_limit_a=1.0,
        voltage_target_v=12.15,
        termination_current_a=0.08,
        termination_hold_s=60.0,
        maximum_charge_time_s=7200.0,
        step_s=0.5,
    )
    charge = simulate_long_charge(parameters)
    truth_mean_soc = charge.soc.mean(axis=1)

    nominal = _estimate(charge.time_s, charge.charging_current_a, truth_mean_soc, initial_soc=0.30)
    offset = _estimate(charge.time_s, charge.charging_current_a, truth_mean_soc, initial_soc=0.30, offset_a=0.010)
    initial_error = _estimate(charge.time_s, charge.charging_current_a, truth_mean_soc, initial_soc=0.40)

    write_metadata(
        run,
        script="charging_soc_demo",
        description="CC-CV 长时充电包络下的充电 SOC 监测与符号转换",
        extra={
            "model_id": bundle["model_id"],
            "termination_reason": charge.termination_reason,
            "state": charge.state,
            "soc_forced_to_100_percent": False,
        },
    )
    write_rows(
        run,
        "charging_soc.csv",
        [
            {
                "time_s": float(charge.time_s[index]),
                "pack_voltage_v": float(charge.pack_voltage_v[index]),
                "charging_current_a": float(charge.charging_current_a[index]),
                "truth_mean_soc": float(truth_mean_soc[index]),
                "estimated_soc": float(nominal["estimated_soc"][index]),
                "estimated_soc_offset_10mA": float(offset["estimated_soc"][index]),
                "estimated_soc_initial_0p40": float(initial_error["estimated_soc"][index]),
            }
            for index in range(charge.time_s.size)
        ],
    )
    write_payload(
        run,
        "charging_summary.json",
        {
            "state": charge.state,
            "termination_reason": charge.termination_reason,
            "duration_s": float(charge.time_s[-1]),
            "final_truth_mean_soc": float(truth_mean_soc[-1]),
            "final_charging_current_a": float(charge.charging_current_a[-1]),
            "final_pack_voltage_v": float(charge.pack_voltage_v[-1]),
            "charge_ah": float(charge.summary.get("charge_ah", float("nan"))),
            "nominal": {k: v for k, v in nominal.items() if k != "estimated_soc"},
            "offset_10mA": {k: v for k, v in offset.items() if k != "estimated_soc"},
            "initial_error_10pp": {k: v for k, v in initial_error.items() if k != "estimated_soc"},
            "note": "COMPLETE 不强制 SOC=100%；终止 SOC 由安时积分给出。",
        },
    )
    plot_series(
        run,
        "22_cc_cv_charging_soc.png",
        {
            "truth mean SOC (ECM)": (charge.time_s, truth_mean_soc),
            "estimated (nominal)": (charge.time_s, nominal["estimated_soc"]),
            "estimated (initial +10 pp)": (charge.time_s, initial_error["estimated_soc"]),
            "estimated (current +10 mA)": (charge.time_s, offset["estimated_soc"]),
        },
        title=f"CC-CV charging SOC — {charge.state} (run {run.run_id})",
        xlabel="time (s)",
        ylabel="SOC (0-1)",
    )
    finish(run, "charging soc demo done")
    print(
        f"[charging_soc_demo] run={run.run_id} state={charge.state} reason={charge.termination_reason} "
        f"duration={charge.time_s[-1]:.1f} s final_truth_SOC={truth_mean_soc[-1]:.4f}"
    )
    for name, case in (("nominal", nominal), ("offset+10mA", offset), ("initial+10pp", initial_error)):
        print(
            f"  {name}: final={case['final_estimated_soc']:.4f} "
            f"RMSE={case['metrics']['rmse_pp']:.3f} pp max={case['metrics']['max_absolute_error_pp']:.3f} pp"
        )


if __name__ == "__main__":
    main()
