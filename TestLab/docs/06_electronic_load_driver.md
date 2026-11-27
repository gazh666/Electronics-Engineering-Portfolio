# 06 电子负载驱动设计

## 1. 作用

虚拟电子负载用于模拟被测电源的负载电流，验证电源在轻载/满载/过流场景下的
设定值响应与流程控制。当前只记录模式与设定值，不对功率环路建模。

## 2. 工作模式

| 模式 | 含义 | 本项目行为 |
| --- | --- | --- |
| `CC` | 恒流 | 可设置拉载电流（0–5 A） |
| `CV` | 恒压 | 只记录模式，不支持设置电流 |
| `CR` | 恒阻 | 只记录模式 |
| `CP` | 恒功率 | 只记录模式，功率环未建模 |

模式输入统一转大写，但不做静默裁剪，例如 `"cc "` 会被判为非法，避免驱动
擅自"修正"用户参数。

## 3. 核心 API

| 方法 | 命令 | 说明 |
| --- | --- | --- |
| `set_mode(mode)` | `MODE CC` | 仅接受 CC/CV/CR/CP |
| `get_mode()` | `MODE?` | 回读模式 |
| `set_current(current)` | `CURR 1.000` | 仅 CC 模式，0–5 A |
| `get_current()` | `CURR?` | 回读并校验范围 |
| `set_input(enabled)` | `INP 1/0` | 严格 bool |
| `get_input()` | `INP?` | 只接受 0/1 |
| `safe_shutdown()` | `INP 0` | 异常收尾 |

## 4. 参数校验与安全设计

- `set_current()` 使用 `validate_number()`：拒绝非数字、`None`、`NaN`、`inf`、
  `bool` 与越界值；
- **非 CC 模式禁止设置电流**：避免把无意义参数写入仪器后产生误导性回读；
- `get_input()` 对 `2 / 1.5 / abc` 等异常响应直接报错，不猜测状态；
- `safe_shutdown()` 只关闭输入，不改变模式与电流设定，便于复现测试条件；
- 未连接时所有操作抛 `InstrumentNotConnectedError`。

## 5. 异常处理

| 场景 | 异常 |
| --- | --- |
| 未知模式 | `ValueError` |
| 电流越界/非法 | `ValueError` |
| 非 CC 模式设置电流 | `RuntimeError` |
| 输入状态非 bool | `TypeError` |
| 回读状态非法 | `InstrumentResponseError` |
| 未连接 | `InstrumentNotConnectedError` |

## 6. 测试覆盖

`tests/test_electronic_load.py` 覆盖：身份、四种模式、电流设置/回读、边界值、
越界与 `NaN/inf/bool`、非 CC 模式拒绝、输入开关、非法输入响应、安全关断。

## 7. 局限

- 不建模真实负载的功率环路、瞬态响应与散热；
- 恒压/恒阻/恒功率模式只保存模式字符串，不参与任何计算；
- 负载输入开关不会改变电源的 SCPI 回读值，跨仪器影响需由
  `engine/dut_bridge.py` 显式桥接。
