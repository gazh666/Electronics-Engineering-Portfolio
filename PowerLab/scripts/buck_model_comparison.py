"""第四阶段：五模型（A-E）真实瞬态对照。

A：第三阶段 SW + 理想 L/C 基线（直接复用第三阶段构建器）
B：+ 电感 DCR 与电容 ESR
C：+ 非理想续流二极管
D：NMOS + 浮动栅极驱动（无外部电容）
E：+ 外部 Cgs/Cgd/Cds
"""

from __future__ import annotations

import pandas as pd

from analysis.model_comparison import (
    compare_models,
    difference_notes,
    dominant_loss,
    loss_share_table,
    output_voltage_regulation,
)
from circuits.nonideal_config import load_nonideal_buck_config
from scripts.nonideal_common import (
    NONIDEAL_RESULTS_ROOT,
    run_case_with_retries,
    save_case,
)
from storage.result_store import ResultStore
from visualization.plots import plot_bar_groups

VARIANTS = ("A", "B", "C", "D", "E")


def main() -> int:
    config = load_nonideal_buck_config()
    store = ResultStore(root=NONIDEAL_RESULTS_ROOT)

    cases = []
    for variant in VARIANTS:
        case = run_case_with_retries(config, variant)
        run_id, run_dir = store.create_run_dir()
        cases.append((variant, case, run_id, run_dir))
        print(
            f"[{variant}] run={run_id} Vout={case.summary.output_voltage_mean_v:.6f} V "
            f"eta={case.accounting.efficiency_power_stage_percent:.4f}% "
            f"P_loss={case.accounting.total_loss_w * 1e3:.4f} mW "
            f"response={case.energy.status}"
        )

    summaries = [case.summary for _, case, _, _ in cases]
    comparison = compare_models(summaries, reference="A")
    shares = loss_share_table(summaries)
    notes = difference_notes(summaries)

    print("[comparison vs Model A]")
    for _, case, _, _ in cases:
        summary = case.summary
        regulation = output_voltage_regulation(summary, config.target_output_voltage_v)
        print(
            f"  {summary.variant}: dVout={regulation['absolute_error_v'] * 1e3:+.3f} mV, "
            f"dominant loss={dominant_loss(summary)}, "
            f"checks={case.checks['passed']}"
        )
    for note in notes:
        print(f"  note: {note}")

    labels = [variant for variant, _, _, _ in cases]
    figure_dir = NONIDEAL_RESULTS_ROOT / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    loss_figure = plot_bar_groups(
        labels,
        {"Total loss (mW)": comparison["total_loss_w"].to_numpy() * 1e3},
        figure_dir / "model_comparison_loss.png",
        title="Total Loss by Model Variant",
        y_label="Total loss (mW)",
    )
    efficiency_figure = plot_bar_groups(
        labels,
        {"Power-stage efficiency (%)": comparison["efficiency_power_stage_percent"].to_numpy()},
        figure_dir / "model_comparison_efficiency.png",
        title="Power-stage Efficiency by Model Variant",
        y_label="Efficiency (%)",
    )
    voltage_figure = plot_bar_groups(
        labels,
        {"Vout (V)": comparison["output_voltage_mean_v"].to_numpy()},
        figure_dir / "model_comparison_output.png",
        title="Mean Output Voltage by Model Variant (target 5 V, not forced)",
        y_label="Output voltage (V)",
    )
    loss_stack_figure = plot_bar_groups(
        labels,
        {
            "MOSFET (mW)": comparison["mosfet_loss_w"].to_numpy() * 1e3,
            "Diode (mW)": comparison["diode_loss_w"].to_numpy() * 1e3,
            "DCR (mW)": comparison["dcr_loss_w"].to_numpy() * 1e3,
            "ESR (mW)": comparison["esr_loss_w"].to_numpy() * 1e3,
            "Gate (mW)": comparison["gate_loss_w"].to_numpy() * 1e3,
        },
        figure_dir / "model_comparison_loss_components.png",
        title="Loss Components by Model Variant",
        y_label="Average loss (mW)",
    )

    for variant, case, run_id, run_dir in cases[:-1]:
        save_case(case, store, run_dir)
    last_variant, last_case, last_run_id, last_dir = cases[-1]
    save_case(
        last_case,
        store,
        last_dir,
        figures={
            "model_comparison_loss.png": loss_figure,
            "model_comparison_efficiency.png": efficiency_figure,
            "model_comparison_output.png": voltage_figure,
            "model_comparison_loss_components.png": loss_stack_figure,
        },
        extra_tables={
            "model_comparison.csv": comparison,
            "model_loss_share.csv": shares,
        },
        extra_json={"difference_notes.json": notes},
    )
    print(f"comparison saved: {last_dir / 'model_comparison.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
