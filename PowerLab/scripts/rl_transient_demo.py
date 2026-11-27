"""RL 阶跃瞬态：电感电流上升、时间常数与储能。

运行：``python -m scripts.rl_transient_demo``
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np
import pandas as pd

from analysis.error_metrics import (
    calculate_error_metrics,
    error_near_time_constant,
    time_weighted_error_metrics,
)
from analysis.theory import (
    DATA_SOURCE,
    inductor_stored_energy,
    rl_step_current,
    rl_time_constant,
)
from circuits.rl_circuit import build_rl_transient
from simulations.config import BasicCircuitsConfig, load_basic_circuits_config
from simulations.runner import SimulationRunner
from storage.result_store import ResultStore
from visualization.plots import plot_comparison


def analyze(
    config: BasicCircuitsConfig | None = None,
    store: ResultStore | None = None,
) -> dict[str, Any]:
    config = config or load_basic_circuits_config()
    store = store or ResultStore()
    runner = SimulationRunner(config.simulation_temperature_c)
    rl = config.rl
    transient = config.rl_transient
    tau_s = rl_time_constant(rl.inductance_h, rl.resistance_ohm)
    steady_current = rl.input_v / rl.resistance_ohm

    circuit = build_rl_transient(
        rl.input_v,
        rl.resistance_ohm,
        rl.inductance_h,
        rise_time_s=rl.rise_time_s,
    )
    result = runner.run_transient(circuit, transient.step_s, transient.end_s, parameters=rl.to_dict())

    time_s = result.data["time_s"].to_numpy()
    inductor_current = result.data["l1_branch_current_a"].to_numpy()
    source_branch_current = result.data["vinput_branch_current_a"].to_numpy()
    supply_current = -source_branch_current

    theory_current = rl_step_current(time_s, rl.input_v, rl.resistance_ohm, rl.inductance_h)
    metrics = calculate_error_metrics(inductor_current, theory_current)
    weighted = time_weighted_error_metrics(time_s, inductor_current, theory_current)
    near_tau = error_near_time_constant(time_s, inductor_current, theory_current, tau_s)

    current_at_tau = float(np.interp(tau_s, time_s, inductor_current))
    theory_at_tau = float(steady_current * (1.0 - np.exp(-1.0)))
    final_current = float(inductor_current[-1])
    final_energy = inductor_stored_energy(rl.inductance_h, final_current)
    steady_energy = inductor_stored_energy(rl.inductance_h, steady_current)

    waveform = result.data.copy()
    waveform["inductor_current_a"] = inductor_current
    waveform["supply_current_a"] = supply_current
    waveform["inductor_voltage_v"] = result.data["inductor_node_v"].to_numpy()

    theory_frame = pd.DataFrame(
        {
            "time_s": time_s,
            "theoretical_current_a": theory_current,
            "data_source": DATA_SOURCE,
        }
    )
    comparison = pd.DataFrame(
        {
            "time_s": time_s,
            "simulated_inductor_current_a": inductor_current,
            "theoretical_current_a": theory_current,
            "absolute_error_a": inductor_current - theory_current,
        }
    )

    _, run_dir = store.create_run_dir(result.run_id)
    figure = plot_comparison(
        time_s,
        inductor_current,
        theory_current,
        run_dir / "waveform.png",
        title="RL Transient (L=10 mH, R=10 Ohm, tau=1 ms)",
        y_label="Inductor current (A)",
        theoretical_label="Analytical theory I(t) = (V/R)(1-exp(-t/tau))",
    )

    summary = {
        "status": "PASS",
        "tau_s": tau_s,
        "steady_state_current_a": steady_current,
        "current_at_one_tau_simulated_a": current_at_tau,
        "current_at_one_tau_theory_a": theory_at_tau,
        "current_at_one_tau_error_a": current_at_tau - theory_at_tau,
        "final_current_a": final_current,
        "final_current_error_a": final_current - steady_current,
        "inductor_energy_at_final_j": final_energy,
        "inductor_energy_at_steady_state_j": steady_energy,
        "max_absolute_error_a": metrics["max_absolute_error"],
        "mae_a": metrics["mae"],
        "rmse_a": metrics["rmse"],
        "time_weighted": weighted,
        "near_time_constant": near_tau,
        "points": result.point_count,
        "duration_ms": result.duration_ms,
        "analysis_command": result.metadata.get("analysis_command"),
        "source_branch_current_first_a": float(source_branch_current[0]),
        "supply_current_first_a": float(supply_current[0]),
        "run_dir": str(run_dir),
        "data_source": {"waveform": "spice_simulation", "theory": DATA_SOURCE},
    }

    checks = {
        "tau_current_within_2mA": abs(current_at_tau - theory_at_tau) < 2e-3,
        "final_current_within_2mA": abs(final_current - steady_current) < 2e-3,
        "current_direction_positive": bool(np.all(inductor_current >= -1e-12)),
        "source_branch_negative": bool(np.all(source_branch_current <= 1e-12)),
        "stored_energy_matches": abs(final_energy - steady_energy) / steady_energy < 0.01,
        "time_weighted_rmse_below_2mA": weighted["rmse_time_weighted"] < 2e-3,
    }
    summary["checks"] = checks
    summary["status"] = "PASS" if all(checks.values()) else "FAIL"

    store.save_result(
        result,
        run_dir=run_dir,
        analysis_parameters={
            "resistance_ohm": rl.resistance_ohm,
            "inductance_h": rl.inductance_h,
            "computed_tau_s": tau_s,
            "steady_state_current_a": steady_current,
        },
        config_snapshot=config.to_dict(),
        theory=theory_frame,
        comparison=comparison,
        waveform=waveform,
        summary=summary,
        figures={"waveform.png": figure},
        log_lines=[
            f"transient points={result.point_count}",
            f"I(1 tau)={current_at_tau:.9g} A",
            f"I(final)={final_current:.9g} A",
        ],
    )
    return summary


def main() -> int:
    try:
        summary = analyze()
    except Exception as exc:  # noqa: BLE001
        ResultStore().save_failure(analysis_name="rl_transient_demo", error=exc)
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
