"""第八阶段主 CLI：理论与数值验证 / 容差 / Monte Carlo / 鲁棒性。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments._stage8_common import STAGE8_EXPERIMENTS_ROOT, STAGE8_RESULTS_ROOT
from reports.validation_report import write_validation_report
from validation.validation_runner import ALL_TASKS, PROFILES, ValidationRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PowerLab 第八阶段：理论与 SPICE 对照、数值收敛、容差与 Monte Carlo 鲁棒性验证"
    )
    parser.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    parser.add_argument(
        "--task",
        action="append",
        choices=list(ALL_TASKS),
        help="只运行指定任务，可重复；默认按 profile 运行",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不运行 SPICE")
    parser.add_argument("--report-only", action="store_true", help="只根据已有结果重新生成报告")
    parser.add_argument("--resume", action="store_true", help="从 results/stage8/checkpoint.json 续跑")
    parser.add_argument("--max-runs", type=int, default=None, help="覆盖本阶段 SPICE 运行上限")
    return parser


def print_plan(profile: str, tasks: list[str], max_runs: int) -> None:
    settings = PROFILES[profile]
    plan = {
        "profile": profile,
        "tasks": tasks,
        "max_spice_runs": max_runs,
        "maximum_steps_s": settings["maximum_steps_s"],
        "solver_variants": settings["solver_variants"],
        "monte_carlo_profile": settings["mc_profile"],
        "results_root": str(STAGE8_RESULTS_ROOT),
        "experiments_root": str(STAGE8_EXPERIMENTS_ROOT),
        "note": "dry-run does not execute ngspice",
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = PROFILES[args.profile]
    tasks = list(args.task or settings["tasks"])
    max_runs = int(args.max_runs or settings["max_spice_runs"])

    if args.dry_run:
        print_plan(args.profile, tasks, max_runs)
        return 0

    if args.report_only:
        summary_path = STAGE8_RESULTS_ROOT / "validation_summary.json"
        if not summary_path.exists():
            print(f"missing {summary_path}; run the validation first", file=sys.stderr)
            return 2
        path = write_validation_report()
        print(f"report: {path}")
        return 0

    runner = ValidationRunner(
        profile=args.profile,
        max_runs=max_runs,
        resume=args.resume,
        tasks=tasks,
    )
    summary = runner.run()
    report = write_validation_report(summary)
    print(
        json.dumps(
            {
                "profile": summary["profile"],
                "tasks_completed": summary["tasks_completed"],
                "budget": summary["budget"],
                "acceptance": summary["acceptance"]["overall_status"],
                "report": str(report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["acceptance"]["overall_status"] != "PARTIAL_FAILURE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
