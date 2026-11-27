"""波形提取：复数保留、方向约定与异常处理。"""

from __future__ import annotations

import numpy as np
import pytest

from simulations.exceptions import InvalidWaveformError
from simulations.waveform_extractor import (
    analysis_branches,
    analysis_nodes,
    branch_waveform,
    extract_ac_node_parts,
    extract_complex_waveform,
    extract_dc_sweep,
    extract_operating_point_nodes,
    extract_real_waveform,
    extract_transient_time,
    node_waveform,
    require_equal_lengths,
    source_branch_key,
    source_branch_waveform,
    supply_current,
)


class FakeAnalysis:
    def __init__(self) -> None:
        self.nodes = {
            "vin": np.array([1.0 + 0.0j, 2.0 + 0.0j]),
            "out": np.array([0.5 + 0.1j, 1.0 - 0.2j]),
            "v-sweep": np.array([0.0, 1.0]),
        }
        self.branches = {"vinput": np.array([-0.001, -0.002])}
        self.sweep = np.array([0.0, 1.0])
        self.time = np.array([0.0, 1e-3])
        self.frequency = np.array([1.0, 10.0])


def test_source_branch_key_mapping():
    assert source_branch_key("input") == "vinput"
    assert source_branch_key("Vinput") == "vinput"
    assert source_branch_key("bias") == "vbias"
    with pytest.raises(ValueError):
        source_branch_key("  ")


def test_complex_waveform_is_preserved():
    values = extract_complex_waveform([1 + 2j, 3 - 4j])
    assert np.iscomplexobj(values)
    assert values[0] == 1 + 2j


def test_node_and_branch_extraction_keep_imaginary_part():
    analysis = FakeAnalysis()
    real, imag = extract_ac_node_parts(analysis, "out")
    assert real[0] == pytest.approx(0.5)
    assert imag[0] == pytest.approx(0.1)
    branch = branch_waveform(analysis, "vinput")
    assert branch[0] == pytest.approx(-0.001)


def test_supply_current_negates_without_abs():
    raw = source_branch_waveform(FakeAnalysis(), "input")
    supplied = supply_current(raw)
    assert supplied[0] == pytest.approx(0.001)
    assert supplied[1] == pytest.approx(0.002)


def test_axis_extraction():
    analysis = FakeAnalysis()
    assert extract_dc_sweep(analysis)[1] == 1.0
    assert extract_transient_time(analysis)[1] == 1e-3
    assert analysis_nodes(analysis) == ["vin", "out"]
    assert analysis_branches(analysis) == ["vinput"]


def test_operating_point_requires_scalar_values():
    analysis = FakeAnalysis()
    analysis.nodes = {"out": np.array([6.0, 7.0])}
    with pytest.raises(InvalidWaveformError):
        extract_operating_point_nodes(analysis)
    analysis.nodes = {"out": np.array([6.0])}
    analysis.branches = {"vinput": np.array([-0.006])}
    assert extract_operating_point_nodes(analysis) == {"out": 6.0}

def test_missing_node_or_branch_raises():
    analysis = FakeAnalysis()
    with pytest.raises(InvalidWaveformError):
        node_waveform(analysis, "missing")
    with pytest.raises(InvalidWaveformError):
        branch_waveform(analysis, "vmissing")


@pytest.mark.parametrize("bad", [[np.nan, 1.0], [np.inf, 1.0], [], [[1.0, 2.0]]])
def test_invalid_real_waveforms_rejected(bad):
    with pytest.raises(InvalidWaveformError):
        extract_real_waveform(bad)


def test_require_equal_lengths():
    assert require_equal_lengths(a=np.zeros(3), b=np.ones(3)) == 3
    with pytest.raises(InvalidWaveformError):
        require_equal_lengths(a=np.zeros(3), b=np.ones(2))
    with pytest.raises(ValueError):
        require_equal_lengths()
