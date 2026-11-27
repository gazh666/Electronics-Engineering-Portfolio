"""虚拟电源动态联动演示：SCPI 设置 -> VirtualDUT -> 模型测量。

所有数值均来自数学模型计算，不是真实硬件测量。
"""

from pathlib import Path

from bench.virtual_test_bench import VirtualTestBench
from instruments.manager import InstrumentManager
from models.virtual_dut import VirtualDUT

ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT_CONFIG = ROOT / "configs" / "instruments.yaml"
DUT_CONFIG = ROOT / "configs" / "dut_config.yaml"


def _state_text(state) -> str:
    """兼容 DUTState 枚举与字符串两种形式。"""
    return getattr(state, "value", state)


def main() -> None:
    dut = VirtualDUT.from_yaml(DUT_CONFIG)

    with InstrumentManager(INSTRUMENT_CONFIG) as manager:
        psu = manager.get_power_supply()
        load = manager.get_electronic_load()
        bench = VirtualTestBench(manager, dut)

        try:
            # 先回到安全状态，再建立标称工况
            psu.set_output(False)
            load.set_input(False)

            psu.set_voltage(12.0)
            psu.set_current(2.0)
            load.set_mode("CC")
            load.set_current(1.0)
            psu.set_output(True)
            load.set_input(True)

            data = bench.get_model_measurements()
            result = data["result"]

            print("SIMULATION MODE")
            print("Input voltage setpoint:", result.vin_setpoint)
            print("Input current limit:", result.input_current_limit)
            print("Input voltage (model):", result.vin)
            print("Input current:", result.iin)
            print("Output voltage:", result.vout)
            print("Output current:", result.iout)
            print("Input power:", result.pin)
            print("Output power:", result.pout)
            print("Power loss:", result.power_loss)
            print("Efficiency:", result.efficiency)
            print("DUT state:", _state_text(result.state))
            print("Data source:", result.source)

            static = bench.get_static_mock_measurements()
            print("Static mock voltage:", static["voltage"].value)
            print("Static mock source:", static["voltage"].source)
            print("Model output voltage:", data["voltage"].value)
            print("Model voltage source:", data["voltage"].source)

            # 负载从 1 A 增加到 2 A，输出电压应因等效输出电阻而下降
            load.set_current(2.0)
            new_result = bench.read_state()
            print("Full-load output:", new_result.vout)
            print("Full-load state:", _state_text(new_result.state))

            assert new_result.vout < result.vout
            assert abs(new_result.vout - 4.96) < 1e-9

            print("Dynamic linkage verification: PASS")
        finally:
            # 异常退出也必须关闭负载输入与电源输出
            try:
                load.set_input(False)
            finally:
                psu.set_output(False)


if __name__ == "__main__":
    main()
