"""阶段四演示：三台虚拟仪器协同工作（真实 ``@sim`` SCPI 通信）。

数据说明：所有读数均来自 PyVISA-sim 脚本（``static_mock`` / ``pyvisa-sim SCPI``），
不是真实电气测量；DMM 读数不会随电源或负载设置变化。
"""

from __future__ import annotations

import logging
from pathlib import Path

from instruments import InstrumentManager

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "instruments.yaml"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    manager = InstrumentManager(CONFIG)
    try:
        manager.open()
        print("Discovered instruments:")
        for name in manager.discover():
            print(" -", name)

        psu = manager.get_power_supply()
        dmm = manager.get_multimeter()
        load = manager.get_electronic_load()

        print("PSU identity:", psu.identify())
        print("DMM identity:", dmm.identify())
        print("Load identity:", load.identify())

        psu.set_voltage(5.0)
        psu.set_current(1.0)
        psu.set_output(True)

        load.set_mode("CC")
        load.set_current(1.0)
        load.set_input(True)

        print("PSU voltage setpoint:", psu.get_voltage())
        print("PSU current limit:", psu.get_current())
        print("PSU output enabled:", psu.get_output())
        print("Load mode:", load.get_mode())
        print("Load current setpoint:", load.get_current())
        print("Load input enabled:", load.get_input())

        voltage = dmm.measure_voltage()
        current = dmm.measure_current()
        resistance = dmm.measure_resistance()
        print("DMM voltage reading:", voltage)
        print("DMM current reading:", current)
        print("DMM resistance reading:", resistance)
        print("Note: DMM readings are static mock values, not real measurements.")

        assert abs(psu.get_voltage() - 5.0) < 1e-3
        assert abs(psu.get_current() - 1.0) < 1e-3
        assert psu.get_output() is True
        assert load.get_mode() == "CC"
        assert abs(load.get_current() - 1.0) < 1e-3
        assert load.get_input() is True
        assert abs(voltage - 5.0) < 1e-3
        assert abs(current - 0.5) < 1e-3
        assert abs(resistance - 4.98) < 1e-3

        load.set_input(False)
        psu.set_output(False)
        assert load.get_input() is False
        assert psu.get_output() is False

        print("Multi-instrument demo: PASS")
        return 0
    finally:
        manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
