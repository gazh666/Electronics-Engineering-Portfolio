"""第七阶段脚本公共工具：运行目录、CSV/JSON 落盘与真实数据绘图。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from storage.result_store import RunDirectory, write_json  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLOTS_DIR_NAME = "plots"


def open_run(category: str) -> RunDirectory:
    run = RunDirectory(category)
    (run.path / PLOTS_DIR_NAME).mkdir(parents=True, exist_ok=True)
    return run


def write_metadata(
    run: RunDirectory,
    *,
    script: str,
    description: str,
    extra: Mapping[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "stage": 7,
        "script": script,
        "description": description,
        "python": "3.11 (conda kaifa_battery)",
        "current_sign": "discharge_positive",
        "data_types": [
            "public_experimental_data",
            "experimental_soc_reference",
            "synthetic_truth",
            "spice_simulation",
            "behavioral_sensor_simulation",
        ],
    }
    if extra:
        payload.update(dict(extra))
    run.write_metadata(payload)


def write_rows(run: RunDirectory, name: str, rows: Sequence[Mapping[str, Any]], header: Sequence[str] | None = None) -> Path:
    if not rows:
        raise ValueError("没有可写出的行")
    columns = list(header) if header is not None else list(rows[0].keys())
    return run.write_waveform(columns, [[row.get(column) for column in columns] for row in rows], name=name)


def write_payload(run: RunDirectory, name: str, payload: Any) -> Path:
    return write_json(run.path / name, payload)


def plot_series(
    run: RunDirectory,
    name: str,
    series: Mapping[str, tuple[Sequence[float], Sequence[float]]],
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    horizontal: Sequence[tuple[float, str]] | None = None,
    styles: Mapping[str, dict[str, Any]] | None = None,
) -> Path:
    figure, axes = plt.subplots(figsize=(9, 4.6))
    for label, (x_values, y_values) in series.items():
        style = (styles or {}).get(label, {})
        axes.plot(np.asarray(x_values, dtype=float), np.asarray(y_values, dtype=float), label=label, **style)
    if horizontal:
        for value, label in horizontal:
            axes.axhline(float(value), linestyle="--", linewidth=1.0, color="gray")
            axes.text(
                float(np.min([np.min(np.asarray(x, dtype=float)) for x, _ in series.values()])),
                float(value),
                label,
                fontsize=8,
                color="gray",
                va="bottom",
            )
    axes.set_title(title)
    axes.set_xlabel(xlabel)
    axes.set_ylabel(ylabel)
    axes.grid(True, alpha=0.3)
    axes.legend(fontsize=8)
    figure.tight_layout()
    path = run.path / PLOTS_DIR_NAME / name
    figure.savefig(path, dpi=120)
    plt.close(figure)
    return path


def plot_bar(
    run: RunDirectory,
    name: str,
    labels: Sequence[str],
    values: Sequence[float | None],
    *,
    title: str,
    ylabel: str,
) -> Path:
    figure, axes = plt.subplots(figsize=(9, 4.4))
    numeric = [0.0 if value is None else float(value) for value in values]
    axes.bar(range(len(labels)), numeric, color="#4C78A8")
    axes.set_xticks(range(len(labels)))
    axes.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    axes.set_title(title)
    axes.set_ylabel(ylabel)
    axes.grid(True, axis="y", alpha=0.3)
    figure.tight_layout()
    path = run.path / PLOTS_DIR_NAME / name
    figure.savefig(path, dpi=120)
    plt.close(figure)
    return path


def plot_categories(
    run: RunDirectory,
    name: str,
    categories: Sequence[str],
    series: Mapping[str, Sequence[float | None]],
    *,
    title: str,
    ylabel: str,
    horizontal: float | None = None,
) -> Path:
    """分组柱状图：x 轴为离散类别（如 cell1/cell2）。"""
    figure, axes = plt.subplots(figsize=(9, 4.4))
    positions = np.arange(len(categories), dtype=float)
    count = max(1, len(series))
    width = 0.8 / count
    for index, (label, values) in enumerate(series.items()):
        numeric = [0.0 if value is None else float(value) for value in values]
        axes.bar(positions + (index - (count - 1) / 2.0) * width, numeric, width, label=label)
    if horizontal is not None:
        axes.axhline(float(horizontal), linestyle="--", linewidth=1.0, color="gray")
    axes.set_xticks(positions)
    axes.set_xticklabels(categories, fontsize=9)
    axes.set_title(title)
    axes.set_ylabel(ylabel)
    axes.grid(True, axis="y", alpha=0.3)
    axes.legend(fontsize=8)
    figure.tight_layout()
    path = run.path / PLOTS_DIR_NAME / name
    figure.savefig(path, dpi=120)
    plt.close(figure)
    return path


def plot_histogram(
    run: RunDirectory,
    name: str,
    values: Sequence[float],
    *,
    title: str,
    xlabel: str,
    bins: int = 40,
) -> Path:
    figure, axes = plt.subplots(figsize=(8, 4.2))
    axes.hist(np.asarray(values, dtype=float), bins=bins, color="#F58518", alpha=0.85)
    axes.set_title(title)
    axes.set_xlabel(xlabel)
    axes.set_ylabel("count")
    axes.grid(True, alpha=0.3)
    figure.tight_layout()
    path = run.path / PLOTS_DIR_NAME / name
    figure.savefig(path, dpi=120)
    plt.close(figure)
    return path


def finish(run: RunDirectory, message: str) -> None:
    run.log(message)
    run.flush_log()
