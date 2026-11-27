# 03 SCPI 协议说明

本文件先解释 VISA / SCPI 的基础概念，再给出 TestLab 三台虚拟仪器的完整命令表。
所有结论均基于当前实际安装版本：PyVISA 1.16.2、PyVISA-sim 0.7.1。

## 1. VISA 是什么

VISA（Virtual Instrument Software Architecture，虚拟仪器软件架构）是 IVI 基金会
制定的仪器 I/O 标准接口。

- 它统一了 GPIB、USB、TCP/IP、串口等不同总线的读写方式，屏蔽厂商差异；
- 在 Python 中通过 **PyVISA** 调用；
- `ResourceManager` 是入口：负责枚举资源（`list_resources`）和打开会话
  （`open_resource`）；
- 生命周期：创建 ResourceManager → 打开资源 → 读写 → 关闭资源 → 关闭
  ResourceManager。

本项目使用 **PyVISA-sim** 作为 VISA 后端（`<yaml>@sim`），不连接真实硬件。
因此 VISA 层的行为（资源名、会话、超时、终止符）与真实仪器一致，但数据来自
YAML 脚本，不是物理测量。

## 2. SCPI 是什么

SCPI（Standard Commands for Programmable Instruments，可编程仪器标准命令）是
建立在 VISA 之上的**应用层文本命令**标准。

- 命令是一棵分层命令树，用 `:` 分隔层级，例如
  `CONF:VOLT:DC`、`SYST:ERR?`；
- 每个命令有短格式与长格式（如 `VOLT` / `VOLTage`），本项目统一使用短格式；
- 命令末尾带 `?` 表示查询，仪器会返回一段文本；
- 命令通常以换行等终止符结束。

```text
VOLT 12.000     设置电压（写命令，无响应）
VOLT?           查询电压设定值（查询命令，有响应）
OUTP 1          打开输出
OUTP?           查询输出状态
```

## 3. VISA 与 SCPI 的区别

| 对比项 | VISA | SCPI |
| --- | --- | --- |
| 层次 | 传输层 / I/O 接口 | 应用层 / 命令语言 |
| 解决问题 | 怎么连上仪器、怎么收发字节 | 发什么内容、仪器如何理解 |
| 关注点 | 资源地址、会话、超时、终止符 | 命令树、参数、响应格式 |
| 类比 | 电话线路与拨号方式 | 通话时使用的语言 |
| 本项目例子 | `ResourceManager("...@sim")`、`open_resource` | `VOLT 12.000`、`*IDN?` |

一句话：**VISA 负责"通道"，SCPI 负责"内容"**。两者缺一不可。

## 4. write 与 query 的区别

| 方法 | 行为 | 适用场景 | 错误用法后果 |
| --- | --- | --- | --- |
| `write(cmd)` | 只发送，不读取响应 | 设置类命令（`VOLT 12`、`OUTP 1`） | 用 write 发查询，响应会滞留在缓冲区，下一次查询读到旧值 |
| `query(cmd)` | 发送后等待并读取响应 | 查询类命令（`VOLT?`、`*IDN?`） | 用 query 发设置命令，会一直等到超时 |

本项目在 `BaseInstrument` 中分别封装 `write()` 与 `query()`，仪器驱动按语义选择，
不允许混用。

**实测证据**：在 PyVISA-sim 0.7.1 中，越界写入 `VOLT 31` 会触发 YAML 的
`e: "ERROR"`，错误串进入输出缓冲区：

```text
VOLT 31   -> （错误回包 ERROR 进入缓冲区）
VOLT?     -> 'ERROR'      ← 读到的是上一条命令的错误回包
VOLT?     -> '12.000'     ← 再下一次才读到正确值
```

这正是驱动必须在发送前做量程校验（`validate_number`）的原因。

## 5. *IDN? 指令的作用

`*IDN?`（Identify）是 SCPI 强制要求的身份查询，返回四段信息：

```text
厂商, 型号, 序列号, 固件版本
TestLab,VirtualPowerSupply,PS001,1.0.0
```

用途：

- 确认连接的确实是目标仪器（而不是同总线上另一台设备）；
- 写入测试报告，保证结果可追溯；
- 在多仪器场景中作为角色匹配后的二次确认。

## 6. 终止字符的作用

终止字符（termination / EOM）标记一条消息的结束，告诉 VISA 层"这条读完了"。

- 本项目 YAML 中 `eom: USB INSTR: q: "\n" r: "\n"`，查询与响应都用换行；
- 驱动绑定资源时统一设置 `read_termination="\n"`、`write_termination="\n"`；
- 终止符不一致的后果：读不到结尾会一直等到超时；终止符过短会把两条响应粘成
  一条；过长则可能把正文截断。

## 7. 通信超时的含义

超时是"等待仪器响应的最长时间"，单位毫秒，本项目默认 2000 ms。

- 超时后 PyVISA 抛出 `VisaIOError`，错误码为 `VI_ERROR_TMO`；
- 驱动将其转换为 `InstrumentTimeoutError`，不会吞掉；
- 超时后仪器侧可能仍有未读数据，必须重新同步（清空缓冲区或重新打开会话），
  否则后续查询会错位；
- 本项目用 YAML 中的 `SLOW?`（无响应查询）来稳定复现超时场景。

## 8. 仪器资源地址的组成

