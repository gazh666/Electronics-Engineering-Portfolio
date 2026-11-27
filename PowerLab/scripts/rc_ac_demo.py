"""RC 低通交流小信号分析（Bode 图与截止频率）。

运行：``python -m scripts.rc_ac_demo``
"""

from __future__ import annotations

import json
import math
import sys
from typing import Any

import numpy as np
import pandas as pd

from analysis.error_metrics import cutoff_frequency_error
from analysis.frequency_response import estimate_cutoff_frequency
from analysis.theory import (
    DATA_SOURCE,
    rc_cutoff_frequency,
    rc_frequency_response,
    rc_time_constant,
)
from circuits.rc_circuit import build_rc_lowpass
from simulations.config import BasicCircuitsConfig, load_basic_circuits_config
from simulations.runner import SimulationRunner
from storage.result_store import ResultStore
from visualization.plots import plot_bode


def analyze(
    config: BasicCircuitsConfig | None = None,
    store: ResultStore | None = None,
) -> dict[str, Any]:
    config = config or load_basic_circuits_config()
    store = store or ResultStore()
    runner = SimulationRunner(config.simulation_temperature_c)
    rc = config.rc
    ac = config.rc_ac

    circuit = build_rc_lowpass(rc.resistance_ohm, rc.capacitance_f)
    result = runner.run_ac(
        circuit,
        ac.start_hz,
        ac.stop_hz,
        ac.points_per_decade,
        variation=ac.variation,
        parameters=rc.to_dict(),
    )

    frequency = result.data["frequency_hz"].to_numpy()
    vin = result.data["vin_real_v"].to_numpy() + 1j * result.data["vin_imag_v"].to_numpy()
    vout = result.data["out_real_v"].to_numpy() + 1j * result.data["out_imag_v"].to_numpy()
    transfer = vout / vin
    magnitude = np.abs(transfer)
    gain_db = 20.0 * np.log10(magnitude)
    phase_deg = np.angle(transfer, deg=True)

    theory = rc_frequency_response(frequency, rc.resistance_ohm, rc.capacitance_f)
    theory_magnitude = theory["magnitude"]
    theory_gain_db = theory["gain_db"]
    theory_phase_deg = theory["phase_deg"]

    cutoff = estimate_cutoff_frequency(frequency, magnitude)
    theory_fc = rc_cutoff_frequency(rc.resistance_ohm, rc.capacitance_f)
    tau = rc_time_constant(rc.resistance_ohm, rc.capacitance_f)

    if cutoff.get("found"):
        simulated_fc = float(cutoff["frequency_hz"])
        gain_at_sim_fc = float(np.interp(np.log10(simulated_fc), np.log10(frequency), gain_db))
        phase_at_sim_fc = float(np.interp(np.log10(simulated_fc), np.log10(frequency), phase_deg))
        fc_error = cutoff_frequency_error(simulated_fc, theory_fc)
    else:
        simulated_fc = None
        gain_at_sim_fc = None
        phase_at_sim_fc = None
        fc_error = None

    gain_error = gain_db - theory_gain_db
    phase_error = phase_deg - theory_phase_deg
    max_gain_error = float(np.max(np.abs(gain_error)))
    max_phase_error = float(np.max(np.abs(phase_error)))

    waveform = result.data.copy()
    waveform["magnitude"] = magnitude
    waveform["gain_db"] = gain_db
    waveform["phase_deg"] = phase_deg

    theory_frame = pd.DataFrame(
        {
            "frequency_hz": frequency,
            "theoretical_magnitude": theory_magnitude,
            "theoretical_gain_db": theory_gain_db,
            "theoretical_phase_deg": theory_phase_deg,
            "data_source": DATA_SOURCE,
        }
    )
    comparison = pd.DataFrame(
        {
            "frequency_hz": frequency,
            "simulated_gain_db": gain_db,
            "theoretical_gain_db": theory_gain_db,
            "gain_error_db": gain_error,
            "simulated_phase_deg": phase_deg,
            "theoretical_phase_deg": theory_phase_deg,
            "phase_error_deg": phase_error,
        }
    )

    _, run_dir = store.create_run_dir(result.run_id)
    magnitude_figure, phase_figure = plot_bode(
        frequency,
        gain_db,
        phase_deg,
        run_dir / "waveform.png",
        run_dir / "phase.png",
        title="RC Low-Pass Filter (R=1 kOhm, C=1 uF)",
        marker_hz=simulated_fc,
        marker_label="fc",
    )

    summary = {
        "status": "PASS",
        "points": result.point_count,
        "tau_s": tau,
        "theoretical_cutoff_hz": theory_fc,
        "simulated_cutoff_hz": simulated_fc,
        "cutoff_interpolation": cutoff,
        "cutoff_error": fc_error,
        "gain_at_cutoff_db": gain_at_sim_fc,
        "phase_at_cutoff_deg": phase_at_sim_fc,
        "max_gain_error_db": max_gain_error,
        "max_phase_error_deg": max_phase_error,
        "first_point": {
            "frequency_hz": float(frequency[0]),
            "magnitude": float(magnitude[0]),
            "gain_db": float(gain_db[0]),
            "phase_deg": float(phase_deg[0]),
        },
        "last_point": {
            "frequency_hz": float(frequency[-1]),
            "magnitude": float(magnitude[-1]),
            "gain_db": float(gain_db[-1]),
            "phase_deg": float(phase_deg[-1]),
        },
        "duration_ms": result.duration_ms,
        "analysis_command": result.metadata.get("analysis_command"),
        "run_dir": str(run_dir),
        "data_source": {"waveform": "spice_simulation", "theory": DATA_SOURCE},
    }

    checks = {
        "cutoff_found": simulated_fc is not None,
        "cutoff_relative_error_below_0p2_percent": bool(
            fc_error is not None and abs(fc_error["relative_error_percent"]) < 0.2
        ),
        "gain_at_cutoff_near_minus_3dB": bool(
            gain_at_sim_fc is not None and abs(gain_at_sim_fc + 3.010299956639812) < 0.05
        ),
        "phase_at_cutoff_near_minus_45deg": bool(
            phase_at_sim_fc is not None and abs(phase_at_sim_fc + 45.0) < 1.0
        ),
        "gain_matches_theory": max_gain_error < 0.01,
        "phase_matches_theory": max_phase_error < 0.1,
    }
    summary["status"] = "PASS" if all(checks.values()) else "FAIL"
    summary["checks"] = checks

    store.save_result(
        result,
        run_dir=run_dir,
        analysis_parameters={
            "resistance_ohm": rc.resistance_ohm,
            "capacitance_f": rc.capacitance_f,
            "ac_start_hz": ac.start_hz,
            "ac_stop_hz": ac.stop_hz,
            "points_per_decade": ac.points_per_decade,
            "derived_cutoff_hz": simulated_fc,
        },
        config_snapshot=config.to_dict(),
        theory=theory_frame,
        comparison=comparison,
        waveform=waveform,
        summary=summary,
        figures={"waveform.png": magnitude_figure, "phase.png": phase_figure},
        log_lines=[
            f"AC points={result.point_count}",
            f"simulated cutoff={simulated_fc}",
            f"theoretical cutoff={theory_fc}",
        ],
    )
    return summary


def main() -> int:
    try:
        summary = analyze()
    except Exception as exc:  # noqa: BLE001
        ResultStore().save_failure(analysis_name="rc_ac_demo", error=exc)
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
