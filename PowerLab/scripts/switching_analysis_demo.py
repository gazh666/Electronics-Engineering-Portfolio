"""开关边沿与开关能量演示：上升/下降时间、延迟、单周期能量。"""

from __future__ import annotations

from circuits.nonideal_config import load_nonideal_buck_config
from scripts.performance_common import (
    PERFORMANCE_RESULTS_ROOT,
    run_performance_case,
    save_performance_run,
)
from storage.result_store import ResultStore


def main() -> int:
    config = load_nonideal_buck_config()
    payload = run_performance_case(config, variant="E", include_spectrum=False)
    store = ResultStore(root=PERFORMANCE_RESULTS_ROOT)
    run_id, run_dir = store.create_run_dir(payload.run_id)
    save_performance_run(
        payload,
        config,
        store,
        run_dir,
        title="Model E Switching Analysis",
        make_figures=True,
    )

    details = payload.switching_details
    print(f"[switching] run={run_id} dir={run_dir}")
    for edge_name in ("turn_on", "turn_off"):
        edge = details.get(edge_name, {})
        print(
            f"  {edge_name}: status={edge.get('status')} "
            f"duration={edge.get('duration_s')} sample_count={edge.get('sample_count')} "
            f"max_gap={edge.get('max_gap_s')}"
        )
    print(f"  turn_on_delay_s: {details.get('turn_on_delay_s')}")
    print(f"  turn_off_delay_s: {details.get('turn_off_delay_s')}")
    print(f"  edges_detected: {details.get('edge_count')}")
    for name in (
        "switching_turn_on_energy_j",
        "switching_turn_off_energy_j",
        "switching_total_energy_j",
        "switching_power_w",
        "switching_edge_resolution_ok",
    ):
        metric = payload.metric(name)
        if metric is not None:
            print(f"  {name}: {metric.value} {metric.unit} [{metric.status.value}]")
    print(f"  overall={payload.overall_status} quality={payload.quality['warning_codes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
