# 02 上游项目分析

## 1. 上游项目与版本

| 项目 | 本地目录 | 版本 | 许可证 |
| --- | --- | --- | --- |
| PyVISA | `pyvisa-main/` | 1.16.2（安装版本） | MIT |
| PyVISA-sim | `pyvisa-sim-main/` | 0.7.1（安装版本） | MIT |

本地源码仅用于阅读和格式核对；运行时使用 Conda 环境中的 PyPI 包，
不修改上游代码。

## 2. PyVISA 的分层

关键位置：

- `pyvisa/highlevel.py:2934`：`ResourceManager`，管理 VISA 会话与资源。
- `pyvisa/highlevel.py:3133`：`list_resources(query="?*::INSTR")`，
  使用 **VISA 资源正则**（不是 Python 正则）枚举资源。
- `pyvisa/highlevel.py:3265`：`open_resource()`，按资源名创建
  `MessageBasedResource` 等具体资源对象。
- `Resource.write()/query()`：发送 SCPI 命令并读取响应。

调用链可以简化为：

```text
业务代码
  -> ResourceManager("...@sim")
  -> open_resource("USB0::...::INSTR")
  -> resource.write("VOLT 12.000\n")
  -> resource.query("VOLT?\n")
```

## 3. PyVISA-sim 的工作方式

关键位置：

- `pyvisa_sim/parser.py:119`：`parse_file()` 读取 YAML。
- `pyvisa_sim/parser.py:102`：校验 `spec` 版本不能高于解析器支持版本。
- `pyvisa_sim/highlevel.py:202`：`list_resources()` 先取设备列表，
  再按 VISA 正则过滤。
- `pyvisa_sim/highlevel.py:226`：`read()` 从会话读取响应字节。
- `pyvisa_sim/highlevel.py:265`：`write()` 把命令交给会话匹配。

YAML 的核心结构：

```yaml
spec: "1.1"
devices:
  virtual_power_supply:
    dialogues:          # 固定问答，例如 *IDN?
      - q: "*IDN?"
        r: "TestLab,VirtualPowerSupply,PS001,1.0.0"
    properties:         # 可读写属性，例如 VOLT / VOLT?
      voltage:
        getter: {q: "VOLT?", r: "{:.3f}"}
        setter: {q: "VOLT {:.3f}", e: "ERROR"}
        specs: {type: float, min: 0, max: 30}
resources:
  USB::0x1111::0x2222::PS001::INSTR:
    device: virtual_power_supply
```

## 4. 重要限制

1. **没有物理耦合**：电源、电子负载、万用表是三个独立会话。负载拉载不会
   改变电源的 `VOLT?` 回读，DMM 也不会自动测到 DUT 输出。
2. **响应是脚本化的**：读数是 YAML 中的状态值或固定字符串，不是电路仿真。
3. **不验证电气规律**：25 V 设定是否能被接受、保护是否触发，都由 YAML
   的 `specs` / `error` 决定，与真实器件无关。
4. **超时/错误需要显式构造**：例如 `SLOW?` 无响应、`BAD?` 返回 `ERROR`，
   否则虚拟仪器通常立即响应。

## 5. TestLab 的复用与新增

复用：

- `ResourceManager`、`open_resource`、`write/query`；
- `@sim` 后端与 YAML 设备定义；
- VISA 资源名与 SCPI 语义。

新增（自主开发层）：

- `instruments/base.py`：统一连接、超时、错误翻译、日志；
- `instruments/power_supply.py`：电源业务 API；
- `instruments/electronic_load.py`、`multimeter.py`：负载与万用表驱动；
- `models/virtual_dut.py`：12 V→5 V 行为模型；
- `engine/dut_bridge.py`：跨仪器数据桥接；
- `engine/test_runner.py`：自动化测试执行；
- `analysis/metrics.py`：工程指标。

因此，上游负责“通信像真仪器”，TestLab 负责“测试流程像真实产线系统”。

## 6. 许可证

PyVISA 与 PyVISA-sim 均为 MIT License。TestLab 保留上游版权与许可说明，
不复制、不修改上游核心源码。
