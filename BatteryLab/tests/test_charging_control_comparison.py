"""CC-CV 对照单元测试：判据函数与抗饱和网表补丁，不执行 SPICE。"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from hardening.charging_control_comparison import (
    ChargingComparisonError,
    _patch_antiwindup,
    soft_start_metrics,
)


class _DummyCircuit:
    def __init__(self, text: str) -> None:
        self.raw_spice = text


def test_patch_antiwindup_freezes_integrators_for_none():
    circuit = _DummyCircuit("R1 a b 1\nBVFRZ vfrz 0 V=limit(V(vraw),-10,10)\nBIFRZ ifrz 0 V=limit(V(iref),-5,5)\n")
    _patch_antiwindup(circuit, "none")
    assert "BVFRZ vfrz 0 V=0" in circuit.raw_spice
    assert "BIFRZ ifrz 0 V=0" in circuit.raw_spice


def test_patch_antiwindup_keeps_conditional_unchanged():
    original = "BVFRZ vfrz 0 V=limit(V(vraw),-10,10)\nBIFRZ ifrz 0 V=limit(V(iref),-5,5)\n"
    circuit = _DummyCircuit(original)
    _patch_antiwindup(circuit, "conditional")
    assert circuit.raw_spice == original


def test_patch_antiwindup_rejects_unknown_method():
    with pytest.raises(ChargingComparisonError):
        _patch_antiwindup(_DummyCircuit(""), "unknown")


def _waveform(peak: float, duration_s: float = 2e-3, dt: float = 1e-6):
    time = np.arange(0.0, duration_s, dt)
    current = np.minimum(peak, 1.0 + (peak - 1.0) * time / duration_s)
    voltage = np.full_like(time, 11.4)
    input_current = np.full_like(time, 2.0)
    inductor = np.full_like(time, peak * 1.1)
    cells = [np.full_like(time, 3.8) for _ in range(3)]
    return SimpleNamespace(
        time_s=time,
        charging_current_a=current,
        input_voltage_v=voltage,
        input_current_a=input_current,
        inductor_current_a=inductor,
        cell_voltages_v=cells,
    )


def _charger():
    return SimpleNamespace(power_stage=SimpleNamespace(switching_frequency_hz=100e3))


def test_soft_start_metrics_reports_peak_and_energy():
    metrics = soft_start_metrics(_waveform(1.1), _charger(), target_current=1.0)
    assert metrics["peak_charging_current_a"] == pytest.approx(1.1)
    assert metrics["overshoot_fraction"] == pytest.approx(0.1)
    assert metrics["startup_energy_j"] > 0
    assert metrics["bms_overvoltage_trip"] is False


def test_soft_start_metrics_flags_overvoltage():
    waveform = _waveform(1.1)
    waveform.cell_voltages_v = [np.full_like(waveform.time_s, 4.3) for _ in range(3)]
    metrics = soft_start_metrics(waveform, _charger(), target_current=1.0)
    assert metrics["bms_overvoltage_trip"] is True
    assert metrics["max_cell_voltage_v"] == pytest.approx(4.3)
