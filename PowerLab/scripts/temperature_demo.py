"""第四阶段：固定器件温度对照（25 / 50 / 75 °C）。

温度为求解器设定的固定结温，不是自热仿真：没有热阻网络、
没有损耗到温度的反馈，也不代表真实散热条件。
"""

from __future__ import annotations

import pandas as pd

from circuits.nonideal_config import load_nonideal_buck_config, temperature_values
from scripts.nonideal_common import (
    NONIDEAL_RESULTS_ROOT,
    run_case_with_retries,
    save_case,
)
from storage.result_store import ResultStore
from visualization.plots import plot_temperature_trend


def main() -> int:
    config = load_nonideal_buck_config()
    temperatures = temperature_values()
    store = ResultStore(root=NONIDEAL_RESULTS_ROOT)

    rows: list[dict[str, object]] = []
    cases = []
    for temperature in temperatures:
        case = run_case_with_retries(config, "E", temperature_c=temperature)
        run_id, run_dir = store.create_run_dir()
        cases.append((float(temperature), case, run_id, run_dir))
        accounting = case.accounting
        rows.append(
            {
                "temperature_c": float(temperature),
                "output_voltage_v": case.summary.output_voltage_mean_v,
                "output_ripple_mv": case.summary.output_voltage_ripple_v * 1e3,
                "efficiency_power_stage_percent": accounting.efficiency_power_stage_percent,
                "mosfet_loss_mw": accounting.mosfet_network_average_power_w * 1e3,
                "diode_loss_mw": accounting.diode_average_power_w * 1e3,
                "dcr_loss_mw": accounting.dcr_loss_w * 1e3,
                "total_loss_mw": accounting.total_loss_w * 1e3,
                "residual_w": accounting.residual_w,
                "run_id": run_id,
            }
        )
        print(
            f"[{temperature:g} C] run={run_id} "
            f"Vout={rows[-1]['output_voltage_v']:.6f} V "
            f"eta={rows[-1]['efficiency_power_stage_percent']:.4f}% "
            f"P_mosfet={rows[-1]['mosfet_loss_mw']:.4f} mW "
            f"P_diode={rows[-1]['diode_loss_mw']:.4f} mW"
        )

    frame = pd.DataFrame(rows)
    figure_dir = NONIDEAL_RESULTS_ROOT / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    efficiency_figure = plot_temperature_trend(
        frame["temperature_c"].to_numpy(),
        {"Efficiency (%)": frame["efficiency_power_stage_percent"].to_numpy()},
        figure_dir / "temperature_efficiency.png",
        title="Power-stage Efficiency vs Fixed Device Temperature",
        y_label="Efficiency (%)",
    )
    loss_figure = plot_temperature_trend(
        frame["temperature_c"].to_numpy(),
        {
            "MOSFET loss (mW)": frame["mosfet_loss_mw"].to_numpy(),
            "Diode loss (mW)": frame["diode_loss_mw"].to_numpy(),
            "DCR loss (mW)": frame["dcr_loss_mw"].to_numpy(),
        },
        figure_dir / "temperature_losses.png",
        title="Loss Components vs Fixed Device Temperature",
        y_label="Average loss (mW)",
    )

    for temperature, case, run_id, run_dir in cases[:-1]:
        save_case(case, store, run_dir)
    last_temperature, last_case, last_run_id, last_dir = cases[-1]
    save_case(
        last_case,
        store,
        last_dir,
        figures={
            "temperature_efficiency.png": efficiency_figure,
            "temperature_losses.png": loss_figure,
        },
        extra_tables={"temperature_summary.csv": frame},
    )
    print(f"summary saved: {last_dir / 'temperature_summary.csv'}")
    print(
        "note: fixed solver temperature only; Level 1 MOSFET has no temperature "
        "parameters, so its parameters are temperature-independent in this model. "
        "No self-heating, no thermal resistance network."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
