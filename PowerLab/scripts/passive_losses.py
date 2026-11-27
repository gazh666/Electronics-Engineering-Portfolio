"""第四阶段：电感 DCR 与电容 ESR 的真实损耗增量。

在同一非理想 Buck（Model E）上依次关闭/开启 DCR 与 ESR，
用真实瞬态数据比较输出、效率与损耗增量。三种组合不是产品规格。
"""

from __future__ import annotations

import pandas as pd

from circuits.nonideal_config import load_nonideal_buck_config
from scripts.nonideal_common import (
    NONIDEAL_RESULTS_ROOT,
    run_case_with_retries,
    save_case,
)
from storage.result_store import ResultStore, write_dataframe
from visualization.plots import plot_bar_groups


def main() -> int:
    base = load_nonideal_buck_config()
    combinations = (
        ("ideal L/C", base.with_dcr(0.0).with_esr(0.0)),
        ("DCR only", base.with_dcr(base.inductor.dcr_ohm).with_esr(0.0)),
        (
            "DCR + ESR",
            base.with_dcr(base.inductor.dcr_ohm).with_esr(base.capacitor.esr_ohm),
        ),
    )

    store = ResultStore(root=NONIDEAL_RESULTS_ROOT)
    rows: list[dict[str, object]] = []
    cases = []
    run_dirs = []
    for label, config in combinations:
        case = run_case_with_retries(config, "E")
        run_id, run_dir = store.create_run_dir()
        cases.append((label, case, run_id, run_dir))
        run_dirs.append((label, run_dir))
        accounting = case.accounting
        rows.append(
            {
                "combination": label,
                "dcr_ohm": config.inductor.dcr_ohm,
                "esr_ohm": config.capacitor.esr_ohm,
                "output_voltage_v": case.summary.output_voltage_mean_v,
                "output_ripple_mv": case.summary.output_voltage_ripple_v * 1e3,
                "efficiency_power_stage_percent": accounting.efficiency_power_stage_percent,
                "dcr_loss_w": accounting.dcr_loss_w,
                "esr_loss_w": accounting.esr_loss_w,
                "total_loss_w": accounting.total_loss_w,
                "run_id": run_id,
            }
        )
        print(
            f"[{label}] run={run_id} Vout={rows[-1]['output_voltage_v']:.6f} V "
            f"eta={rows[-1]['efficiency_power_stage_percent']:.4f}% "
            f"P_DCR={accounting.dcr_loss_w * 1e3:.3f} mW "
            f"P_ESR={accounting.esr_loss_w * 1e3:.3f} mW"
        )

    frame = pd.DataFrame(rows)
    labels = [item[0] for item in run_dirs]
    final_label, final_case, final_run_id, final_dir = cases[-1]
    loss_figure = plot_bar_groups(
        labels,
        {
            "DCR loss (mW)": frame["dcr_loss_w"].to_numpy() * 1e3,
            "ESR loss (mW)": frame["esr_loss_w"].to_numpy() * 1e3,
        },
        final_dir / "passive_losses.png",
        title="Inductor DCR and Capacitor ESR Loss (real transient)",
        y_label="Average loss (mW)",
    )
    efficiency_figure = plot_bar_groups(
        labels,
        {"Efficiency (%)": frame["efficiency_power_stage_percent"].to_numpy()},
        final_dir / "passive_loss_efficiency.png",
        title="Power-stage Efficiency with Passive Parasitics",
        y_label="Efficiency (%)",
    )

    for label, case, run_id, run_dir in cases[:-1]:
        save_case(case, store, run_dir)
    save_case(
        final_case,
        store,
        final_dir,
        figures={
            "passive_losses.png": loss_figure,
            "passive_loss_efficiency.png": efficiency_figure,
        },
        extra_tables={"passive_loss_summary.csv": frame},
    )
    print(f"summary saved: {final_dir / 'passive_loss_summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
