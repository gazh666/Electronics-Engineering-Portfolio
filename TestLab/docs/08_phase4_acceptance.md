# 08 阶段四验收清单

本文件记录阶段四（多仪器管理、万用表、电子负载）的实际验收结果。
所有命令均在 `TestLab` 根目录执行，环境为 Windows + `kaifa`（Python 3.11.18）。

## 1. 验收项

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 环境依赖无冲突 | 通过 | `pip check` → `No broken requirements found.` |
| 发现 3 台虚拟仪器 | 通过 | `PS001 / DMM001 / LOAD001` |
| 三台仪器身份查询 | 通过 | 三个 `*IDN?` 均返回 TestLab 虚拟型号 |
| 电源设定与回读 | 通过 | 5.0 V / 1.0 A / 输出 True |
| 负载 CC 模式与拉载 | 通过 | `MODE CC`、1.0 A、`INP 1` |
| DMM 三项读数 | 通过 | 5.0 V / 0.5 A / 4.98 Ω（固定模拟值） |
| Manager 打开/复用 | 通过 | 重复调用返回同一对象 |
| 单台关闭不影响其他 | 通过 | 关闭 PS001 后 DMM/负载仍可用 |
| 重复关闭/重复连接 | 通过 | 幂等，无异常 |
| 批量关闭安全关断 | 通过 | 关闭前输出/输入回到 0 |
| 清理失败不掩盖原始异常 | 通过 | 保留测试体异常 |
| 异常响应与超时 | 通过 | 统一转为 `InstrumentResponseError` / `InstrumentTimeoutError` |

## 2. 实际执行的命令

```powershell
conda run -n kaifa python -m pip check
conda run -n kaifa python -m scripts.multi_instrument_demo
conda run -n kaifa python -m scripts.power_supply_demo
conda run -n kaifa python -m pytest tests -v
```

## 3. 真实运行结果

```text
No broken requirements found.

Discovered instruments:
 - USB0::0x1111::0x2222::PS001::0::INSTR
 - USB0::0x1111::0x2222::DMM001::0::INSTR
 - USB0::0x1111::0x2222::LOAD001::0::INSTR
PSU identity: TestLab,VirtualPowerSupply,PS001,1.0.0
DMM identity: TestLab,VirtualMultimeter,DMM001,1.0.0
Load identity: TestLab,VirtualElectronicLoad,LOAD001,1.0.0
PSU voltage setpoint: 5.0
PSU current limit: 1.0
PSU output enabled: True
Load mode: CC
Load current setpoint: 1.0
Load input enabled: True
DMM voltage reading: 5.0
DMM current reading: 0.5
DMM resistance reading: 4.98
Note: DMM readings are static mock values, not real measurements.
Multi-instrument demo: PASS
```

全量测试：

```text
196 passed in 6.76s
```

## 4. 数据来源声明

- 三台仪器的 SCPI 回读均为 PyVISA-sim 脚本化数据（`pyvisa-sim SCPI` /
  `static_mock`）；
- DMM 的 `model(virtual_dut)+dmm_noise` 通道只用于自动化测试判定；
- 本阶段没有任何真实电气测量结果。

## 5. 已知局限

- DMM SCPI 读数固定，不随电源/负载设置变化；
- 负载 CP/CV/CR 模式只记录模式，不建模功率/电阻/电压环；
- 同一 YAML 同一时间只允许一个打开的 Manager（PyVISA-sim 共享状态限制）；
- 未接入真实仪器，未验证真实总线时序、断线重连与热插拔。
