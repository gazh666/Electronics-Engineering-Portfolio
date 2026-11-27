"""第四阶段采集实验落盘：运行目录、波形、指标、图表与元数据。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from circuits.spice_utils import get_solve_count, reset_solve_counter
from storage.result_store import RunDirectory, json_safe, utc_now, write_json


def new_sensing_run(category: str = "sensing") -> RunDirectory:
    reset_solve_counter()
    run = RunDirectory(category)
    run.log(f"启动采集实验: {category}")
    return run


def write_frame(run: RunDirectory, name: str, frame: pd.DataFrame) -> Path:
    path = run.path / name
    frame.to_csv(path, index=False, float_format="%.12g", encoding="utf-8")
    return path


def write_rows(run: RunDirectory, name: str, rows: Sequence[Mapping[str, Any]]) -> Path:
    frame = pd.DataFrame([dict(row) for row in rows])
    return write_frame(run, name, frame)


def write_plots(
    run: RunDirectory,
    plot_specs: Sequence[tuple[str, Callable[..., Path], dict[str, Any]]],
) -> dict[str, str]:
    output: dict[str, str] = {}
    plot_dir = run.path / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    for name, function, kwargs in plot_specs:
        path = function(path=plot_dir / name, **kwargs)
        output[name] = str(path)
    return output


def finalize_run(
    run: RunDirectory,
    *,
    script: str,
    summary: Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    solves = get_solve_count()
    payload = {
        "script": script,
        "run_id": run.run_id,
        "generated_at": utc_now(),
        "real_spice_solves": solves,
        "data_sources": [
            "spice_simulation",
            "adc_behavioral_model",
            "analytical_theory",
            "educational_assumption",
            "datasheet_specification",
        ],
        **dict(summary),
    }
    write_json(run.path / "summary.json", payload)
    run.write_metadata({**dict(metadata or {}), "script": script, "real_spice_solves": solves})
    run.log(f"真实 SPICE 求解次数={solves}")
    run.flush_log()
    return payload


def array_frame(columns: Mapping[str, Sequence[float]]) -> pd.DataFrame:
    lengths = {len(value) for value in columns.values()}
    if len(lengths) != 1:
        raise ValueError("所有列长度必须一致")
    return pd.DataFrame({key: np.asarray(value, dtype=float) for key, value in columns.items()})
