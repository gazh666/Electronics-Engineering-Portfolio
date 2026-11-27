"""采集链路：模拟输出 → ADC → 工程量恢复 → 校准 → 状态判定。

该模块只接收"已经过真实 SPICE 或解析模型得到的模拟电压"，不负责电路求解，
从而把电路仿真与数据恢复解耦，避免用 Python 输出冒充 SPICE 结果。
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from sensing import adc as adc_module
from sensing.calibration import CalibrationModel, identity_calibration
from sensing.current_decoder import current_from_output
from sensing.models import (
    STATUS_COMMON_MODE_OUT_OF_RANGE,
    STATUS_INVALID_INPUT,
    STATUS_SATURATED,
    STATUS_SENSOR_OPEN,
    STATUS_SENSOR_SHORT,
    STATUS_VALID,
    MeasurementResult,
    make_result,
)
from sensing.temperature_decoder import temperature_from_voltage
from sensing.voltage_decoder import cell_voltage_from_output


def _convert(analog_v: float, config: adc_module.ADCConfig, errors: adc_module.ADCErrorModel | None, rng):
    if errors is None:
        return adc_module.adc_convert(analog_v, config)
    return adc_module.adc_convert_real(analog_v, config, errors, rng)


def measure_voltage(
    *,
    channel_name: str,
    reference_cell_v: float | None,
    analog_output_v: float,
    gain: float,
    reference_v: float,
    adc_config: adc_module.ADCConfig,
    adc_errors: adc_module.ADCErrorModel | None = None,
    calibration: CalibrationModel | None = None,
    output_low_v: float = 0.0,
    output_high_v: float = 5.0,
    pin_common_mode_v: float | None = None,
    common_mode_min_v: float = 0.0,
    common_mode_max_v: float = 5.0,
    rng: np.random.Generator | None = None,
    run_id: str | None = None,
    circuit_model: str = "four_resistor_differential_amplifier",
    parameter_source: str = "educational_assumption",
) -> MeasurementResult:
    model = calibration or identity_calibration()
    sample = _convert(analog_output_v, adc_config, adc_errors, rng)
    status = STATUS_VALID
    note = ""
    if analog_output_v <= output_low_v or analog_output_v >= output_high_v or sample.saturated:
        status = STATUS_SATURATED
        note = "放大器输出或 ADC 输入饱和"
    elif pin_common_mode_v is not None and not (common_mode_min_v <= pin_common_mode_v <= common_mode_max_v):
        status = STATUS_COMMON_MODE_OUT_OF_RANGE
        note = f"运放引脚共模 {pin_common_mode_v:.4f} V 超出 [{common_mode_min_v}, {common_mode_max_v}]"

    estimated = model.apply(
        cell_voltage_from_output(sample.decoded_voltage_v, gain=gain, reference_v=reference_v)
    )
    return make_result(
        channel_name=channel_name,
        physical_input=None if reference_cell_v is None else float(reference_cell_v),
        analog_output_v=float(analog_output_v),
        adc_code=sample.code,
        estimated_value=float(estimated),
        unit="V",
        status=status,
        data_source="adc_behavioral_model",
        run_id=run_id,
        circuit_model=circuit_model,
        calibration_id=model.calibration_id or None,
        raw_signal=float(analog_output_v),
        filtered_signal=float(analog_output_v),
        parameter_source=parameter_source,
        note=note,
    )


def measure_current(
    *,
    channel_name: str,
    reference_current_a: float | None,
    analog_output_v: float,
    amplifier_gain: float,
    shunt_ohm: float,
    zero_reference_v: float,
    adc_config: adc_module.ADCConfig,
    adc_errors: adc_module.ADCErrorModel | None = None,
    calibration: CalibrationModel | None = None,
    output_low_v: float = 0.0,
    output_high_v: float = 5.0,
    common_mode_v: float | None = None,
    common_mode_min_v: float = -4.0,
    common_mode_max_v: float = 80.0,
    rng: np.random.Generator | None = None,
    run_id: str | None = None,
    circuit_model: str = "ina240_specification_reference_behavioral_model",
    parameter_source: str = "datasheet_specification",
) -> MeasurementResult:
    model = calibration or identity_calibration()
    sample = _convert(analog_output_v, adc_config, adc_errors, rng)
    status = STATUS_VALID
    note = ""
    if analog_output_v <= output_low_v or analog_output_v >= output_high_v or sample.saturated:
        status = STATUS_SATURATED
        note = "电流放大器输出或 ADC 输入饱和"
    elif common_mode_v is not None and not (common_mode_min_v <= common_mode_v <= common_mode_max_v):
        status = STATUS_COMMON_MODE_OUT_OF_RANGE
        note = f"电流放大器共模 {common_mode_v:.4f} V 超出 [{common_mode_min_v}, {common_mode_max_v}]"

    estimated = model.apply(
        current_from_output(
            sample.decoded_voltage_v,
            gain=amplifier_gain,
            shunt_ohm=shunt_ohm,
            reference_v=zero_reference_v,
        )
    )
    return make_result(
        channel_name=channel_name,
        physical_input=None if reference_current_a is None else float(reference_current_a),
        analog_output_v=float(analog_output_v),
        adc_code=sample.code,
        estimated_value=float(estimated),
        unit="A",
        status=status,
        data_source="adc_behavioral_model",
        run_id=run_id,
        circuit_model=circuit_model,
        calibration_id=model.calibration_id or None,
        raw_signal=float(analog_output_v),
        filtered_signal=float(analog_output_v),
        parameter_source=parameter_source,
        note=note,
    )


def measure_temperature(
    *,
    channel_name: str,
    reference_temperature_c: float | None,
    analog_output_v: float,
    adc_config: adc_module.ADCConfig,
    r25_ohm: float = 10000.0,
    beta_k: float = 3950.0,
    pullup_ohm: float = 10000.0,
    excitation_v: float = 3.3,
    adc_errors: adc_module.ADCErrorModel | None = None,
    calibration: CalibrationModel | None = None,
    rng: np.random.Generator | None = None,
    run_id: str | None = None,
    circuit_model: str = "ntc_grounded_pullup_divider",
    parameter_source: str = "educational_assumption",
) -> MeasurementResult:
    model = calibration or identity_calibration()
    sample = _convert(analog_output_v, adc_config, adc_errors, rng)
    status = STATUS_VALID
    note = ""
    estimated: float | None = None
    if analog_output_v <= 0.02 * excitation_v:
        status = STATUS_SENSOR_SHORT
        note = "NTC 分压接近 0，疑似传感器短路"
    elif analog_output_v >= 0.98 * excitation_v:
        status = STATUS_SENSOR_OPEN
        note = "NTC 分压接近激励电压，疑似传感器开路"
    elif sample.saturated:
        status = STATUS_SATURATED
        note = "ADC 输入饱和"
    else:
        try:
            estimated = model.apply(
                temperature_from_voltage(
                    sample.decoded_voltage_v,
                    r25_ohm=r25_ohm,
                    beta_k=beta_k,
                    pullup_ohm=pullup_ohm,
                    excitation_v=excitation_v,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 必须保留无法反演的真实原因
            status = STATUS_INVALID_INPUT
            note = f"温度无法反演: {type(exc).__name__}: {exc}"

    return make_result(
        channel_name=channel_name,
        physical_input=None if reference_temperature_c is None else float(reference_temperature_c),
        analog_output_v=float(analog_output_v),
        adc_code=sample.code,
        estimated_value=estimated,
        unit="degC",
        status=status,
        data_source="adc_behavioral_model",
        run_id=run_id,
        circuit_model=circuit_model,
        calibration_id=model.calibration_id or None,
        raw_signal=float(analog_output_v),
        filtered_signal=float(analog_output_v),
        parameter_source=parameter_source,
        note=note,
    )


def results_to_rows(results: Sequence[MeasurementResult]) -> list[dict[str, object]]:
    return [result.as_dict() for result in results]
