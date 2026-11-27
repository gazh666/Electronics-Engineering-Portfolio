"""第四阶段：非理想 Buck（Model E）真实瞬态主演示。

包含 Level 1 NMOS、浮动栅极驱动、非理想二极管、电感 DCR、电容 ESR。
"""

from __future__ import annotations

import numpy as np

from circuits.nonideal_config import load_nonideal_buck_config
from scripts.nonideal_common import (
    NONIDEAL_RESULTS_ROOT,
    run_case_with_retries,
    save_case,
)
from storage.result_store import ResultStore
from visualization.plots import plot_bar_groups, plot_nonideal_switching, plot_time_series


def main() -> int:
    config = load_nonideal_buck_config()
    case = run_case_with_retries(config, "E")

    store = ResultStore(root=NONIDEAL_RESULTS_ROOT)
    run_id, run_dir = store.create_run_dir()

    frame = case.frame
    start = case.steady.start_time_s
    end = min(start + 2.0 * config.period_s, case.steady.end_time_s)
    mask = (frame["time_s"] >= start) & (frame["time_s"] <= end)
    window = frame.loc[mask]

    switching_figure = plot_nonideal_switching(
        window["time_s"].to_numpy(dtype=float),
        window["mosfet_vds_v"].to_numpy(dtype=float),
        window["mosfet_drain_terminal_current_a"].to_numpy(dtype=float),
        window["mosfet_vgs_v"].to_numpy(dtype=float),
        window["inductor_current_a"].to_numpy(dtype=float),
        run_dir / "nonideal_switching.png",
        title="Nonideal Buck Switching Waveforms (Model E, 2 cycles)",
    )
    startup_voltage = plot_time_series(
        frame["time_s"].to_numpy(dtype=float) * 1e3,
        {"Vout (V)": frame["vout_v"].to_numpy(dtype=float)},
        run_dir / "nonideal_output_voltage.png",
        title="Nonideal Buck Output Voltage (full transient)",
        y_label="Output voltage (V)",
        x_label="Time (ms)",
    )
    startup_current = plot_time_series(
        frame["time_s"].to_numpy(dtype=float) * 1e3,
        {"IL (A)": frame["inductor_current_a"].to_numpy(dtype=float)},
        run_dir / "nonideal_inductor_current.png",
        title="Nonideal Buck Inductor Current (full transient)",
        y_label="Inductor current (A)",
        x_label="Time (ms)",
    )
    loss_figure = plot_bar_groups(
        ["MOSFET", "Diode", "DCR", "ESR", "RG", "RGS"],
        {
            "Loss (mW)": np.asarray(
                [
                    case.accounting.mosfet_network_average_power_w,
                    case.accounting.diode_average_power_w,
                    case.accounting.dcr_loss_w,
                    case.accounting.esr_loss_w,
                    case.accounting.gate_resistor_loss_w,
                    case.accounting.pulldown_loss_w,
                ],
                dtype=float,
            )
            * 1e3
        },
        run_dir / "nonideal_loss_breakdown.png",
        title="Nonideal Buck Loss Breakdown (steady-state window)",
        y_label="Average loss (mW)",
    )

    save_case(
        case,
        store,
        run_dir,
        figures={
            "nonideal_switching.png": switching_figure,
            "nonideal_output_voltage.png": startup_voltage,
            "nonideal_inductor_current.png": startup_current,
            "nonideal_loss_breakdown.png": loss_figure,
        },
    )

    accounting = case.accounting
    print(f"[Model E] run={run_id}")
    print(
        f"  Vout={case.summary.output_voltage_mean_v:.6f} V, "
        f"ripple={case.summary.output_voltage_ripple_v * 1e3:.4f} mVpp, "
        f"IL={case.summary.inductor_current_mean_a:.6f} A"
    )
    print(
        f"  Pin={accounting.input_average_power_w:.6f} W, "
        f"Pdrv={accounting.driver_average_power_w:.6f} W, "
        f"Pout={accounting.output_average_power_w:.6f} W"
    )
    print(
        f"  eta_stage={accounting.efficiency_power_stage_percent:.4f}%, "
        f"eta_system={accounting.efficiency_system_percent:.4f}%"
    )
    print(
        f"  total_loss={accounting.total_loss_w:.6f} W, "
        f"residual={accounting.residual_w:.3e} W "
        f"(ratio {case.energy.residual_ratio:.3e}, {case.energy.status})"
    )
    print(
        f"  stress: VDS_max={case.stress.mosfet_vds_max_v:.4f} V, "
        f"ID_peak={case.stress.drain_current_peak_a:.4f} A "
        f"(p99.9 {case.stress.drain_current_p999_a:.4f} A), "
        f"VGS_max={case.stress.gate_source_voltage_max_v:.4f} V"
    )
    print(
        f"  switching: {len(case.switching.turn_on_intervals_s)} turn-on, "
        f"{len(case.switching.turn_off_intervals_s)} turn-off, "
        f"E_total={case.switching.total_energy_j:.3e} J"
    )
    print(f"  checks passed: {case.checks['passed']}")
    return 0 if case.checks["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
