"""Task 25：零点校准、两点校准与校准集/验证集分离演示。

每个通道使用一次真实 ngspice 直流扫描生成连续曲线，再在预先指定的
校准点与独立验证点上读取读数。校准系数只由校准点拟合。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from analysis.sensing_metrics import compute_metrics
from circuits.current_sensing import CurrentSenseConfig, sweep_current_fast
from circuits.differential_amplifier import (
    DifferentialAmplifierConfig,
    sweep_high_voltage_fast,
    teaching_opamp_spec,
)
from circuits.ntc_sensing import NtcConfig, sweep_temperatures_fast
from circuits.opamp_models import CurrentAmplifierSpec
from scripts.stage4_common import adc_settings
from sensing.calibration import fit_two_point_calibration, fit_zero_calibration
from sensing.temperature_decoder import temperature_from_voltage
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame, write_plots
from storage.result_store import write_json
from visualization.plots import plot_multi_series

SOURCE = "真实 ngspice 直流扫描（spice_simulation）"


def _interp(points, xs, ys):
    return [float(np.interp(point, xs, ys)) for point in points]


def main() -> int:
    adc = adc_settings()
    run = new_sensing_run("sensing")

    # --- 电压通道：非理想器件实例 ---
    nominal_amp = DifferentialAmplifierConfig(r1_ohm=100e3, r2_ohm=50e3, r3_ohm=100e3, r4_ohm=50e3, reference_v=0.2)
    actual_amp = DifferentialAmplifierConfig(r1_ohm=100.1e3, r2_ohm=49.95e3, r3_ohm=99.9e3, r4_ohm=50.05e3, reference_v=0.2)
    opamp = teaching_opamp_spec(actual_amp, offset_v=80e-6, gbw_hz=1e6)

    voltage_cal_points = [3.0, 4.1]
    voltage_validation_points = [2.5, 3.3, 3.7, 3.9, 4.25]
    dense_voltage = np.arange(2.5, 4.2501, 0.01)
    voltage_sweep = sweep_high_voltage_fast(dense_voltage.tolist(), actual_amp, opamp=opamp)
    voltage_x = [row["vhigh_v"] for row in voltage_sweep]
    voltage_vout = [row["vout_v"] for row in voltage_sweep]

    def voltage_pre(point: float) -> float:
        output = float(np.interp(point, voltage_x, voltage_vout))
        return (output - nominal_amp.reference_v) / nominal_amp.nominal_gain

    voltage_cal_rows = []
    voltage_cal_measured = []
    for point in voltage_cal_points:
        pre = voltage_pre(point)
        voltage_cal_measured.append(pre)
        voltage_cal_rows.append({"type": "calibration", "reference_v": point, "pre_cal_v": pre})
    voltage_model = fit_two_point_calibration(
        voltage_cal_points[0], voltage_cal_measured[0], voltage_cal_points[1], voltage_cal_measured[1], calibration_id="voltage_two_point"
    )

    voltage_rows = []
    references = []
    pre_values = []
    post_values = []
    for point in voltage_validation_points:
        pre = voltage_pre(point)
        post = voltage_model.apply(pre)
        references.append(point)
        pre_values.append(pre)
        post_values.append(post)
        voltage_rows.append(
            {
                "type": "validation",
                "reference_v": point,
                "pre_cal_v": pre,
                "pre_error_mv": (pre - point) * 1000.0,
                "post_cal_v": post,
                "post_error_mv": (post - point) * 1000.0,
            }
        )

    # --- 电流通道 ---
    nominal_current = CurrentSenseConfig(shunt_ohm=0.01, amplifier_gain=50.0, reference_v=1.65)
    actual_shunt = 0.01005
    actual_gain = 50.0 * (1.0 - 0.0015)
    current_amp_spec = CurrentAmplifierSpec(
        name="ina240_cal",
        gain=actual_gain,
        reference_voltage_v=1.65,
        input_offset_v=20e-6,
        cmrr_db=132.0,
        bandwidth_hz=400e3,
        output_low_v=0.1,
        output_high_v=4.9,
    )
    current_config = CurrentSenseConfig(shunt_ohm=actual_shunt, amplifier_gain=actual_gain, reference_v=1.65)
    current_cal_points = [-2.0, 2.0]
    current_validation_points = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]

    dense_current = np.arange(-2.5, 2.5001, 0.01)
    current_sweep = sweep_current_fast(dense_current.tolist(), current_config, amplifier_spec=current_amp_spec)
    current_x = [row["current_a"] for row in current_sweep]
    current_vout = [row["vout_v"] for row in current_sweep]

    def current_pre(point: float) -> float:
        output = float(np.interp(point, current_x, current_vout))
        return (output - nominal_current.reference_v) / (nominal_current.amplifier_gain * nominal_current.shunt_ohm)

    zero_measured = current_pre(0.0)
    zero_model = fit_zero_calibration(zero_measured, calibration_id="current_zero")

    current_cal_measured = []
    current_cal_rows = []
    for point in current_cal_points:
        pre = current_pre(point)
        current_cal_measured.append(pre)
        current_cal_rows.append({"type": "calibration", "reference_a": point, "pre_cal_a": pre})
    current_model = fit_two_point_calibration(
        current_cal_points[0], current_cal_measured[0], current_cal_points[1], current_cal_measured[1], calibration_id="current_two_point"
    )

    current_rows = []
    current_references = []
    current_pre_values = []
    current_zero_values = []
    current_post_values = []
    for point in current_validation_points:
        pre = current_pre(point)
        zero_corrected = zero_model.apply(pre)
        post = current_model.apply(pre)
        current_references.append(point)
        current_pre_values.append(pre)
        current_zero_values.append(zero_corrected)
        current_post_values.append(post)
        current_rows.append(
            {
                "type": "validation",
                "reference_a": point,
                "pre_cal_a": pre,
                "pre_error_ma": (pre - point) * 1000.0,
                "zero_cal_a": zero_corrected,
                "zero_error_ma": (zero_corrected - point) * 1000.0,
                "two_point_a": post,
                "two_point_error_ma": (post - point) * 1000.0,
            }
        )

    # --- 温度通道 ---
    nominal_ntc = NtcConfig()
    actual_ntc = NtcConfig(r25_ohm=10100.0, beta_k=3926.3, pullup_ohm=9990.0)
    temperature_cal_points = [0.0, 60.0]
    temperature_validation_points = [10.0, 20.0, 25.0, 30.0, 40.0, 50.0]

    dense_temperature = np.arange(0.0, 60.001, 0.5)
    temperature_sweep = sweep_temperatures_fast(dense_temperature.tolist(), actual_ntc)
    temperature_x = [row["temperature_c"] for row in temperature_sweep]
    temperature_voltage = [row["spice_voltage_v"] for row in temperature_sweep]

    def temperature_pre(point: float) -> float:
        voltage = float(np.interp(point, temperature_x, temperature_voltage))
        return temperature_from_voltage(
            voltage,
            r25_ohm=nominal_ntc.r25_ohm,
            beta_k=nominal_ntc.beta_k,
            pullup_ohm=nominal_ntc.pullup_ohm,
            excitation_v=nominal_ntc.excitation_v,
        )

    temperature_cal_measured = []
    temperature_cal_rows = []
    for point in temperature_cal_points:
        pre = temperature_pre(point)
        temperature_cal_measured.append(pre)
        temperature_cal_rows.append(
            {
                "type": "calibration",
                "reference_c": point,
                "ntc_voltage_v": float(np.interp(point, temperature_x, temperature_voltage)),
                "pre_cal_c": pre,
            }
        )
    temperature_model = fit_two_point_calibration(
        temperature_cal_points[0], temperature_cal_measured[0], temperature_cal_points[1], temperature_cal_measured[1], calibration_id="temperature_two_point"
    )

    temperature_rows = []
    temperature_references = []
    temperature_pre_values = []
    temperature_post_values = []
    for point in temperature_validation_points:
        pre = temperature_pre(point)
        post = temperature_model.apply(pre)
        temperature_references.append(point)
        temperature_pre_values.append(pre)
        temperature_post_values.append(post)
        temperature_rows.append(
            {
                "type": "validation",
                "reference_c": point,
                "ntc_voltage_v": float(np.interp(point, temperature_x, temperature_voltage)),
                "pre_cal_c": pre,
                "pre_error_c": pre - point,
                "post_cal_c": post,
                "post_error_c": post - point,
            }
        )

    write_frame(run, "voltage_calibration_points.csv", pd.DataFrame(voltage_cal_rows))
    write_frame(run, "voltage_validation.csv", pd.DataFrame(voltage_rows))
    write_frame(run, "current_calibration_points.csv", pd.DataFrame(current_cal_rows))
    write_frame(run, "current_validation.csv", pd.DataFrame(current_rows))
    write_frame(run, "temperature_calibration_points.csv", pd.DataFrame(temperature_cal_rows))
    write_frame(run, "temperature_validation.csv", pd.DataFrame(temperature_rows))
    write_json(
        run.path / "calibration_models.json",
        {
            "voltage": voltage_model.as_dict(),
            "current_zero": zero_model.as_dict(),
            "current_two_point": current_model.as_dict(),
            "temperature": temperature_model.as_dict(),
            "adc_lsb_v": adc.lsb_v,
        },
    )

    voltage_metrics = {
        "pre": compute_metrics(pre_values, references, unit="V"),
        "post": compute_metrics(post_values, references, unit="V"),
    }
    current_metrics = {
        "pre": compute_metrics(current_pre_values, current_references, unit="A"),
        "zero": compute_metrics(current_zero_values, current_references, unit="A"),
        "two_point": compute_metrics(current_post_values, current_references, unit="A"),
    }
    temperature_metrics = {
        "pre": compute_metrics(temperature_pre_values, temperature_references, unit="degC"),
        "post": compute_metrics(temperature_post_values, temperature_references, unit="degC"),
    }

    plots = write_plots(
        run,
        [
            (
                "20_voltage_calibration.png",
                plot_multi_series,
                {
                    "series": [
                        ("校准前误差", references, [(value - ref) * 1000.0 for value, ref in zip(pre_values, references)]),
                        ("两点校准后误差", references, [(value - ref) * 1000.0 for value, ref in zip(post_values, references)]),
                    ],
                    "xlabel": "验证电压 (V)",
                    "ylabel": "误差 (mV)",
                    "title": "单体电压通道校准前后误差（校准集与验证集分离）",
                    "annotation": f"{SOURCE}；校准点 3.0/4.1 V，验证点独立。",
                },
            ),
            (
                "21_current_calibration.png",
                plot_multi_series,
                {
                    "series": [
                        ("校准前", current_references, [(value - ref) * 1000.0 for value, ref in zip(current_pre_values, current_references)]),
                        ("仅零点校准", current_references, [(value - ref) * 1000.0 for value, ref in zip(current_zero_values, current_references)]),
                        ("两点校准", current_references, [(value - ref) * 1000.0 for value, ref in zip(current_post_values, current_references)]),
                    ],
                    "xlabel": "验证电流 (A)",
                    "ylabel": "误差 (mA)",
                    "title": "双向电流通道零点/两点校准对照",
                    "annotation": f"{SOURCE}；零点校准不能修正增益误差。",
                },
            ),
            (
                "22_temperature_calibration.png",
                plot_multi_series,
                {
                    "series": [
                        ("校准前", temperature_references, [(value - ref) for value, ref in zip(temperature_pre_values, temperature_references)]),
                        ("两点校准后", temperature_references, [(value - ref) for value, ref in zip(temperature_post_values, temperature_references)]),
                    ],
                    "xlabel": "验证温度 (℃)",
                    "ylabel": "误差 (℃)",
                    "title": "NTC 温度通道校准前后误差",
                    "annotation": f"{SOURCE}；校准点 0/60 ℃，验证点独立。",
                },
            ),
        ],
    )

    summary = {
        "voltage": {"metrics": voltage_metrics, "model": voltage_model.as_dict(), "rows": voltage_rows},
        "current": {
            "metrics": current_metrics,
            "zero_model": zero_model.as_dict(),
            "two_point_model": current_model.as_dict(),
            "rows": current_rows,
        },
        "temperature": {"metrics": temperature_metrics, "model": temperature_model.as_dict(), "rows": temperature_rows},
        "plots": plots,
    }
    payload = finalize_run(
        run,
        script="scripts/calibration_demo.py",
        summary=summary,
        metadata={"note": "校准系数只使用校准点；验证点不参与拟合。"},
    )

    print(f"run_id={run.run_id}")
    print(f"电压：校准前最大误差={voltage_metrics['pre']['max_abs_error']*1000:.4f} mV，两点后={voltage_metrics['post']['max_abs_error']*1000:.4f} mV")
    print(f"电流：校准前最大误差={current_metrics['pre']['max_abs_error']*1000:.4f} mA，零点后={current_metrics['zero']['max_abs_error']*1000:.4f} mA，两点后={current_metrics['two_point']['max_abs_error']*1000:.4f} mA")
    print(f"温度：校准前最大误差={temperature_metrics['pre']['max_abs_error']:.4f} ℃，两点后={temperature_metrics['post']['max_abs_error']:.4f} ℃")
    print(f"真实 SPICE 求解次数={payload['real_spice_solves']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
