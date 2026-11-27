"""第四阶段总验收：器件判据 + 五模型 + 时间步长敏感性。

所有数据来自真实 ngspice 运行；本脚本只汇总与判定，不修改任何波形。
"""

from __future__ import annotations

import pandas as pd

from analysis.buck_waveforms import analyze_pwm_waveform
from analysis.device_characteristics import (
    check_device_limits,
    extract_diode_forward,
    extract_diode_reverse,
    extract_off_state,
    extract_transfer_characteristics,
    rds_on_at_current,
)
from analysis.model_comparison import compare_models, difference_notes, loss_share_table
from analysis.power_metrics import frame_window, time_average
from circuits.nonideal_buck import get_variant_features
from circuits.nonideal_config import (
    load_device_models,
    load_nonideal_buck_config,
    load_validation_limits,
)
from simulations.device_runner import (
    run_diode_forward,
    run_diode_reverse,
    run_mosfet_off_state,
    run_mosfet_output,
    run_mosfet_transfer,
)
from simulations.nonideal_buck_runner import run_nonideal_buck_transient
from scripts.nonideal_common import (
    NONIDEAL_RESULTS_ROOT,
    STAGE4_RESULTS_ROOT,
    build_frame,
    run_case_with_retries,
    save_case,
)
from storage.result_store import ResultStore, write_dataframe, write_json

VARIANTS = ("A", "B", "C", "D", "E")


def _device_checks() -> tuple[dict, dict]:
    models = load_device_models()
    mosfet = models["mosfet"]
    diode = models["diode"]
    tests = models["mosfet_tests"]
    diode_tests = models["diode_tests"]
    temperature = 25.0

    transfer = extract_transfer_characteristics(
        run_mosfet_transfer(
            mosfet,
            vds_v=float(tests["transfer"]["vds_v"]),
            vgs_start_v=float(tests["transfer"]["vgs_start_v"]),
            vgs_stop_v=float(tests["transfer"]["vgs_stop_v"]),
            vgs_step_v=float(tests["transfer"]["vgs_step_v"]),
            temperature_c=temperature,
        )
    )
    output_result = run_mosfet_output(
        mosfet,
        vgs_v=float(tests["rds_point"]["vgs_v"]),
        vds_start_v=float(tests["output"]["vds_start_v"]),
        vds_stop_v=float(tests["output"]["vds_stop_v"]),
        vds_step_v=float(tests["output"]["vds_step_v"]),
        temperature_c=temperature,
    )
    rds = rds_on_at_current(output_result, float(tests["rds_point"]["target_current_a"]))
    off_state = extract_off_state(
        run_mosfet_off_state(
            mosfet,
            vgs_v=float(tests["off_state"]["vgs_v"]),
            vds_start_v=0.0,
            vds_stop_v=float(tests["off_state"]["vds_v"]),
            vds_step_v=0.1,
            temperature_c=temperature,
        )
    )
    diode_forward = extract_diode_forward(
        run_diode_forward(
            diode,
            vd_start_v=float(diode_tests["forward_start_v"]),
            vd_stop_v=float(diode_tests["forward_stop_v"]),
            vd_step_v=float(diode_tests["forward_step_v"]),
            temperature_c=temperature,
        ),
        diode_tests["reference_currents_a"],
    )
    diode_reverse = extract_diode_reverse(
        run_diode_reverse(
            diode,
            vd_start_v=float(diode_tests["reverse_start_v"]),
            vd_stop_v=float(diode_tests["reverse_stop_v"]),
            vd_step_v=float(diode_tests["reverse_step_v"]),
            temperature_c=temperature,
        )
    )
    checks = check_device_limits(
        transfer=transfer,
        rds=rds,
        off_state=off_state,
        diode_forward=diode_forward,
        diode_reverse=diode_reverse,
        limits=load_validation_limits(),
    )
    payload = {
        "transfer": transfer,
        "rds_on": rds,
        "off_state": off_state,
        "diode_forward": diode_forward,
        "diode_reverse": diode_reverse,
    }
    return checks, payload


