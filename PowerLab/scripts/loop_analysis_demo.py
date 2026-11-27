"""环路分析演示：线性化平均模型的 Bode、裕度、极点与带宽。"""

from __future__ import annotations

import math

import pandas as pd

from analysis.stability_analysis import (
    carrier_small_signal_gain,
    describe_closed_loop_poles,
    solve_operating_duty,
    stability_report,
)
from circuits.closed_loop_config import load_closed_loop_config
from simulations.averaged_model_runner import averaged_parameters_from_config

from .stage7_common import save_csv, save_json


def main() -> int:
    config = load_closed_loop_config()
    parameters = averaged_parameters_from_config(config)
    duty = solve_operating_duty(parameters, config.target_voltage_v)
    pwm_gain = carrier_small_signal_gain(duty)
    report = stability_report(
        parameters,
        config.controller.kp,
        config.controller.ki,
        target_v=config.target_voltage_v,
        pwm_gain=pwm_gain,
        limits={"phase_margin_deg": {"min": 45.0}, "finite_gain_margin_db": {"min": 6.0}},
    )
    bode = report["frequency_response"]
    poles = describe_closed_loop_poles(report)
    save_csv("loop_bode.csv", bode)
    save_csv("loop_poles.csv", poles)
    payload = {key: value for key, value in report.items() if key != "frequency_response"}
    payload["poles_table"] = poles.to_dict(orient="records")
    payload["data_source"] = "linearized_average_model"
    print(
        f"duty={duty:.5f} pwm_gain={pwm_gain:.4f} "
        f"PM={report['phase_margin_deg']} GM={report['gain_margin_db']} "
        f"bandwidth={report['bandwidth_hz']:.2f} Hz status={report['status']}"
    )
    for item in report["closed_loop_poles"]["poles"]:
        print("pole:", item)
    gm = report["gain_margin_db"]
    if gm is None or (isinstance(gm, float) and not math.isfinite(gm)):
        print("gain margin: NOT_RESOLVED (no -180 deg crossing)")
    print("saved:", save_json("loop_analysis_demo.json", payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
