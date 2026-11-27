# 07 多仪器管理设计

## 1. 为什么只保留一个 ResourceManager

`ResourceManager` 是进程级资源。多台仪器如果各自创建，会出现：

- 句柄重复占用；
- 同一 YAML 的模拟设备状态被多份实例共享，互相干扰；
- 关闭其中一台时可能让其他仪器的会话失效。

实测结论：对同一 YAML 创建两个 `ResourceManager`，它们会共享
PyVISA-sim 的设备状态；关闭其中一个后，另一个已打开的会话会失效。
因此本项目规定：**同一 YAML 只允许一个打开的 `InstrumentManager`**，
重复打开会抛 `InstrumentError`，释放后可重新打开。

## 2. 角色与序列号

| 序列号 | 角色 | 驱动类 | 资源名 |
| --- | --- | --- | --- |
| `PS001` | `psu` | `PowerSupply` | `USB0::0x1111::0x2222::PS001::0::INSTR` |
| `DMM001` | `dmm` | `VirtualMultimeter` / `Multimeter` | `...::DMM001::0::INSTR` |
| `LOAD001` | `load` | `ElectronicLoad` | `...::LOAD001::0::INSTR` |

`DEVICE_TYPES` 保存"序列号 → 角色"映射，`ROLE_KEYWORDS` 保存"角色 → 序列号
关键字"，两者共同完成资源发现与驱动创建。

## 3. 发现机制

```python
manager = InstrumentManager(CONFIG)
manager.open()                 # ResourceManager("<yaml>@sim")
manager.discover()             # 3 个 USB INSTR 资源名
manager.open_device("PS001")   # 按序列号打开，重复调用返回同一对象
manager.get_multimeter()       # DMM001 的便捷方法
```

发现只依赖当前配置的 `@sim` 后端，**不会**自动连接真实仪器。

## 4. 生命周期与关闭顺序

```text
open()
 ├─ 检查配置文件存在 / 是否已有活动 Manager
 ├─ 创建 ResourceManager 并枚举资源
 └─ get_* / open_device 按需打开资源

close()
 ├─ 逐个设备安全关断（负载 INP 0、电源 OUTP 0）
 ├─ 释放每台仪器的会话与资源
 ├─ 关闭 ResourceManager
 └─ 解除配置占用标记
```

- `close_device(serial)`：只影响目标仪器，其他仪器继续可用；关闭后可重新打开；
- 关闭失败不会中断其他仪器的清理，最终以 `ExceptionGroup` 汇报；
- `__exit__` 中如果清理失败且测试体本身已抛异常，**保留原始异常**，只记录日志；
- 驱动构造失败时，释放本次新打开的资源，避免半开连接。

## 5. 资源所有权

- ResourceManager 与资源归 Manager 所有；
- 驱动的 `owns_resource=False`，`close()` 只解除自身引用；
- 因此单台驱动关闭不会误关共享资源，Manager 统一关闭时也不会重复关闭。

## 6. 异常与并发

| 场景 | 行为 |
| --- | --- |
| 配置文件不存在 | `FileNotFoundError` |
| 未知序列号 | `ValueError` |
| 同一 YAML 重复打开 Manager | `InstrumentError` |
| 单台设备安全关断失败 | 继续释放会话，最后抛 `InstrumentError` |
| 批量关闭中某台失败 | 其余仪器继续清理，最后抛 `ExceptionGroup` |
| 测试体异常 + 清理异常 | 保留测试体原始异常 |

## 7. 局限

- 仍是单进程、单线程模型；未实现线程安全锁；
- 未实现真实仪器所需的超时重连、断线恢复与设备热插拔；
- 角色匹配依赖序列号关键字，真实仪器需要按 `*IDN?` 做二次校验。
