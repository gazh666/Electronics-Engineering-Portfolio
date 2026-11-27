"""Task 12-17：解析 CALCE 真实数据、质量检查并生成图表。

所有数据来自 CALCE 官方公开实验数据，不是本人硬件实测。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml

from analysis.battery_metrics import split_sign_capacity_ah, summarize_measurement
from datasets.calce_loader import LoadedDataset, load_all_archives
from datasets.catalog import load_manifest, save_manifest_payload
from datasets.data_quality import check_frame, cleaning_record
from storage.result_store import RunDirectory, json_safe, write_json
from visualization.plots import plot_dual_axis, plot_histogram, plot_step_segments, plot_xy

RAW_LABEL = "数据来源：CALCE 公开实验数据（INR18650-20R），非本人实测"


def _stage_labels(frame: pd.DataFrame) -> pd.Series:
    current = frame["current_a"].to_numpy(dtype=float)
    labels = np.where(current > 1e-9, "discharge", np.where(current < -1e-9, "charge", "rest"))
    return pd.Series(labels, index=frame.index)


def _pick_source_file(dataset: LoadedDataset, keyword: str | None = None) -> str:
    files = dataset.source_files
    if keyword:
        for name in files:
            if keyword in name:
                return name
    return files[0]


def _single_file(dataset: LoadedDataset, keyword: str | None = None) -> pd.DataFrame:
    name = _pick_source_file(dataset, keyword)
    return dataset.frame[dataset.frame["source_file"] == name].reset_index(drop=True)


def _dataset_summary_row(dataset: LoadedDataset, quality: dict) -> dict:
    frame = dataset.frame
    info = dataset.summary()
    discharge_ah, charge_ah = (None, None)
    sample = _single_file(dataset)
    if len(sample) > 2:
        time_s = sample["time_s"].to_numpy(dtype=float)
        current = sample["current_a"].to_numpy(dtype=float)
        if np.all(np.isfinite(time_s)) and np.all(np.diff(time_s) > 0) and np.all(np.isfinite(current)):
            discharge_ah, charge_ah = split_sign_capacity_ah(time_s, current)
    info.update(
        {
            "quality_status": quality["status"],
            "sampling_median_s": quality["timestep_stats_s"]["median"],
            "derived_discharge_capacity_ah": discharge_ah,
            "derived_charge_capacity_ah": charge_ah,
            "max_raw_charge_capacity_ah": float(np.nanmax(frame["charge_capacity_ah"])) if frame["charge_capacity_ah"].notna().any() else None,
            "max_raw_discharge_capacity_ah": float(np.nanmax(frame["discharge_capacity_ah"])) if frame["discharge_capacity_ah"].notna().any() else None,
            "temperature_rows": quality["temperature_available_rows"],
        }
    )
    return info


def _plot_initial_capacity(dataset: LoadedDataset, plots_dir: Path, tag: str) -> list[str]:
    frame = _single_file(dataset)
    produced: list[str] = []
    annotation = f"{RAW_LABEL}；{dataset.dataset_id}；{tag}"
    produced.append(
        str(
            plot_dual_axis(
                frame,
                path=plots_dir / "01_initial_capacity_voltage_current.png",
                x="time_s",
                y_left="voltage_v",
                y_right="current_a",
                xlabel="测试时间 (s)",
                left_label="端电压 (V)",
                right_label="电流 (A，放电为正)",
                title="CALCE 初始容量测试：电压与电流",
                annotation=annotation,
            )
        )
    )
    produced.append(
        str(
            plot_xy(
                frame["time_s"],
                frame["discharge_capacity_ah"],
                path=plots_dir / "02_initial_capacity_discharge_capacity.png",
                xlabel="测试时间 (s)",
                ylabel="累计放电容量 (Ah)",
                title="CALCE 初始容量测试：放电容量",
                annotation=annotation,
            )
        )
    )
    power = frame["voltage_v"].to_numpy(dtype=float) * frame["current_a"].to_numpy(dtype=float)
    produced.append(
        str(
            plot_xy(
                frame["time_s"],
                power,
                path=plots_dir / "03_initial_capacity_power.png",
                xlabel="测试时间 (s)",
                ylabel="瞬时功率 (W，放电为正)",
                title="CALCE 初始容量测试：功率",
                annotation=annotation,
                color="#9467bd",
            )
        )
    )
    intervals = np.diff(frame["time_s"].to_numpy(dtype=float))
    intervals = intervals[np.isfinite(intervals) & (intervals > 0)]
    if len(intervals):
        produced.append(
            str(
                plot_histogram(
                    intervals,
                    path=plots_dir / "04_sampling_interval_histogram.png",
                    xlabel="采样间隔 (s)",
                    title="CALCE 数据采样间隔分布",
                    annotation=annotation,
                )
            )
        )
    staged = frame.copy()
    staged["stage"] = _stage_labels(staged)
    produced.append(
        str(
            plot_step_segments(
                staged,
                path=plots_dir / "05_stage_segments.png",
                x="time_s",
                y="voltage_v",
                label_column="stage",
                xlabel="测试时间 (s)",
                ylabel="端电压 (V)",
                title="CALCE 初始容量测试：充放电阶段",
                annotation=annotation,
            )
        )
    )
    return produced


def _plot_dynamic(dataset: LoadedDataset, plots_dir: Path, tag: str) -> list[str]:
    frame = _single_file(dataset)
    annotation = f"{RAW_LABEL}；{dataset.dataset_id}；{tag}"
    produced = [
        str(
            plot_xy(
                frame["time_s"],
                frame["current_a"],
                path=plots_dir / "06_dynamic_current.png",
                xlabel="测试时间 (s)",
                ylabel="电流 (A，放电为正)",
                title=f"CALCE {tag} 动态电流",
                annotation=annotation,
                color="#d62728",
            )
        ),
        str(
            plot_xy(
                frame["time_s"],
                frame["voltage_v"],
                path=plots_dir / "07_dynamic_voltage.png",
                xlabel="测试时间 (s)",
                ylabel="端电压 (V)",
                title=f"CALCE {tag} 动态电压响应",
                annotation=annotation,
            )
        ),
    ]
    return produced


def _plot_ocv(dataset: LoadedDataset, plots_dir: Path, tag: str, prefix: str) -> list[str]:
    frame = _single_file(dataset)
    annotation = f"{RAW_LABEL}；{dataset.dataset_id}；{tag}"
    produced = [
        str(
            plot_xy(
                frame["time_s"],
                frame["voltage_v"],
                path=plots_dir / f"{prefix}_ocv_voltage.png",
                xlabel="测试时间 (s)",
                ylabel="端电压 (V)",
                title=f"CALCE {tag} 电压曲线",
                annotation=annotation,
            )
        )
    ]
    staged = frame.copy()
    staged["stage"] = _stage_labels(staged)
    produced.append(
        str(
            plot_step_segments(
                staged,
                path=plots_dir / f"{prefix}_ocv_stage_segments.png",
                x="time_s",
                y="voltage_v",
                label_column="stage",
                xlabel="测试时间 (s)",
                ylabel="端电压 (V)",
                title=f"CALCE {tag} 充放电/静置分段",
                annotation=annotation,
            )
        )
    )
    return produced


def main() -> int:
    config = yaml.safe_load((PROJECT_ROOT / "configs" / "dataset_config.yaml").read_text(encoding="utf-8"))
    limits = config.get("quality", {})
    manifest = load_manifest()
    records = manifest.get("records", [])
    if not records:
        raise SystemExit("清单为空，请先运行 scripts.download_calce_data")

    datasets = load_all_archives(records)
    run = RunDirectory("calce")
    processed_dir = run.path / "processed"
    plots_dir = run.path / "plots"
    processed_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    quality_reports: dict[str, dict] = {}
    summary_rows: list[dict] = []
    cleaning: dict[str, dict] = {}
    plot_paths: dict[str, list[str]] = {}
    total_points = 0

    type_map = {record["dataset_id"]: record.get("test_type") for record in records}
    for dataset in datasets:
        test_type = type_map.get(dataset.dataset_id)
        quality = check_frame(dataset.frame, limits)
        quality_reports[dataset.dataset_id] = quality
        cleaning[dataset.dataset_id] = cleaning_record(dataset.frame)
        total_points += len(dataset.frame)
        output = dataset.frame.copy()
        output.to_csv(processed_dir / f"{dataset.dataset_id}.csv.gz", index=False, compression="gzip")
        summary_rows.append(_dataset_summary_row(dataset, quality))

        if test_type == "initial_capacity" and dataset.dataset_id.endswith("sp2_initial_capacity_20151016"):
            plot_paths[dataset.dataset_id] = _plot_initial_capacity(dataset, plots_dir, "初始容量测试")
        elif test_type == "dst":
            plot_paths[dataset.dataset_id] = _plot_dynamic(dataset, plots_dir, "DST 动态应力测试")
        elif test_type == "fuds":
            plot_paths[dataset.dataset_id] = _plot_dynamic(dataset, plots_dir, "FUDS 动态工况")
        elif test_type == "us06":
            plot_paths[dataset.dataset_id] = _plot_dynamic(dataset, plots_dir, "US06 动态工况")
        elif test_type == "bjdst":
            plot_paths[dataset.dataset_id] = _plot_dynamic(dataset, plots_dir, "BJDST 动态工况")
        elif test_type == "low_current_ocv":
            plot_paths[dataset.dataset_id] = _plot_ocv(dataset, plots_dir, "低电流 OCV", "08_low_current")
        elif test_type == "incremental_ocv":
            plot_paths[dataset.dataset_id] = _plot_ocv(dataset, plots_dir, "增量 OCV", "09_incremental")

    summary_frame = pd.DataFrame(summary_rows)
    summary_frame.to_csv(run.path / "dataset_summary.csv", index=False)
    write_json(run.path / "data_quality.json", quality_reports)
    write_json(run.path / "cleaning_record.json", cleaning)

    # 回填清单中的原始符号约定与时间单位
    sign_by_id = {dataset.dataset_id: dataset.current_sign for dataset in datasets}
    for record in records:
        if record["dataset_id"] in sign_by_id:
            record["original_current_sign"] = sign_by_id[record["dataset_id"]]
            record["original_time_unit"] = "s"
    save_manifest_payload(manifest)

    run.write_metadata(
        {
            "script": "scripts/calce_data_demo.py",
            "provider": "CALCE",
            "cell_model": "INR18650-20R",
            "data_source": "public_experimental_data",
        }
    )
    output_summary = {
        "data_source": "public_experimental_data",
        "datasets_parsed": len(datasets),
        "total_points": total_points,
        "quality_status_counts": {
            status: sum(1 for report in quality_reports.values() if report["status"] == status)
            for status in ("PASS", "WARN", "FAIL")
        },
        "dataset_summary_csv": str(run.path / "dataset_summary.csv"),
        "data_quality_json": str(run.path / "data_quality.json"),
        "plots": plot_paths,
        "dataset_summaries": json_safe(summary_rows),
    }
    run.write_summary(output_summary)
    run.log(f"解析 {len(datasets)} 个数据集，共 {total_points} 个采样点")
    run.flush_log()

    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "run_path": str(run.path),
                "datasets_parsed": len(datasets),
                "total_points": total_points,
                "quality_status_counts": output_summary["quality_status_counts"],
                "dataset_summary_csv": str(run.path / "dataset_summary.csv"),
                "plots_dir": str(plots_dir),
                "dataset_summaries": summary_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
