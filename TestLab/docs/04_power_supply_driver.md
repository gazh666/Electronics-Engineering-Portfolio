# 04 程控电源驱动设计

本文件说明程控直流电源的基础概念、驱动设计、设计取舍与能力边界。
所有数值与测试结果均来自实际运行，使用的虚拟仪器定义见
`configs/instruments.yaml`。

## 1. 程控直流电源基础概念

### 1.1 程控直流电源的作用

程控直流电源是可通过总线（GPIB/USB/LAN 等）设定输出电压、电流上限和输出开关的
直流供电设备，常用于元器件、板卡和电源产品的研发与产线测试。

典型使用流程：设定电压 → 设定限流 → 打开输出 → 等待稳定 → 用万用表/示波器
测量 → 关闭输出。本项目的虚拟电源完整走这条流程，但数据由 PyVISA-sim 脚本提供。

### 1.2 电压设定值与实际输出电压

| 概念 | 含义 | 本项目中的表现 |
| --- | --- | --- |
| 电压设定值 | 下发给仪器的目标电压 | `VOLT 12.000`，回读 `VOLT?` 得到 `12.000` |
| 实际输出电压 | 端子上的真实电压 | **未测量**。需外部 DMM 采集，且受负载、线阻、纹波、温漂影响 |

`get_voltage()` 返回的是**设定参数回读**，只能证明"指令已生效"，不能证明
"端子电压就是 12.000 V"。文档与代码注释均按此语义标注。

### 1.3 电流限制与实际负载电流

- **电流限制**是保护上限，由用户设定（本项目 0–5 A）；
- **实际负载电流**由被测负载决定，不由电源单方面决定；
- 当负载需求小于限值时，电源稳压输出，电流随负载变化；
- 当负载需求达到限值，电源进入限流状态，电压被拉低以维持电流不超限。

本项目只回读限流设定值（`CURR?`），不测量真实负载电流。

### 1.4 恒压 CV 与恒流 CC 工作模式

| 模式 | 触发条件 | 行为 |
| --- | --- | --- |
| CV（恒压） | 负载电流 < 限流值 | 维持设定电压，电流由负载决定 |
| CC（恒流） | 负载电流达到限流值 | 维持限流值，电压随负载下降 |

工作点由"设定电压 + 设定限流 + 负载"共同决定。真实电源在 CV/CC 之间连续切换，
并伴随瞬态过冲；本项目**不建模模式切换与瞬态过程**，只保存两个设定值。

## 2. 文件与职责

| 文件 | 职责 |
| --- | --- |
| `instruments/base.py` | 公共连接管理、SCPI 收发、超时、错误翻译、日志 |
| `instruments/power_supply.py` | 电源业务 API：电压/电流/输出 |
| `instruments/manager.py` | 发现资源、按角色打开、共享资源 |
| `scripts/power_supply_demo.py` | 电源驱动独立演示 |
| `tests/test_power_supply.py` | 正常、边界、异常测试 |
| `tests/test_discovery.py` | 资源发现与角色匹配测试 |

## 3. 类结构

```python
class PowerSupply(BaseInstrument):
    def connect(self) -> None
    def close(self) -> None
    def set_voltage(self, voltage: float) -> None
    def get_voltage(self) -> float
    def set_current(self, current: float) -> None
    def get_current(self) -> float
    def set_output(self, enabled: bool) -> None
    def get_output(self) -> bool
```

支持两种使用方式：

```python
# 方式一：驱动自己管理 ResourceManager（适合独立演示）
with PowerSupply(CONFIG) as psu:
    psu.set_voltage(12.0)

# 方式二：由 InstrumentManager 统一管理多台仪器（推荐）
with InstrumentManager(CONFIG) as manager:
    psu = manager.create("psu", PowerSupply)
```

第二种方式下 `owns_resource=False`，资源由 Manager 统一关闭，避免重复关闭。

## 4. 参数校验（为什么需要）

```python
value = validate_number(voltage, "电压", 0.0, 30.0)
self.write(f"VOLT {value:.3f}")
```