def _timestep_rows(config) -> pd.DataFrame:
    features = get_variant_features("E")
    rows = []
    for max_step in (50e-9, 25e-9, 12.5e-9):
        try:
            result = run_nonideal_buck_transient(
                config, "E", end_time_s=1.0e-3, max_step_time_s=max_step
            )
        except Exception as error:  # noqa: BLE001
            rows.append(
                {
                    "max_step_time_s": max_step,
                    "status": f"failed: {type(error).__name__}",
                    "point_count": None,
                    "minimum_step_s": None,
                    "maximum_step_s": None,
                    "mean_step_s": None,
                    "max_step_respected": None,
                    "output_voltage_v": None,
                    "output_ripple_mv": None,
                    "inductor_current_a": None,
                    "complete_cycles": None,
                }
            )
            continue
        frame = build_frame(result, config, features)
        pwm = analyze_pwm_waveform(
            frame["time_s"],
            frame["mosfet_vgs_v"],
            low_voltage_v=config.gate_driver.low_voltage_v,
            high_voltage_v=config.gate_driver.drive_voltage_v,
        )
        end = float(frame["time_s"].iloc[-1])
        window = frame_window(frame, end - 2.0 * config.period_s, end)
        statistics = result.metadata.get("time_step_statistics", {})
        rows.append(
            {
                "max_step_time_s": max_step,
                "status": "success",
                "point_count": int(len(result.data)),
                "minimum_step_s": statistics.get("min_step_s"),
                "maximum_step_s": statistics.get("max_step_s"),
                "mean_step_s": statistics.get("mean_step_s"),
                "max_step_respected": statistics.get("max_step_respected"),
                "output_voltage_v": time_average(
                    window["time_s"].to_numpy(dtype=float),
                    window["vout_v"].to_numpy(dtype=float),
                ),
                "output_ripple_mv": float(
                    window["vout_v"].max() - window["vout_v"].min()
                )
                * 1e3,
                "inductor_current_a": time_average(
                    window["time_s"].to_numpy(dtype=float),
                    window["inductor_current_a"].to_numpy(dtype=float),
                ),
                "complete_cycles": pwm.complete_cycles,
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    config = load_nonideal_buck_config()
    store = ResultStore(root=NONIDEAL_RESULTS_ROOT)

    device_checks, device_payload = _device_checks()
    print(f"[device] passed={device_checks['passed']}")
    for name, item in device_checks["checks"].items():
        print(f"  {name}: {item['passed']} value={item['value']}")

    cases = []
    for variant in VARIANTS:
        case = run_case_with_retries(config, variant)
        run_id, run_dir = store.create_run_dir()
        cases.append((variant, case, run_id, run_dir))
        print(
            f"[model {variant}] run={run_id} "
            f"Vout={case.summary.output_voltage_mean_v:.6f} V "
            f"eta={case.accounting.efficiency_power_stage_percent:.4f}% "
            f"checks={case.checks['passed']}"
        )

    summaries = [case.summary for _, case, _, _ in cases]
    comparison = compare_models(summaries, reference="A")
    shares = loss_share_table(summaries)
    notes = difference_notes(summaries)

    timestep = _timestep_rows(config)
    print("[timestep sensitivity, 1 ms transient Model E]")
    for row in timestep.to_dict("records"):
        if row["status"] != "success":
            print(f"  max_step={row['max_step_time_s'] * 1e9:.1f} ns {row['status']}")
            continue
        print(
            f"  max_step={row['max_step_time_s'] * 1e9:.1f} ns points={row['point_count']} "
            f"Vout={row['output_voltage_v']:.6f} V ripple={row['output_ripple_mv']:.4f} mV"
        )

    models_ok = all(case.checks["passed"] for _, case, _, _ in cases)
    summary = {
        "device_checks": device_checks,
        "device_characteristics": device_payload,
        "models": {case.variant: case.to_summary_dict() for _, case, _, _ in cases},
        "comparison_notes": notes,
        "timestep_sensitivity": timestep.to_dict("records"),
        "overall_passed": bool(device_checks["passed"] and models_ok),
        "data_source": "spice_simulation",
    }

    for variant, case, run_id, run_dir in cases[:-1]:
        save_case(case, store, run_dir)
    last_case, last_dir = cases[-1][1], cases[-1][3]
    save_case(
        last_case,
        store,
        last_dir,
        extra_tables={
            "model_comparison.csv": comparison,
            "model_loss_share.csv": shares,
            "timestep_sensitivity.csv": timestep,
            "device_checks.csv": pd.DataFrame(
                [
                    {
                        "check": name,
                        "value": item["value"],
                        "passed": item["passed"],
                    }
                    for name, item in device_checks["checks"].items()
                ]
            ),
        },
    )

    print(f"[stage4] device_passed={device_checks['passed']} models_passed={models_ok}")

    stage4_store = ResultStore(root=STAGE4_RESULTS_ROOT)
    stage4_id, stage4_dir = stage4_store.create_run_dir()
    write_json(stage4_dir / "stage4_validation.json", summary)
    write_dataframe(stage4_dir / "model_comparison.csv", comparison)
    write_dataframe(stage4_dir / "model_loss_share.csv", shares)
    write_dataframe(stage4_dir / "timestep_sensitivity.csv", timestep)
    write_dataframe(
        stage4_dir / "device_checks.csv",
        pd.DataFrame(
            [
                {"check": name, "value": item["value"], "passed": item["passed"]}
                for name, item in device_checks["checks"].items()
            ]
        ),
    )
    print(f"[stage4] summary saved: {stage4_dir / 'stage4_validation.json'}")
    return 0 if summary["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
