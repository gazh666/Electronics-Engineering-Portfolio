"""第四阶段：浮动高侧栅极驱动与栅极电阻的真实瞬态对比。

驱动源是理想浮动电压源（以开关节点为参考），不是 Bootstrap 电路；
不含自举充电、UVLO 或驱动供电模型。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from circuits.nonideal_config import load_device_models, load_nonideal_buck_config
from simulations.nonideal_buck_runner import with_gate_resistance
from scripts.nonideal_common import (
    NONIDEAL_RESULTS_ROOT,
    run_case_with_retries,
    save_case,
)
from storage.result_store import ResultStore
from visualization.plots import plot_separate_time_series


def _two_cycle_window(case, periods: float = 2.0) -> pd.DataFrame:
    start = case.steady.start_time_s
    end = min(start + periods * case.config.period_s, case.steady.end_time_s)
    frame = case.frame
    mask = (frame["time_s"] >= start) & (frame["time_s"] <= end)
    return frame.loc[mask].reset_index(drop=True)


def main() -> int:
    base = load_nonideal_buck_config()
    resistances = load_device_models()["gate_driver_tests"]["resistance_values_ohm"]

    store = ResultStore(root=NONIDEAL_RESULTS_ROOT)
    rows: list[dict[str, object]] = []
    cases = []
    for resistance in resistances:
        config = with_gate_resistance(base, float(resistance))
        # 个别栅极电阻在 25 ns 最大步长下会触发 ngspice
        # "timestep too small"；自动换用更小步长并记录重试。
        case = run_case_with_retries(config, "E")
        run_id, run_dir = store.create_run_dir()
        window = _two_cycle_window(case)
        cases.append((float(resistance), case, run_id, run_dir, window))

        gate_current = window["gate_current_a"].to_numpy(dtype=float)
        rows.append(
            {
                "gate_resistance_ohm": float(resistance),
                "gate_resistor_loss_mw": case.accounting.gate_resistor_loss_w * 1e3,
                "pulldown_loss_mw": case.accounting.pulldown_loss_w * 1e3,
                "driver_power_mw": case.accounting.driver_average_power_w * 1e3,
                "gate_current_peak_a": float(np.max(np.abs(gate_current))),
                "switching_energy_uj": case.switching.total_energy_j * 1e6,
                "turn_on_count": len(case.switching.turn_on_intervals_s),
                "turn_off_count": len(case.switching.turn_off_intervals_s),
                "vgs_max_v": case.stress.gate_source_voltage_max_v,
                "vgs_min_v": case.stress.gate_source_voltage_min_v,
                "efficiency_power_stage_percent": case.accounting.efficiency_power_stage_percent,
                "used_max_step_time_s": case.result.metadata.get("used_max_step_time_s"),
                "convergence_retries": len(
                    case.result.metadata.get("convergence_retries", [])
                ),
                "run_id": run_id,
            }
        )
        print(
            f"[RG={resistance:g} ohm] run={run_id} "
            f"step={rows[-1]['used_max_step_time_s'] * 1e9:.2f} ns "
            f"P_RG={rows[-1]['gate_resistor_loss_mw']:.4f} mW "
            f"E_sw={rows[-1]['switching_energy_uj']:.4f} uJ "
            f"IG_peak={rows[-1]['gate_current_peak_a']:.4f} A"
        )

    frame = pd.DataFrame(rows)
    figure_dir = NONIDEAL_RESULTS_ROOT / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    voltage_figure = plot_separate_time_series(
        {
            f"VGS, RG={item[0]:g} ohm": (
                item[4]["time_s"].to_numpy(dtype=float),
                item[4]["mosfet_vgs_v"].to_numpy(dtype=float),
            )
            for item in cases
        },
        figure_dir / "gate_driver_vgs.png",
        title="Gate-Source Voltage vs Gate Resistance (2 cycles)",
        y_label="VGS (V)",
    )
    current_figure = plot_separate_time_series(
        {
            f"IG, RG={item[0]:g} ohm": (
                item[4]["time_s"].to_numpy(dtype=float),
                item[4]["gate_current_a"].to_numpy(dtype=float),
            )
            for item in cases
        },
        figure_dir / "gate_driver_current.png",
        title="Gate Terminal Current vs Gate Resistance (2 cycles)",
        y_label="Gate current (A)",
    )

    for resistance, case, run_id, run_dir, _ in cases[:-1]:
        save_case(case, store, run_dir)
    last_resistance, last_case, last_run_id, last_dir, _ = cases[-1]
    save_case(
        last_case,
        store,
        last_dir,
        figures={
            "gate_driver_vgs.png": voltage_figure,
            "gate_driver_current.png": current_figure,
        },
        extra_tables={"gate_driver_summary.csv": frame},
    )
    print(f"summary saved: {last_dir / 'gate_driver_summary.csv'}")
    print(
        "note: ideal floating source referenced to the switch node; "
        "not a bootstrap gate driver."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