`set_current()` 范围为 `0–5 A`。`validate_number()` 会拒绝：

- 非数字字符串（`"abc"`）；
- `None`；
- `NaN` / `±inf`；
- 布尔值（`True` 会被 `float()` 静默转成 `1.0`，必须显式拒绝）；
- 超出量程的值。

**为什么必须在发送前校验**：PyVISA-sim 对越界写入会返回 `ERROR`，该错误串留在
输出缓冲区，导致下一次查询读到旧错误（详见 `docs/03` 第 4 节实测）。真实仪器
同样存在错误队列与响应错位风险，因此校验属于驱动层职责，而不是"提高通过率"的
手段。

`set_output()` 要求严格的 `bool`，避免 `1`、`"1"` 等隐式真值导致歧义。

回读侧同样有校验：`query_float()` 拒绝 `nan/inf`，`query_int()` 拒绝非整数，
`get_output()` 只接受 `0/1`，避免把异常响应当成有效状态。

## 5. 异常与资源释放

| 场景 | 异常/行为 |
| --- | --- |
| 未连接就调用 API | `InstrumentNotConnectedError` |
| 通信超时 | `InstrumentTimeoutError` |
| 仪器返回 `ERROR` | `InstrumentError` |
| 电压/电流越界 | `ValueError` |
| 输出参数不是 bool | `TypeError` |
| 连接失败 | 释放已创建的 Manager，不残留半开连接 |
| 重复 `close()` | 幂等，不报错 |
| 重复 `connect()` | 幂等，复用原会话 |

## 6. SCPI 交互序列

```text
*IDN?            -> TestLab,VirtualPowerSupply,PS001,1.0.0
VOLT?            -> 0.000
CURR?            -> 1.000
OUTP?            -> 0
VOLT 12.000
CURR 2.000
OUTP 1
VOLT?            -> 12.000
CURR?            -> 2.000
OUTP?            -> 1
OUTP 0
OUTP?            -> 0
```

## 7. 实际运行结果

执行：

```powershell
conda run -n kaifa python -m scripts.power_supply_demo
```

实际输出（退出码 0）：

```text
Instrument: TestLab,VirtualPowerSupply,PS001,1.0.0
Default voltage: 0.0
Default current limit: 1.0
Default output state: False
Voltage setpoint: 12.0
Current limit: 2.0
Output state: True
Configuration test: PASS
Output disabled: True
```

执行：

```powershell
conda run -n kaifa python -m pytest tests/test_discovery.py tests/test_power_supply.py -v
```

实际结果：

```text
49 passed in 1.18s
```

执行全量测试：

```powershell
conda run -n kaifa python -m pytest tests -v
```

实际结果：

```text
161 passed in 6.43s
```

电源驱动测试覆盖：

- 身份查询与连接；
- 电压/电流设置与回读（含 0、上限、3 位小数精度）；
- 输出开关；
- 电压/电流越界、NaN、±inf、字符串、None、bool；
- 回读 `nan/inf/-inf` 与非数字字符串；
- 输出状态非法响应（`2`、`1.5`、`abc`）；
- 未连接操作；
- 重复连接、重复关闭；
- 上下文管理器退出后资源释放；
- 连接失败后的资源清理；
- 非法参数不改变之前的有效设定值；
- 单个驱动关闭后共享 ResourceManager 仍可用。

## 8. 设计取舍

### 8.1 为什么需要统一通信基类

三台仪器（电源、万用表、电子负载）都要做同样的事：连接、设置超时与终止符、
写/查、错误翻译、日志、释放。如果每台仪器各写一份，会出现：

- 异常类型不统一，上层无法统一处理；
- 终止符/超时设置遗漏；
- 日志格式不一致，排障困难；
- 关闭逻辑重复且容易出错。

`BaseInstrument` 把这些公共行为收敛到一处，仪器子类只写业务 API（`VOLT`、
`CURR` 等），符合"单一职责"。

