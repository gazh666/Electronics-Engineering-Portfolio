"""开关级闭环 Buck 演示：真实行为 PI + PWM 调制 + 非理想功率级。"""

from __future__ import annotations

import argparse

from experiments.closed_loop_validation import steady_state_metrics
from circuits.closed_loop_config import load_closed_loop_config
from simulations.averaged_model_runner import averaged_metrics, run_averaged_closed_loop
from simulations.closed_loop_runner import (
    calibrated_open_loop_duty,
    run_closed_loop_with_fallback,
    save_closed_loop_run,
)

from .stage7_common import save_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stage 7 closed-loop buck demo")
    parser.add_argument("--profile", choices=("smoke", "standard"), default="smoke")
    parser.add_argument("--variant", choices=("E", "D", "SW"), default="E")
    args = parser.parse_args(argv)

    base = load_closed_loop_config().with_variant(args.variant)
    payload: dict[str, object] = {
        "profile": args.profile,
        "variant": args.variant,
        "data_source": "spice_simulation",
        "runs": {},
    }

    closed = run_closed_loop_with_fallback(
        base.with_name("stage7_demo_closed"), mode="closed_loop"
    )
    closed_info = {
        "run_id": closed.run_id,
        "point_count": closed.point_count,
        "duration_ms": closed.duration_ms,
        "step_fallback": closed.metadata.get("step_fallback"),
        "steady_state": steady_state_metrics(closed),
        "pwm_statistics_after_startup": closed.metadata.get("pwm_statistics_after_startup"),
        "quality": closed.metadata.get("quality"),
    }
    directory = save_closed_loop_run(
        closed,
        save_waveform=True,
        extra_metadata={"experiment": "closed_loop_buck_demo", "scheme": "closed_loop"},
    )
    closed_info["run_directory"] = str(directory)
    payload["runs"]["closed_loop"] = closed_info

    duty = calibrated_open_loop_duty(base)
    opened = run_closed_loop_with_fallback(
        base.with_open_loop_duty(duty).with_name("stage7_demo_open"), mode="open_loop"
    )
    open_info = {
        "run_id": opened.run_id,
        "point_count": opened.point_count,
        "duration_ms": opened.duration_ms,
        "step_fallback": opened.metadata.get("step_fallback"),
        "open_loop_duty_cycle": duty,
        "steady_state": steady_state_metrics(opened),
        "pwm_statistics_after_startup": opened.metadata.get("pwm_statistics_after_startup"),
        "note": "fixed duty calibrated offline; not a closed loop",
    }
    open_directory = save_closed_loop_run(
        opened,
        save_waveform=True,
        extra_metadata={"experiment": "closed_loop_buck_demo", "scheme": "open_loop"},
    )
    open_info["run_directory"] = str(open_directory)
    payload["runs"]["open_loop"] = open_info

    averaged = run_averaged_closed_loop(base)
    payload["averaged_model"] = {
        "run_id": averaged.run_id,
        "metrics": averaged_metrics(averaged),
        "note": "averaged model reference; not a switching waveform",
    }
    save_json("closed_loop_buck_demo.json", payload)

    closed_steady = closed_info["steady_state"]
    open_steady = open_info["steady_state"]
    print(
        f"[closed_loop] variant={args.variant} run={closed.run_id} "
        f"Vout={closed_steady['mean_v']:.6f} V "
        f"ripple={closed_steady['peak_to_peak_v']*1e3:.3f} mV "
        f"duty={closed_steady['mean_duty']:.4f} ccm={closed_steady['ccm_fraction']:.3f}"
    )
    print(
        f"[open_loop] duty={duty:.4f} run={opened.run_id} "
        f"Vout={open_steady['mean_v']:.6f} V "
        f"ripple={open_steady['peak_to_peak_v']*1e3:.3f} mV"
    )
    print("saved:", "results/stage7/demos/closed_loop_buck_demo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
