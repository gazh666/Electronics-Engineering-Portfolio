"""输入特性演示：5 个输入电压点的真实 SPICE 扫描与输入调整率。"""

from __future__ import annotations

from circuits.nonideal_config import load_nonideal_buck_config
from experiments.line_characteristics import run_line_characteristic
from scripts.performance_common import PERFORMANCE_RESULTS_ROOT
from storage.result_store import ResultStore, write_dataframe, write_json
from visualization.plots import plot_line_characteristic

INPUT_VOLTAGES_V = (9.0, 10.8, 12.0, 14.4, 16.0)


def main() -> int:
    config = load_nonideal_buck_config()
    sweep = run_line_characteristic(config, INPUT_VOLTAGES_V, variant="E")

    store = ResultStore(root=PERFORMANCE_RESULTS_ROOT)
    run_id, run_dir = store.create_run_dir()
    write_dataframe(run_dir / "line_characteristic.csv", sweep.table)
    write_json(run_dir / "line_regulation.json", sweep.regulation)
    write_json(
        run_dir / "metadata.json",
        {
            "run_id": run_id,
            "analysis": "line_characteristic",
            "variant": "E",
            "input_voltages_v": list(INPUT_VOLTAGES_V),
            "data_source": "spice_simulation",
            "runs": list(sweep.runs),
        },
    )
    plot_line_characteristic(
        sweep.table,
        run_dir / "plots" / "line_characteristic.png",
        title="Line Characteristic (Model E, feed-forward duty)",
    )

    print(f"[line] run={run_id} dir={run_dir}")
    print(sweep.table.to_string(index=False))
    regulation = sweep.regulation
    print(
        "  line regulation: "
        f"status={regulation.get('status')} "
        f"span={regulation.get('span_percent')}% "
        f"sensitivity={regulation.get('sensitivity_mv_per_v')} mV/V "
        f"note={regulation.get('control_note')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
