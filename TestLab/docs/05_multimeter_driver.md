# 05 数字万用表驱动设计

## 1. 作用

虚拟 DMM 用于读取直流电压、电流与电阻，验证供电/拉载流程是否正常。
本项目的 DMM 有两条完全不同的读数通道，必须严格区分：

| 通道 | 方法 | 数据来源 | 用途 |
| --- | --- | --- | --- |
| SCPI 测量通道 | `measure_voltage()` / `measure_current()` / `measure_resistance()` | YAML 固定模拟值（`static_mock`） | 通信链路、多仪器流程演示 |
| 模型读数通道 | `read_dc_voltage(true_value)` | VirtualDUT 真值 + ADC 噪声（`model(virtual_dut)+dmm_noise`） | 自动化测试判定 |

SCPI 通道的读数**不会**随电源电压或负载电流变化，也不代表 DUT 端子的真实电压。

## 2. SCPI 命令与响应

| 方法 | 命令 | 响应示例 | 说明 |
| --- | --- | --- | --- |
| `measure_voltage()` | `MEAS:VOLT?` | `5.0000` | 固定模拟电压 |
| `measure_current()` | `MEAS:CURR?` | `0.5000` | 固定模拟电流 |
| `measure_resistance()` | `MEAS:RES?` | `4.9800` | 固定模拟电阻 |
| `measure_bad()` | `BAD?` | `ERROR` | 模拟非法响应 |
| `measure_slow()` | `SLOW?` | 无响应 | 模拟通信超时 |

## 3. 核心实现

```python
def measure_resistance(self) -> float:
    value = self.query_float("MEAS:RES?")   # 拒绝非数字 / NaN / inf
    if value < 0:
        raise ValueError(f"电阻读数不能为负: {value!r}")
    return value
```

- 解析全部走 `BaseInstrument.query_float()`，异常响应统一转
  `InstrumentResponseError`；
- 负电阻是物理上不可能的响应，直接拒绝，不参与后续计算；
- 未连接时所有测量方法都会抛 `InstrumentNotConnectedError`。

## 4. 异常处理

| 场景 | 异常 |
| --- | --- |
| 未连接 | `InstrumentNotConnectedError` |
| 返回 `ERROR` | `InstrumentResponseError` |
| 返回非数字 / `NaN` / `inf` | `InstrumentResponseError` |
| `SLOW?` 无响应 | `InstrumentTimeoutError` |
| 电阻为负 | `ValueError` |

## 5. 测试覆盖

`tests/test_multimeter.py` 覆盖：身份查询、电压/电流读数、电阻读数、负电阻、
`nan/inf/abc` 非法响应、`ERROR` 响应、超时、未连接操作、模型噪声读数。

## 6. 局限

- 固定模拟值只用于验证通信与流程，不能用于电源精度/负载调整率结论；
- 多台虚拟仪器不共享物理状态，DMM 不会自动测到电源或负载的变化；
- 真实 DMM 的量程、采样率、输入阻抗、共模抑制等特性均未建模。
