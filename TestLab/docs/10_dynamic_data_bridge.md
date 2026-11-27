# 10 多仪器动态数据桥接

## 1. 为什么 PyVISA-sim 不能自动模拟设备间电气关系

PyVISA-sim 只根据 YAML 定义响应 SCPI 指令，它把每台仪器当作独立的
“指令-响应”脚本，不理解电源、负载与万用表之间的电气连接。因此：

- 电子负载设置 2 A，不会改变电源的 `VOLT?` 回读值；
- 电源设置 5 V，万用表 `MEAS:VOLT?` 仍返回 YAML 中写死的值；
- 关闭一台仪器的会话，不会自动影响另一台。

真实的电气关系必须由应用层显式建立，这就是数据桥接层的职责。

## 2. SCPI 参数回读

每轮计算前，桥接层重新读取以下设置值（均为仪器设定值，不是物理测量）：

| 参数 | 指令 | 来源 |
| --- | --- | --- |
| 输入电压设定 | `VOLT?` | 虚拟电源 |
| 输入电流限制 | `CURR?` | 虚拟电源 |
| 电源输出状态 | `OUTP?` | 虚拟电源 |
| 负载电流设定 | `CURR?` | 虚拟电子负载 |
| 负载模式 | `MODE?` | 虚拟电子负载 |
| 负载输入状态 | `INP?` | 虚拟电子负载 |

负载启用时仅支持 CC 模式；其他模式直接抛 `NotImplementedError`，
不生成看似合理的模型结果。

## 3. VirtualTestBench 如何关联设备

`bench/virtual_test_bench.py` 持有 `InstrumentManager`、`VirtualDUT` 和
`DutDataBridge`：

```text
InstrumentManager
   ├── get_power_supply()  ──┐
   ├── get_electronic_load()─┼──> DutDataBridge.acquire()
   └── get_multimeter()     │        │
                                    ├── 读取 SCPI 设置值
                                    ├── VirtualDUT.calculate()
                                    └── DUTResult（带来源标签）
```

`read_state()` 每次调用都会重新读取仪器设置并重新计算，
不复用上一次结果；同一快照中的电压、电流、功率来自同一次 `DUTResult`。

## 4. ModelMultimeter

`ModelMultimeter` 是模型测量适配器，不访问 SCPI：

- `measure_voltage()` → `Measurement(vout, "V", "behavioral_model")`
- `measure_current()` → `Measurement(iout, "A", "behavioral_model")`

`Measurement` 同时携带数值、单位与来源标签，报告层据此区分数据来源。

## 5. 固定模拟响应与动态模型数据

| 通道 | 数据来源 | 典型值 | 是否随设置变化 |
| --- | --- | --- | --- |
| 原始 DMM `MEAS:VOLT?` | YAML 固定响应 | 5.0 V | 否 |
| 原始 DMM `MEAS:CURR?` | YAML 固定响应 | 0.5 A | 否 |
| 模型电压 | `VirtualDUT` 计算 | 4.98 V @ 1 A | 是 |
| 模型电流 | `VirtualDUT` 计算 | 1.0 A @ 1 A | 是 |

两条通道用途不同：固定响应用于验证 SCPI 通信链路；模型数据用于
电源性能判定。二者不得混入同一性能指标，也不得把固定响应描述为
真实测量。

## 6. 为什么保留原始 Multimeter 驱动

- 验证 SCPI 读写、异常响应、超时处理是否正常；
- 为未来接入真实硬件保留统一接口；
- 模型适配层只增加数据来源，不替换底层驱动，避免推翻已有实现。

## 7. 未来如何接入 ngspice 与真实硬件

- **ngspice**：保持 `VirtualDUT.calculate()` 接口不变，把内部实现替换为
  调用 ngspice 的稳态/瞬态仿真结果；桥接层与报告层无需修改。
- **真实硬件**：把 `ModelMultimeter` 替换为真实 DMM 读数，桥接层改为
  读取真实电源/负载的回读值；数据来源标签改为 `real hardware`。
- 无论哪种接入方式，都必须保留来源标签与异常传播，禁止在通信失败时
  生成替代数据。
