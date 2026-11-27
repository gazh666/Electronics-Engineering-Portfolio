"""第五阶段脚本共用流水线：运行、保存、绘图。

与第四阶段 ``scripts/nonideal_common.py`` 相同的原则：
脚本只调用这里，确保所有入口使用同一套稳态窗口、功率边界和保存格式。
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from analysis.buck_waveforms import analyze_pwm_waveform
from analysis.performance_analyzer import PerformanceAnalyzer
from analysis.performance_models import (
    PerformanceResult,
    load_analysis_config,
    load_limits,
)
from circuits.nonideal_config import NonidealBuckConfig
from simulations.nonideal_buck_runner import run_nonideal_buck_transient
from storage.result_store import ResultStore, write_dataframe, write_json
from visualization.plots import (
    plot_harmonic_amplitudes,
    plot_ripple_window,
    plot_spectrum,
)

PERFORMANCE_RESULTS_ROOT = Path("results/performance")


def run_performance_case(
    config: NonidealBuckConfig,
    *,
    variant: str = "E",
    analyzer: PerformanceAnalyzer | None = None,
    profile: str | None = None,
    include_spectrum: bool = True,
    end_time_s: float | None = None,
) -> PerformanceResult:
    """运行一次真实瞬态并做完整性能分析。"""
    result = run_nonideal_buck_transient(config, variant, end_time_s=end_time_s)
    engine = analyzer or PerformanceAnalyzer()
    return engine.analyze(
        result,
        config,
        variant=variant,
        include_spectrum=include_spectrum,
        profile=profile,
    )


def check_table(result: PerformanceResult) -> pd.DataFrame:
    return pd.DataFrame([check.to_dict() for check in result.checks])


def save_performance_run(
    result: PerformanceResult,
    config: NonidealBuckConfig,
    store: ResultStore,
    run_dir: Path,
    *,
    extra_tables: dict[str, pd.DataFrame] | None = None,
    extra_json: dict[str, Any] | None = None,
    title: str | None = None,
    make_figures: bool = True,
) -> Path:
    """保存一次运行的 JSON/CSV/图。"""
    payload = result.to_dict()
    metadata = {
        "run_id": result.run_id,
        "title": title or result.circuit_name,
        "circuit_name": result.circuit_name,
        "variant": result.variant,
        "data_source": result.data_source,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "circuit_config": config.to_dict(),
        "analysis_notes": list(result.notes),
        "specification_type": "project_assumption",
        "raw_point_count": result.raw_point_count,
        "algorithms": "analysis.performance_analyzer.PerformanceAnalyzer.analyze",
    }
    write_json(run_dir / "metadata.json", metadata)
    write_json(run_dir / "performance_metrics.json", payload)
    write_json(run_dir / "quality.json", dict(result.quality))
    write_json(run_dir / "summary.json", {
        "run_id": result.run_id,
        "overall_status": result.overall_status,
        "total_checks": len(result.checks),
        "status_counts": _status_counts(result),
        "quality": {
            "passed": result.quality.get("passed"),
            "error_codes": result.quality.get("error_codes", []),
            "warning_codes": result.quality.get("warning_codes", []),
        },
    })
    write_dataframe(run_dir / "checks.csv", check_table(result))

    # 配置与分析参数快照，保证结果可追溯。
    (run_dir / "config_snapshot.yaml").write_text(
        yaml.safe_dump(config.to_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (run_dir / "analysis_config.yaml").write_text(
        yaml.safe_dump(load_analysis_config(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (run_dir / "limits_snapshot.yaml").write_text(
        yaml.safe_dump(load_limits(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    if result.circuit_netlist:
        (run_dir / "circuit.cir").write_text(result.circuit_netlist, encoding="utf-8")

    # 原始分析窗口与稳态窗口波形，便于复算。
    if result.window_frame is not None and len(result.window_frame) > 2:
        window = result.window_frame
        write_dataframe(run_dir / "waveform.csv", window)
        window_time = window["time_s"].to_numpy(dtype=float)
        keep = window_time >= window_time[-1] - 5.0 * float(config.period_s)
        write_dataframe(
            run_dir / "steady_state_waveform.csv", window.loc[keep]
        )

    # 指标明细 CSV 与分组 JSON。
    metric_rows: list[dict[str, Any]] = []
    for group_name, group in payload.get("groups", {}).items():
        for metric in group.get("metrics", {}).values():
            metric_rows.append({"group": group_name, **metric})
    write_dataframe(
        run_dir / "performance_metrics.csv", pd.DataFrame(metric_rows)
    )
    groups = payload.get("groups", {})
    write_json(
        run_dir / "power_metrics.json",
        {"power": groups.get("power", {}), "efficiency": groups.get("efficiency", {})},
    )
    write_json(
        run_dir / "ripple_metrics.json",
        {
            "ripple": groups.get("ripple", {}),
            "decomposition": dict(result.ripple_decomposition),
        },
    )
    write_json(
        run_dir / "switching_metrics.json",
        {
            "switching": groups.get("switching", {}),
            "details": dict(result.switching_details),
        },
    )
    write_json(run_dir / "performance_checks.json", [c.to_dict() for c in result.checks])
    write_json(run_dir / "data_quality.json", dict(result.quality))

    harmonics = pd.DataFrame(result.harmonic_entries)
    if not harmonics.empty:
        write_dataframe(run_dir / "harmonics.csv", harmonics)
    if result.cycle_statistics:
        per_cycle = result.cycle_statistics.get("per_cycle_ripple", [])
        cycle_table = pd.DataFrame(
            {
                "cycle_index": np.arange(1, len(per_cycle) + 1),
                "ripple_vpp_v": per_cycle,
            }
        )
        write_dataframe(run_dir / "cycle_ripple.csv", cycle_table)
        write_dataframe(run_dir / "cycle_statistics.csv", cycle_table)
    spectrum = result.spectrum
    if spectrum is not None:
        write_dataframe(
            run_dir / "spectrum.csv",
            pd.DataFrame(
                {
                    "frequency_hz": spectrum.frequency_hz,
                    "amplitude_peak_v": spectrum.amplitude_peak,
                    "amplitude_rms_v": spectrum.amplitude_rms,
                    "amplitude_dbv": spectrum.amplitude_dbv,
                    "psd_v2_per_hz": spectrum.psd,
                }
            ),
        )
        write_json(run_dir / "spectrum_metadata.json", spectrum.metadata())
    (run_dir / "execution.log").write_text(
        "\n".join(
            [
                f"run_id={result.run_id}",
                f"variant={result.variant}",
                f"data_source={result.data_source}",
                f"raw_point_count={result.raw_point_count}",
                f"overall_status={result.overall_status}",
                f"analysis_time={datetime.now().isoformat(timespec='seconds')}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for name, table in (extra_tables or {}).items():
        write_dataframe(run_dir / name, table)
    for name, data in (extra_json or {}).items():
        write_json(run_dir / name, data)

    if make_figures:
        save_default_figures(result, run_dir, title=title)
    return run_dir


def save_default_figures(
    result: PerformanceResult, run_dir: Path, *, title: str | None = None
) -> list[Path]:
    """保存纹波、频谱、谐波三张基础图。"""
    plot_dir = Path(run_dir) / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    prefix = title or str(result.variant)
    outputs: list[Path] = []
    window = result.window_frame
    if window is not None and len(window) > 2:
        time = window["time_s"].to_numpy(dtype=float)
        command = window["drive_vgs_command_v"].to_numpy(dtype=float)
        low = float(np.percentile(command, 1.0))
        high = float(np.percentile(command, 99.0))
        boundaries: tuple[float, ...] = ()
        if high > low:
            boundaries = analyze_pwm_waveform(
                time, command, low_voltage_v=low, high_voltage_v=high
            ).cycle_boundaries_s
        outputs.append(
            plot_ripple_window(
                time,
                window["vout_v"].to_numpy(dtype=float),
                window["inductor_current_a"].to_numpy(dtype=float),
                boundaries,
                plot_dir / "ripple_window.png",
                title=f"{prefix} Ripple",
            )
        )
    spectrum = result.spectrum
    if spectrum is not None:
        outputs.append(
            plot_spectrum(
                spectrum.frequency_hz,
                spectrum.amplitude_peak,
                plot_dir / "spectrum.png",
                title=f"{prefix} Output Spectrum",
                maximum_frequency_hz=min(
                    1.2e6, float(spectrum.resample.trusted_max_hz)
                ),
                harmonics=list(result.harmonic_entries),
            )
        )
    if result.harmonic_entries:
        orders = [entry["order"] for entry in result.harmonic_entries]
        amplitudes = [
            entry["amplitude_peak"] if entry["amplitude_peak"] is not None else 0.0
            for entry in result.harmonic_entries
        ]
        statuses = [entry["status"] for entry in result.harmonic_entries]
        outputs.append(
            plot_harmonic_amplitudes(
                orders,
                amplitudes,
                statuses,
                plot_dir / "harmonics.png",
                title=f"{prefix} Harmonics",
            )
        )
    return outputs


def _status_counts(result: PerformanceResult) -> dict[str, int]:
    counts: dict[str, int] = {}
    for check in result.checks:
        counts[check.status] = counts.get(check.status, 0) + 1
    return counts


def with_load(config: NonidealBuckConfig, resistance_ohm: float) -> NonidealBuckConfig:
    return replace(config, load_resistance_ohm=float(resistance_ohm))


def with_input(config: NonidealBuckConfig, input_voltage_v: float) -> NonidealBuckConfig:
    return replace(config, input_voltage_v=float(input_voltage_v))


def config_summary(config: NonidealBuckConfig) -> dict[str, Any]:
    return {
        "input_voltage_v": config.input_voltage_v,
        "target_output_voltage_v": config.target_output_voltage_v,
        "switching_frequency_hz": config.switching_frequency_hz,
        "duty_cycle": config.duty_cycle,
        "load_resistance_ohm": config.load_resistance_ohm,
        "inductance_h": config.inductor.inductance_h,
        "dcr_ohm": config.inductor.dcr_ohm,
        "capacitance_f": config.capacitor.capacitance_f,
        "esr_ohm": config.capacitor.esr_ohm,
    }


__all__ = [
    "PERFORMANCE_RESULTS_ROOT",
    "asdict",
    "config_summary",
    "run_performance_case",
    "save_default_figures",
    "save_performance_run",
    "with_input",
    "with_load",
]
