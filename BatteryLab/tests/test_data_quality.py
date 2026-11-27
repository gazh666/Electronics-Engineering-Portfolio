"""数据质量检查测试（人工构造数据仅用于异常处理验证）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from datasets.data_quality import check_frame, cleaning_record


def _frame(rows: int = 20, voltage: float = 3.8, current: float = 1.0) -> pd.DataFrame:
    time_s = np.arange(rows, dtype=float)
    return pd.DataFrame(
        {
            "dataset_id": "synthetic",
            "cell_id": "TEST",
            "cycle_index": np.ones(rows),
            "step_index": np.ones(rows),
            "segment_id": ["1-1"] * rows,
            "time_s": time_s,
            "voltage_v": np.full(rows, voltage),
            "current_a": np.full(rows, current),
            "temperature_c": np.full(rows, np.nan),
            "charge_capacity_ah": np.zeros(rows),
            "discharge_capacity_ah": np.linspace(0.0, 0.005, rows),
            "source_file": ["synthetic.xlsx"] * rows,
            "source_sheet": ["Sheet1"] * rows,
            "source_row": np.arange(2, rows + 2),
        }
    )


def test_clean_frame_passes():
    report = check_frame(_frame())
    assert report["status"] == "PASS"
    assert report["rows"] == 20
    assert report["voltage_out_of_range"] == 0


def test_voltage_out_of_range_warns():
    frame = _frame()
    frame.loc[0, "voltage_v"] = 9.0
    report = check_frame(frame)
    assert report["voltage_out_of_range"] == 1
    assert report["status"] in {"WARN", "FAIL"}


def test_duplicate_rows_detected():
    frame = pd.concat([_frame(), _frame().iloc[[0]]], ignore_index=True)
    report = check_frame(frame)
    assert report["duplicate_rows"] == 1


def test_time_reset_detected():
    frame = pd.concat([_frame(rows=10, voltage=3.9), _frame(rows=10, voltage=3.8)], ignore_index=True)
    report = check_frame(frame)
    assert report["time_resets"] == 1
    assert report["negative_intervals"] == 1
    assert report["segment_count"] == 1


def test_missing_and_infinity_counts():
    frame = _frame()
    frame.loc[2, "voltage_v"] = np.nan
    frame.loc[3, "current_a"] = np.inf
    report = check_frame(frame)
    assert report["missing"]["voltage_v"] == 1
    assert report["infinity_counts"]["current_a"] == 1
    assert report["status"] in {"WARN", "FAIL"}


def test_cleaning_record_keeps_all_points():
    frame = _frame()
    record = cleaning_record(frame)
    assert record["raw_points"] == record["processed_points"] == len(frame)
    assert record["removed_points"] == 0
    assert record["original_file_reference"] == ["synthetic.xlsx"]
