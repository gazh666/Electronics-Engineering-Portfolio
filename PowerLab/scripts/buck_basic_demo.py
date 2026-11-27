"""任务 2-8：Buck 基础开环瞬态仿真与波形分析。

真实运行一次 5 ms 瞬态仿真，输出：

- 启动电压 / 电感电流；
- 稳态窗口内的门极、开关节点、电感电流与输出纹波；
- 与理想理论的对照验证。
"""

from __future__ import annotations

import sys
from typing import Any

from analysis.buck_waveforms import PWMAnalysis
from circuits.buck_config import BuckParameters, load_buck_config
from scripts.buck_common import (
    BUCK_RESULTS_ROOT,
    BuckCase,
    default_validation_limits,
    record_failure,
    run_and_analyze,
    save_case,
)
from storage.result_store import ResultStore
from visualization.plots import (
    plot_buck_startup,
    plot_buck_startup_current,
    plot_buck_switching_overview,
)


def _plot_window(pwm: PWMAnalysis) -> tuple[float, float]:
    """最后三个完整开关周期，用于查看稳态开关波形。"""
    starts = pwm.cycle_start_times_s
    if len(starts) < 3:
        raise ValueError("need at least three cycles for the switching plot")
    return starts[-3], pwm.cycle_end_times_s[-1]


def build_case(parameters: BuckParameters) -> BuckCase:
    return run_and_analyze(parameters, validation_limits=default_validation_limits())


def analyze(parameters: BuckParameters) -> dict[str, Any]:
    case = build_case(parameters)
    return {
        "run_id": case.result.run_id,
        "mode": case.mode.mode.value,
        "steady_state_status": case.window.status,
        "output_voltage_mean_v": (
            None if case.metrics is None else case.metrics["output_voltage_mean_v"]
        ),
        "output_voltage_ripple_vpp": (
            None if case.metrics is None else case.metrics["output_voltage_ripple_vpp"]
        ),
        "inductor_current_ripple_app": (
            None if case.metrics is None else case.metrics["inductor_current_ripple_app"]
        ),
        "simulated_end_s": case.simulated_end_s,
        "point_count": case.result.point_count,
    }


def main() -> int:
    parameters: BuckParameters | None = None
    try:
        parameters = load_buck_config()
        case = build_case(parameters)
        if case.validation is None:
            raise RuntimeError("basic demo requires validation results")

        store = ResultStore(root=BUCK_RESULTS_ROOT)
        _, run_dir = store.create_run_dir(case.result.run_id)
        plots_dir = run_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)

        start, end = _plot_window(case.pwm)
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
                startup_peak_a=float(case.waveforms["inductor_current_a"].max()),
            ),
            "plots/switching_waveforms.png": plot_buck_switching_overview(
                case.waveforms["time_s"],
                case.waveforms["gate_v"],
                case.waveforms["switch_node_v"],
                case.waveforms["inductor_current_a"],
                case.waveforms["vout_v"],
                plots_dir / "switching_waveforms.png",
                start_s=start,
                end_s=end,
            ),
        }

        saved = save_case(case, store, run_dir, figures=figures)

        print("Buck basic demo")
        print(f"  run_dir     = {saved}")
        print(f"  mode        = {case.mode.mode.value}")
        print(f"  steady      = {case.window.status}")
        print(f"  Vout_mean   = {case.metrics['output_voltage_mean_v']:.6f} V")
        print(f"  Vout_ripple = {case.metrics['output_voltage_ripple_vpp'] * 1e3:.3f} mVpp")
        print(f"  IL_ripple   = {case.metrics['inductor_current_ripple_app']:.6f} A")
        print(f"  validation  = {case.validation.status}")
        print(f"  points      = {case.result.point_count}")

        ok = case.window.is_steady and case.validation.status == "PASS"
        return 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        directory = record_failure("buck_basic_demo", exc, parameters=parameters)
        print(f"Buck basic demo FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"failure log: {directory}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
