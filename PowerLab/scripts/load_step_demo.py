"""负载阶跃演示：闭环与固定占空比开环在同一功率级下对比，并给出平均模型对照。"""

from __future__ import annotations

import argparse

import pandas as pd

from experiments.load_step import DEFAULT_CASES, run_load_step_experiment

from .stage7_common import save_csv, save_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stage 7 load step demo")
    parser.add_argument("--profile", choices=("smoke", "standard"), default="smoke")
    parser.add_argument("--case", default="load_step_1a_to_2a")
    args = parser.parse_args(argv)

    cases = (args.case,) if args.profile == "smoke" else DEFAULT_CASES
    report = run_load_step_experiment(
        cases=cases,
        save=True,
        save_waveform_cases=(
            (args.case,) if args.profile == "standard" else ()
        ),
    )
    table = pd.DataFrame(report["event_table"])
    if not table.empty:
        save_csv("load_step_events.csv", table)
    save_json("load_step_demo.json", report)
    print(
        f"[load_step] profile={args.profile} cases={len(cases)} "
        f"records={len(report['records'])} failures={len(report['failures'])} "
        f"failed_checks={len(report['failed_limit_checks'])}"
    )
    for record in report["records"]:
        items = record.get("metrics") or []
        if isinstance(items, dict):
            items = [items]
        for metrics in items:
            event = metrics.get("event") or {}
            print(
                f"  {record['case']} {record['scheme']} "
                f"max_dev={metrics.get('maximum_absolute_deviation_v')} V "
                f"recovery={((metrics.get('recovery_strict') or {}).get('recovery_time_s'))} s "
                f"event={event.get('event_id')}"
            )
    print("saved:", "results/stage7/demos/load_step_demo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
