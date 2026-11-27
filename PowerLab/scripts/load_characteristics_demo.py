"""负载特性演示：7 个负载点的真实 SPICE 扫描与负载调整率。"""

from __future__ import annotations

from circuits.nonideal_config import load_nonideal_buck_config
from experiments.load_characteristics import run_load_characteristic
from scripts.performance_common import PERFORMANCE_RESULTS_ROOT
from storage.result_store import ResultStore, write_dataframe, write_json
from visualization.plots import plot_load_characteristic

RESISTANCES_OHM = (50.0, 20.0, 10.0, 5.0, 2.5, 2.0, 5.0 / 3.0)


def main() -> int:
    config = load_nonideal_buck_config()
    sweep = run_load_characteristic(config, RESISTANCES_OHM, variant="E")

    store = ResultStore(root=PERFORMANCE_RESULTS_ROOT)
    run_id, run_dir = store.create_run_dir()
    write_dataframe(run_dir / "load_characteristic.csv", sweep.table)
    write_json(run_dir / "load_regulation.json", sweep.regulation)
    write_json(
        run_dir / "metadata.json",
        {
            "run_id": run_id,
            "analysis": "load_characteristic",
            "variant": "E",
            "resistances_ohm": list(RESISTANCES_OHM),
            "data_source": "spice_simulation",
            "runs": list(sweep.runs),
        },
    )
    plot_load_characteristic(
        sweep.table,
        run_dir / "plots" / "load_characteristic.png",
        title="Load Characteristic (Model E, open loop)",
    )

    print(f"[load] run={run_id} dir={run_dir}")
    print(sweep.table.to_string(index=False))
    regulation = sweep.regulation
    print(
        "  load regulation: "
        f"status={regulation.get('status')} "
        f"span={regulation.get('span_percent')}% "
        f"ccm_slope={regulation.get('ccm_slope_mv_per_a')} mV/A "
        f"ccm_points={regulation.get('ccm_points')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
