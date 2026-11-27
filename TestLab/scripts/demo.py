"""TestLab 端到端演示：连接虚拟仪器、执行全部用例并生成报告。

运行方式（在 TestLab 目录下）::

    python -m scripts.demo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许以 python scripts/demo.py 或 python -m scripts.demo 两种方式运行
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import results_dir  # noqa: E402
from engine.test_runner import ScenarioTestRunner  # noqa: E402
from instruments import ElectronicLoad, InstrumentManager, PowerSupply, VirtualMultimeter  # noqa: E402
from models.virtual_dut import VirtualDUT  # noqa: E402
from reports.generator import build_report, save_csv, save_json  # noqa: E402


def _print_records(records: list[dict]) -> None:
    print("\n===== 测试结果 =====")
    for record in records:
        print(
            f"[{record['status']:5s}] {record['case_id']} {record['case_name']} "
            f"({record['duration_ms']:.1f} ms)"
        )
        efficiency = record["efficiency"]
        efficiency_text = "N/A" if efficiency is None else f"{efficiency} %"
        print(
            f"        Vin={record['vin']} V, Vout={record['vout']} V, "
            f"Iout={record['iout']} A, Pin={record['pin']} W, "
            f"Pout={record['pout']} W, 效率={efficiency_text}"
        )
        print(
            f"        状态: 预期 {record['expected_state']} / "
            f"实际 {record['actual_state']}"
        )
        for check in record["checks"]:
            print(
                f"        - {check['name']}: {check['value']} {check['unit']} "
                f"(min={check['min']}, max={check['max']}) -> "
                f"{check.get('status', 'PASS' if check['passed'] else 'FAIL')} "
                f"| {check['detail']}"
            )
        if record.get("retries"):
            print(f"        重试次数: {record['retries']}")
        for fault in record.get("faults", []):
            if fault["occurrences"]:
                print(
                    f"        故障注入: {fault['fault_type']} @ {fault['location']} "
                    f"x{fault['occurrences']} -> {fault['final_status']}"
                )
        if record["status"] in ("ERROR", "SKIP"):
            print(f"        说明: {record['error_message']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TestLab 虚拟仪器自动化测试演示")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "instruments.yaml"))
    parser.add_argument(
        "--cases",
        default=str(PROJECT_ROOT / "configs" / "scenario_cases.yaml"),
    )
    parser.add_argument("--results", default=str(results_dir()))
    args = parser.parse_args(argv)

    with InstrumentManager(args.config) as manager:
        print("发现虚拟仪器资源：")
        for name in manager.available:
            print(f"  - {name}")

        psu = manager.create("psu", PowerSupply)
        dmm = manager.create("dmm", VirtualMultimeter)
        load = manager.create("load", ElectronicLoad)
        print(f"PSU  : {psu.identify()}")
        print(f"DMM  : {dmm.identify()}")
        print(f"ELoad: {load.identify()}")

        dut = VirtualDUT()
        runner = ScenarioTestRunner(psu, dmm, load, dut)
        records = runner.run_file(args.cases)

    report = build_report(records)
    json_path = save_json(report, args.results)
    csv_path = save_csv(records, report["run_id"], args.results)

    _print_records(records)
    summary = report["summary"]
    pass_rate = summary.get("pass_rate_percent")
    pass_rate_text = "N/A" if pass_rate is None else f"{pass_rate:.2f}%"
    print(
        f"\n汇总: 共 {summary['total']} 项 | PASS {summary['PASS']} | "
        f"FAIL {summary['FAIL']} | ERROR {summary['ERROR']} | SKIP {summary['SKIP']} "
        f"| 通过率 {pass_rate_text}"
    )
    print(f"数据来源: {', '.join(report['data_sources'])}")
    print(f"JSON 报告: {json_path}")
    print(f"CSV 明细 : {csv_path}")

    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
