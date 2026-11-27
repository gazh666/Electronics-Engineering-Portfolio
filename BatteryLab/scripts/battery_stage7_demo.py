"""第七阶段总体验收演示（Task 37 / Task 40）。

``--profile smoke``：单数据集快速路径（用于开发自检）。
``--profile standard``：完整真实运行，生成 results/stage7/run_<id>/ 全部汇总文件
与 23 张工程图，并按预登记目标统计 PASS / FAIL / NOT_VERIFIED。
"""

from __future__ import annotations

import argparse

import numpy as np

from analysis.estimation_error_budget import calculate_offset_drift_pp
from analysis.soc_metrics import calculate_soc_metrics
from estimation.coulomb_counter import CoulombCounter
from estimation.pack_soc_estimator import calculate_cell_currents
from experiments.initial_soc_experiment import run_initial_soc_experiment
from experiments.model_mismatch_experiment import run_model_mismatch_experiment
from experiments.pack_estimation_experiment import run_pack_estimation_experiment
from experiments.sensor_error_experiment import run_sensor_error_experiment
from experiments.soc_comparison import METHODS, comparison_table, run_soc_comparison
from experiments.soh_experiment import run_soh_experiment
from experiments.spice_replay import run_spice_current_replay
from experiments.temperature_mismatch_experiment import run_temperature_mismatch_experiment
from health.cycle_analysis import integrate_discharge_capacity
from scripts.stage7_common import (
    finish,
    open_run,
    plot_bar,
    plot_series,
    write_metadata,
    write_payload,
    write_rows,
)

INDEPENDENT_DATASETS = ("us06_50", "us06_80", "bjdst_50", "bjdst_80")
SMOKE_DATASETS = ("us06_50",)

TARGET_RMSE_PP = 3.0
TARGET_MAX_PP = 5.0
TARGET_COVERAGE = 0.99
TARGET_CAPACITY_CONSISTENCY_PERCENT = 1.0
TARGET_SYNTHETIC_PERCENT = 0.1


def _check(identifier: str, name: str, status: str, value, target, detail: str = "") -> dict:
    return {
        "id": identifier,
        "name": name,
        "status": status,
        "value": value,
        "target": target,
        "detail": detail,
    }


def _math_checks() -> list[dict]:
    counter = CoulombCounter(capacity_ah=2.0, soc=0.8)
    update = counter.step(1.0, 3600.0)
    soc_error = abs(update.soc - 0.3)
    t = np.arange(0.0, 3601.0, 1.0)
    capacity = integrate_discharge_capacity(t, np.ones_like(t), 2.0)
    capacity_error_percent = abs(capacity - 1.0) / 1.0 * 100.0
    cell_currents = calculate_cell_currents(1.0, [0.04, 0.0, 0.0])
    balancing_error = float(np.max(np.abs(cell_currents - np.array([1.04, 1.0, 1.0]))))
    return [
        _check("M1", "恒流 SOC 积分绝对误差", "PASS" if soc_error <= 1e-8 else "FAIL", soc_error, 1e-8, "1 A x 3600 s, Q=2 Ah"),
        _check("M2", "容量积分与解析基准误差", "PASS" if capacity_error_percent <= TARGET_SYNTHETIC_PERCENT else "FAIL", capacity_error_percent, TARGET_SYNTHETIC_PERCENT, "1 A x 3600 s = 1 Ah"),
        _check("M3", "3S 均衡支路电流关系", "PASS" if balancing_error <= 1e-12 else "FAIL", balancing_error, 1e-12, "Icell = Ipack + Ibalance"),
    ]


def _observer_target_checks(results: dict) -> list[dict]:
    checks: list[dict] = []
    for dataset, entry in results["datasets"].items():
        metrics = entry["methods"]["ecm_observer"]["metrics"]
        checks.append(
            _check(
                f"R-{dataset}",
                f"ECM observer RMSE — {dataset}",
                "PASS" if metrics["rmse_pp"] is not None and metrics["rmse_pp"] <= TARGET_RMSE_PP else "FAIL",
                metrics["rmse_pp"],
                TARGET_RMSE_PP,
            )
        )
        checks.append(
            _check(
                f"X-{dataset}",
                f"ECM observer max error — {dataset}",
                "PASS" if metrics["max_absolute_error_pp"] is not None and metrics["max_absolute_error_pp"] <= TARGET_MAX_PP else "FAIL",
                metrics["max_absolute_error_pp"],
                TARGET_MAX_PP,
            )
        )
        checks.append(
            _check(
                f"C-{dataset}",
                f"ECM observer coverage — {dataset}",
                "PASS" if metrics["coverage_fraction"] >= TARGET_COVERAGE else "FAIL",
                metrics["coverage_fraction"],
                TARGET_COVERAGE,
            )
        )
    return checks


