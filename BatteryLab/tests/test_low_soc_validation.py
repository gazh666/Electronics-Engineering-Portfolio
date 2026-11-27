"""低 SOC 分区误差单元测试：用合成残差表验证统计口径，不读历史数据。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hardening.low_soc_model_analysis import band_metrics, model_comparison


def _frame() -> pd.DataFrame:
    soc = np.array([0.02, 0.03, 0.12, 0.30, 0.70, 0.90])
    measured = np.full_like(soc, 3.4)
    return pd.DataFrame({
        "experiment": ["demo"] * soc.size,
        "model": ["second_order_rc"] * soc.size,
        "measured_voltage_v": measured,
        "predicted_voltage_v": measured + np.array([0.10, 0.20, 0.02, 0.01, 0.005, 0.002]),
        "soc_reference": soc,
    })


def test_band_metrics_splits_into_registered_bands():
    rows = band_metrics(_frame())
    lows = [row["band_low"] for row in rows]
    assert lows == pytest.approx([0.0, 0.10, 0.20, 0.50])
    zero = next(row for row in rows if row["band_low"] == 0.0)
    assert zero["points"] == 2
    assert zero["rmse_mv"] == pytest.approx(np.sqrt((100.0 ** 2 + 200.0 ** 2) / 2), rel=1e-9)


def test_band_metrics_reports_signed_mean_error():
    rows = band_metrics(_frame())
    zero = next(row for row in rows if row["band_low"] == 0.0)
    assert zero["mean_error_mv"] == pytest.approx(150.0)


def test_model_comparison_reports_single_row_per_group():
    rows = model_comparison(_frame())
    assert len(rows) == 1
    assert rows[0]["experiment"] == "demo"
    assert rows[0]["soc_min"] == pytest.approx(0.02)
    assert rows[0]["soc_max"] == pytest.approx(0.90)
    assert rows[0]["max_abs_mv"] == pytest.approx(200.0)


def test_band_metrics_drops_empty_bands():
    frame = _frame()
    frame = frame[frame["soc_reference"] < 0.1]
    rows = band_metrics(frame)
    assert [row["band_low"] for row in rows] == pytest.approx([0.0])
