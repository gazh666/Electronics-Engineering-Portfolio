"""第六阶段最终验收：20 个工况 + 56 项检查。

所有数值来自真实运行：12 个开关级工况为真实 ngspice，其余为 ECM/行为级/软件测试。
限值在 configs/stage6_validation.yaml 中预登记，本脚本不修改任何限值。

运行：conda run -n kaifa_battery python -m scripts.stage6_validation_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.charging_loop_analysis import (
    analyze_current_loop,
    analyze_voltage_loop,
    bandwidth_separation_ratio,
    default_frequency_grid,
)
from analysis.charging_validation import evaluate_limits, load_preregistered_limits
from charging.battery_adapter import load_identified_battery_bundle
from charging.anti_windup import conditional_integral_rate
from charging.config import load_charger_config, load_controller_config, load_charging_cases
from charging.pi_controller import PIController
from circuits.charger_buck import PackFixture
from circuits.charger_spice_controller import (
    CascadeParameters,
    ChargerCircuitError,
    MINIMUM_RELIABLE_STEP_S,
    build_cascade_circuit,
    run_cascade_buck,
)
from circuits.spice_utils import get_solve_count, reset_solve_counter
from protection.limits import load_limits
from scripts.stage6_common import (
    Check,
    check_at_least,
    check_at_most,
    check_true,
    check_within,
    finish_run,
    fmt,
    format_table,
    make_run,
    summarize_checks,
)
from simulations.averaged_charger import AveragedChargerParameters, simulate_averaged_charge
from simulations.charging_experiments import run_experiment
from simulations.charger_spice_runner import MINIMUM_RELIABLE_STEP_S as RUNNER_STEP_S, prerun_netlist


def _netlist(charger, controller) -> str:
    return prerun_netlist("C01", charger=charger, controller=controller)


def _margin_measurements(charger, controller) -> dict:
    bundle = load_identified_battery_bundle(charger.battery.identified_model_id)
    cells = charger.battery.series_cells
    r0 = cells * float(bundle["parameters"].r0_ohm)
    r1 = cells * float(bundle["parameters"].r1_ohm)
    c1 = float(bundle["parameters"].c1_f) / cells
    power = charger.power_stage
    grid = default_frequency_grid()
    current_loop = analyze_current_loop(
        grid,
        vin_v=power.input_voltage_v,
        inductance_h=power.inductance_h,
        capacitance_f=power.capacitance_f,
        load_resistance_ohm=r0 + power.path_resistance_ohm,
        capacitor_esr_ohm=power.capacitor_esr_ohm,
        kp_duty_per_a=controller.current_loop.kp,
        ki_duty_per_as=controller.current_loop.ki,
        inductor_dc_resistance_ohm=power.inductor_dcr_ohm,
    )
    voltage_loop = analyze_voltage_loop(
        grid,
        r0,
        r1,
        c1,
        controller.voltage_loop.kp,
        controller.voltage_loop.ki,
        inner_loop_gain=current_loop["loop_gain"],
    )
    return {
        "current_loop": current_loop,
        "voltage_loop": voltage_loop,
        "bandwidth_separation_ratio": bandwidth_separation_ratio(current_loop, voltage_loop),
    }


def run(root: Path | None = None) -> dict:
    charger = load_charger_config()
    controller = load_controller_config()
    limits = load_preregistered_limits()
    run_dir = make_run("stage6_validation")
    reset_solve_counter()

    case_results: dict[str, dict] = {}
    for case in load_charging_cases():
        case_results[case.id] = run_experiment(case, persist_spice=case.method == "spice_simulation")

    spice_ids = [case_id for case_id, item in case_results.items() if item["method"] == "spice_simulation"]
    non_spice_ids = [case_id for case_id, item in case_results.items() if item["method"] != "spice_simulation"]
    spice = {case_id: case_results[case_id]["summary"] for case_id in spice_ids}

    margins = _margin_measurements(charger, controller)
    current_loop = margins["current_loop"]
    voltage_loop = margins["voltage_loop"]

    # ---------- 13 项预登记限值 ----------
    cc_ids = ("C01", "C04", "C05", "C06", "C08", "C09")
    cc_error = max(abs(float(spice[case_id]["cc_mean_error_a"])) for case_id in cc_ids)
    measured = {
        "cc_mean_error_a": abs(float(spice["C01"]["cc_mean_error_a"])),
        "cc_period_average_error_a": cc_error,
        "cc_startup_overshoot_fraction": max(0.0, float(spice["C01"]["max_charging_current_a"]) / 1.0 - 1.0),
        "cv_mean_error_v": abs(float(spice["C02"]["cv_mean_error_v"])),
        "cv_period_average_error_v": abs(float(spice["C03"]["cv_mean_error_v"])),
        "cc_cv_voltage_overshoot_v": float(spice["C03"]["voltage_overshoot_v"]),
        "power_stage_efficiency_min_percent": float(spice["C01"]["power_stage_efficiency_percent"]),
        "power_conservation_residual_fraction": max(
            abs(float(spice[case_id]["power_conservation_residual_fraction"]))
            for case_id in ("C01", "C02", "C03", "C19")
        ),
        "phase_margin_deg": float(voltage_loop["phase_margin_deg"]),
        "gain_margin_db": (
            {"infinite": True} if voltage_loop["gain_margin_infinite"] else voltage_loop["gain_margin_db"]
        ),
        "bandwidth_separation_ratio": float(margins["bandwidth_separation_ratio"]),
        "soc_consistency_tolerance_ah": abs(float(case_results["C18"]["summary"]["soc_consistency_ah"])),
        "intrinsic_solver_consistency_ppm": max(
            abs(float(spice[case_id]["intrinsic_solver_consistency_ppm"] or 0.0))
            for case_id in spice_ids
        ),
    }
    limit_report = evaluate_limits(measured, limits)
    limit_checks = [
        Check(
            item["name"],
            item["value"],
            item["limit"],
            item["unit"],
            item["status"],
            item.get("note", ""),
        )
        for item in limit_report["results"]
    ]

    # ---------- 配置与网表 ----------
    protection = charger.validate_against_protection()
    netlist = _netlist(charger, controller)
    config_checks = [
        check_true("cv_per_cell_below_ov_release",
                   protection["per_cell_cv_v"] < protection["cell_overvoltage_release_v"]),
        check_true("charge_oc_above_constant_current",
                   protection["charge_overcurrent_trip_a"] > charger.charging.constant_current_a),
        check_true("automatic_restart_disabled", not bool(charger.charging.automatic_restart_enabled)),
        check_true("input_voltage_above_cv_target",
                   charger.power_stage.input_voltage_v > charger.charging.constant_voltage_v),
        check_true("cv_duty_within_limit",
                   charger.charging.constant_voltage_v / charger.power_stage.input_voltage_v
                   <= charger.controller.duty_max),
        check_at_most("reliable_step_limit_s", MINIMUM_RELIABLE_STEP_S, 2e-8, "s",
                      "实测 50 ns 会产生 PWM 边沿量化伪极限环"),
        check_true("netlist_contains_voltage_loop", "BEV ev 0" in netlist and "BIREF iref 0" in netlist),
        check_true("netlist_contains_current_loop", "BEI ei 0" in netlist and "BII 0 xi I=" in netlist),
        check_true("netlist_feedforward_uses_filtered_output", "RFF out ff_in" in netlist and "(V(out)" not in netlist),
        check_true("netlist_conditional_integral_present", "1-V(vfrz)" in netlist and "1-V(ifrz)" in netlist),
    ]

    # ---------- 数值可靠性 ----------
    try:
        run_cascade_buck(
            charger.power_stage,
            PackFixture.from_equivalent_voltage(11.4, charger.power_stage.path_resistance_ohm,
                                               series_cells=charger.battery.series_cells),
            CascadeParameters.from_configs(charger, controller),
            duration_s=1e-5,
            step_s=5e-8,
        )
        guard_raised = False
    except ChargerCircuitError:
        guard_raised = True

    pi = PIController(kp=0.025, ki=50.0, kaw=1000.0)
    pi.integral = 0.5
    pi.step(error=0.2, dt_s=1e-5, lower=0.0, upper=0.5)
    frozen_integral = pi.integral
    reference_rate = conditional_integral_rate(50.0, 0.2, 1000.0, 0.5, 0.6)
    reference_integral = 0.5 + reference_rate * 1e-5

    averaged = simulate_averaged_charge(
        AveragedChargerParameters.from_configs(charger, controller).validate(),
        initial_soc=0.63,
        duration_s=float(spice["C01"]["duration_s"]),
        stop_at_termination=False,
    )
    numerical_checks = [
        check_true("step_guard_rejects_50ns", guard_raised, "50 ns 必须在求解前被拒绝"),
        check_true("anti_windup_freeze_holds_integral", abs(frozen_integral - 0.5) < 1e-12,
                   "饱和且误差同向时积分冻结"),
        check_within("pi_law_matches_reference_calculation", frozen_integral - reference_integral, 1e-12, "1"),
        check_within("averaged_vs_switching_final_current",
                     float(averaged.charging_current_a[-1]) - float(spice["C01"]["final_charging_current_a"]),
                     0.10, "A", "跨层次对照，仅作数量级一致性"),
        check_true("no_negative_current_in_normal_cc",
                   float(spice["C01"]["max_reverse_current_a"]) <= 0.01, "正常 CC 不应出现明显反向电流"),
        check_true("breakpoint_artifacts_documented",
                   int(spice["C01"]["raw_limits"]["switching_breakpoint_steps"]) > 0
                   and spice["C01"]["raw_limits"]["voltage_check_basis"] == "pwm_period_average_equivalent_to_afe_sampling"),
    ]

    # ---------- 工况判定 ----------
    case_checks = []
    for case_id in spice_ids + non_spice_ids:
        item = case_results[case_id]
        case_checks.append(
            Check(
                f"case_{case_id}",
                1.0 if item["status"] == "PASS" else 0.0,
                1.0,
                "bool",
                item["status"],
                item["method"],
            )
        )

    # ---------- 综合证据 ----------
    persisted = all(
        item.get("run_dir")
        and (Path(item["run_dir"]) / "circuit.cir").exists()
        and (Path(item["run_dir"]) / "waveform.csv").exists()
        and (Path(item["run_dir"]) / "summary.json").exists()
        for item in (case_results[case_id] for case_id in spice_ids)
    )
    stage_limits = load_limits()
    thresholds_ok = (
        abs(stage_limits.cell_overvoltage_trip_v - 4.25) < 1e-9
        and abs(stage_limits.cell_overvoltage_release_v - 4.15) < 1e-9
        and abs(stage_limits.cell_undervoltage_trip_v - 2.80) < 1e-9
        and abs(stage_limits.charge_overcurrent_trip_a - 1.50) < 1e-9
        and not bool(stage_limits.automatic_restart)
    )
    persisted_netlists = all(
        item.get("run_dir") and "BII 0 xi I=" in (Path(item["run_dir"]) / "circuit.cir").read_text(encoding="utf-8")
        for item in (case_results[case_id] for case_id in spice_ids)
    )
    evidence_checks = [
        check_true("all_20_cases_pass",
                   all(case_results[case_id]["status"] == "PASS" for case_id in case_results),
                   "20 个工况全部 PASS"),
        check_at_most("spice_solve_budget", get_solve_count(), 80, "solves",
                      "预算 80 次真实 ngspice 求解"),
        check_true("results_persisted", persisted, "每个开关级工况均有网表/波形/汇总"),
        check_true("no_python_generated_waveform", persisted_netlists,
                   "每个开关级网表都含网表内 PI 行为源，波形只能来自 ngspice"),
        check_true("protection_thresholds_unchanged", thresholds_ok,
                   "OV 4.25/4.15 V、UV 2.80 V、充电过流 1.50 A、禁止自动重启"),
        check_at_most("soc_consistency_ah", abs(float(case_results["C18"]["summary"]["soc_consistency_ah"])),
                      0.005, "Ah"),
        check_at_most("long_charge_energy_closure_fraction",
                      abs(float(case_results["C14"]["summary"]["energy"]["closure_residual_fraction"])),
                      0.01, "1", "长时 ECM 能量闭合残差"),
    ]

    checks = config_checks + numerical_checks + limit_checks + case_checks + evidence_checks
    summary = summarize_checks(checks)

    print("== 13 项预登记限值 ==")
    print(format_table(
        [[item["name"], fmt(item["value"]), fmt(item["limit"]), item["unit"], item["status"]]
         for item in limit_report["results"]],
        ["指标", "实测", "限值", "单位", "判定"],
    ))
    print("\n== 20 个工况 ==")
    print(format_table(
        [[case_id, case_results[case_id]["method"], case_results[case_id]["status"]]
         for case_id in spice_ids + non_spice_ids],
        ["工况", "层次", "判定"],
    ))
    print("\n== 56 项检查汇总 ==")
    print(f"PASS {summary['passed']} / FAIL {summary['failed']} / NOT_MEASURED {summary['not_measured']} / 合计 {summary['total']}")
    for item in checks:
        if item.status != "PASS":
            print(f"  [{item.status}] {item.name}: measured={fmt(item.measured)} limit={fmt(item.limit)} {item.note}")

    payload = {
        "kind": "stage6_final_validation",
        "layer": "mixed_all_layers",
        "preregistered_limits": limits,
        "measured_limit_inputs": measured,
        "limit_report": limit_report,
        "margins": {
            "current_loop": {key: value for key, value in current_loop.items() if key not in ("loop_gain", "plant")},
            "voltage_loop": {key: value for key, value in voltage_loop.items() if key not in ("loop_gain", "plant")},
            "bandwidth_separation_ratio": margins["bandwidth_separation_ratio"],
        },
        "cases": {
            case_id: {
                "method": case_results[case_id]["method"],
                "status": case_results[case_id]["status"],
                "summary": case_results[case_id]["summary"],
                "run_dir": case_results[case_id].get("run_dir"),
            }
            for case_id in spice_ids + non_spice_ids
        },
        "spice_solves": get_solve_count(),
        **summary,
    }
    run_dir.write_config_snapshot({"charger": charger.to_dict(), "controller": controller.to_dict()})
    finished = finish_run(run_dir, payload)
    print(f"\n运行目录: {finished['run_dir']}")
    print(f"最终结果: {summary['status']}")
    return finished


if __name__ == "__main__":
    run()
