# 92 系统架构与接口说明

## 1. 系统边界

```
3S 电池 ECM（第三阶段）
      │  Ibat, Vbat
      ▼
独立保护通路（第五阶段许可 + 0.052 Ω 通路）
      │  Ipath, Vin
      ▼
Buck 功率级（PowerLab 真实拓扑与控制器）
      │
      ▼
负载（2.5 Ω 或等效恒流）
```

- 电池不是理想电压源：`Ueff = Σ(OCV_i − Vpol_i)`，端电压 `Vbat = Ueff − I·Rpack`；
- 保护通路是串联元件，因此 Buck 输入电压随电池电流变化；
- 控制反馈取自 Buck 输出，负载变化会通过输入功率反向影响电池端电压。

## 2. 四层验证模型（按证据强度）

| 层级 | 模型 | 用途 | 能证明 | 不能证明 |
| --- | --- | --- | --- | --- |
| L1 历史回放 | PowerLab 历史 Run 指标 | 基准/候选对比 | 历史结果可复算 | 新工况 |
| L2 准稳态耦合 | ECM + 已验证功率映射 | 静态工作点 | 电压/电流/功率一致性 | 动态响应 |
| L3 平均动态 | 3 状态 CCM + PI | 负载阶跃、收敛 | 趋势与稳定性 | 开关纹波 |
| L4 同网表 SPICE | ECM + 保护 + 开关级 Buck | 纹波、瞬态、保护电气后果 | 同一网表双向耦合 | BMS 检测时间、商业器件行为 |

任何结论都必须注明来自哪一层。

## 3. 接口契约

| 接口 | 输入 | 输出 | 只读约束 |
| --- | --- | --- | --- |
| `integration.battery_port_adapter` | 辨识参数、SOC | `BatteryPortState`、`TerminalState` | 只读 results |
| `integration.protection_adapter` | 端电压、电流、温度 | 充放电许可、激活/锁存故障 | 不写保护配置 |
| `integration.powerlab_adapter` | PowerLab 根目录 | 参数快照、历史重算、真实调用 | 不写 PowerLab |
| `integration.testlab_adapter` | 测量列表、限值 | TestLab 判定结果 + 哈希 | 不写 TestLab |
| `integration.measurement_exchange` | 测量项 | JSON 交换包 | 校验后才允许 VERIFIED |

## 4. 状态语义

| 状态 | 含义 |
| --- | --- |
| PASS | 本阶段有有效证据且满足冻结限值 |
| FAIL | 有有效证据但不满足限值 |
| BLOCKED | 缺少必要工具/数据，无法执行 |
| NOT_VERIFIED | 执行了但未取得可判定证据 |
| ERROR | 执行异常 |

`VERIFIED` 只用于测量项本身（来源与计算可追溯），与工程 PASS 是两件事。

## 5. 失败与回退纪律

- 联合 SPICE 求解失败：记录真实异常，允许数值步长回退（25→50→100 ns），
  回退后必须写明实际步长，禁止用回退结果冒充原配置；
- 功率映射：只接受收敛、稳态、CCM、输出稳压四条件同时满足的点；
- 缺映射、缺波形、缺项目目录：一律 BLOCKED，不生成替代数据。
