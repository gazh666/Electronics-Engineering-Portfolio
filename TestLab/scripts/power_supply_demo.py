"""程控电源独立演示：身份查询、设定/回读、输出开关与参数校验。

运行方式（在 TestLab 目录下）::

    python -m scripts.power_supply_demo
"""

from pathlib import Path

from instruments.power_supply import PowerSupply

ROOT = Path(__file__).resolve().parents[1]

CONFIG = ROOT / "configs" / "instruments.yaml"


def main() -> None:
    with PowerSupply(CONFIG) as psu:
        print("Instrument:", psu.identify())

        # 以下回读均为仪器设定参数，不代表实际物理测量值
        print("Default voltage:", psu.get_voltage())
        print("Default current limit:", psu.get_current())
        print("Default output state:", psu.get_output())

        try:
            psu.set_voltage(12.0)
            psu.set_current(2.0)
            psu.set_output(True)

            voltage = psu.get_voltage()
            current = psu.get_current()
            output = psu.get_output()

            print("Voltage setpoint:", voltage)
            print("Current limit:", current)
            print("Output state:", output)

            assert abs(voltage - 12.0) < 0.001
            assert abs(current - 2.0) < 0.001
            assert output is True

            print("Configuration test: PASS")

        finally:
            psu.set_output(False)

        # 保护性收尾后再回读一次（仍是模拟设定值，不是电气测量）
        print("Output disabled:", not psu.get_output())


if __name__ == "__main__":
    main()
