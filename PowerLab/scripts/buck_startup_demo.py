"""任务 5-6：Buck 启动过程分析。

真实运行默认 5 ms 瞬态，统计输出电压 / 电感电流峰值与进入稳态所需时间，
并明确未达到稳态时返回 ``NOT_SETTLED``，不伪造稳定时间。
"""

from __future__ import annotations

import sys

from circuits.buck_config import BuckParameters, load_buck_config
from scripts.buck_common import (
    BUCK_RESULTS_ROOT,
    default_validation_limits,
    record_failure,
    run_and_analyze,
    save_case,
    startup_metrics,
)
from storage.result_store import ResultStore
from visualization.plots import plot_buck_startup, plot_buck_startup_current


def main() -> int:
    parameters: BuckParameters | None = None
    try:
        parameters = load_buck_config()
        case = run_and_analyze(parameters, validation_limits=default_validation_limits())
        metrics = startup_metrics(case)

        store = ResultStore(root=BUCK_RESULTS_ROOT)
        _, run_dir = store.create_run_dir(case.result.run_id)
        plots_dir = run_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)

        figures = {
            "plots/startup_output_voltage.png": plot_buck_startup(
                case.waveforms["time_s"],
                case.waveforms["vout_v"],
                plots_dir / "startup_output_voltage.png",
                target_voltage_v=case.parameters.circuit.target_output_voltage_v,
                steady_window=(case.window.start_time_s, case.window.end_time_s),
            ),
            "plots/startup_inductor_current.png": plot_buck_startup_current(
                case.waveforms["time_s"],
                case.waveforms["inductor_current_a"],
                plots_dir / "startup_inductor_current.png",
                steady_mean_a=(
                    case.metrics["inductor_current_mean_a"] if case.metrics else None
                ),
                startup_peak_a=metrics["peak_inductor_current_a"],
            ),
        }
        saved = save_case(
            case,
            store,
            run_dir,
            figures=figures,
            extra_json_files={"startup_metrics.json": metrics},
            summary_extra={"startup": metrics},
        )

        print("Buck startup demo")
        print(f"  run_dir            = {saved}")
        print(f"  output peak        = {metrics['output_peak_v']:.6f} V")
        print(f"  output overshoot   = {metrics['output_overshoot_ratio'] * 100:.3f} %")
        print(f"  current peak       = {metrics['peak_inductor_current_a']:.6f} A")
        print(f"  settling Vout      = {metrics['settling_time_vout_s']}")
        print(f"  settling IL        = {metrics['settling_time_il_s']}")
        print(f"  steady status      = {case.window.status}")

        ok = (
            case.window.is_steady
            and metrics["settling_time_vout_s"] is not None
        )
        return 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        directory = record_failure("buck_startup_demo", exc, parameters=parameters)
        print(f"Buck startup demo FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"failure log: {directory}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
