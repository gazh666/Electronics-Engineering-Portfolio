"""输入前馈开/关对照：同一 12 V→9 V 线阶跃、同一功率级与 PI 参数。"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from analysis.transient_metrics import analyze_events
from circuits.closed_loop_config import load_closed_loop_config
from experiments import load_transient_limits
from experiments.line_step import line_event
from simulations.closed_loop_runner import run_closed_loop_with_fallback, save_closed_loop_run
from storage.result_store import write_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "results" / "stage7" / "experiments" / "feedforward_comparison.json"
CASE = "vin_step_down_12_to_9"


def _run(feedforward_enabled: bool) -> dict:
    base = load_closed_loop_config().with_named_line(CASE)
    config = (
        base.with_name(f"stage7_ff_{'on' if feedforward_enabled else 'off'}")
        .with_timing(0.016, step_time_s=5e-8, max_step_time_s=5e-8)
        .with_controller(replace(base.controller, feedforward_enabled=feedforward_enabled))
    )
    event = line_event(config, CASE)
    run = run_closed_loop_with_fallback(config, mode="closed_loop")
    limits = load_transient_limits()
    tolerance = float(limits.get("recovery", {}).get("tolerance_v", 0.05))
    metrics = analyze_events(
        run.data["time_s"],
        run.data["vout_v"],
        [event],
        target_v=config.target_voltage_v,
        tolerance_v=tolerance,
        period_s=config.period_s,
        hold_cycles=20,
        pre_window_s=1e-3,
        data_source=run.data_source,
    )[0]
    directory = save_closed_loop_run(
        run,
        save_waveform=True,
        extra_metadata={"experiment": "feedforward_comparison", "metrics": metrics},
    )
    return {
        "feedforward_enabled": feedforward_enabled,
        "run_id": run.run_id,
        "run_directory": str(directory),
        "point_count": run.point_count,
        "duration_ms": run.duration_ms,
        "step_fallback": run.metadata.get("step_fallback"),
        "metrics": metrics,
        "data_source": run.data_source,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true", help="写入 results/stage7/experiments")
    args = parser.parse_args()
    records = [_run(True), _run(False)]
    payload = {"experiment": "feedforward_comparison", "case": CASE, "records": records}
    if args.save:
        write_json(OUTPUT, payload)
        print(f"[feedforward] wrote {OUTPUT}")
    for record in records:
        metrics = record["metrics"]
        recovery = (metrics.get("recovery_strict") or {}).get("recovery_time_s")
        print(
            f"  ff={'on' if record['feedforward_enabled'] else 'off'} "
            f"droop={metrics['droop_v']:.4f} V "
            f"overshoot={metrics['overshoot_v']:.4f} V "
            f"final={metrics['final_mean_v']:.5f} V "
            f"recovery={recovery if recovery is not None else 'NOT_RECOVERED'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
