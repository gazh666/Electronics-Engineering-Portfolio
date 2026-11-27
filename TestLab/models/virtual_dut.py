"""虚拟被测电源（DUT）稳态数学行为模型。

模型定义：12 V 输入、5 V 输出、额定 2 A 的简化降压 DC-DC 电源。

重要边界说明：
- 本模型是**简化的确定性数学行为模型**，不是 SPICE 开关电路仿真，
  不是真实硬件测试，也不能证明真实电源的保护特性；
- 0.90 的转换效率是预设模型参数，不是实验测得的效率；
- 模型采用“保护即停机”的简化策略：过流/输入限流时输出归零，
  真实电源可能存在恒流、折返、打嗝、锁存等不同保护方式；
- 模型不考虑空载静态功耗、开关损耗、纹波、瞬态响应与温度变化；
- 后续可在此接口后替换为真实 SPICE 仿真输出或真实硬件测量。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

#: 行为模型数据来源标签，用于报告中区分仪器设定值与模型计算值
MODEL_SOURCE = "behavioral_model"

#: 配置文件必须包含的模型参数
REQUIRED_CONFIG_KEYS = (
    "nominal_input_voltage",
    "min_input_voltage",
    "max_input_voltage",
    "nominal_output_voltage",
    "max_output_current",
    "output_resistance",
    "nominal_efficiency",
)


class DUTState(str, Enum):
    """DUT 工作/保护状态。

    继承 ``str`` 以兼容既有代码与报告中的字符串比较（``state == "NORMAL"``）。
    """

    NORMAL = "NORMAL"
    OUTPUT_OFF = "OUTPUT_OFF"
    UNDERVOLTAGE = "UNDERVOLTAGE"
    OVERVOLTAGE = "OVERVOLTAGE"
    OVERCURRENT = "OVERCURRENT"
    INPUT_CURRENT_LIMIT = "INPUT_CURRENT_LIMIT"

    def __str__(self) -> str:
        """打印与报告展示时只输出状态名，例如 ``NORMAL``。"""
        return self.value


@dataclass(frozen=True)
class DUTConfig:
    """DUT 模型参数（不可变，来自默认值或 YAML 配置）。

    所有参数在构造时校验；非法配置直接抛 ``ValueError``，
    避免带着错误参数进入后续计算。
    """

    name: str = "Virtual Buck DC-DC Converter"
    nominal_input_voltage: float = 12.0
    min_input_voltage: float = 9.0
    max_input_voltage: float = 16.0
    nominal_output_voltage: float = 5.0
    max_output_current: float = 2.0
    output_resistance: float = 0.02
    nominal_efficiency: float = 0.90
    protection_strategy: str = "shutdown"
    data_source: str = MODEL_SOURCE

    def __post_init__(self) -> None:
        values = (
            self.nominal_input_voltage,
            self.min_input_voltage,
            self.max_input_voltage,
            self.nominal_output_voltage,
            self.max_output_current,
            self.output_resistance,
            self.nominal_efficiency,
        )
        for value in values:
            # bool 是 int 的子类，必须显式拒绝，避免 True 被当作 1.0
            if isinstance(value, bool):
                raise ValueError("配置值不能是布尔类型")
            if not isinstance(value, (int, float)):
                raise ValueError("配置值必须是数字")
            if not math.isfinite(value):
                raise ValueError("配置值必须是有限数值")

        if not (0 < self.min_input_voltage < self.max_input_voltage):
            raise ValueError("输入电压范围非法：需满足 0 < 最低 < 最高")
        if not (
            self.min_input_voltage
            <= self.nominal_input_voltage
            <= self.max_input_voltage
        ):
            raise ValueError("标称输入电压超出允许范围")
        if self.nominal_output_voltage <= 0:
            raise ValueError("标称输出电压必须大于 0")
        if self.max_output_current <= 0:
            raise ValueError("最大输出电流必须大于 0")
        if self.output_resistance < 0:
            raise ValueError("等效输出电阻不能为负数")
        if not 0 < self.nominal_efficiency <= 1:
            raise ValueError("转换效率必须大于 0 且不超过 1")

        # 额定电流下的输出电压必须为正，否则模型自相矛盾
        rated_voltage = (
            self.nominal_output_voltage
            - self.max_output_current * self.output_resistance
        )
        if rated_voltage <= 0:
            raise ValueError("额定电流下输出电压必须大于 0")

        if self.protection_strategy != "shutdown":
            raise ValueError("仅支持 shutdown 保护策略")
        if self.data_source != MODEL_SOURCE:
            raise ValueError(f"数据来源必须标记为 {MODEL_SOURCE}")


@dataclass
class DUTResult:
    """一次 DUT 行为计算结果。

    前 8 个字段保持与旧版一致的位置顺序，后续字段带默认值，
    避免破坏既有调用方与测试。
    """

    vin: float
    iin: float
    vout: float
    iout: float
    pin: float
    pout: float
    efficiency: float | None
    state: DUTState | str
    source: str = MODEL_SOURCE
    #: 电源输入电压设定值（与模型实际供电电压 ``vin`` 区分）
    vin_setpoint: float | None = None
    #: 电源输入电流限制设定值
    input_current_limit: float | None = None
    #: 电子负载需求电流设定值（与模型实际输出电流 ``iout`` 区分）
    load_current_setpoint: float | None = None
    #: 输入功率与输出功率之差
    power_loss: float = 0.0


class VirtualDUT:
    """12 V 输入 / 5 V 输出 DC-DC 电源的确定性行为模型。

    参数既可通过 :class:`DUTConfig` 注入，也可通过 ``from_yaml`` 读取；
    实例属性保留可变，供故障注入层临时覆盖（退出后恢复）。
    """

    def __init__(self, config: DUTConfig | None = None) -> None:
        self.config = config if config is not None else DUTConfig()
        # 从配置初始化运行参数；故障注入会临时覆盖这些属性
        self.nominal_voltage = self.config.nominal_output_voltage
        self.min_input = self.config.min_input_voltage
        self.max_input = self.config.max_input_voltage
        self.max_current = self.config.max_output_current
        self.output_resistance = self.config.output_resistance
        self.nominal_efficiency = self.config.nominal_efficiency

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> "VirtualDUT":
        """从 YAML 配置构造模型；缺失字段与非法参数给出明确错误。"""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"DUT 配置文件不存在: {path}")

        with path.open("r", encoding="utf-8") as file:
            raw = yaml.safe_load(file)

        if not isinstance(raw, dict):
            raise ValueError("DUT 配置文件顶层必须是映射")
        if "dut" not in raw:
            raise ValueError("DUT 配置文件缺少 dut 段")

        data = raw["dut"]
        if not isinstance(data, dict):
            raise ValueError("dut 段必须是映射")

        missing = [key for key in REQUIRED_CONFIG_KEYS if key not in data]
        if missing:
            raise ValueError(f"DUT 配置缺少字段: {', '.join(missing)}")

        optional = {}
        for key in ("name", "protection_strategy", "data_source"):
            if key in data:
                optional[key] = data[key]

        try:
            config = DUTConfig(
                **{key: float(data[key]) for key in REQUIRED_CONFIG_KEYS},
                **optional,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"DUT 配置非法: {exc}") from exc

        return cls(config)

    @staticmethod
    def _validate_number(value: float, name: str) -> float:
        """把输入转换为有限非负数；布尔值与 NaN/inf 一律拒绝。"""
        if isinstance(value, bool):
            raise ValueError(f"非法 {name}: 不能是布尔值")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"非法 {name}: {value!r}") from None
        if not math.isfinite(number):
            raise ValueError(f"非法 {name}: 必须是有限数值")
        if number < 0:
            raise ValueError(f"非法 {name}: 不能为负数")
        return number

    def _shutdown_result(
        self,
        *,
        vin: float,
        vin_setpoint: float,
        input_current_limit: float | None,
        load_current_setpoint: float,
        state: DUTState,
        output_enabled: bool,
    ) -> DUTResult:
        """保护停机结果：输出归零，效率不可定义。"""
        return DUTResult(
            vin=vin if output_enabled else 0.0,
            iin=0.0,
            vout=0.0,
            iout=0.0,
            pin=0.0,
            pout=0.0,
            power_loss=0.0,
            efficiency=None,
            state=state,
            vin_setpoint=vin_setpoint,
            input_current_limit=input_current_limit,
            load_current_setpoint=load_current_setpoint,
        )

    def calculate(
        self,
        vin: float,
        load_current: float,
        enabled: bool = True,
        *,
        input_current_limit: float | None = None,
        output_enabled: bool | None = None,
        load_enabled: bool | None = None,
    ) -> DUTResult:
        """根据输入电压、电流限制与负载需求计算稳态结果。

        参数
        ----
        vin
            输入电压设定值（V），由虚拟程控电源的设定值提供。
        load_current
            电子负载需求电流（A）。
        enabled
            输出使能；``output_enabled`` 提供时以其为准。
        input_current_limit
            电源输入电流限制（A）；``None`` 表示不检查（兼容旧调用）。
        output_enabled
            电源输出状态；``None`` 时使用 ``enabled``。
        load_enabled
            电子负载输入状态；``False`` 时按空载（0 A）计算。

        兼容性
        ------
        旧调用 ``calculate(vin, load_current, enabled=False)`` 保持有效；
        同时支持阶段五参考写法的位置参数 ``calculate(vin, limit, load)``。
        当第三个位置参数不是布尔值时，按 ``(vin, 限制, 负载)`` 解释。
        """
        # 兼容阶段五参考调用顺序：第三个位置参数不是 bool 时视为电流限制
        if not isinstance(enabled, bool) and input_current_limit is None:
            input_current_limit = load_current
            load_current = enabled
            enabled = True

        vin_setpoint = self._validate_number(vin, "input voltage")
        load_current_setpoint = self._validate_number(
            load_current, "load current"
        )
        if input_current_limit is None:
            limit = math.inf
            limit_record = None
        else:
            limit = self._validate_number(
                input_current_limit, "input current limit"
            )
            limit_record = limit

        if output_enabled is None:
            output_enabled = enabled
        if not isinstance(output_enabled, bool):
            raise TypeError("输出状态必须是 bool")
        if load_enabled is None:
            load_enabled = True
        if not isinstance(load_enabled, bool):
            raise TypeError("负载状态必须是 bool")

        # 判定顺序：输出关闭 > 欠压 > 过压 > 过流 > 输入限流 > 正常
        effective_load = load_current_setpoint if load_enabled else 0.0

        if not output_enabled:
            state = DUTState.OUTPUT_OFF
        elif vin_setpoint < self.min_input:
            state = DUTState.UNDERVOLTAGE
        elif vin_setpoint > self.max_input:
            state = DUTState.OVERVOLTAGE
        elif effective_load > self.max_current:
            state = DUTState.OVERCURRENT
        else:
            state = DUTState.NORMAL

        if state != DUTState.NORMAL:
            return self._shutdown_result(
                vin=vin_setpoint,
                vin_setpoint=vin_setpoint,
                input_current_limit=limit_record,
                load_current_setpoint=load_current_setpoint,
                state=state,
                output_enabled=output_enabled,
            )

        vout = self.nominal_voltage - effective_load * self.output_resistance
        iout = effective_load
        pout = vout * iout
        # 效率为预设模型参数：输入功率按固定效率反推
        pin = pout / self.nominal_efficiency
        iin = pin / vin_setpoint
        power_loss = pin - pout

        # 输入电流超过程控电源限流：采用简化停机策略
        if iin > limit:
            return self._shutdown_result(
                vin=vin_setpoint,
                vin_setpoint=vin_setpoint,
                input_current_limit=limit_record,
                load_current_setpoint=load_current_setpoint,
                state=DUTState.INPUT_CURRENT_LIMIT,
                output_enabled=output_enabled,
            )

        values = (vout, iout, pout, pin, iin, power_loss)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("模型计算结果出现非有限数值")

        efficiency = pout / pin if pin > 0 else None

        return DUTResult(
            vin=vin_setpoint,
            iin=iin,
            vout=vout,
            iout=iout,
            pin=pin,
            pout=pout,
            efficiency=efficiency,
            state=DUTState.NORMAL,
            vin_setpoint=vin_setpoint,
            input_current_limit=limit_record,
            load_current_setpoint=load_current_setpoint,
            power_loss=power_loss,
        )
