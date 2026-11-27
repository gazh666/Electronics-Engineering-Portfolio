"""单工况工程性能分析演示：12 V 输入、1 A 负载。"""

from __future__ import annotations

from pathlib import Path

from analysis.performance_analyzer import PerformanceAnalyzer
from bench.virtual_test_bench import VirtualTestBench
from instruments.manager import InstrumentManager
from models.virtual_dut import VirtualDUT

ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT_CONFIG = ROOT / "configs" / "instruments.yaml"
DUT_CONFIG = ROOT / "configs" / "dut_config.yaml"
LIMITS_CONFIG = ROOT / "configs" / "performance_limits.yaml"


def main() -> None:
    dut = VirtualDUT.from_yaml(DUT_CONFIG)
    analyzer = PerformanceAnalyzer(LIMITS_CONFIG)

    with InstrumentManager(INSTRUMENT_CONFIG) as manager:
        bench = VirtualTestBench(manager, dut)
        psu = bench.psu
        load = bench.load
        try:
            psu.set_output(False)
            load.set_input(False)
            psu.set_voltage(12.0)
            psu.set_current(2.0)
            load.set_mode("CC")
            load.set_current(1.0)
            psu.set_output(True)
            load.set_input(True)

            result = bench.read_state()
            analysis = analyzer.analyze(result)

            print("Run mode: 12 V input / 1 A load")
            print("Data source:", analysis["source"])
            print("DUT state:", analysis["state"])
            print("Data quality:", analysis["data_quality_status"])
            print("Metric status:", analysis["metric_status"])
            print("Metrics:")
            for name, value in analysis["metrics"].items():
                print(f"  {name}: {value}")
            print("Limit checks:")
            for check in analysis["checks"]:
                print(
                    f"  {check['metric']}: value={check['value']} "
                    f"unit={check['unit']} status={check['status']} "
                    f"limits=[{check['lower']}, {check['upper']}]"
                )
            print("Performance demo: PASS")
        finally:
            try:
                load.set_input(False)
            finally:
                psu.set_output(False)


if __name__ == "__main__":
    main()
