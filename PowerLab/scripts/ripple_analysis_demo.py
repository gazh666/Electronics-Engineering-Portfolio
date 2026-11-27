"""纹波分析演示：平均、峰峰值、交流有效值、逐周期纹波与 ESR 分解。"""

from __future__ import annotations

from analysis.ripple_analysis import theoretical_ripple_components
from circuits.nonideal_config import load_nonideal_buck_config
from scripts.performance_common import (
    PERFORMANCE_RESULTS_ROOT,
    run_performance_case,
    save_performance_run,
)
from storage.result_store import ResultStore
from visualization.plots import plot_ripple_window


def main() -> int:
    config = load_nonideal_buck_config()
    payload = run_performance_case(config, variant="E", include_spectrum=False)
    store = ResultStore(root=PERFORMANCE_RESULTS_ROOT)
    run_id, run_dir = store.create_run_dir(payload.run_id)
    save_performance_run(
        payload,
        config,
        store,
        run_dir,
        title="Model E Ripple Analysis",
        make_figures=False,
    )

    window = payload.window_frame
    from analysis.buck_waveforms import analyze_pwm_waveform
    import numpy as np

    time = window["time_s"].to_numpy(dtype=float)
    command = window["drive_vgs_command_v"].to_numpy(dtype=float)
    pwm = analyze_pwm_waveform(
        time,
        command,
        low_voltage_v=float(np.percentile(command, 1.0)),
        high_voltage_v=float(np.percentile(command, 99.0)),
    )
    plot_ripple_window(
        time,
        window["vout_v"].to_numpy(dtype=float),
        window["inductor_current_a"].to_numpy(dtype=float),
        pwm.cycle_boundaries_s,
        run_dir / "plots" / "ripple_window.png",
        title="Model E Steady-State Ripple",
    )

    print(f"[ripple] run={run_id} dir={run_dir}")
    for name in (
        "output_voltage_mean_v",
        "output_voltage_ripple_vpp",
        "output_voltage_ac_rms_v",
        "output_voltage_total_rms_v",
        "cycle_ripple_mean_v",
        "cycle_ripple_max_v",
        "cycle_ripple_std_v",
        "output_voltage_capacitor_ripple_vpp",
        "output_voltage_esr_ripple_vpp",
    ):
        metric = payload.metric(name)
        if metric is not None:
            print(f"  {name}: {metric.value} {metric.unit} [{metric.status.value}]")

    detail = payload.ripple_decomposition
    theory = theoretical_ripple_components(
        payload.numeric("inductor_current_ripple_a") or 0.0,
        payload.numeric("switching_frequency_hz") or config.switching_frequency_hz,
        config.capacitor.capacitance_f,
        config.capacitor.esr_ohm,
    )
    print(
        "  decomposition: "
        f"Vpp(out)={detail.get('output_vpp_v'):.6f} V, "
        f"Vpp(cap)={detail.get('capacitor_internal_vpp_v'):.6f} V, "
        f"Vpp(ESR)={detail.get('esr_vpp_v'):.6f} V, "
        f"reconstruction max|err|={detail.get('reconstruction_max_abs_v'):.3e} V"
    )
    print(
        "  theory: "
        f"C-ripple={theory['capacitor_voltage_ripple_vpp'] * 1e3:.3f} mV, "
        f"ESR-ripple={theory['esr_voltage_ripple_vpp'] * 1e3:.3f} mV"
    )
    print(f"  cycles: {payload.cycle_statistics.get('cycle_count')}")
    print(f"  overall={payload.overall_status} quality={payload.quality['error_codes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
