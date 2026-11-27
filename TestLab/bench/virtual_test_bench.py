"""虚拟测试台：把仪器 SCPI 回读值送入 DUT 模型，并输出带来源标签的测量。

PyVISA-sim 不会自动建立多台虚拟仪器之间的电气关系：电源不会因为负载
拉载而改变回读值，DMM 也不会自动测到 DUT 输出。因此本层显式读取
电源与负载的设置值，再调用 :class:`VirtualDUT` 计算，最后以
``behavioral_model`` 来源标签交给演示与报告。

本层不修改 SCPI 响应，也不把模型结果伪装成真实测量。
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.dut_bridge import BridgeReading, DutDataBridge
from instruments.electronic_load import ElectronicLoad
from instruments.manager import InstrumentManager
from instruments.power_supply import PowerSupply
from models.virtual_dut import DUTResult, VirtualDUT


@dataclass(frozen=True)
class Measurement:
    """一条带单位与来源标签的测量值。"""

    value: float
    unit: str
    source: str


class ModelMultimeter:
    """基于 DUT 计算结果的模型测量适配器。

    与真实万用表驱动无关：它只读取同一份 :class:`DUTResult`，
    保证同一次快照中的电压、电流来自同一次模型计算。
    """

    def __init__(self, result: DUTResult) -> None:
        self.result = result

    def measure_voltage(self) -> Measurement:
        return Measurement(
            value=self.result.vout,
            unit="V",
            source=self.result.source,
        )

    def measure_current(self) -> Measurement:
        return Measurement(
            value=self.result.iout,
            unit="A",
            source=self.result.source,
        )


class VirtualTestBench:
    """组合仪器管理器与 DUT 模型的虚拟测试台。"""

    def __init__(
        self,
        manager: InstrumentManager,
        dut: VirtualDUT | None = None,
    ) -> None:
        self.manager = manager
        self.dut = dut if dut is not None else VirtualDUT()
        self.psu: PowerSupply = manager.get_power_supply()
        self.load: ElectronicLoad = manager.get_electronic_load()
        self.bridge = DutDataBridge(self.psu, self.load, self.dut)

    def read_snapshot(self) -> BridgeReading:
        """读取一次完整快照（仪器设定值 + 模型结果 + 来源）。"""
        return self.bridge.acquire()

    def read_state(self) -> DUTResult:
        """读取仪器设置并重新计算 DUT 稳态结果。

        每次调用都会重新读取 SCPI 设置值，不使用缓存的模型结果。
        """
        return self.read_snapshot().dut

    def get_model_measurements(self) -> dict[str, object]:
        """返回模型测量：电压、电流与完整结果来自同一次计算。"""
        result = self.read_state()
        meter = ModelMultimeter(result)
        return {
            "result": result,
            "voltage": meter.measure_voltage(),
            "current": meter.measure_current(),
        }

    def get_static_mock_measurements(self) -> dict[str, Measurement]:
        """返回原始 DMM 的固定模拟响应，并标记 ``static_mock``。"""
        dmm = self.manager.get_multimeter()
        return {
            "voltage": Measurement(
                value=dmm.measure_voltage(),
                unit="V",
                source="static_mock",
            ),
            "current": Measurement(
                value=dmm.measure_current(),
                unit="A",
                source="static_mock",
            ),
        }
