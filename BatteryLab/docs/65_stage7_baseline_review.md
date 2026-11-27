# 65 第七阶段基线复核与问题定义

日期：2026-11-26
运行环境：Conda `kaifa_battery` / Python 3.11.18 / numpy / PySpice 1.5 / ngspice 34

## 1. 目标

在不修改 TestLab / PowerLab 的前提下，为 BatteryLab 增加 SOC / SOH 估计能力，
并用真实 CALCE 数据做可复现验证。所有结论必须区分：

- 真实实验数据；
- 由真实数据推导的参考量（例如由电流积分的参考 SOC）；
- 合成真值（synthetic truth）；
- SPICE 仿真；
- 硬件实测（本阶段没有）。

## 2. 基线事实（逐项核实）

| 项 | 结果 |
| --- | --- |
| 解释器 | Python 3.11.18（conda `kaifa_battery`） |
| 依赖一致性 | `pip check`：No broken requirements found |
| 基线测试 | 第七阶段开始前 `pytest tests -q` = 366 passed |
| 第七阶段结束后 | `pytest tests -q` = **412 passed（64.78 s）** |
| 版本控制 | BatteryLab 目录**不是 git 仓库**，`git status` 报 not a git repository，无法提供 commit diff |
| 冻结模型 | `calce_sp2_25c_inr18650_20r_first_order_v1` |

冻结模型参数（来自 `data/identified/model_calce_sp2_25c_inr18650_20r_first_order_v1/identified_parameters.yaml`）：

| 参数 | 数值 | 单位 |
| --- | --- | --- |
| capacity_ah | 2.0280827046460144 | Ah |
| r0_ohm | 0.0770684639742517 | Ω |
| r1_ohm | 0.022844622881180852 | Ω |
| tau1_s | 18.01583641375959 | s |
| c1_f | 788.6248 | F |
| 辨识 SOC 区间 | 0.01063693 ~ 0.50683666 | 0-1 |

辨识区间只有约 10%–51% SOC，因此把模型用于 0–1 全区间属于**外推**，结果中
必须标注。

## 3. 数据资产

`configs/dataset_split.yaml` 的真实角色：

| 数据集 | 角色 | 第七阶段用法 |
| --- | --- | --- |
| dst_50 | training | 训练集，仅作开发自检 |
| dst_80 | development | 用于确定静置阈值与校正频率 |
| fuds_50 / fuds_80 | independent_validation | 第三阶段已用于选模，**只能作历史对照** |
| us06_50 / us06_80 | extra_validation | 未参与调参，作为独立测试 |
| bjdst_50 / bjdst_80 | extra_validation | 未参与调参，作为独立测试 |

环境与老化数据：

- 仅 25℃ 数据；`temperature_extension.available = false` → 温度失配实验 NOT_VERIFIED；
- `data/raw` 只有 9 个 zip，均为初始容量/OCV/动态工况，没有连续老化数据 →
  真实 SOH/内阻老化 NOT_VERIFIED。

实测采样特征（脚本运行得到）：

| 数据集 | 样本数 | 时长 s | 中位 dt s | 最大 dt s |
| --- | --- | --- | --- | --- |
| dst_50 | 6685 | 6740 | ~1.0 | — |
| us06_50 | 6874 | 6897 | 1.003 | 1.559 |
| bjdst_50 | 6940 | 7008 | ~1.0 | — |

参考 SOC 会略低于 0（容量口径差异），因此评价时掩码 `0 ≤ ref ≤ 1` 并报告覆盖率。

## 4. 本阶段严格边界

1. 不修改 TestLab / PowerLab。
2. 不覆盖历史结果，每次运行新建 `results/.../run_<id>`。
3. 不降低预登记限值。
4. 不虚构数据、不虚构实验次数。
5. 实验参考 SOC ≠ 实测真实 SOC。
6. 固定时间常数残差反馈观测器**不叫 EKF**。
7. 第七阶段完成后暂停，不提前做第八阶段 KiCad。

## 5. 关键结论（详见 docs/76）

- 22 项预登记检查 PASS，0 FAIL，6 项 NOT_VERIFIED；
- ECM 观测器在 4 个独立工况上 RMSE 1.61–2.00 pp、最大误差 2.93–3.09 pp、
  覆盖率 100%；
- 真实 ngspice 电流回放 2 次求解，区间电荷误差 −0.00149%；
- 温度失配与真实老化没有数据，保持 NOT_VERIFIED。

## 6. 复现基线

```bash
conda run -n kaifa_battery python -m pytest tests -q
conda run -n kaifa_battery pip check
```

## 7. 练习与面试题

练习：

1. 用 `git status` 验证 BatteryLab 是否受版本控制，并说明为什么这会影响
   "可追溯性"但不等同于"结果无效"。
2. 从 `configs/dataset_split.yaml` 找出所有 `extra_validation` 数据集，说明
   为何它们比 FUDS 更适合做本阶段独立测试。

面试题：

1. 为什么"同一条电流积分得到的参考 SOC"不能证明绝对 SOC 精度？
2. 模型辨识区间只有 10%–51%，把它用于 0–100% 会带来哪两类风险？