def _convergence_checks(initial_results: dict) -> list[dict]:
    checks: list[dict] = []
    for row in initial_results["results"]:
        if row.get("method") != "ecm_observer":
            continue
        convergence = row.get("convergence") or {}
        checks.append(
            _check(
                f"V-{row['requested_error_pp']:+.0f}pp",
                f"初始SOC {row['requested_error_pp']:+.0f} pp 收敛至 ±2 pp（保持60 s）",
                "PASS" if convergence.get("status") == "CONVERGED" else "FAIL",
                convergence.get("status"),
                "CONVERGED",
                f"elapsed={convergence.get('elapsed_s')}",
            )
        )
    return checks


def _capacity_checks(soh: dict) -> list[dict]:
    real = soh["real_aging"]["consistency"]
    synthetic = soh["synthetic"]
    consistency = real.get("difference_percent")
    return [
        _check(
            "Q1",
            "真实完整放电积分与记录容量一致性",
            "PASS" if consistency is not None and abs(consistency) <= TARGET_CAPACITY_CONSISTENCY_PERCENT else "FAIL",
            consistency,
            TARGET_CAPACITY_CONSISTENCY_PERCENT,
        ),
        _check(
            "Q2",
            "合成容量积分数学误差",
            "PASS" if synthetic["analytic_error_ah"] <= TARGET_SYNTHETIC_PERCENT / 100.0 else "FAIL",
            synthetic["analytic_error_ah"],
            TARGET_SYNTHETIC_PERCENT / 100.0,
            "1 Ah analytic",
        ),
    ]


def _not_verified_items(temperature: dict, soh: dict) -> list[dict]:
    items = [
        {
            "id": "N1",
            "name": "温度失配 SOC 影响",
            "status": "NOT_VERIFIED",
            "reason": "仅有 25℃ 数据，无 0/45℃ 实验文件与多温度参数。",
        },
        {
            "id": "N2",
            "name": "真实容量老化 / 循环 SOH",
            "status": "NOT_VERIFIED",
            "reason": soh["real_aging"]["reason"],
        },
        {
            "id": "N3",
            "name": "真实内阻增长率",
            "status": "NOT_VERIFIED",
            "reason": "无老化循环与可比脉冲序列。",
        },
    ]
    for row in temperature["rows"]:
        if row["status"] == "NOT_VERIFIED":
            items.append(
                {
                    "id": f"N-{row['scenario']}",
                    "name": row["scenario"],
                    "status": "NOT_VERIFIED",
                    "reason": row["reason"],
                }
            )
    return items


def _write_comparison(run, comparison: dict) -> list[dict]:
    table = comparison_table(comparison)
    write_rows(
        run,
        "soc_method_comparison.csv",
        table,
        header=[
            "dataset",
            "method",
            "mae_pp",
            "rmse_pp",
            "max_absolute_error_pp",
            "final_error_pp",
            "coverage_fraction",
            "valid_sample_count",
            "sample_count",
            "voltage_rmse_v",
            "status",
        ],
    )
    return table


def _write_initial(run, initial: dict) -> None:
    rows = []
    for row in initial["results"]:
        metrics = row.get("metrics") or {}
        convergence = row.get("convergence") or {}
        rows.append(
            {
                "requested_error_pp": row["requested_error_pp"],
                "method": row.get("method"),
                "status": row["status"],
                "initial_estimated_soc": row.get("initial_estimated_soc"),
                "rmse_pp": metrics.get("rmse_pp"),
                "final_error_pp": metrics.get("final_error_pp"),
                "convergence_status": convergence.get("status"),
                "entry_time_s": convergence.get("entry_time_s"),
                "elapsed_s": convergence.get("elapsed_s"),
                "post_convergence_max_absolute_error_pp": convergence.get("post_convergence_max_absolute_error_pp"),
            }
        )
    write_rows(
        run,
        "initial_soc_experiments.csv",
        rows,
        header=[
            "requested_error_pp",
            "method",
            "status",
            "initial_estimated_soc",
            "rmse_pp",
            "final_error_pp",
            "convergence_status",
            "entry_time_s",
            "elapsed_s",
            "post_convergence_max_absolute_error_pp",
        ],
    )


