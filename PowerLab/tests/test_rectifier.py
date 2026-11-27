"""半波整流：真实瞬态波形、导通区间与时间加权指标。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.theory import half_wave_average_voltage, half_wave_load_power, half_wave_rms_voltage
from circuits.models import RectifierParameters
from circuits.rectifier import build_half_wave_rectifier
from simulations.runner import SimulationRunner


@pytest.fixture(scope="module")
def rectifier_data():
    parameters = RectifierParameters()
    circuit = build_half_wave_rectifier(parameters)
    result = SimulationRunner(25.0).run_transient(circuit, 2e-5, 0.1)
    time_s = result.data["time_s"].to_numpy()
    vin = result.data["vin_v"].to_numpy()
    vout = result.data["out_v"].to_numpy()
    return time_s, vin, vout, result


def test_rectifier_waveform_shape(rectifier_data):
    time_s, vin, vout, result = rectifier_data
    assert result.point_count == 5008
    assert time_s[0] == pytest.approx(0.0)
    assert time_s[-1] == pytest.approx(0.1, abs=1e-9)
    assert np.all(np.isfinite(vout))


def test_output_is_never_significantly_negative(rectifier_data):
    _, _, vout, _ = rectifier_data
    # 反偏漏电流约 1 nA 在 1 kOhm 负载上产生约 1 uV 负压，是真实模型行为。
    assert float(np.min(vout)) > -2e-6


def test_output_below_input_peak(rectifier_data):
    _, vin, vout, _ = rectifier_data
    assert float(np.max(vout)) < float(np.max(vin))
    assert float(np.max(vout)) > 8.5


def test_average_and_rms_match_ideal_within_tolerance(rectifier_data):
    time_s, _, vout, _ = rectifier_data
    span = time_s[-1] - time_s[0]
    average = float(np.trapz(vout, time_s) / span)
    rms = float(np.sqrt(np.trapz(vout**2, time_s) / span))
    assert average == pytest.approx(half_wave_average_voltage(10.0), rel=0.15)
    assert rms == pytest.approx(half_wave_rms_voltage(10.0), rel=0.15)
    power = rms**2 / 1_000.0
    assert power == pytest.approx(half_wave_load_power(10.0, 1_000.0), rel=0.25)


def test_conduction_fraction_is_slightly_below_half(rectifier_data):
    _, vin, vout, _ = rectifier_data
    conducting = vout > 1e-3
    fraction = float(np.count_nonzero(conducting)) / vout.size
    assert 0.2 < fraction < 0.5
    # 输出峰值应出现在输入峰值附近
    peak_index = int(np.argmax(vout))
    assert abs(float(vin[peak_index]) - float(np.max(vin))) < 0.5


def test_invalid_rectifier_parameters_raise():
    with pytest.raises(ValueError):
        RectifierParameters(input_peak_v=0.0)
    with pytest.raises(ValueError):
        RectifierParameters(frequency_hz=-50.0)
    with pytest.raises(ValueError):
        build_half_wave_rectifier(RectifierParameters(source_resistance_ohm=0.0))
