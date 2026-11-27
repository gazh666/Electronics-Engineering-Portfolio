"""程控直流电源驱动：设定值读写、输出开关与参数校验。

注意：``get_voltage`` / ``get_current`` 返回的是仪器**设定参数回读**，
不是 DUT 的实际物理测量值。
"""

from __future__ import annotations

from pathlib import Path

from .base import (
    BaseInstrument,
    InstrumentError,
    InstrumentNotConnectedError,
    validate_number,
)
from .manager import InstrumentManager


class PowerSupply(BaseInstrument):
    """TestLab 虚拟程控电源。

    既可作为独立演示使用（传入 instruments.yaml 路径，自行管理资源），
    也可由 :class:`InstrumentManager` 创建并共享资源。
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        resource=None,
        name: str = "PowerSupply",
        timeout_ms: int = 2000,
        owns_resource: bool = True,
    ) -> None:
        super().__init__(
            resource=resource,
            name=name,
            timeout_ms=timeout_ms,
            owns_resource=owns_resource,
        )
        self.config_path = Path(config_path).resolve() if config_path is not None else None
        self._manager: InstrumentManager | None = None
        self._owns_manager = False

    # --- 连接管理 ---

    def connect(self) -> None:
        """建立连接；重复调用不会重复创建 ResourceManager。"""
        if self.connected:
            return
        if self.config_path is None:
            raise InstrumentNotConnectedError(
                "PowerSupply: 未配置 instruments.yaml 路径，无法建立连接"
            )
        if self._manager is None:
            self._manager = InstrumentManager(self.config_path)
            try:
                self._manager.open()
                self._owns_manager = True
                self.bind(self._manager.open_resource("psu"), owns_resource=False)
            except Exception:
                # 连接失败时立即释放已创建的 ResourceManager，避免资源泄漏
                if self._manager is not None:
                    if self._owns_manager:
                        self._manager.close()
                    self._manager = None
                    self._owns_manager = False
                raise
        else:
            self.bind(self._manager.open_resource("psu"), owns_resource=False)

    def close(self) -> None:
        """释放仪器；若资源由自身管理，则一并关闭 ResourceManager。"""
        super().close()
        if self._owns_manager and self._manager is not None:
            self._manager.close()
            self._manager = None
            self._owns_manager = False

    # --- SCPI 功能 ---

    def set_voltage(self, voltage: float) -> None:
        """设置输出电压（0~30 V），非法参数在发送前拦截。"""
        value = validate_number(voltage, "电压", 0.0, 30.0)
        self.write(f"VOLT {value:.3f}")

    def get_voltage(self) -> float:
        """回读电压设定值（单位 V，非物理测量值）。"""
        return self.query_float("VOLT?")

    def set_current(self, current: float) -> None:
        """设置电流限制（0~5 A）。"""
        value = validate_number(current, "电流", 0.0, 5.0)
        self.write(f"CURR {value:.3f}")

    def get_current(self) -> float:
        """回读电流限制设定值（单位 A，非物理测量值）。"""
        return self.query_float("CURR?")

    def set_output(self, enabled: bool) -> None:
        """开启/关闭输出，参数必须是 bool。"""
        if not isinstance(enabled, bool):
            raise TypeError("输出状态必须是 bool")
        self.write(f"OUTP {1 if enabled else 0}")

    def get_output(self) -> bool:
        """回读输出开关状态（0/1），非法响应一律报错而不是猜测。"""
        value = self.query_int("OUTP?")
        if value not in (0, 1):
            raise InstrumentError(f"{self.name}: 输出状态响应非法 {value!r}")
        return value == 1
