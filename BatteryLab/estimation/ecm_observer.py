"""轻量 ECM 状态观测器（Task 12 / Task 13）。

结构（一阶或二阶 RC）：

```text
V_pred = OCV(SOC) - I·R0 - Σ Vp_i
residual = V_meas - V_pred
ΔSOC = -expm1(-dt/τ_c) · residual / (dOCV/dSOC)
|ΔSOC| ≤ maximum_correction_rate · dt
```

**这不是 EKF**：没有状态协方差预测、没有测量噪声阵 R、没有卡尔曼增益矩阵，
只是一个固定时间常数 τ_c 的非线性电压残差反馈。文档中禁止称其为"EKF"或
"最优状态估计器"。

时间轴约定（与第二阶段一致）：在 ``[t_k, t_k+1)`` 用 ``I_k`` 推进 SOC 与 RC
状态；到达 ``t_k+1`` 后，用新时刻测量电压计算残差。因此 ``step`` 同时接收
``previous_current_a``（区间电流）与 ``current_a``（新时刻电流，用于端电压
瞬时欧姆项）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from estimation.coulomb_counter import CoulombCounter


class ObserverError(ValueError):
    """观测器输入非法。"""


@dataclass(frozen=True)
class ObserverRCBranch:
    resistance_ohm: float
    time_constant_s: float

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.resistance_ohm)) or float(self.resistance_ohm) <= 0.0:
            raise ObserverError("RC 支路电阻必须为正")
        if not math.isfinite(float(self.time_constant_s)) or float(self.time_constant_s) <= 0.0:
            raise ObserverError("RC 时间常数必须为正")


@dataclass(frozen=True)
class ObserverResult:
    soc: float
    predicted_soc: float
    predicted_voltage_v: float
    residual_v: float
    correction: float
    status: str
    unclipped_soc: float | None = None
    saturated: bool = False


class ECMObserver:
    """基于 ECM 端电压残差的固定增益状态反馈观测器。"""

    def __init__(
        self,
        counter: CoulombCounter,
        r0_ohm: float,
        branches: tuple[ObserverRCBranch, ...],
        ocv_model,
        correction_time_constant_s: float = 120.0,
        minimum_ocv_slope: float = 0.2,
        maximum_correction_rate: float = 0.001,
        maximum_residual_v: float = 0.35,
        current_step_threshold_a: float = 0.5,
        soc_bounds: tuple[float, float] = (0.0, 1.0),
    ) -> None:
        if not isinstance(counter, CoulombCounter):
            raise ObserverError("counter 必须是 CoulombCounter")
        if not math.isfinite(float(r0_ohm)) or float(r0_ohm) <= 0.0:
            raise ObserverError("R0 必须为正")
        if not branches:
            raise ObserverError("至少需要一个 RC 支路")
        if not all(hasattr(ocv_model, name) for name in ("voltage_at", "slope_at")):
            raise ObserverError("ocv_model 必须提供 voltage_at 与 slope_at")
        if not math.isfinite(float(correction_time_constant_s)) or float(correction_time_constant_s) <= 0.0:
            raise ObserverError("校正时间常数必须为正")
        if not math.isfinite(float(minimum_ocv_slope)) or float(minimum_ocv_slope) <= 0.0:
            raise ObserverError("最小 OCV 斜率必须为正")
        if not math.isfinite(float(maximum_correction_rate)) or float(maximum_correction_rate) <= 0.0:
            raise ObserverError("最大校正速率必须为正")
        if not math.isfinite(float(maximum_residual_v)) or float(maximum_residual_v) <= 0.0:
            raise ObserverError("残差门限必须为正")
        if not (0.0 <= float(soc_bounds[0]) < float(soc_bounds[1]) <= 1.0):
            raise ObserverError("SOC 边界非法")

        self.counter = counter
        self.r0_ohm = float(r0_ohm)
        self.branches = tuple(branches)
        self.ocv_model = ocv_model
        self.correction_time_constant_s = float(correction_time_constant_s)
        self.minimum_ocv_slope = float(minimum_ocv_slope)
        self.maximum_correction_rate = float(maximum_correction_rate)
        self.maximum_residual_v = float(maximum_residual_v)
        self.current_step_threshold_a = float(current_step_threshold_a)
        self.soc_bounds = (float(soc_bounds[0]), float(soc_bounds[1]))
        # 初始极化状态显式假设为"实验开始前已充分静置"，即 Vp=0。
        self.polarization = [0.0 for _ in self.branches]
        self.saturation_events: list[dict[str, float | str]] = []
        self.last_status = "INITIALIZED"

    def update_rc(self, previous_current_a: float, dt_s: float) -> None:
        """一阶 RC 精确离散（零阶保持电流）。"""
        if not math.isfinite(float(previous_current_a)) or not math.isfinite(float(dt_s)):
            raise ObserverError("RC 更新输入非法")
        if dt_s <= 0.0:
            raise ObserverError("时间步必须为正")
        new_values: list[float] = []
        for vp, branch in zip(self.polarization, self.branches):
            decay = math.exp(-dt_s / branch.time_constant_s)
            one_minus_decay = -math.expm1(-dt_s / branch.time_constant_s)
            new_values.append(
                vp * decay + float(previous_current_a) * branch.resistance_ohm * one_minus_decay
            )
        self.polarization = new_values

    def step(
        self,
        previous_current_a: float,
        current_a: float,
        measured_voltage_v: float,
        dt_s: float,
        allow_voltage_correction: bool = True,
    ) -> ObserverResult:
        values = [previous_current_a, current_a, measured_voltage_v, dt_s]
        if not all(math.isfinite(float(value)) for value in values):
            raise ObserverError("观测器输入非法")
        if dt_s <= 0.0:
            raise ObserverError("时间步必须为正")

        soc_update = self.counter.step(float(previous_current_a), float(dt_s))
        predicted_soc = soc_update.soc
        self.update_rc(float(previous_current_a), float(dt_s))

        ocv = self.ocv_model.voltage_at(predicted_soc)
        predicted_voltage = ocv - float(current_a) * self.r0_ohm - float(sum(self.polarization))
        residual = float(measured_voltage_v) - predicted_voltage
        slope = self.ocv_model.slope_at(predicted_soc)

        correction = 0.0
        status = "PREDICT_ONLY"

        if soc_update.status != "VALID":
            status = soc_update.status
        elif not allow_voltage_correction:
            status = "PREDICT_ONLY"
        elif not math.isfinite(slope) or slope < self.minimum_ocv_slope:
            status = "LOW_OBSERVABILITY"
        elif abs(residual) > self.maximum_residual_v:
            status = "RESIDUAL_GATED"
        elif abs(float(current_a) - float(previous_current_a)) > self.current_step_threshold_a:
            status = "CURRENT_STEP_HOLD"
        else:
            alpha = -math.expm1(-float(dt_s) / self.correction_time_constant_s)
            correction = alpha * residual / slope
            limit = self.maximum_correction_rate * float(dt_s)
            correction = min(max(correction, -limit), limit)
            status = "VOLTAGE_CORRECTED"

        unclipped = predicted_soc + correction
        saturated = not (self.soc_bounds[0] <= unclipped <= self.soc_bounds[1])
        corrected_soc = min(max(unclipped, self.soc_bounds[0]), self.soc_bounds[1])
        actual_correction = corrected_soc - predicted_soc

        if saturated:
            self.saturation_events.append(
                {
                    "step": float(self.counter.step_count),
                    "unclipped_soc": float(unclipped),
                    "clipped_soc": float(corrected_soc),
                    "status": status,
                }
            )

        self.counter.soc = corrected_soc
        self.last_status = status

        return ObserverResult(
            soc=corrected_soc,
            predicted_soc=predicted_soc,
            predicted_voltage_v=float(predicted_voltage),
            residual_v=float(residual),
            correction=float(actual_correction),
            status=status,
            unclipped_soc=float(unclipped),
            saturated=bool(saturated),
        )
