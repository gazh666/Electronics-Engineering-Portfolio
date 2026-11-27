"""容量型 SOH 演示（Task 23 / Task 24 / Task 25 / Task 26 / Task 40）。"""

from __future__ import annotations

from analysis.health_metrics import data_quality_summary
from experiments.soh_experiment import run_soh_experiment
from scripts.stage7_common import (
    finish,
    open_run,
    plot_series,
    write_metadata,
    write_payload,
    write_rows,
)


def main() -> None:
    run = open_run("battery_health")
    experiment = run_soh_experiment()
    synthetic = experiment["synthetic"]
    table = synthetic["cycle_table"]
    real = experiment["real_aging"]

    write_metadata(
        run,
        script="capacity_soh_demo",
        description="容量型 SOH：真实一次完整放电一致性检查 + 合成老化循环管线验证",
        extra={
            "real_aging_status": real["status"],
            "synthetic_source_type": "synthetic_truth",
        },
    )
    write_payload(run, "aging_data_manifest.json", experiment["manifest"])
    write_rows(
        run,
        "cycle_capacity.csv",
        table,
        header=[
            "cell_id",
            "cycle_index",
            "discharge_capacity_ah",
            "reference_capacity_ah",
            "capacity_soh_percent",
            "capacity_loss_percent",
            "temperature_c",
            "cutoff_voltage_v",
            "recorded_capacity_ah",
            "integrated_capacity_ah",
            "integrated_minus_recorded_ah",
            "integrated_minus_recorded_percent",
            "data_quality_status",
        ],
    )
    write_rows(
        run,
        "capacity_soh.csv",
        [
            {
                "cell_id": row["cell_id"],
                "cycle_index": row["cycle_index"],
                "capacity_soh_percent": row["capacity_soh_percent"],
                "capacity_loss_percent": row["capacity_loss_percent"],
                "data_quality_status": row["data_quality_status"],
            }
            for row in table
        ],
        header=["cell_id", "cycle_index", "capacity_soh_percent", "capacity_loss_percent", "data_quality_status"],
    )
    write_rows(
        run,
        "real_capacity_consistency.csv",
        [real["cycle_row"]],
        header=[
            "cell_id",
            "cycle_index",
            "discharge_capacity_ah",
            "reference_capacity_ah",
            "capacity_soh_percent",
            "capacity_loss_percent",
            "temperature_c",
            "cutoff_voltage_v",
            "recorded_capacity_ah",
            "integrated_capacity_ah",
            "integrated_minus_recorded_ah",
            "integrated_minus_recorded_percent",
            "data_quality_status",
        ],
    )
    write_payload(
        run,
        "data_quality.json",
        {
            "cycle_status_counts": data_quality_summary([row["data_quality_status"] for row in table]),
            "real_aging_status": real["status"],
            "real_aging_reason": real["reason"],
            "real_cycles": real["available_complete_cycles"],
            "synthetic_analytic_status": synthetic["analytic_status"],
            "synthetic_analytic_error_ah": synthetic["analytic_error_ah"],
            "capacity_update": synthetic["capacity_update"],
        },
    )
    write_payload(run, "capacity_soh_summary.json", {
        "real": real,
        "synthetic_summary": synthetic["summary"],
        "synthetic_analytic_status": synthetic["analytic_status"],
    })

    cycles = [row["cycle_index"] for row in table]
    plot_series(
        run,
        "17_capacity_vs_cycle.png",
        {"discharge capacity (synthetic aging)": (cycles, [row["discharge_capacity_ah"] for row in table])},
        title=f"Discharge capacity vs cycle — synthetic aging (run {run.run_id})",
        xlabel="cycle index",
        ylabel="capacity (Ah)",
        horizontal=[(2.0 * 0.8, "80% reference line (teaching only)")],
    )
    plot_series(
        run,
        "18_capacity_soh_curve.png",
        {"capacity SOH (synthetic aging)": (cycles, [row["capacity_soh_percent"] for row in table])},
        title=f"Capacity-based SOH — synthetic aging (run {run.run_id})",
        xlabel="cycle index",
        ylabel="SOH (%)",
        horizontal=[(80.0, "80% reference line (teaching only)")],
    )
    finish(run, "capacity soh demo done")
    print(
        f"[capacity_soh_demo] run={run.run_id} real_status={real['status']} "
        f"real_integrated={real['consistency']['integrated_capacity_ah']:.6f} Ah "
        f"recorded_diff={real['consistency']['difference_percent']:.5f} % "
        f"consistency={real['consistency']['consistency_status']}"
    )
    print(
        f"  synthetic: analytic={synthetic['analytic_status']} final_SOH={synthetic['summary']['final_soh_percent']:.3f}% "
        f"update {synthetic['capacity_update']['active_before_session']:.3f}->{synthetic['capacity_update']['active_after_session']:.3f} Ah"
    )


if __name__ == "__main__":
    main()
