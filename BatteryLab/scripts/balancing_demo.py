"""第五阶段实验 4：被动均衡电流、功耗、温升与 3S 不一致性收敛。

前半段用真实 ngspice 求均衡支路电流与电阻功耗；后半段在冻结 ECM 上做 12 小时
库仑积分，验证电压差是否真的收敛，并给出均衡耗时与理想耗时对比。

运行：conda run -n kaifa_battery python -m scripts.balancing_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from battery_models.ocv_model import load_ocv_reference
from battery_models.parameters import load_ecm_models
from circuits.balancing_circuit import run_balancing_spice
from circuits.spice_utils import get_solve_count, reset_solve_counter
from protection.balancing import balance_branch_current, simulate_passive_balancing
from scripts.stage5_common import (
    cell_soc_for_voltage,
    check_at_least,
    check_at_most,
    check_within,
    make_pack,
    stage5_limits,
    summarize_checks,
)
from storage.result_store import RunDirectory, write_json
from visualization.plots import plot_xy


def run(root: Path | None = None) -> dict:
    reset_solve_counter()
    limits = stage5_limits()
    run_dir = RunDirectory("protection", root=root)
    run_dir.write_metadata(
        {
            "stage": "stage5",
            "experiment": "passive_balancing",
            "note": "均衡电阻为热耗散元件；本实验不评估热仿真，只做一阶温升估算",
        }
    )

    target_voltages = (4.05, 4.12, 4.18)
    spice = run_balancing_spice(limits, target_voltages, (False, False, True))
    run_dir.write_waveform(
        [
            "cell_id",
            "enabled",
            "cell_voltage_v",
            "branch_current_a",
            "resistor_power_w",
            "mosfet_power_w",
            "resistor_temperature_c",
        ],
        [
            (
                channel.cell_id,
                channel.enabled,
                channel.cell_voltage_v,
                channel.branch_current_a,
                channel.resistor_power_w,
                channel.mosfet_power_w,
                channel.resistor_temperature_c,
            )
            for channel in spice.channels
        ],
        name="balancing_spice_channels.csv",
    )

    definition = load_ecm_models()["first_order_rc"]
    ocv = load_ocv_reference()
    socs = [cell_soc_for_voltage(voltage, definition, ocv) for voltage in target_voltages]
    pack = make_pack(socs)
    long_run = simulate_passive_balancing(
        pack.cells,
        limits,
        duration_s=12.0 * 3600.0,
        step_s=limits.balance_step_s,
        permitted=True,
    )
    run_dir.write_waveform(
        ["time_s", "max_cell_voltage_v", "min_cell_voltage_v", "delta_cell_voltage_v", "pack_voltage_v"],
        [
            (time, maximum, minimum, delta, pack_voltage)
            for time, maximum, minimum, delta, pack_voltage in zip(
                long_run.time_s,
                long_run.max_cell_voltage_v,
                long_run.min_cell_voltage_v,
                long_run.delta_cell_voltage_v,
                long_run.pack_voltage_v,
            )
        ],
        name="balancing_long_run.csv",
    )
    write_json(
        run_dir.path / "balancing_long_run.json",
        {
            "initial_soc": dict(zip([cell.cell_id for cell in pack.cells], socs)),
            "summary": long_run.summary(),
            "energy_wh": long_run.energy_dissipated_wh,
        },
    )
    plot_xy(
        long_run.time_s,
        long_run.delta_cell_voltage_v,
        path=run_dir.path / "plots" / "balancing_delta_voltage.png",
        xlabel="时间 / s",
        ylabel="最大电压差 / V",
        title="被动均衡：3S 电芯电压差收敛",
        annotation=f"初始 {long_run.initial_delta_v:.4f} V → 最终 {long_run.final_delta_v:.4f} V",
    )
    plot_xy(
        [time / 3600.0 for time in long_run.time_s],
        long_run.cell_soc["cell3"],
        path=run_dir.path / "plots" / "balancing_cell3_soc.png",
        xlabel="时间 / h",
        ylabel="cell3 SOC",
        title="被均衡单体 SOC 变化",
    )

    analytic_current = balance_branch_current(
        target_voltages[2], limits.balance_resistor_ohm, limits.balance_mosfet_rds_on_ohm
    )
    measured_current = spice.channels[2].branch_current_a
    peak_power = max(
        channel.resistor_power_w + channel.mosfet_power_w for channel in spice.channels
    )
    peak_temperature = max(channel.resistor_temperature_c for channel in spice.channels)

    # 理想耗时：把所有高于最低单体的电芯都放电到"最低单体 OCV + stop_delta"，
    # 所需总电荷除以平均均衡电流。
    low_ocv = float(ocv.voltage(socs[0]))
    target_voltage = low_ocv + limits.balance_stop_delta_v
    target_soc = cell_soc_for_voltage(target_voltage, definition, ocv)
    charge_to_remove_ah = sum(
        max(soc - target_soc, 0.0) for soc in socs
    ) * definition.parameters.capacity_ah
    final_current = balance_branch_current(
        target_voltage, limits.balance_resistor_ohm, limits.balance_mosfet_rds_on_ohm
    )
    average_current = 0.5 * (analytic_current + final_current)
    ideal_time_s = charge_to_remove_ah * 3600.0 / average_current
    measured_stop = long_run.time_to_stop_s or 12.0 * 3600.0
    time_error = abs(measured_stop - ideal_time_s) / ideal_time_s

    verdicts = [
        check_within(
            "均衡电流相对误差（SPICE vs 解析）",
            (measured_current - analytic_current) / analytic_current,
            0.02,
            "-",
        ),
        check_at_most("单支路峰值功耗", peak_power, 0.25, "W"),
        check_at_most(
            "均衡电阻温升估算",
            peak_temperature - limits.balance_ambient_temperature_c,
            45.0,
            "℃",
        ),
        check_at_least(
            "电压差收敛比例",
            long_run.delta_reduction_fraction,
            0.80,
            "-",
            "12 小时静置均衡",
        ),
        check_at_most("均衡耗时相对理想值偏差", time_error, 0.25, "-"),
        check_at_most(
            "均衡结束时残余电压差",
            long_run.final_delta_v,
            limits.balance_stop_delta_v + 0.02,
            "V",
        ),
    ]

    summary = {
        "run_id": run_dir.run_id,
        "real_spice_solves": get_solve_count(),
        "target_cell_voltages_v": list(target_voltages),
        "initial_soc": socs,
        "spice": {
            "analytic_current_a": analytic_current,
            "measured_current_a": measured_current,
            "peak_power_w": peak_power,
            "peak_resistor_temperature_c": peak_temperature,
            "channels": spice.to_dict(),
        },
        "long_run": long_run.summary(),
        "ideal": {
            "charge_to_remove_ah": charge_to_remove_ah,
            "average_current_a": average_current,
            "ideal_time_s": ideal_time_s,
            "measured_stop_s": long_run.time_to_stop_s,
            "relative_error": time_error,
        },
        "verdict": summarize_checks(verdicts),
    }
    run_dir.write_summary(summary)
    run_dir.flush_log()
    return {"run_id": run_dir.run_id, "summary": summary, "checks": verdicts, "path": str(run_dir.path)}


def main() -> int:
    result = run()
    verdict = result["summary"]["verdict"]
    print(f"run_id={result['run_id']}")
    for check in verdict["checks"]:
        print(f"{check['status']:4s} {check['name']:34s} measured={check['measured']} limit={check['limit']}")
    print(f"total PASS={verdict['passed']} FAIL={verdict['failed']}")
    return 0 if verdict["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
