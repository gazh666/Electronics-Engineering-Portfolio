"""任务 10-15：Buck 稳态窗口、纹波与能量平衡分析。

只有完整开关周期且满足稳态判据时才计算稳态指标；
否则报告 ``NOT_SETTLED``，不把启动瞬态当作开关纹波。
"""

from __future__ import annotations

import sys
from typing import Any

from circuits.buck_config import BuckParameters, load_buck_config
from scripts.buck_common import (
    BUCK_RESULTS_ROOT,
    default_validation_limits,
    record_failure,
    run_and_analyze,
    save_case,
)
from storage.result_store import ResultStore
from visualization.plots import plot_buck_switching_overview


def _checks(case) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, measured: Any, criterion: str) -> None:
        checks.append(
            {
                "name": name,
                "status": "PASS" if passed else "FAIL",
                "measured": measured,
                "criterion": criterion,
            }
        )

    add("steady_state_window", case.window.is_steady, case.window.status, "STEADY_STATE")
    if case.metrics is not None:
        add(
            "output_voltage_near_target",
            abs(case.metrics["output_voltage_mean_v"] - case.parameters.circuit.target_output_voltage_v)
            / case.parameters.circuit.target_output_voltage_v
            <= 0.10,
            case.metrics["output_voltage_mean_v"],
            "within 10% of target",
        )
        add(
            "output_ripple_design",
            case.metrics["output_voltage_ripple_vpp"] <= 0.05,
            case.metrics["output_voltage_ripple_vpp"],
            "<= 0.05 Vpp",
        )
        add(
            "per_cycle_ripple_stable",
            case.metrics["output_ripple_std_v"] <= 0.001,
            case.metrics["output_ripple_std_v"],
            "<= 1 mV standard deviation",
        )
    if case.volt_second is not None:
        add(
            "inductor_volt_second_balance",
            (
                case.volt_second["relative_error"] is not None
                and case.volt_second["relative_error"] <= 0.05
            ),
            case.volt_second["relative_error"],
            "relative error <= 5%",
        )
    if case.charge_balance is not None:
        add(
            "capacitor_charge_balance",
            (
                case.charge_balance["relative_error"] is not None
                and case.charge_balance["relative_error"] <= 0.05
            ),
            case.charge_balance["relative_error"],
            "relative error <= 5%",
        )
    return checks


def main() -> int:
    parameters: BuckParameters | None = None
    try:
        parameters = load_buck_config()
        case = run_and_analyze(parameters, validation_limits=default_validation_limits())
        checks = _checks(case)
        status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"

        store = ResultStore(root=BUCK_RESULTS_ROOT)
        _, run_dir = store.create_run_dir(case.result.run_id)
        plots_dir = run_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)

        starts = case.pwm.cycle_start_times_s
        start, end = starts[-3], case.pwm.cycle_end_times_s[-1]
        figure = plot_buck_switching_overview(
            case.waveforms["time_s"],
            case.waveforms["gate_v"],
            case.waveforms["switch_node_v"],
            case.waveforms["inductor_current_a"],
            case.waveforms["vout_v"],
            plots_dir / "steady_state_switching.png",
            start_s=start,
            end_s=end,
        )

        payload = {
            "status": status,
            "checks": checks,
            "window": case.window.to_dict(),
            "metrics": case.metrics,
            "volt_second_balance": case.volt_second,
            "charge_balance": case.charge_balance,
            "per_cycle_output_ripple_vpp": (
                None if case.metrics is None else case.metrics["per_cycle_output_ripple_vpp"]
            ),
            "per_cycle_inductor_ripple_app": (
                None if case.metrics is None else case.metrics["per_cycle_inductor_ripple_app"]
            ),
            "data_source": "spice_simulation",
        }
        saved = save_case(
            case,
            store,
            run_dir,
            figures={"plots/steady_state_switching.png": figure},
            extra_json_files={"steady_state_checks.json": payload},
            summary_extra={"steady_state_checks": status},
        )

        print("Buck steady-state demo")
        print(f"  run_dir        = {saved}")
        print(f"  window         = {case.window.start_time_s:.9g} .. {case.window.end_time_s:.9g} s")
        print(f"  cycles         = {case.window.complete_cycles}")
        print(f"  Vout mean      = {case.metrics['output_voltage_mean_v']:.6f} V")
        print(f"  Vout ripple    = {case.metrics['output_voltage_ripple_vpp'] * 1e3:.3f} mVpp")
        print(f"  IL ripple      = {case.metrics['inductor_current_ripple_app']:.6f} A")
        print(f"  volt-second    = {case.volt_second['relative_error']:.3e}")
        print(f"  charge balance = {case.charge_balance['relative_error']:.3e}")
        print(f"  checks         = {status}")
        return 0 if status == "PASS" else 1
    except Exception as exc:  # noqa: BLE001
        directory = record_failure("buck_steady_state_demo", exc, parameters=parameters)
        print(
            f"Buck steady-state demo FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        print(f"failure log: {directory}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
