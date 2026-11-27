"""RC 充电瞬态：真实 ngspice 瞬态仿真 + 理论对照。

运行::

    python -m scripts.rc_transient_demo

说明：脉冲源带 1 μs 上升时间，理论公式假设理想瞬时阶跃，
因此起始阶段允许存在物理模型差异。
"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.metrics import rc_metrics
from analysis.error_metrics import time_weighted_error_metrics
from analysis.theory import DATA_SOURCE, rc_time_constant
from circuits.rc import build_rc_charging
from circuits.rc_circuit import build_rc_transient
from simulations.artifacts import create_run_dir, write_json, write_text
from simulations.config import (
    BasicCircuitsConfig,
    RCConfig,
    load_basic_circuits_config,
    load_simulation_config,
)
from simulations.environment import collect_environment
from simulations.runner import SimulationRunner
from storage.result_store import ResultStore
from visualization.plots import plot_comparison


def simulate_rc_transient(config: RCConfig | None = None) -> pd.DataFrame:
    """执行一次真实瞬态分析，返回时间与电压序列（不写磁盘）。"""
    config = config or load_simulation_config().rc
    circuit = build_rc_charging(
        config.vin_v,
        config.resistance_ohm,
        config.capacitance_f,
        rise_time_s=config.rise_time_s,
    )

    simulator = circuit.simulator(temperature=25, nominal_temperature=25)
    analysis = simulator.transient(step_time=config.step_time_s, end_time=config.end_time_s)

    time_s = np.asarray(analysis.time, dtype=float)
    vin_v = np.asarray(analysis["vin"], dtype=float)
    vout_v = np.asarray(analysis["out"], dtype=float)

    if time_s.size != vout_v.size or time_s.size < 2:
        raise RuntimeError("ngspice 返回的瞬态数据长度异常")

    theoretical_v = config.vin_v * (1.0 - np.exp(-time_s / config.tau_s))
    return pd.DataFrame(
        {
            "time_s": time_s,
            "vin_v": vin_v,
            "spice_vout_v": vout_v,
            "ideal_step_theoretical_v": theoretical_v,
        }
    )


def analyze_charge_discharge(
    config: BasicCircuitsConfig | None = None,
    store: ResultStore | None = None,
) -> dict[str, object]:
    """12 ms 充放电瞬态：同一仿真中包含充电与放电两个阶段。

    放电理论初值使用实际开始放电时刻的仿真电压，而不是假设 5 V 充满。
    """
    config = config or load_basic_circuits_config()
    store = store or ResultStore()
    runner = SimulationRunner(config.simulation_temperature_c)
    rc = config.rc
    transient = config.rc_transient
    tau_s = rc_time_constant(rc.resistance_ohm, rc.capacitance_f)
    pulse_width = transient.end_s / 2.0

    circuit = build_rc_transient(
        rc.input_v,
        rc.resistance_ohm,
        rc.capacitance_f,
        rise_time_s=rc.rise_time_s,
        pulse_width_s=pulse_width,
        period_s=transient.end_s,
    )
    result = runner.run_transient(circuit, transient.step_s, transient.end_s, parameters=rc.to_dict())

    time_s = result.data["time_s"].to_numpy()
    vin_v = result.data["vin_v"].to_numpy()
    vout_v = result.data["out_v"].to_numpy()

    falling = np.where((time_s > pulse_width * 0.5) & (vin_v < 0.5 * rc.input_v))[0]
    if falling.size == 0:
        raise RuntimeError("未在仿真波形中找到放电起始点")
    fall_index = int(falling[0])
    discharge_t0 = float(time_s[fall_index])
    discharge_v0 = float(vout_v[fall_index])

    charge_theory = rc.input_v * (1.0 - np.exp(-time_s / tau_s))
    discharge_theory = discharge_v0 * np.exp(-(time_s - discharge_t0) / tau_s)
    theory_v = np.where(time_s < discharge_t0, charge_theory, discharge_theory)

    charge_mask = time_s < discharge_t0
    discharge_mask = ~charge_mask
    error = vout_v - theory_v
    weighted = time_weighted_error_metrics(time_s, vout_v, theory_v)

    def _interp(target: float) -> float:
        return float(np.interp(target, time_s, vout_v))

    charge_checkpoints = []
    for multiple in (1, 2, 3):
        target = multiple * tau_s
        if target >= discharge_t0:
            continue
        simulated = _interp(target)
        theoretical = float(rc.input_v * (1.0 - np.exp(-target / tau_s)))
        charge_checkpoints.append(
            {
                "tau_multiple": multiple,
                "time_s": target,
                "simulated_v": simulated,
                "theoretical_v": theoretical,
                "absolute_error_v": simulated - theoretical,
            }
        )

    discharge_checkpoints = []
    for multiple in (1, 2):
        target = discharge_t0 + multiple * tau_s
        if target > time_s[-1]:
            continue
        simulated = _interp(target)
        theoretical = float(discharge_v0 * np.exp(-(target - discharge_t0) / tau_s))
        discharge_checkpoints.append(
            {
                "tau_multiple": multiple,
                "time_s": target,
                "simulated_v": simulated,
                "theoretical_v": theoretical,
                "absolute_error_v": simulated - theoretical,
            }
        )

    waveform = result.data.copy()
    theory_frame = pd.DataFrame(
        {
            "time_s": time_s,
            "theoretical_v": theory_v,
            "phase": np.where(charge_mask, "charge", "discharge"),
            "data_source": DATA_SOURCE,
        }
    )
    comparison = pd.DataFrame(
        {
            "time_s": time_s,
            "simulated_vout_v": vout_v,
            "theoretical_v": theory_v,
            "absolute_error_v": error,
            "phase": np.where(charge_mask, "charge", "discharge"),
        }
    )

    _, run_dir = store.create_run_dir(result.run_id)
    figure = plot_comparison(
        time_s,
        vout_v,
        theory_v,
        run_dir / "waveform.png",
        title="RC Charge/Discharge Transient (tau=1 ms)",
        y_label="Capacitor voltage (V)",
        theoretical_label="Piecewise theory (actual discharge initial value)",
    )

    summary = {
        "status": "PASS",
        "tau_s": tau_s,
        "points": result.point_count,
        "nonuniform_sampling": bool(result.metadata.get("nonuniform_sampling", False)),
        "discharge_start_s": discharge_t0,
        "discharge_initial_v": discharge_v0,
        "charge_checkpoints": charge_checkpoints,
        "discharge_checkpoints": discharge_checkpoints,
        "max_absolute_error_v": float(np.max(np.abs(error))),
        "rmse_v": float(np.sqrt(np.mean(error**2))),
        "time_weighted": weighted,
        "final_voltage_v": float(vout_v[-1]),
        "duration_ms": result.duration_ms,
        "analysis_command": result.metadata.get("analysis_command"),
        "run_dir": str(run_dir),
        "data_source": {"waveform": "spice_simulation", "theory": DATA_SOURCE},
    }
    summary["status"] = "PASS" if all(
        [
            abs(charge_checkpoints[0]["simulated_v"] - 3.1606) < 0.03,
            abs(discharge_checkpoints[0]["absolute_error_v"]) < 0.03,
            abs(discharge_v0 - 4.9876) < 0.02,
        ]
    ) else "FAIL"

    store.save_result(
        result,
        run_dir=run_dir,
        analysis_parameters={
            "resistance_ohm": rc.resistance_ohm,
            "capacitance_f": rc.capacitance_f,
            "rise_time_s": rc.rise_time_s,
            "pulse_width_s": pulse_width,
            "discharge_t0_s": discharge_t0,
            "discharge_initial_v": discharge_v0,
        },
        config_snapshot=config.to_dict(),
        theory=theory_frame,
        comparison=comparison,
        waveform=waveform,
        summary=summary,
        figures={"waveform.png": figure},
        log_lines=[
            f"transient points={result.point_count}",
            f"discharge starts at {discharge_t0:.9g} s with V={discharge_v0:.9g} V",
        ],
    )
    return summary


def main() -> int:
    config = load_simulation_config().rc
    try:
        frame = simulate_rc_transient(config)
        metrics = rc_metrics(
            frame["time_s"].to_numpy(),
            frame["spice_vout_v"].to_numpy(),
            vin_v=config.vin_v,
            tau_s=config.tau_s,
            checkpoints_tau=config.checkpoints_tau,
        )
    except Exception as exc:  # noqa: BLE001 - 命令行需要如实上报仿真失败
        print(f"仿真失败: {exc}", file=sys.stderr)
        return 1

    run_dir = create_run_dir("rc")
    frame.to_csv(run_dir / "rc_transient.csv", index=False)
    write_text(run_dir / "netlist.cir", str(build_rc_charging(
        config.vin_v,
        config.resistance_ohm,
        config.capacitance_f,
        rise_time_s=config.rise_time_s,
    )))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(frame["time_s"] * 1e3, frame["spice_vout_v"], label="ngspice simulation")
    ax.plot(
        frame["time_s"] * 1e3,
        frame["ideal_step_theoretical_v"],
        linestyle="--",
        label="Ideal-step theory",
    )
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Capacitor voltage (V)")
    ax.set_title("RC Transient Response")
    ax.grid(True)
    ax.legend()
    fig.savefig(run_dir / "rc_transient.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    write_json(
        run_dir / "metrics.json",
        {
            "config": config.to_dict(),
            "metrics": metrics,
            "environment": collect_environment(),
            "data_source": "spice_simulation",
            "backend": "PySpice 1.5 + ngspice shared DLL",
            "note": "Theory uses an ideal instantaneous step; source rise time is finite.",
        },
    )

    print(f"Sample count: {metrics['sample_count']}")
    print(f"Time span:    {metrics['time_start_s']:.6e} .. {metrics['time_end_s']:.6e} s")
    for point in metrics["checkpoints"]:
        print(
            f"t={point['time_s'] * 1e3:.3f} ms "
            f"({point['tau_multiple']:.0f} tau): "
            f"sim={point['simulated_v']:.6f} V, "
            f"theory={point['ideal_step_theoretical_v']:.6f} V, "
            f"|err|={point['absolute_error_v']:.6f} V"
        )
    print(f"Final simulated voltage: {metrics['final_simulated_v']:.6f} V")
    print(f"Max absolute error:      {metrics['max_absolute_error_v']:.6f} V")
    print(f"RMSE:                    {metrics['rmse_v']:.6f} V")
    print(f"Run directory:           {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
