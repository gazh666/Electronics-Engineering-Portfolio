"""CALCE 电流符号检测：修复低电流 OCV 文件被误判为 UNKNOWN 的缺陷。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from datasets.calce_loader import load_archive

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
LOW_CURRENT = RAW_DIR / "SP1_25C_LC_OCV_11_5_2015.zip"
CAPACITY = RAW_DIR / "SP2_Initial_capacity_10_16_2015.zip"


@pytest.mark.skipif(not LOW_CURRENT.exists(), reason="缺少 CALCE 低电流 OCV 原始文件")
def test_low_current_ocv_sign_detected_as_charge_positive():
    loaded = load_archive(LOW_CURRENT, dataset_id="test_ocv", cell_id="SP1")
    assert loaded.current_sign == "charge_positive"
    frame = loaded.frame
    charge_steps = frame[frame["step_index"] == 1.0]
    discharge_steps = frame[frame["step_index"] == 3.0]
    assert charge_steps["current_a"].mean() < 0
    assert discharge_steps["current_a"].mean() > 0


@pytest.mark.skipif(not CAPACITY.exists(), reason="缺少 CALCE 容量原始文件")
def test_capacity_file_sign_normalized_to_discharge_positive():
    """原始文件以正电流表示充电；加载后必须归一化为放电为正。"""
    loaded = load_archive(CAPACITY, dataset_id="test_capacity", cell_id="SP2")
    assert loaded.current_sign == "charge_positive"
    frame = loaded.frame
    charge = frame[frame["step_index"] == 2.0]
    discharge = frame[frame["step_index"] == 6.0]
    assert charge["current_a"].mean() < 0
    assert discharge["current_a"].mean() > 0
    assert discharge["voltage_v"].iloc[-1] < discharge["voltage_v"].iloc[0]
    assert np.all(np.diff(discharge["time_s"].to_numpy()) > 0)
