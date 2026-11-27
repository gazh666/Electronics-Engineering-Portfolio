"""Task 21/22/23：NTC 阻温特性、真实 SPICE 分压、ADC 恢复与自热状态。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from circuits.ntc_sensing import run_open_short, sweep_temperatures_fast
from scripts.stage4_common import adc_settings, ntc_settings
from sensing.adc import adc_convert
from sensing.config import load_ntc_config
from sensing.temperature_decoder import ntc_power_w, ntc_temperature, resistance_from_voltage, voltage_sensitivity_v_per_c
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame, write_plots
from visualization.plots import plot_multi_series, plot_xy

SOURCE = "真实 ngspice 工作点求解（spice_simulation）"


def main() -> int:
    config = load_ntc_config()
    ntc_config = ntc_settings(config)
    adc_config = adc_settings()
    run = new_sensing_run("sensing")

    temperatures = [float(value) for value in config["temperature_range"]["experiment_temperatures_c"]]
    rows = sweep_temperatures_fast(temperatures, ntc_config)

    for row in rows:
        sample = adc_convert(row["spice_voltage_v"], adc_config)
        recovered_resistance = resistance_from_voltage(
            sample.decoded_voltage_v,
            pullup_ohm=ntc_config.pullup_ohm,
            excitation_v=ntc_config.excitation_v,
        )
        recovered_temperature = ntc_temperature(
            recovered_resistance,
            r25_ohm=ntc_config.r25_ohm,
            beta_k=ntc_config.beta_k,
        )
        row.update(
            {
                "adc_code": sample.code,
                "adc_decoded_v": sample.decoded_voltage_v,
                "adc_recovered_temperature_c": recovered_temperature,
                "adc_temperature_error_c": recovered_temperature - row["temperature_c"],
                "sensitivity_v_per_c": voltage_sensitivity_v_per_c(
                    row["temperature_c"],
                    r25_ohm=ntc_config.r25_ohm,
                    beta_k=ntc_config.beta_k,
                    pullup_ohm=ntc_config.pullup_ohm,
                    excitation_v=ntc_config.excitation_v,
                ),
            }
        )

    open_short = run_open_short(ntc_config)
    open_short_rows = []
    for name, payload in open_short.items():
        sample = adc_convert(payload["voltage_v"], adc_config)
        open_short_rows.append(
            {
                "case": name,
                "resistance_ohm": payload["resistance_ohm"],
                "voltage_v": payload["voltage_v"],
                "voltage_fraction": payload["voltage_fraction_of_excitation"],
                "adc_code": sample.code,
                "expected_status": payload["expected_status"],
            }
        )

    frame = pd.DataFrame(rows)
    write_frame(run, "ntc_temperature_sweep.csv", frame)
    write_frame(run, "ntc_open_short.csv", pd.DataFrame(open_short_rows))

    self_heating = config["self_heating"]
    if self_heating.get("dissipation_coefficient_mw_per_c") is None:
        self_heating_status = "NOT_VERIFIED"
        self_heating_note = "缺少真实 NTC 耗散系数，不填入任意自热温升。"
    else:
        self_heating_status = "AVAILABLE"
        self_heating_note = ""

    max_theory_error_v = float(frame["voltage_error_v"].abs().max())
    max_temperature_error_c = float(frame["temperature_error_c"].abs().max())
    max_adc_temperature_error_c = float(frame["adc_temperature_error_c"].abs().max())

    plots = write_plots(
        run,
        [
            (
                "17_ntc_resistance_temperature.png",
                plot_xy,
                {
                    "x": frame["temperature_c"].tolist(),
                    "y": (frame["resistance_ohm"] / 1000.0).tolist(),
                    "xlabel": "温度 (℃)",
                    "ylabel": "NTC 电阻 (kΩ)",
                    "title": "NTC 阻温曲线（R25=10 kΩ，B=3950 K）",
                    "annotation": "解析阻温模型 + 真实 SPICE 分压验证；教学 B 值不代表商业型号选型。",
                    "color": "#8c564b",
                },
            ),
            (
                "18_ntc_divider_temperature.png",
                plot_multi_series,
                {
                    "series": [
                        ("SPICE 分压", frame["temperature_c"].tolist(), frame["spice_voltage_v"].tolist()),
                        ("理论分压", frame["temperature_c"].tolist(), frame["theory_voltage_v"].tolist()),
                    ],
                    "xlabel": "温度 (℃)",
                    "ylabel": "NTC 分压 (V)",
                    "title": "NTC 分压随温度变化（3.3 V 激励，10 kΩ 上拉）",
                    "annotation": f"{SOURCE}；25 ℃ 理论分压 1.65 V。",
                },
            ),
            (
                "19_ntc_temperature_recovery_error.png",
                plot_multi_series,
                {
                    "series": [
                        ("理想反演误差", frame["temperature_c"].tolist(), frame["temperature_error_c"].tolist()),
                        ("12 位 ADC 后误差", frame["temperature_c"].tolist(), frame["adc_temperature_error_c"].tolist()),
                    ],
                    "xlabel": "温度 (℃)",
                    "ylabel": "温度误差 (℃)",
                    "title": "NTC 温度恢复误差",
                    "annotation": f"{SOURCE}；量化误差随温度变化，非线性来自阻温曲线。",
                },
            ),
        ],
    )

    summary = {
        "ntc": {
            "r25_ohm": ntc_config.r25_ohm,
            "beta_k": ntc_config.beta_k,
            "pullup_ohm": ntc_config.pullup_ohm,
            "excitation_v": ntc_config.excitation_v,
        },
        "temperature_range_c": [ntc_config.minimum_temperature_c, ntc_config.maximum_temperature_c],
        "max_spice_vs_theory_voltage_error_v": max_theory_error_v,
        "max_temperature_error_c": max_temperature_error_c,
        "max_adc_temperature_error_c": max_adc_temperature_error_c,
        "sweep": rows,
        "open_short": open_short_rows,
        "self_heating": {
            "status": self_heating_status,
            "note": self_heating_note,
            "power_at_25c_w": ntc_power_w(25.0, r25_ohm=ntc_config.r25_ohm, beta_k=ntc_config.beta_k, pullup_ohm=ntc_config.pullup_ohm, excitation_v=ntc_config.excitation_v),
        },
        "plots": plots,
    }
    payload = finalize_run(
        run,
        script="scripts/ntc_sensing_demo.py",
        summary=summary,
        metadata={"config": "configs/ntc_config.yaml", "adc": "configs/afe_config.yaml"},
    )

    print(f"run_id={run.run_id}")
    print(frame[["temperature_c", "resistance_ohm", "spice_voltage_v", "adc_code", "adc_temperature_error_c"]].to_string(index=False))
    print(f"最大 SPICE-理论电压误差={max_theory_error_v*1e6:.3f} µV，最大温度误差（理想反演）={max_temperature_error_c:.6f} ℃，最大 ADC 后误差={max_adc_temperature_error_c:.6f} ℃")
    print(pd.DataFrame(open_short_rows).to_string(index=False))
    print(f"自热分析状态={self_heating_status}：{self_heating_note}")
    print(f"真实 SPICE 求解次数={payload['real_spice_solves']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
