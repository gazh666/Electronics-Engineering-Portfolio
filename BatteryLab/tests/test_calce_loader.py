"""CALCE 解析测试（使用实际下载文件）。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from datasets.calce_loader import UNIFIED_COLUMNS, load_archive

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW = PROJECT_ROOT / "data" / "raw"
INITIAL_ZIP = RAW / "SP2_Initial_capacity_10_16_2015.zip"


pytestmark = pytest.mark.skipif(not INITIAL_ZIP.exists(), reason="真实 CALCE 文件未下载")


def test_load_real_initial_capacity():
    dataset = load_archive(INITIAL_ZIP, dataset_id="test_sp2_initial", cell_id="SP2")
    frame = dataset.frame
    assert list(frame.columns) == UNIFIED_COLUMNS
    assert len(frame) > 1000
    assert dataset.current_sign == "charge_positive"
    assert frame["source_sheet"].iloc[0].startswith("Channel")
    assert (frame["source_file"] == dataset.source_files[0]).all()
    assert frame["voltage_v"].between(2.0, 4.5).mean() > 0.99
    assert frame["current_a"].abs().max() < 5.0


def test_sign_converted_to_discharge_positive():
    dataset = load_archive(INITIAL_ZIP, dataset_id="test_sp2_sign", cell_id="SP2")
    frame = dataset.frame
    discharge_growth = frame["discharge_capacity_ah"].diff() > 1e-6
    positive_current = frame["current_a"] > 0
    both = discharge_growth & positive_current
    assert both.sum() > 10, "放电容量增长区间应出现正电流（内部约定）"


def test_original_file_untouched(tmp_path):
    source = INITIAL_ZIP
    before = source.stat().st_size
    load_archive(source, dataset_id="test_untouched", cell_id="SP2")
    assert source.stat().st_size == before


def test_corrupt_archive_raises(tmp_path):
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("note.txt", "not an excel file")
    with pytest.raises(ValueError):
        load_archive(broken, dataset_id="broken", cell_id="UNKNOWN")
