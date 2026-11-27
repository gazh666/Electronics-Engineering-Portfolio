# 19 第三阶段基线复核（真实文件与数据）

本文对应 Task 1：在进入真实数据辨识前，逐项确认前两阶段真实存在的文件、接口、数据完整性与工具可用性。
所有结论来自本机实际执行，不是规划推断。

## 1. 执行命令与实测输出

```powershell
cd "BatteryLab"
Get-Location
Get-ChildItem -Force
conda run -n kaifa_battery python --version
conda run -n kaifa_battery python -m pip check
conda run -n kaifa_battery python -m scripts.verify_environment
conda run -n kaifa_battery python -m pytest tests -v
```

| 检查 | 实测结果 |
| --- | --- |
| 工作目录 | `BatteryLab` |
| 版本控制 | 该目录不是 git 仓库，`git status --short` 不可用（如实记录，不伪造） |
| Python | 3.11.18（环境 `kaifa_battery`） |
| 关键包 | numpy 2.4.6、pandas 3.1.1、scipy 1.17.1、PyBaMM 26.11.0.0、PySpice 1.5 |
| ngspice | 34（`spice_environment_demo` 可真实启动并求解） |
| `pip check` | 无损坏依赖 |
| `verify_environment` | 全部检查 PASS |
| 第二阶段基线 | 118 passed |
| 第三阶段完成后 | 168 passed（含本次新增 8 项边界测试） |

## 2. 逐项核查真实文件

| 任务书要求路径 | 实际情况 |
| --- | --- |
| `docs/08_stage1_validation.md` | 存在 |
| `docs/18_stage2_validation.md` | 存在 |
| `data/raw/` | 存在，含 9 个 CALCE zip |
| `data/processed/` | 存在（第一阶段清洗结果） |
| `data/manifests/` | 存在，`dataset_manifest.json` 记录文件名与 SHA256 |
| `datasets/calce_loader.py` | 存在，支持 xls/xlsx、跨工作表、符号检测 |
| `datasets/data_quality.py` | 存在 |
| `battery_models/ocv_model.py` | 存在；第三阶段新增 `IdentifiedOcvModel` |
| `battery_models/ecm_solver.py` | 存在；零阶保持统一求解器 |
| `battery_models/first_order_rc.py` | 存在 |
| `battery_models/second_order_rc.py` | 存在 |
| `battery_models/battery_pack.py` | 存在；3S1P 串并联与限压逻辑 |
| `analysis/pulse_response.py` | 存在 |
| `analysis/battery_metrics.py` | 存在 |
| `analysis/model_comparison.py` | 存在 |
| `circuits/battery_ecm_circuit.py` | 存在；生成真实 ngspice 网表 |

## 3. 真实数据与实验条件

| 项目 | 实际情况 |
| --- | --- |
| 电芯型号 | INR18650-20R |
| 额定容量 | 2.0 Ah |
| 样品编号 | SP1、SP2、SP3（同型号不同样品） |
| 实验温度 | 仅 25 ℃ |
| 初始 SOC | 由放电容量平衡反算：`SOC0 = 1 - qd(动态段起点)/Q_measured` |
| 实测容量 | SP2 2.028083 Ah；SP1 2.009165 Ah |
| 电流符号（原始） | 充电为正、放电为负 |
| 电流符号（项目归一化） | 放电为正、充电为负 |
| 时间轴 | 原始采样秒；区间 `[t_k, t_k+1)` 用左端电流（零阶保持） |

符号归一化：

```text
I_normalized = -I_raw        # 仅当文件声明 charge_positive 时
SOC(t) = SOC0 - (1/Q) ∫ I_normalized dt
```

### 3.1 公式推导与单位

原始文件充电为正，项目约定放电为正，因此归一化是一步线性变换：

```text
I_norm,k = s · I_raw,k，s = −1（charge_positive）或 +1（discharge_positive）
qd_k = Σ_{j<k} I_norm,j · Δt_j / 3600     [Ah]
```

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `I_raw` | 文件原始电流 | A |
| `I_norm` | 归一化电流 | A |
| `s` | 符号因子 ±1 | 1 |
| `Q` | 实测容量 | Ah |
| `Δt` | 采样间隔 | s |