```text
USB0::0x1111::0x2222::PS001::0::INSTR
 │      │        │       │     │   └── 资源类：INSTR（消息型仪器）
 │      │        │       │     └────── 接口索引
 │      │        │       └──────────── 序列号
 │      │        └──────────────────── 产品 ID
 │      └───────────────────────────── 厂商 ID
 └──────────────────────────────────── 接口类型 + 板号
```

- 接口类型常见值：`USB`、`GPIB`、`TCPIP`、`ASRL`（串口）；
- 简写 `USB::0x1111::0x2222::PS001::INSTR` 也能被 PyVISA 解析，打开时会规范化
  为 `USB0::...::0::INSTR`（本项目已实测）；
- 可用 `list_resources("?*::INSTR")` 枚举当前后端的全部资源。

本项目资源发现结果：

```text
USB0::0x1111::0x2222::PS001::0::INSTR    程控电源
USB0::0x1111::0x2222::DMM001::0::INSTR   数字万用表
USB0::0x1111::0x2222::LOAD001::0::INSTR 直流电子负载
```

## 9. 通信参数

- 传输层：PyVISA-sim，`USB INSTR` 资源；
- 结束符：查询与响应均为 `\n`；
- 命令风格：不带前导冒号，例如 `VOLT`、`VOLT?`；
- 错误回包：`ERROR`；驱动会转换为 `InstrumentError`，避免把错误字符串当数字
  继续计算。

## 10. 程控电源（PSU）

| 命令 | 类型 | 响应格式 | 说明 |
| --- | --- | --- | --- |
| `*IDN?` | 查询 | 字符串 | 仪器身份 |
| `*RST` / `*CLS` | 写 | 无 | 复位/清状态 |
| `VOLT?` | 查询 | `12.000` | 读取电压设定值 |
| `VOLT 12.000` | 写 | 无 | 设置电压，范围 0–30 V |
| `CURR?` | 查询 | `2.000` | 读取电流限值 |
| `CURR 2.000` | 写 | 无 | 设置电流限值，范围 0–5 A |
| `OUTP?` | 查询 | `0` / `1` | 输出状态 |
| `OUTP 1` | 写 | 无 | 打开/关闭输出 |
| `SYST:ERR?` | 查询 | `0,"No error"` | 错误队列 |

驱动 API 与命令映射：

```text
set_voltage(12.0) -> "VOLT 12.000"
get_voltage()     -> "VOLT?" -> 12.000
set_current(2.0)  -> "CURR 2.000"
get_current()     -> "CURR?" -> 2.000
set_output(True)  -> "OUTP 1"
get_output()      -> "OUTP?" -> True
```

## 11. 数字万用表（DMM）

| 命令 | 类型 | 响应格式 | 说明 |
| --- | --- | --- | --- |
| `*IDN?` | 查询 | 字符串 | 仪器身份 |
| `*RST` / `*CLS` | 写 | 无 | 复位/清状态 |
| `CONF:VOLT:DC` | 写 | 无 | 配置直流电压测量 |
| `CONF:CURR:DC` | 写 | 无 | 配置直流电流测量 |
| `MEAS:VOLT?` | 查询 | `5.0000` | 电压读数（模拟） |
| `MEAS:CURR?` | 查询 | `0.5000` | 电流读数（模拟） |
| `SLOW?` | 查询 | 无响应 | 模拟通信超时 |
| `BAD?` | 查询 | `ERROR` | 模拟非法响应 |

注意：`MEAS:VOLT?` 返回的是 YAML 中 `voltage` 属性的值，**不是** DUT 模型
的真实输出。自动化测试中，模型输出电压由 `DutDataBridge` 显式提供，
DMM 噪声通道标记为 `model(virtual_dut)+dmm_noise`。

## 12. 直流电子负载（ELoad）

| 命令 | 类型 | 响应格式 | 说明 |
| --- | --- | --- | --- |
| `*IDN?` | 查询 | 字符串 | 仪器身份 |
| `*RST` / `*CLS` | 写 | 无 | 复位/清状态 |
| `MODE?` | 查询 | `CC` | 当前负载模式 |
| `MODE CC` | 写 | 无 | 设置恒流模式（CC/CV/CR） |
| `CURR?` | 查询 | `1.000` | 读取拉载电流 |
| `CURR 1.000` | 写 | 无 | 设置拉载电流，范围 0–5 A |
| `INP?` | 查询 | `0` / `1` | 负载输入状态 |
| `INP 1` | 写 | 无 | 打开/关闭负载输入 |
| `SYST:ERR?` | 查询 | `0,"No error"` | 错误队列 |

## 13. 异常响应与数据来源

- 写命令越界时，YAML 返回 `ERROR`。TestLab 在驱动层先用 `validate_number()`
  做量程校验，避免把非法值发给仪器后造成响应错位。
- `SLOW?` 无响应会触发 PyVISA 超时，驱动转换为 `InstrumentTimeoutError`。
- `BAD?` 返回 `ERROR`，驱动转换为 `InstrumentError`。
- 未定义的查询同样返回 `ERROR`，由基类统一转换为 `InstrumentError`。
- 所有 SCPI 回读均为**设定值/仪器状态**，报告中标记为 `pyvisa-sim SCPI`；
  不得描述为真实电气测量。
