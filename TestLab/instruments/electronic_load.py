"""直流电子负载驱动：模式配置、拉载电流与输入开关。"""

from __future__ import annotations

from .base import (
    BaseInstrument,
    InstrumentResponseError,
    validate_number,
)

#: 支持的工作模式（CP 为恒功率模式，虚拟负载只记录模式，不建模功率环）
VALID_MODES = frozenset({"CC", "CV", "CR", "CP"})

MIN_CURRENT = 0.0
MAX_CURRENT = 5.0


class ElectronicLoad(BaseInstrument):
    """恒流/恒压/恒阻/恒功率电子负载。"""

    def set_mode(self, mode: str) -> None:
        """设置工作模式（CC/CV/CR/CP），参数不做静默纠正。"""
        normalized = str(mode).upper()
        if normalized not in VALID_MODES:
            raise ValueError(f"不支持的负载模式: {mode!r}")
        self.write(f"MODE {normalized}")

    def get_mode(self) -> str:
        """回读工作模式。"""
        return self.query("MODE?").upper()

    def set_current(self, current: float) -> None:
        """设置拉载电流（0~5 A）。

        恒流参数只在 CC 模式下有意义；其他模式设置会拒绝，
        避免把无关参数写进仪器后产生误导性回读。
        """
        value = validate_number(current, "负载电流", MIN_CURRENT, MAX_CURRENT)
        if self.get_mode() != "CC":
            raise RuntimeError("只有 CC 模式允许设置拉载电流")
        self.write(f"CURR {value:.3f}")

    def get_current(self) -> float:
        """回读拉载电流设定值，并校验范围。"""
        value = self.query_float("CURR?")
        if not MIN_CURRENT <= value <= MAX_CURRENT:
            raise InstrumentResponseError(f"拉载电流回读越界: {value!r}")
        return value

    def set_input(self, enabled: bool) -> None:
        """开启/关闭负载输入。"""
        if not isinstance(enabled, bool):
            raise TypeError("负载输入状态必须是 bool")
        self.write(f"INP {1 if enabled else 0}")

    def get_input(self) -> bool:
        """回读负载输入状态（仅接受 0/1）。"""
        value = self.query_int("INP?")
        if value not in (0, 1):
            raise InstrumentResponseError(f"负载输入状态响应非法: {value!r}")
        return value == 1

    def safe_shutdown(self) -> None:
        """关闭负载输入，供异常处理与测试收尾使用。"""
        self.set_input(False)

