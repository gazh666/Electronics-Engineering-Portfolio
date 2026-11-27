"""数字万用表驱动：SCPI 测量通道 + 被测件模型读数通道。

数据来源说明：
- ``measure_voltage`` / ``measure_current`` / ``measure_resistance``：
  仪器 SCPI 返回的**固定模拟读数**（``static_mock``），不随电源或负载设置变化；
- ``read_dc_voltage``：VirtualDUT 模型真值叠加 ADC 噪声，供自动化测试使用，
  报告中标记为 ``model(virtual_dut)+dmm_noise``。

注意：SCPI 读数不是真实电气测量，也不代表电源端子上的实际电压。
"""

from __future__ import annotations

import random

from .base import BaseInstrument

#: DMM 模型读数来源标签
DMM_SOURCE = "model(virtual_dut)+dmm_noise"
#: DMM SCPI 固定模拟读数来源标签
STATIC_SOURCE = "static_mock"


class VirtualMultimeter(BaseInstrument):
    """带 ADC 噪声模型的虚拟数字万用表。"""

    def __init__(
        self,
        resource=None,
        name: str = "DMM",
        timeout_ms: int = 2000,
        noise_rms: float = 0.0008,
        seed: int | None = 2028,
        owns_resource: bool = True,
    ) -> None:
        super().__init__(
            resource=resource,
            name=name,
            timeout_ms=timeout_ms,
            owns_resource=owns_resource,
        )
        self.noise_rms = noise_rms
        self._rng = random.Random(seed)

    # --- 配置 ---

    def configure_voltage(self) -> None:
        """配置为直流电压测量。"""
        self.write("CONF:VOLT:DC")

    def configure_current(self) -> None:
        """配置为直流电流测量。"""
        self.write("CONF:CURR:DC")

    # --- SCPI 测量通道 ---

    def measure_voltage(self) -> float:
        """读取直流电压模拟读数（V），来源为固定模拟值。"""
        return self.query_float("MEAS:VOLT?")

    def measure_current(self) -> float:
        """读取直流电流模拟读数（A），来源为固定模拟值。"""
        return self.query_float("MEAS:CURR?")

    def measure_resistance(self) -> float:
        """读取直流电阻模拟读数（Ω）。

        负值是物理上不可能的响应，直接判为非法数据，不参与后续计算。
        """
        value = self.query_float("MEAS:RES?")
        if value < 0:
            raise ValueError(f"电阻读数不能为负: {value!r}")
        return value

    def measure_bad(self) -> float:
        """触发仪器错误响应，用于验证异常处理。"""
        return self.query_float("BAD?")

    def measure_slow(self) -> float:
        """触发无响应查询，用于验证超时处理。"""
        return self.query_float("SLOW?")

    # --- 模型读数通道 ---

    def read_dc_voltage(self, true_value: float) -> float:
        """把模拟前端真值转换为 DMM 读数（叠加 ADC 噪声）。"""
        return true_value + self._rng.gauss(0.0, self.noise_rms)


#: 兼容阶段四验收命名（与 ``VirtualMultimeter`` 完全等价）
Multimeter = VirtualMultimeter
