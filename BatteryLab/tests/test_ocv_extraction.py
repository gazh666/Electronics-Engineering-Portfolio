"""OCV-SOC 提取、迟滞与查表模型覆盖性。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from battery_models.ocv_model import IdentifiedOcvModel, OcvError
from identification.ocv_extractor import (
    OcvExtractionError,
    build_ocv_table,
    extract_low_current_ocv,
    relaxation_points,
)


def _two_branch_frame(capacity_ah=2.0, current=0.1, points=4001):
    """构造：满充后 0.1 A 放电到空，再 0.1 A 充电回满。"""
    dt = 5.0
    steps = []
    time_offset = 0.0
    step_index = 3.0
    for direction, sign in (("discharge", 1.0), ("charge", -1.0)):
        duration = capacity_ah / current * 3600.0
        time = np.linspace(0.0, duration, points)
        soc_start = 1.0 if direction == "discharge" else 0.0
        soc = soc_start - sign * (time / duration) * 1.0
        voltage = 3.0 + 1.2 * np.clip(soc, 0.0, 1.0) ** 0.8
        steps.append(
            pd.DataFrame(
                {
                    "time_s": time + time_offset,
                    "current_a": sign * current,
                    "voltage_v": voltage,
                    "step_index": step_index,
                    "source_file": "synthetic.xls",
                    "source_sheet": "Channel_1",
                }
            )
        )
        time_offset += duration + 100.0
        step_index += 1.0
    return pd.concat(steps, ignore_index=True)


def test_extract_low_current_ocv_shapes():
    frame = _two_branch_frame()
    result = extract_low_current_ocv(frame, capacity_ah=2.0, grid_points=101)
    assert len(result["average"]) == 101
    assert result["metrics"]["common_points"] > 50
    average = result["average"]["ocv_v"].to_numpy(dtype=float)
    assert np.all(np.diff(average[np.isfinite(average)]) > -0.2)
    assert result["hysteresis"]["hysteresis_v"].abs().max() < 0.1


def test_extract_requires_both_low_current_branches():
    frame = _two_branch_frame()
    frame = frame[frame["current_a"] > 0]
    with pytest.raises(OcvExtractionError):
        extract_low_current_ocv(frame, capacity_ah=2.0)


def test_build_ocv_table_covers_unit_interval():
    frame = _two_branch_frame()
    result = extract_low_current_ocv(frame, capacity_ah=2.0, grid_points=51)
    soc, ocv, metadata = build_ocv_table(result["average"])
    assert soc[0] == 0.0
    assert soc[-1] == 1.0
    assert np.all(np.diff(soc) > 0)
    assert metadata["points"] == len(soc)
    assert metadata["endpoint_extension"] in ("none", "constant_hold_low_soc", "constant_hold_high_soc", "constant_hold_both_ends")


def test_identified_ocv_model_rejects_extrapolation():
    model = IdentifiedOcvModel((0.0, 0.5, 1.0), (3.0, 3.6, 4.2))
    assert model.voltage(0.5) == pytest.approx(3.6)
    with pytest.raises(OcvError):
        model.voltage(1.2)
    with pytest.raises(OcvError):
        model.voltage(-0.1)


def test_identified_ocv_requires_unit_interval():
    with pytest.raises(OcvError):
        IdentifiedOcvModel((0.1, 1.0), (3.0, 4.2))


def test_relaxation_points_flags_incomplete():
    time = np.concatenate([np.arange(0, 100, 10.0), np.arange(100, 3100, 10.0)])
    current = np.concatenate([np.full(10, 1.0), np.zeros(300)])
    voltage = np.concatenate([np.full(10, 3.5), 3.5 + 0.1 * (1 - np.exp(-(np.arange(300) * 10.0) / 3000.0))])
    frame = pd.DataFrame({"time_s": time, "current_a": current, "voltage_v": voltage})
    points, report = relaxation_points(frame, initial_soc=0.5, capacity_ah=2.0, minimum_rest_s=1000.0)
    assert report["rest_segments"] == 1
    assert points["quality_status"].iloc[0] in ("IDENTIFIED", "RELAXATION_INCOMPLETE")