### 3.2 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `load_archive(archive, dataset_id, cell_id)` | 读取 CALCE 压缩包为统一表 |
| `_detect_sign_simple(frame)` | 符号检测 |
| `convert_current_sign(frame, sign)` | 归一化为放电为正 |
| `load_experiment_frame(record)` | 按工作表过滤并校验时间轴 |
| `check_packages / check_ngspice / summarize` | 环境检查与汇总（`scripts/verify_environment.py`） |

## 4. 复核时发现的真实缺陷与修复

**缺陷**：`datasets/calce_loader.py::_detect_sign_simple` 只覆盖“平均电流为正”的分支。
`SP1_25C_LC_OCV_11_5_2015.zip` 以 0.1 A 放电为主、局部充电，平均电流为负，返回 `UNKNOWN`。

**影响**：无法确定低电流 OCV 的积分方向，直接阻断第三阶段 OCV 提取。

**修复**：补齐 `mean_current < 0` 的两种组合（电压上升/下降各一支），并新增回归测试
`tests/test_calce_sign_detection.py`。修复后 9 个文件全部得到明确符号，且与原始工步物理含义一致。

说明：`data/manifests/dataset_manifest.json` 中历史 `current_sign` 字段与当前检测可能不一致；
加载器每次运行都重新检测，回归测试直接校验归一化后的电流方向，因此不影响阶段三结果。

## 5. 实际文件路径与关键源码逐行解释

- `datasets/calce_loader.py`（符号检测与归一化）
- `scripts/verify_environment.py`（环境检查）
- `configs/dataset_split.yaml`（数据角色与 SHA256）

```python
def _detect_sign_simple(frame: pd.DataFrame) -> str:
    mean_current = float(frame["current_a"].mean())          # 原始平均电流
    voltage_delta = float(frame["voltage_v"].iloc[-1] - frame["voltage_v"].iloc[0])
    if mean_current > 0 and voltage_delta > 0:               # 正电流且电压上升 → 充电为正
        return "charge_positive"
    if mean_current > 0 and voltage_delta < 0:               # 正电流但电压下降 → 放电为正
        return "discharge_positive"
    if mean_current < 0 and voltage_delta < 0:               # 负电流且电压下降 → 充电为正
        return "charge_positive"
    if mean_current < 0 and voltage_delta > 0:               # 负电流且电压上升 → 放电为正
        return "discharge_positive"
    return "UNKNOWN"
```

第 1 行取平均电流；第 2 行用首末电压差判断能量方向；后 4 行覆盖四种组合；无法判定时明确返回
`UNKNOWN`，而不是猜测。

## 6. 运行命令

```powershell
cd "BatteryLab"
conda run -n kaifa_battery python -m scripts.verify_environment
conda run -n kaifa_battery python -m pytest tests/test_calce_sign_detection.py -v
```

## 7. 实际结果

- 环境与依赖完整，ngspice 真实可用；
- 16 个要求路径全部存在（路径以实际项目为准）；
- 修复符号检测缺陷后，9 个 CALCE 文件全部可解析；
- 第二阶段 118 项测试保持通过，为第三阶段提供可信基线。

## 8. 已知局限

1. 只有 25 ℃，没有 0 ℃/45 ℃ 真实文件，温度特性必然 `NOT_VERIFIED`；
2. OCV 来自 SP1，动态与容量来自 SP2，增量 OCV 来自 SP3，属于跨样品参考模型；
3. `dataset_manifest.json` 的历史符号字段不可作为运行时依据；
4. 本目录不是 git 仓库，无法用提交哈希标识版本。

## 9. 学习练习

1. 用一段 10 点数据手算 `mean_current` 与 `voltage_delta`，判断符号；
2. 构造“平均电流为 0”的对称充放电段，说明为什么必须拒绝判定；
3. 把 `SOC0 = 1 - qd/Q` 改写成积分形式，并解释为什么不能用验证电压反推 SOC0。

## 10. 面试题

1. 为什么原始实验文件的电流符号不能直接用于模型？
2. 只有平均电流与首末电压，符号检测的失效场景有哪些？
3. 为什么跨样品 OCV + 动态数据仍然可以构建参考模型？边界在哪里？