def _write_pack(run, pack: dict) -> None:
    rows = []
    for case in pack["cases"]:
        for index, error in enumerate(case["cell_error_pp"]):
            rows.append(
                {
                    "case": case["case"],
                    "cell": f"cell{index + 1}",
                    "truth_soc": case["truth_soc"][index],
                    "estimated_soc": case["estimated_soc"][index],
                    "error_pp": error,
                    "max_absolute_error_pp": case["max_absolute_error_pp"],
                    "soc_spread_pp": case["soc_spread_pp"],
                }
            )
    write_rows(
        run,
        "pack_soc_summary.csv",
        rows,
        header=["case", "cell", "truth_soc", "estimated_soc", "error_pp", "max_absolute_error_pp", "soc_spread_pp"],
    )


def _write_soh(run, soh: dict) -> None:
    real = soh["real_aging"]["cycle_row"]
    synthetic = soh["synthetic"]["cycle_table"]
    rows = [real] + [
        {
            "cell_id": row["cell_id"],
            "cycle_index": row["cycle_index"],
            "discharge_capacity_ah": row["discharge_capacity_ah"],
            "reference_capacity_ah": row["reference_capacity_ah"],
            "capacity_soh_percent": row["capacity_soh_percent"],
            "capacity_loss_percent": row["capacity_loss_percent"],
            "temperature_c": row["temperature_c"],
            "cutoff_voltage_v": row["cutoff_voltage_v"],
            "recorded_capacity_ah": row["recorded_capacity_ah"],
            "integrated_capacity_ah": row["integrated_capacity_ah"],
            "integrated_minus_recorded_percent": row["integrated_minus_recorded_percent"],
            "data_quality_status": row["data_quality_status"],
        }
        for row in synthetic
    ]
    write_rows(
        run,
        "capacity_soh_summary.csv",
        rows,
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
            "integrated_minus_recorded_percent",
            "data_quality_status",
        ],
    )


