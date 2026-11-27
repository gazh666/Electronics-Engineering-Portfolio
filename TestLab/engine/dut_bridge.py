"""独立数据连接层：把仪器设定值送入 DUT 行为模型，再把结果交给测量层。

PyVISA-sim 的多台虚拟仪器之间**不会自动共享物理状态**：电子负载拉载
不会改变电源的 SCPI 回读值，DMM 也不会自动测到 DUT 输出电压。
因此本层显式完成数据桥接：

    虚拟电源 SCPI 回读(vin) ┐
                            ├─> VirtualDUT.calculate() ─> DUTResult
    虚拟负载 SCPI 回读(iout) ┘                              │
                                                            └─> DMM 测量层

本层不修改 SCPI 响应，也不把固定 YAML 响应伪装成动态测量；
模型结果以 ``behavioral_model`` 来源标签交给测量层与报告。

可选的 ``fault_injector`` 只用于阶段八的故障注入测试：它在读取仪器后
按配置修改读数或抛出通信异常，不改变 SCPI 层行为。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from instruments.electronic_load import ElectronicLoad
from instruments.power_supply import PowerSupply
from models.virtual_dut import DUTResult, VirtualDUT

from .fault_injector import LOCATION_LOAD_CURRENT, LOCATION_PSU_VOLTAGE, FaultInjector

T = TypeVar("T")


@dataclass(frozen=True)
class BridgeReading:
    """一次数据桥接的完整快照（仪器设定值 + 模型结果 + 来源）。"""

    vin_setpoint: float
    load_current_setpoint: float
    load_input_enabled: bool
    dut: DUTResult
    vin_source: str
    load_source: str
    #: 电源输入电流限制设定值（A）
    input_current_limit: float = 0.0
    #: 电源输出状态
    psu_output_enabled: bool = True
    #: 电子负载工作模式
    load_mode: str = "CC"

    @property
    def sources(self) -> dict[str, str]:
        """各数据字段的来源标签，用于报告区分仪器值与模型值。"""
        return {
            "input_voltage": self.vin_source,
            "load_current": self.load_source,
            "dut_output": self.dut.source,
        }


class DutDataBridge:
    """读取仪器设定值并调用 DUT 模型的独立数据连接层。"""

    def __init__(
        self,
        psu: PowerSupply,
        load: ElectronicLoad,
        dut: VirtualDUT,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.psu = psu
        self.load = load
        self.dut = dut
        self.fault_injector = fault_injector

    def acquire(self, enabled: bool | None = None) -> BridgeReading:
        """读取仪器设定值并计算 DUT 结果。

        - 输入电压、电流限制、输出状态均取自电源 SCPI 回读；
        - 负载电流与输入状态取自电子负载 SCPI 回读；
        - 负载启用时仅支持 CC 模式，其他模式拒绝计算；
        - ``enabled=None`` 时使用电源实际输出状态；
        - 通信异常直接向上抛出，不生成替代测量数据。
        """
        vin = self._read(LOCATION_PSU_VOLTAGE, self.psu.get_voltage)
        input_current_limit = self.psu.get_current()
        psu_output_enabled = self.psu.get_output()
        load_current = self._read(LOCATION_LOAD_CURRENT, self.load.get_current)
        load_mode = self.load.get_mode()
        load_enabled = self.load.get_input()

        if load_enabled and load_mode != "CC":
            raise NotImplementedError(
                f"当前仅支持 CC 模式负载，实际模式: {load_mode}"
            )

        applied_current = load_current if load_enabled else 0.0
        output_enabled = psu_output_enabled if enabled is None else enabled

        result = self.dut.calculate(
            vin,
            applied_current,
            enabled=output_enabled,
            input_current_limit=input_current_limit,
            output_enabled=output_enabled,
            load_enabled=load_enabled,
        )
        return BridgeReading(
            vin_setpoint=vin,
            load_current_setpoint=load_current,
            load_input_enabled=load_enabled,
            dut=result,
            vin_source=self.psu.SOURCE,
            load_source=self.load.SOURCE,
            input_current_limit=input_current_limit,
            psu_output_enabled=psu_output_enabled,
            load_mode=load_mode,
        )

    def _read(self, location: str, supplier: Callable[[], T]) -> T:
        """读取仪器；若配置了故障注入，则在返回值上应用故障。"""
        value = supplier()
        if self.fault_injector is None:
            return value
        return self.fault_injector.apply(location, value)  # type: ignore[return-value]