### 8.2 为什么 ResourceManager 由外部统一管理

- ResourceManager 是进程级资源，重复创建会浪费句柄，且多实例之间状态不一致；
- 多仪器场景需要一个地方统一枚举资源、按角色分配、统一关闭；
- 若每台仪器各自创建并关闭 ResourceManager，一台仪器关闭时可能误伤其他仪器。

因此本项目由 `InstrumentManager` 持有唯一 ResourceManager，只把**已打开的资源**
注入驱动，并设置 `owns_resource=False`。驱动拿不到 ResourceManager，从结构上
不可能误关共享资源（已有测试覆盖）。

### 8.3 为什么使用 try/finally 释放资源

```python
try:
    psu.set_output(True)
    run_test()
finally:
    psu.set_output(False)   # 无论测试成功、失败还是抛异常，都回到安全状态
```

- 测试中途异常时，若没有 `finally`，输出可能一直保持开启，危及被测件；
- `try/finally` 保证"关闭输出"一定执行，且不会掩盖原始异常；
- 资源层同样遵循此原则：`__exit__` 负责关闭会话，Manager 负责统一关闭资源。

## 9. 数据语义与局限

- `get_voltage()` / `get_current()` 是**仪器设定参数回读**，不是 DUT 的真实
  电气测量值；
- 电源驱动不负责计算 DUT 输出，该工作由 `models/virtual_dut.py` 与
  `engine/dut_bridge.py` 完成；
- 当前模拟设备**无法验证**以下真实物理特性：
  - 实际输出电压精度、纹波与噪声；
  - 负载瞬态响应、过冲与恢复时间；
  - CV/CC 切换行为与限流折返特性；
  - 保护阈值（OVP/OCP/OTP）的真实精度与动作时间；
  - 线损、开尔文远端补偿、温度漂移与热特性；
  - 效率的真实值（模型中的 0.90 是预设参数，不是实验结果）；
  - EMC/EMI 与安规特性。
- 未来接入真实仪器时，优先只替换资源打开方式与 YAML 配置，尽量不改业务层 API。

## 10. 与原始 PyVISA-sim 的区别

| 对比项 | 原始 PyVISA-sim | 本阶段自主开发（TestLab） |
| --- | --- | --- |
| 定位 | VISA 后端模拟器：解析 YAML，返回脚本化响应 | 应用层测试平台：驱动、管理、判定、报告 |
| 是否修改上游源码 | —— | **不修改**，仅通过 `<yaml>@sim` 加载自定义定义 |
| 仪器抽象 | 无业务驱动，需用户自行拼 SCPI | `BaseInstrument` + 三台业务驱动 |
| 参数校验 | 越界时返回 `ERROR`（会造成响应错位） | 发送前 `validate_number` 拦截，回读再做有限性校验 |
| 异常体系 | 抛出 PyVISA 底层异常 | 统一翻译为 `InstrumentError` / `InstrumentTimeoutError` / `InstrumentNotConnectedError` |
| 多仪器资源 | 每台仪器独立会话，无统一管理 | `InstrumentManager` 统一持有 ResourceManager 与角色匹配 |
| 数据语义 | YAML 固定响应 | 明确区分 `pyvisa-sim SCPI` 设定值与行为模型值 |
| 测试与文档 | 上游自带测试（针对模拟器本身） | 针对本平台驱动/流程的测试与中文文档 |

## 11. 本阶段自主开发与验证清单

- `instruments/base.py`：连接、SCPI 收发、超时、异常翻译、日志、幂等关闭；
- `instruments/power_supply.py`：电压/限流设定与回读、输出开关、边界与响应校验；
- `instruments/manager.py`：资源发现、角色匹配、共享资源、统一关闭；
- `scripts/power_supply_demo.py`：真实 `@sim` 通信演示，含失败保护；
- `tests/test_power_supply.py`、`tests/test_discovery.py`：49 个用例覆盖正常、
  边界、异常与资源生命周期；
- 全量回归：161 passed，0 failed。
