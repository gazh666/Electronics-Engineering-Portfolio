"""输入电压扰动演示：PWL 源驱动的线阶跃，闭环与开环对比。"""

from __future__ import annotations

import argparse

import pandas as pd

from experiments.line_step import DEFAULT_CASES, run_line_step_experiment

from .stage7_common import save_csv, save_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stage 7 line step demo")
    parser.add_argument("--profile", choices=("smoke", "standard"), default="smoke")
    parser.add_argument("--case", default="vin_step_down_12_to_9")
    args = parser.parse_args(argv)

    cases = (args.case,) if args.profile == "smoke" else DEFAULT_CASES
    report = run_line_step_experiment(
        cases=cases,
        save=True,
        save_waveform_cases=((args.case,) if args.profile == "standard" else ()),
    )
    table = pd.DataFrame(report["event_table"])
    if not table.empty:
        save_csv("line_step_events.csv", table)
    save_json("line_step_demo.json", report)
    print(
        f"[line_step] profile={args.profile} cases={len(cases)} "
        f"records={len(report['records'])} failures={len(report['failures'])} "
        f"failed_checks={len(report['failed_limit_checks'])}"
    )
    for record in report["records"]:
        metrics = record.get("metrics") or {}
        print(
            f"  {record['case']} {record['scheme']} "
            f"max_dev={metrics.get('maximum_absolute_deviation_v')} V "
            f"recovery={((metrics.get('recovery_strict') or {}).get('recovery_time_s'))} s"
        )
    print("saved:", "results/stage7/demos/line_step_demo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
