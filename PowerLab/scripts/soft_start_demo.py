"""软启动演示：不同参考上升时间下的启动超调与峰值电流。"""

from __future__ import annotations

import argparse

import pandas as pd

from experiments.soft_start import DEFAULT_DURATIONS_S, run_soft_start_experiment

from .stage7_common import save_csv, save_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stage 7 soft start demo")
    parser.add_argument("--profile", choices=("smoke", "standard"), default="smoke")
    args = parser.parse_args(argv)

    durations = (0.0, 0.002) if args.profile == "smoke" else DEFAULT_DURATIONS_S
    report = run_soft_start_experiment(durations_s=durations, save=True)
    rows = []
    for record in report["records"]:
        startup = record.get("startup") or {}
        rows.append(
            {
                "label": record["label"],
                "soft_start_duration_s": record["soft_start_duration_s"],
                "run_id": record.get("run_id"),
                "overshoot_percent": startup.get("overshoot_percent"),
                "peak_inductor_current_a": startup.get("peak_inductor_current_a"),
                "peak_input_current_a": startup.get("peak_input_current_a"),
                "rise_time_s": startup.get("rise_time_s"),
                "raw_settling_time_s": startup.get("raw_settling_time_s"),
                "limit_status": (record.get("limit_check") or {}).get("status"),
            }
        )
    if rows:
        save_csv("soft_start_summary.csv", pd.DataFrame(rows))
    save_json("soft_start_demo.json", report)
    print(
        f"[soft_start] profile={args.profile} records={len(report['records'])} "
        f"failures={len(report['failures'])} failed_checks={len(report['failed_limit_checks'])}"
    )
    for row in rows:
        print(
            f"  {row['label']} overshoot={row['overshoot_percent']}% "
            f"peak_iL={row['peak_inductor_current_a']} A "
            f"peak_iin={row['peak_input_current_a']} A status={row['limit_status']}"
        )
    print("saved:", "results/stage7/demos/soft_start_demo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
