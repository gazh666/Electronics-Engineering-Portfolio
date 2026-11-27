"""频谱与谐波演示：SW 基线（A）与非理想模型（E）对照。"""

from __future__ import annotations

import pandas as pd

from analysis.performance_analyzer import PerformanceAnalyzer
from circuits.nonideal_config import load_nonideal_buck_config
from scripts.performance_common import (
    PERFORMANCE_RESULTS_ROOT,
    run_performance_case,
    save_performance_run,
)
from storage.result_store import ResultStore
from visualization.plots import plot_harmonic_amplitudes, plot_spectrum


def main() -> int:
    config = load_nonideal_buck_config()
    analyzer = PerformanceAnalyzer()
    store = ResultStore(root=PERFORMANCE_RESULTS_ROOT)
    comparison_rows = []

    for variant, title in (("A", "Model A Spectrum"), ("E", "Model E Spectrum")):
        payload = run_performance_case(
            config, variant=variant, analyzer=analyzer, include_spectrum=True
        )
        run_id, run_dir = store.create_run_dir(payload.run_id)
        save_performance_run(
            payload,
            config,
            store,
            run_dir,
            title=title,
            make_figures=False,
        )
        spectrum = payload.spectrum
        if spectrum is None:
            raise RuntimeError("spectrum was not produced")
        plot_dir = run_dir / "plots"
        plot_dir.mkdir(parents=True, exist_ok=True)
        plot_spectrum(
            spectrum.frequency_hz,
            spectrum.amplitude_peak,
            plot_dir / "spectrum.png",
            title=title,
            maximum_frequency_hz=min(1.2e6, spectrum.resample.trusted_max_hz),
            harmonics=list(payload.harmonic_entries),
        )
        if payload.harmonic_entries:
            plot_harmonic_amplitudes(
                [entry["order"] for entry in payload.harmonic_entries],
                [
                    entry["amplitude_peak"] if entry["amplitude_peak"] is not None else 0.0
                    for entry in payload.harmonic_entries
                ],
                [entry["status"] for entry in payload.harmonic_entries],
                plot_dir / "harmonics.png",
                title=title,
            )
        resolved = sum(
            1 for entry in payload.harmonic_entries if entry["status"] == "AVAILABLE"
        )
        print(
            f"[spectrum {variant}] run={run_id} dir={run_dir} "
            f"df={spectrum.resample.frequency_resolution_hz:.2f} Hz "
            f"trusted={spectrum.resample.trusted_max_hz / 1e6:.3f} MHz "
            f"cycles={spectrum.resample.complete_cycles} "
            f"THD={payload.numeric('thd_percent')} "
            f"resolved_harmonics={resolved}/{len(payload.harmonic_entries)}"
        )
        comparison_rows.append(
            {
                "variant": variant,
                "fundamental_hz": payload.numeric("spectrum_fundamental_frequency_hz"),
                "frequency_resolution_hz": spectrum.resample.frequency_resolution_hz,
                "trusted_max_hz": spectrum.resample.trusted_max_hz,
                "complete_cycles": spectrum.resample.complete_cycles,
                "thd_percent": payload.numeric("thd_percent"),
                "resolved_harmonics": resolved,
            }
        )

    table = pd.DataFrame(comparison_rows)
    last_dir = run_dir
    table.to_csv(last_dir / "spectrum_comparison.csv", index=False)
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
