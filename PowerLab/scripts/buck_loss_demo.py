"""第四阶段：非理想 Buck 损耗分解与能量平衡（全部来自真实波形）。

MOSFET 网络损耗 = 漏极端口 ``<VDS*ID>`` + 栅极端口 ``<VGS*IG>``；
导通估算用器件特性扫描得到的 RDS(on)，只用于拆分，不改动真实损耗。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.device_characteristics import rds_on_at_current
from analysis.loss_analysis import component_loss_fractions, loss_summary_table
from circuits.nonideal_config import load_device_models, load_nonideal_buck_config
from simulations.device_runner import run_mosfet_output
from scripts.nonideal_common import (
    NONIDEAL_RESULTS_ROOT,
    run_case_with_retries,
    save_case,
)
from storage.result_store import ResultStore
from visualization.plots import plot_bar_groups


def main() -> int:
    config = load_nonideal_buck_config()
    models = load_device_models()
    tests = models["mosfet_tests"]

    output_result = run_mosfet_output(
        models["mosfet"],
        vgs_v=float(tests["rds_point"]["vgs_v"]),
        vds_start_v=float(tests["output"]["vds_start_v"]),
        vds_stop_v=float(tests["output"]["vds_stop_v"]),
        vds_step_v=float(tests["output"]["vds_step_v"]),
        temperature_c=25.0,
    )
    rds = rds_on_at_current(output_result, float(tests["rds_point"]["target_current_a"]))
    rds_on = rds["rds_on_ohm"]
    print(
        f"[rds_on] target {rds['target_current_a']:.3f} A -> {rds_on} ohm "
        f"({rds['status']})"
    )

    case = run_case_with_retries(config, "E", rds_on_ohm=rds_on)
    accounting = case.accounting

    loss_table = pd.DataFrame(loss_summary_table(accounting))
    fractions = component_loss_fractions(accounting)
    loss_table["share_of_total"] = loss_table["item"].map(fractions).fillna(
        loss_table["power_w"] / accounting.total_loss_w
        if accounting.total_loss_w > 0
        else np.nan
    )

    balance = case.energy
    energy_table = pd.DataFrame(
        [
            {"item": "input", "power_w": accounting.input_average_power_w},
            {"item": "driver", "power_w": accounting.driver_average_power_w},
            {"item": "output", "power_w": -accounting.output_average_power_w},
            {"item": "mosfet_network", "power_w": -accounting.mosfet_network_average_power_w},
            {"item": "diode", "power_w": -accounting.diode_average_power_w},
            {"item": "inductor_dcr", "power_w": -accounting.dcr_loss_w},
            {"item": "capacitor_esr", "power_w": -accounting.esr_loss_w},
            {"item": "gate_resistor", "power_w": -accounting.gate_resistor_loss_w},
            {"item": "gate_pulldown", "power_w": -accounting.pulldown_loss_w},
            {"item": "residual", "power_w": accounting.residual_w},
        ]
    )

    switching_power = case.switching.total_energy_j / accounting.duration_s
    print(f"[Model E] steady window {accounting.duration_s * 1e3:.4f} ms")
    print(
        f"  Pin={accounting.input_average_power_w:.6f} W "
        f"Pdrv={accounting.driver_average_power_w:.6f} W "
        f"Pout={accounting.output_average_power_w:.6f} W"
    )
    for row in loss_table.to_dict("records"):
        print(f"  {row['item']:<16} {row['power_w'] * 1e3:10.4f} mW")
    print(
        f"  total {accounting.total_loss_w * 1e3:.4f} mW; "
        f"residual {accounting.residual_w:.3e} W "
        f"({case.energy.residual_ratio:.3e}, {case.energy.status})"
    )
    print(
        f"  conduction estimate (RDS={rds_on:.6f} ohm): "
        f"{case.conduction_estimate_w:.6f} W; "
        f"switching interval power: {switching_power:.6f} W"
    )

    store = ResultStore(root=NONIDEAL_RESULTS_ROOT)
    run_id, run_dir = store.create_run_dir()
    figure = plot_bar_groups(
        loss_table["item"].tolist(),
        {"Average power (mW)": loss_table["power_w"].to_numpy() * 1e3},
        run_dir / "buck_loss_breakdown.png",
        title="Nonideal Buck Loss Breakdown (real transient, Model E)",
        y_label="Average power (mW)",
        log_scale=False,
    )
    save_case(
        case,
        store,
        run_dir,
        figures={"buck_loss_breakdown.png": figure},
        extra_tables={
            "loss_table.csv": loss_table,
            "energy_table.csv": energy_table,
        },
    )
    print(f"  saved: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