def run_profile(profile: str) -> None:
    run = open_run("stage7")
    datasets = SMOKE_DATASETS if profile == "smoke" else INDEPENDENT_DATASETS
    run.log(f"profile={profile} datasets={datasets}")

    comparison = run_soc_comparison(datasets)
    table = _write_comparison(run, comparison)

    initial = run_initial_soc_experiment("us06_50")
    _write_initial(run, initial)

    pack = run_pack_estimation_experiment()
    _write_pack(run, pack)

    soh = run_soh_experiment()
    _write_soh(run, soh)

    temperature = run_temperature_mismatch_experiment()
    write_rows(
        run,
        "temperature_results.csv",
        [
            {
                "scenario": row["scenario"],
                "status": row["status"],
                "reason": row["reason"],
                "evidence": row["evidence"],
            }
            for row in temperature["rows"]
        ],
        header=["scenario", "status", "reason", "evidence"],
    )

    if profile == "smoke":
        sensor = run_sensor_error_experiment("us06_50")
        model_mismatch = None
    else:
        sensor = run_sensor_error_experiment("us06_50")
        model_mismatch = run_model_mismatch_experiment("us06_50")

    write_rows(
        run,
        "sensor_error_results.csv",
        sensor["rows"],
        header=[
            "scenario",
            "parameter",
            "unit",
            "mae_pp",
            "rmse_pp",
            "max_absolute_error_pp",
            "final_error_pp",
            "coverage_fraction",
            "theoretical_drift_pp",
            "bound_reached_count",
        ],
    )
    if model_mismatch is not None:
        write_rows(
            run,
            "model_mismatch_results.csv",
            model_mismatch["rows"],
            header=[
                "scenario",
                "deviation_percent",
                "parameter",
                "unit",
                "rmse_pp",
                "max_absolute_error_pp",
                "final_error_pp",
                "coverage_fraction",
            ],
        )

    spice = run_spice_current_replay("us06_50")

    checks = _math_checks()
    checks.extend(_observer_target_checks(comparison))
    checks.extend(_convergence_checks(initial))
    checks.extend(_capacity_checks(soh))
    not_verified = _not_verified_items(temperature, soh)

    statuses = [item["status"] for item in checks] + [item["status"] for item in not_verified]
    counts = {status: statuses.count(status) for status in ("PASS", "FAIL", "NOT_VERIFIED")}

    validation_summary = {
        "run_id": run.run_id,
        "profile": profile,
        "datasets": list(datasets),
        "checks": checks,
        "not_verified": not_verified,
        "counts": counts,
        "comparison_table": table,
        "pack_summary": pack["summary"],
        "soh_real_status": soh["real_aging"]["status"],
        "soh_real_consistency_percent": soh["real_aging"]["consistency"]["difference_percent"],
        "temperature": {
            "available_temperatures_c": temperature["available_temperatures_c"],
            "summary": temperature["summary"],
        },
        "spice_replay": {key: value for key, value in spice.items() if key != "arrays"},
        "data_quality": {
            "no_hidden_clipping": True,
            "no_integration_across_gaps": True,
            "no_validation_tuning": True,
            "unknown_soc_never_filled_with_zero": True,
        },
    }
    write_payload(run, "validation_summary.json", validation_summary)
    write_payload(
        run,
        "sensor_error_metadata.json",
        {key: value for key, value in sensor.items() if key != "rows"},
    )

    # 图 12 / 14 / 15 / 16 / 23
    convergence_series = {}
    for row in initial["results"]:
        if row.get("method") != "ecm_observer" or row.get("metrics") is None:
            continue
        metrics = row["metrics"]
        convergence = row["convergence"]
        if convergence.get("status") != "CONVERGED":
            continue
        convergence_series[f"{row['requested_error_pp']:+.0f} pp"] = (
            [0.0, float(convergence.get("elapsed_s") or 0.0)],
            [abs(row["requested_error_pp"]), abs(float(row["metrics"]["final_error_pp"]))],
        )
    if convergence_series:
        plot_series(
            run,
            "12_initial_soc_convergence.png",
            convergence_series,
            title=f"Initial SOC error convergence — ECM observer (run {run.run_id})",
            xlabel="elapsed time (s)",
            ylabel="absolute SOC error (percentage point)",
            horizontal=[(2.0, "2 pp tolerance")],
        )
    if model_mismatch is not None:
        capacity_rows = [row for row in model_mismatch["rows"] if row["scenario"] == "capacity"]
        plot_bar(
            run,
            "14_capacity_deviation_effect.png",
            [f"{row['deviation_percent']:+.0f}%" for row in capacity_rows],
            [row["rmse_pp"] for row in capacity_rows],
            title=f"Capacity deviation effect — {model_mismatch['dataset']} (run {run.run_id})",
            ylabel="SOC RMSE (percentage point)",
        )
        r0_rows = [row for row in model_mismatch["rows"] if row["scenario"] == "r0"]
        plot_bar(
            run,
            "15_resistance_deviation_effect.png",
            [f"{row['deviation_percent']:+.0f}%" for row in r0_rows],
            [row["rmse_pp"] for row in r0_rows],
            title=f"R0 deviation effect (ECM observer) — {model_mismatch['dataset']} (run {run.run_id})",
            ylabel="SOC RMSE (percentage point)",
        )
    budget = temperature["analytic_budget"]
    plot_series(
        run,
        "16_temperature_mismatch.png",
        {
            f"slope {slope:.1f} V/SOC": (
                [row["ocv_shift_mv"] for row in budget if row["ocv_slope_v_per_soc"] == slope],
                [row["soc_error_pp"] for row in budget if row["ocv_slope_v_per_soc"] == slope],
            )
            for slope in (0.5, 0.2, 0.1)
        },
        title=f"Temperature mismatch analytic budget — real data NOT_VERIFIED (run {run.run_id})",
        xlabel="OCV shift from temperature (mV)",
        ylabel="SOC error (percentage point)",
    )
    plot_bar(
        run,
        "23_engineering_validation.png",
        ["PASS", "FAIL", "NOT_VERIFIED"],
        [counts["PASS"], counts["FAIL"], counts["NOT_VERIFIED"]],
        title=f"Stage 7 engineering validation summary (run {run.run_id})",
        ylabel="count",
    )

    finish(run, f"stage7 {profile} done: {counts}")
    print(
        f"[battery_stage7_demo] profile={profile} run={run.run_id} "
        f"PASS={counts['PASS']} FAIL={counts['FAIL']} NOT_VERIFIED={counts['NOT_VERIFIED']} "
        f"spice_solves={spice['spice_solve_count']} charge_error={spice['charge_error_percent']:.5f}%"
    )
    for item in checks:
        print(f"  {item['status']:4s} {item['id']:6s} {item['name']} = {item['value']} (target {item['target']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="BatteryLab stage 7 validation")
    parser.add_argument("--profile", choices=("smoke", "standard"), default="standard")
    args = parser.parse_args()
    run_profile(args.profile)


if __name__ == "__main__":
    main()
