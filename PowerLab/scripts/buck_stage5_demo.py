"""第五阶段总验收：统一性能分析、基准工况、负载/输入特性与 HTML 报告。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from analysis.performance_analyzer import PerformanceAnalyzer
from analysis.performance_models import load_cases
from circuits.nonideal_config import load_nonideal_buck_config
from experiments.line_characteristics import run_line_characteristic
from experiments.load_characteristics import run_load_characteristic
from experiments.performance_benchmark import run_performance_benchmark
from reports.performance_report import write_performance_report
from scripts.performance_common import (
    PERFORMANCE_RESULTS_ROOT,
    config_summary,
    run_performance_case,
    save_performance_run,
)
from scripts.load_characteristics_demo import RESISTANCES_OHM
from scripts.line_characteristics_demo import INPUT_VOLTAGES_V
from storage.result_store import ResultStore, write_dataframe, write_json
from visualization.plots import plot_line_characteristic, plot_load_characteristic

STAGE5_RESULTS_ROOT = Path("results/buck_stage5")


def main() -> int:
    config = load_nonideal_buck_config()
    analyzer = PerformanceAnalyzer()
    performance_store = ResultStore(root=PERFORMANCE_RESULTS_ROOT)

    # 1) 完整性能基线（含频谱、谐波、图与 HTML 报告）
    baseline = run_performance_case(
        config, variant="E", analyzer=analyzer, include_spectrum=True
    )
    baseline_id, baseline_dir = performance_store.create_run_dir(baseline.run_id)
    save_performance_run(
        baseline,
        config,
        performance_store,
        baseline_dir,
        title="Stage 5 Baseline (Model E)",
        make_figures=True,
    )
    report_path = write_performance_report(baseline_dir)

    # 2) 基准工况（A / E / 轻载 / 高 ESR / 低压 / 高压）
    benchmark = run_performance_benchmark(load_cases(), config, analyzer=analyzer)

    # 3) 负载特性
    load_sweep = run_load_characteristic(config, RESISTANCES_OHM, variant="E")
    load_id, load_dir = performance_store.create_run_dir()
    write_dataframe(load_dir / "load_characteristic.csv", load_sweep.table)
    write_json(load_dir / "load_regulation.json", load_sweep.regulation)
    write_json(
        load_dir / "metadata.json",
        {
            "run_id": load_id,
            "analysis": "load_characteristic",
            "variant": "E",
            "data_source": "spice_simulation",
        },
    )
    plot_load_characteristic(
        load_sweep.table,
        load_dir / "plots" / "load_characteristic.png",
        title="Stage 5 Load Characteristic",
    )

    # 4) 输入特性
    line_sweep = run_line_characteristic(config, INPUT_VOLTAGES_V, variant="E")
    line_id, line_dir = performance_store.create_run_dir()
    write_dataframe(line_dir / "line_characteristic.csv", line_sweep.table)
    write_json(line_dir / "line_regulation.json", line_sweep.regulation)
    write_json(
        line_dir / "metadata.json",
        {
            "run_id": line_id,
            "analysis": "line_characteristic",
            "variant": "E",
            "data_source": "spice_simulation",
        },
    )
    plot_line_characteristic(
        line_sweep.table,
        line_dir / "plots" / "line_characteristic.png",
        title="Stage 5 Line Characteristic",
    )

    baseline_metrics = {
        "output_voltage_mean_v": baseline.numeric("output_voltage_mean_v"),
        "output_voltage_ripple_vpp": baseline.numeric("output_voltage_ripple_vpp"),
        "inductor_current_mean_a": baseline.numeric("inductor_current_mean_a"),
        "efficiency_system_percent": baseline.numeric("efficiency_system_percent"),
        "thd_percent": baseline.numeric("thd_percent"),
        "spectrum_frequency_resolution_hz": baseline.numeric(
            "spectrum_frequency_resolution_hz"
        ),
        "overall_status": baseline.overall_status,
        "quality": dict(baseline.quality),
    }

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_source": "spice_simulation",
        "specification_type": "project_assumption",
        "configuration": config_summary(config),
        "baseline": baseline_metrics,
        "benchmark": {
            "spice_run_count": benchmark.spice_run_count,
            "unique_config_count": benchmark.unique_config_count,
            "skipped_duplicates": benchmark.skipped_duplicates,
            "rows": benchmark.table.to_dict("records"),
        },
        "load_characteristic": {
            "regulation": load_sweep.regulation,
            "rows": load_sweep.table.to_dict("records"),
        },
        "line_characteristic": {
            "regulation": line_sweep.regulation,
            "rows": line_sweep.table.to_dict("records"),
        },
        "artifacts": {
            "baseline_run": str(baseline_dir),
            "baseline_report": str(report_path),
            "load_run": str(load_dir),
            "line_run": str(line_dir),
        },
    }
    overall_passed = (
        baseline.overall_status == "PASS"
        and baseline.quality.get("passed", False)
    )
    summary["overall_passed"] = bool(overall_passed)

    stage5_store = ResultStore(root=STAGE5_RESULTS_ROOT)
    stage5_id, stage5_dir = stage5_store.create_run_dir()
    write_json(stage5_dir / "stage5_validation.json", summary)
    write_dataframe(stage5_dir / "benchmark.csv", benchmark.table)
    write_dataframe(stage5_dir / "load_characteristic.csv", load_sweep.table)
    write_dataframe(stage5_dir / "line_characteristic.csv", line_sweep.table)

    print(f"[stage5] run={stage5_id} dir={stage5_dir}")
    print(
        f"  baseline Vout={baseline_metrics['output_voltage_mean_v']:.6f} V "
        f"ripple={baseline_metrics['output_voltage_ripple_vpp'] * 1e3:.3f} mV "
        f"eta={baseline_metrics['efficiency_system_percent']:.4f}% "
        f"THD={baseline_metrics['thd_percent']:.3f}% "
        f"status={baseline.overall_status}"
    )
    print(
        f"  benchmark runs={benchmark.spice_run_count} "
        f"unique={benchmark.unique_config_count} skipped={benchmark.skipped_duplicates}"
    )
    print(
        f"  load span={load_sweep.regulation.get('span_percent'):.3f}% "
        f"ccm_slope={load_sweep.regulation.get('ccm_slope_mv_per_a')} mV/A"
    )
    print(
        f"  line span={line_sweep.regulation.get('span_percent'):.3f}% "
        f"sensitivity={line_sweep.regulation.get('sensitivity_mv_per_v')} mV/V"
    )
    print(f"  report={report_path}")
    print(f"  overall_passed={overall_passed}")
    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
