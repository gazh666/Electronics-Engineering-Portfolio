"""PI 控制器演示：限幅、积分饱和与反算抗饱和（离散时间，非 SPICE）。"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from control.models import ControllerConfig
from control.pi_controller import PIController

from .stage7_common import save_csv, save_json

DT = 1e-6
END = 0.020
L = 47e-6
C = 100e-6
R = 2.5
VIN = 12.0


def simulate(method: str) -> tuple[pd.DataFrame, dict[str, float]]:
    config = ControllerConfig(
        kp=0.0585, ki=117.66, duty_min=0.02, duty_max=0.40,
        feedforward_enabled=True, anti_windup=method, tracking_gain=2000.0,
    )
    controller = PIController(config)
    il, vc = 0.0, 0.0
    rows = []
    for step in range(int(END / DT)):
        time_s = step * DT
        reference = 5.0 if time_s < 0.010 else 4.2
        sample = controller.update(reference, vc, DT, vin_v=VIN)
        duty = sample.limited_duty
        di = (duty * VIN - vc) / L
        dvc = (il - vc / R) / C
        il += di * DT
        vc += dvc * DT
        rows.append(
            {
                "time_s": time_s,
                "method": method,
                "vref_v": reference,
                "vout_v": vc,
                "error_v": sample.error_v,
                "duty_cmd": duty,
                "integral_state": sample.integral_state,
                "saturated": abs(sample.raw_duty - duty) > 1e-12,
            }
        )
    frame = pd.DataFrame(rows)
    tail = frame[frame["time_s"] > 0.018]
    summary = {
        "method": method,
        "final_vout_v": float(frame["vout_v"].iloc[-1]),
        "tail_mean_v": float(tail["vout_v"].mean()),
        "final_integral_state": float(frame["integral_state"].iloc[-1]),
        "maximum_integral_state": float(frame["integral_state"].max()),
        "saturation_fraction": float(frame["saturated"].mean()),
        "maximum_vout_v": float(frame["vout_v"].max()),
    }
    return frame, summary


def main() -> int:
    frames = []
    summaries = []
    for method in ("none", "conditional", "back_calculation"):
        frame, summary = simulate(method)
        frames.append(frame)
        summaries.append(summary)
        print(
            f"{method}: final={summary['final_vout_v']:.4f} V "
            f"tail={summary['tail_mean_v']:.4f} V "
            f"max_integral={summary['maximum_integral_state']:.4f} "
            f"saturation={summary['saturation_fraction']*100:.1f}%"
        )
    save_csv("pi_controller_demo.csv", pd.concat(frames, ignore_index=True))
    print("saved:", save_json("pi_controller_demo.json", {
        "data_source": "discrete_time_pi_with_euler_plant",
        "controller": {"kp": 0.0585, "ki": 117.66, "duty_max": 0.40},
        "summaries": summaries,
        "note": "plant is a simple averaged LC model, not a switching SPICE run",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
