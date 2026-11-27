# TestLab 简历证据表（真实数据 · 复核版）

> 采集时间：2026-11-25（Asia/Shanghai）
> 工作区：`TestLab`，分支 `master`，HEAD `6156c2b`，共 4 个提交，**无 remote**。
> 环境：Windows 10（10.0.26200），conda 环境 `kaifa`，Python 3.11.18。
> 原则：只记录实际执行/实际读取到的数据；未执行项标 `NOT_VERIFIED`。
> 项目性质：**PyVISA-sim 应用层二次开发 + AI 辅助开发**，个人学习项目，不是企业量产项目。

---

## 0. 本次实际执行的验证命令

| 命令 | 实际结果 | 时间 |
| --- | --- | --- |
| `git status --short` | 151 项：33 修改 / 1 删除 / 117 未跟踪；未 add、未 commit | 2026-11-25 |
| `conda run -n kaifa python --version` | `Python 3.11.18` | 2026-11-25 |
| `conda run -n kaifa python -m pip check` | `No broken requirements found.` | 2026-11-25 |
| `python -m pytest tests --collect-only -q` | `557 tests collected in 1.40s` | 2026-11-25 |
| `python -m pytest tests -v` | `557 passed in 20.47s`（0 failed / 0 skipped） | 2026-11-25 |
| `python -m pytest tests --cov=... --cov-report=term --cov-report=json` | `557 passed in 34.53s`；`TOTAL 5682 stmts, 734 miss, 1786 branch, 335 BrPart, 84%` | 2026-11-25 |
| `python -m ruff check .` | `All checks passed!` | 2026-11-25 |
| `python -m scripts.verify_release` | 7 PASS + 3 `NOT_VERIFIED` | 2026-11-25 |
| `python -m scripts.run_test_suite --suite SUITE-REGRESSION` | 12/12 PASS，run_id `0ac59300384940b98fc78633e064f439` | 2026-11-25 10:03 |

### 0.1 模块覆盖率（coverage.py 语句 + 分支，JSON 实测）

| 模块 | 语句 | 分支 | 综合覆盖率 |
| --- | --- | --- | --- |
| `core` | 27/27 | 4/4 | 100.0% |
| `bench` | 39/39 | 0/0 | 100.0% |
| `engine` | 1112/1188 | 303/352 | 91.9% |
| `instruments` | 428/468 | 101/120 | 90.0% |
| `analysis` | 453/502 | 161/202 | 87.2% |
| `models` | 150/167 | 57/72 | 86.6% |
| `storage` | 300/339 | 57/82 | 84.8% |
| `reports` | 348/396 | 109/146 | 84.3% |
| `reliability` | 877/1025 | 279/386 | 81.9% |
| `ui` | 1214/1531 | 274/422 | 76.2% |
| **合计** | **4948/5682（87.1%）** | **1345/1786（75.3%）** | **84.27%（显示 84%）** |

最低文件：`ui/views/instruments.py` 40.6%、`ui/views/performance.py` 42.2%、`ui/components.py` 57.7%。
简历写“综合覆盖率 84%（语句 87.1% / 分支 75.3%）”，不要写“全模块 90%+”。

---

## 1. 量化指标证据表

| # | 量化指标 | 实际数值 | 统计口径 | 证据文件及行号 | 运行编号 / 数据位置 | 是否适合写入简历 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 虚拟仪器类型 | 3 类 / 3 个 VISA 资源 | `devices` + `resources` 段计数 | `configs/instruments.yaml` L11-173、L175-181 | — | ✅ |
| 2 | SCPI 指令（YAML 定义） | **21 条 = 查询 12 + 设置 9**；单设备各 10 条（含共享共 30 条次） | 三台设备 YAML 指令并集去重 | `configs/instruments.yaml` L24-173 | — | ✅ 写“21 条去重 SCPI 定义” |
| 2b | SCPI 指令（驱动实际发送） | **18 条 = 查询 11 + 设置 7** | 驱动代码实际调用；`*RST`、`*CLS`、`SYST:ERR?` 仅定义未调用 | `instruments/power_supply.py` L83-112；`multimeter.py` L47-87；`electronic_load.py` L21-66 | — | ✅ 更严谨时用 18 |
| 3 | 公开方法 | **30 个** = 业务方法 21（PSU 6 + DMM 8 + Load 7）+ 基类通信/生命周期 9 | 不含属性、`__enter__/__exit__`；PSU 重写的 `connect/close` 不重复计数 | `instruments/base.py` L132-279；`instruments/manager.py` L146-258 | — | ✅ 写“30 个公开方法” |
| 4 | 业务测试用例 | 配置 12 条（TC001–TC012），全部启用并实际执行 | YAML 条目数 | `configs/test_cases.yaml` L32-175 | `0ac59300384940b98fc78633e064f439` | ✅ |
| 5 | 测试方案 | 4 套：`SUITE-SMOKE` 2、`SUITE-PROTECTION` 4、`SUITE-REGRESSION` 12、`SUITE005` 5 | 方案 `cases` 计数 | `configs/test_suites.yaml` L16-62 | 同上 | ✅ |
| 6 | DUT 状态类型 | 6 种：`NORMAL/OUTPUT_OFF` + 4 保护态 | 枚举成员计数 | `models/virtual_dut.py` L39-50、L310-351 | — | ✅ |
| 7 | 工程指标 | **7 类独立指标 / 10 个指标函数**（另有 4 个兼容实现 + 7 个辅助函数，共 21 个公开函数） | 只把物理量公式计为指标，统计/聚合函数不计 | `analysis/metrics.py` L54-241、L257-355；明细见 §2 | — | ✅ 写“10 个指标函数（7 类指标）” |
| 8 | 扫描工况 | 39 点：负载 11、线性 10、二维 18 | 实际运行 `sample_counts` | `configs/sweep_config.yaml` L5-48；`results/performance_20261124_174411_09c255/summary.json` | `performance_20261124_174411_09c255` | ✅ |
| 9 | 故障注入场景 | 配置 9、触发 9；单次运行注入 11 次 | `triggered_scenario_count=9`、`total_fault_injections=11` | `configs/fault_scenarios.yaml` L33-110 | `20261124_094417_ea05cd14` | ✅（注明模拟） |
| 10 | 异常场景结果 | 见 §3.3 逐场景表 | 每场景 1 条基准用例，F009 另加 1 条 SKIP | `results/reliability/run_20261124_094417_ea05cd14/scenario_results.csv` | `20261124_094417_ea05cd14` | ✅（模拟） |
| 11 | 重试与恢复 | 重试 3 / 可重试操作 2 / 恢复 1 / 恢复率 50.0% / 耗尽 1 / 开销 400 ms | 分母为可重试故障操作数，不是注入次数 | `retry_statistics.json`；`reliability_summary.json` | `20261124_094417_ea05cd14` | ✅（模拟） |
| 12 | Pytest | 557 收集、557 通过、0 失败、0 跳过 | pytest 实测 | `tests/`（38 文件） | 2026-11-25 | ✅ |
| 13 | 覆盖率 | 84.27%（语句 87.1% / 分支 75.3%） | coverage.py 语句+分支 | §0.1；`docs/29_test_quality_report.md` | 2026-11-25 | ✅ |
| 14 | 12 用例回归耗时 | 引擎 11.698 ms；墙钟 178 ms | 引擎 `total_duration_ms` + `runs` 起止时间；模型计算非硬件耗时 | `runs` 表 `0ac59300...`；`results/automation/run_0ac59300.../summary.json` | `0ac59300384940b98fc78633e064f439` | ⚠️ 只写“毫秒级模型执行” |
| 15 | Streamlit 页面 | 6 页 | `PAGE_NAME` 常量 | `ui/views/*.py`；`tests/test_streamlit_app.py` L13-19 | — | ✅ |
| 16 | 数据导出格式 | CSV、JSON、HTML + 离线综合报告 HTML | 服务层导出函数 | `ui/service.py` L1363-1455；`reports/generator.py` L706-822 | `6e5b159f...` | ✅ |
| 17 | SQLite | 4 张业务表；当前 57 / 133 / 328 / 188 行 | 实际行数（新增 12 用例运行后） | `storage/sqlite_store.py` L32-103；`results/testlab.db` | 2026-11-25 | ✅ |
| 18 | 代码规模 | 72 个应用层 `.py`、15,201 行；测试 38 文件、5,302 行 | 排除第三方/缓存/results | 本次统计 | — | ✅ |
| 19 | Docker | `NOT_VERIFIED` | 未安装 Docker，仅有配置文件 | `Dockerfile`、`compose.yaml` | 2026-11-25 | ❌ |
| 20 | Linux 部署 | `NOT_VERIFIED` | 无 Linux 实机记录 | `scripts/start_linux.sh`、`docs/31_linux_deployment.md` | 2026-11-25 | ❌ |
| 21 | GitHub Actions | `NOT_VERIFIED` | 无 remote、未推送、无真实 CI 记录 | `.github/workflows/ci.yml` | 2026-11-25 | ❌ |
| 22 | 真实硬件 | `NOT_VERIFIED` | DMM 为 `static_mock`，无真实仪器 | `instruments/multimeter.py` L1-22 | — | ❌ |
| 23 | 纹波 / 瞬态 | 未实现 | 模型无时间序列 | `analysis/metrics.py` L1-9 | — | ❌ |
| 24 | 静态检查 | ruff 0 错误 | E4/E7/E9/F | `pyproject.toml` | 2026-11-25 | ✅ |
| 25 | 综合报告/备份 | 报告 HTML 13,614 B；备份 307,200 B，完整性 ok | 文件实际大小 | `results/reports/`、`results/backups/` | 2026-11-24/25 | ✅ |
| 26 | Git 状态 | 151 项未提交，4 个提交，无 remote | 见 §4 分类 | `git status --short` | 2026-11-25 | ⚠️ 只写“本地 Git 管理” |

---

## 2. 工程指标函数复核（修正原“15 个指标函数”口径）

`analysis/metrics.py` 共 21 个公开函数，其中只有 10 个是实现物理量的指标函数，归为 7 类：

| 类别 | 函数（行号） | 公式 | 输入 → 输出 |
| --- | --- | --- | --- |
| 功率 | `input_power` L54 | Pin = Vin × Iin | 电压/电流 → W |
| 功率 | `output_power` L61 | Pout = Vout × Iout | 电压/电流 → W |
| 功率 | `power_loss_watts` L202 | Ploss = Pin − Pout | 四参数 → W（允许负值暴露异常） |
| 效率 | `efficiency_percent` L68 | η = Pout / Pin × 100 | 四参数 → %；Pin=0 返回 `None` |
| 电压误差 | `voltage_error_volts` L178 | ΔV = Vm − Vref | → V（带符号） |
| 电压误差 | `signed_voltage_error_percent` L189 | ΔV% = (Vm − Vref)/Vref × 100 | → %（带符号） |
| 电压误差 | `absolute_voltage_error_percent` L197 | \|ΔV\|/Vref × 100 | → %（判限值用） |
| 负载调整率 | `load_regulation_percent` L133 | \|Vnl − Vfl\| / Vnom × 100 | 三参数 → % |
| 线性调整率 | `line_regulation_span_percent` L211 | (Vmax − Vmin)/Vnom × 100 | 序列+标称 → % |
| 线性调整率 | `line_regulation_mv_per_v` L229 | \|ΔVout\| × 1000 / \|ΔVin\| | 四参数 → mV/V |

不计为独立指标的 11 个函数：

- 兼容/通用重复实现（4）：`power_watts` L171、`voltage_absolute_error` L109、`voltage_error_percent` L116、`line_regulation_percent` L153。
- 数据质量/统计/聚合（7）：`efficiency_anomaly` L84、`calculate_metrics` L257、`pass_rate_percent` L283、`missing_fields` L301、`mean` L341、`std` L348、`summarize` L355。

> 简历统一写“10 个工程指标函数（覆盖功率、效率、电压误差、负载调整率、线性调整率 5 类物理量 / 7 类指标）”。

---

## 3. 真实业务运行明细

### 3.1 完整 12 用例方案（本次实际执行）

| 字段 | 实际值 |
| --- | --- |
| run_id | `0ac59300384940b98fc78633e064f439` |
| 测试方案 | `SUITE-REGRESSION`「完整回归测试」 |
| 计划 / 执行 | 12 / 12 |
| PASS / FAIL / ERROR / SKIP | **12 / 0 / 0 / 0** |
| 有效判定通过率 PASS/(PASS+FAIL) | 100.0% |
| 已执行通过比例 PASS/已执行 | 100.0% |
| 计划通过比例 PASS/计划 | 100.0% |
| 运行耗时 | 引擎 11.698 ms；墙钟 02:03:07.224→02:03:07.402 UTC（178 ms） |
| 数据来源 | `behavioral_model`（12 条全部） |
| 检查项 | 35 条，全部 PASS |
| 结果文件 | `results/automation/run_0ac59300384940b98fc78633e064f439/` |

逐用例：TC001–TC012 全部 PASS，单例引擎耗时 0.823–1.655 ms。

### 3.2 普通测试运行（SUITE005）

| 字段 | 实际值 |
| --- | --- |
| run_id | `6e5b159fc91b43e3a5d1eb1d3879276c` |
| 方案 / 计划 / 执行 | `SUITE005` / 5 / 5 |
| PASS / FAIL / ERROR / SKIP | 5 / 0 / 0 / 0 |
| 三种通过率 | 均为 100% |
| 耗时 | 引擎 4.74 ms；墙钟约 58 ms |
| 数据来源 | `behavioral_model` |
| 结果文件 | `results/automation/run_6e5b159fc91b43e3a5d1eb1d3879276c/` |

### 3.3 可靠性验证运行（10 个实验）

| 字段 | 实际值 |
| --- | --- |
| run_id | `20261124_094417_ea05cd14` |
| 计划 / 执行 | 11 / 10（F009 额外 1 条后续用例被 SKIP） |
| PASS / FAIL / ERROR / SKIP | 2 / 2 / 6 / 1 |
| 有效判定通过率 PASS/(PASS+FAIL) | **50.0%** |
| 已执行通过比例 PASS/已执行 | **20.0%** |
| 实验通过率（独立口径） | **10/10 = 100%**（“按预期识别并处理故障”） |
| 耗时 | 各场景引擎合计 428.2 ms；整体墙钟约 784 ms |
| 数据来源 | `behavioral_model` / `fault_injected_model` |
| 结果文件 | `results/reliability/run_20261124_094417_ea05cd14/` |

| 场景 | 状态 | 关键现象 |
| --- | --- | --- |
| NONE | PASS | 无注入基线 |
| F001 单次超时 | PASS | 重试 1 次后恢复 |
| F002 持续超时 | ERROR | 3 次尝试、2 次重试后耗尽 |
| F003 断开 | ERROR | 清理 `NOT_VERIFIED` |
| F004 非法响应 | ERROR | 响应解析失败 |
| F005 NaN | ERROR | 数据质量拦截 |
| F006 Infinity | ERROR | 数据质量拦截 |
| F007 电压偏移 -0.3 V | FAIL | 4.68 V 低于下限 4.9 V |
| F008 电流偏移 +0.2 A | FAIL | 1.2 A 超过上限 1.05 A |
| F009 关闭失败 | ERROR + SKIP | 强制停止并跳过后续用例 |

### 3.4 通过率统一定义（本次核对代码后的口径）

| 名称 | 公式 | 代码位置 | 使用方 |
| --- | --- | --- | --- |
| 有效判定通过率 `pass_rate` | PASS / (PASS + FAIL) | `engine/models.py` L304 | 引擎汇总、Web 组件 `ui/components.py` L313 |
| 已执行通过比例 | PASS / (PASS + FAIL + ERROR) | `analysis/metrics.py` L283-298 | 旧版 JSON 报告 `reports/generator.py` L73 |
| 计划通过比例 `planned_pass_rate` | PASS / 计划数 | `engine/models.py` L306 | 引擎汇总 |
| 实验通过率 | 符合预期实验数 / 实验总数 | `reliability/reliability_analyzer.py` L363 | 可靠性汇总 |

> 已知差异（不在本任务修改）：`analysis.metrics.pass_rate_percent` 与引擎 `pass_rate` 分母不同。
> 简历中一律写明“有效判定通过率”，避免与 20% 的已执行比例混淆。

---

## 4. Git 151 项变更分类（未提交、未推送）

| 类别 | 数量 | 内容 |
| --- | --- | --- |
| 自主源码 | 49 | `app.py`、`core/`、`ui/`、`engine/`、`instruments/`、`models/`、`bench/`、`analysis/`、`storage/`、`reports/`、`reliability/`、`scripts/`（含 `.ps1`/`.sh` 启动脚本） |
| 测试 | 36 | `tests/` 下新增/修改的 pytest 文件 |
| 配置/依赖 | 18 | `configs/*.yaml`、`requirements*.txt`、`environment.yml`、`pyproject.toml`、`.streamlit/` |
| 文档/素材 | 43 | `docs/01–34`、`portfolio/`、`assets/`、`README/AGENTS/CHANGELOG/LICENSE/THIRD_PARTY_NOTICES/VERSION` |
| 工程化配置 | 5 | `.gitignore`、`Dockerfile`、`.dockerignore`、`compose.yaml`、`.github/workflows/ci.yml` |
| 生成结果 / 数据库 | 0（已被忽略） | `results/`、`*.db`、`.coverage`、`coverage.xml`、`__pycache__/`、`.pytest_cache/` |
| **合计** | **151** | — |

结论：当前没有发现“不应提交却被跟踪”的文件；忽略规则见 `.gitignore`。
建议提交顺序：配置/依赖 → 源码 → 测试 → 文档 → 工程化配置，提交前人工确认 `assets/` 中截图内容。

---

## 5. NOT_VERIFIED 清单（不得写入简历）

Docker 构建/运行、Linux 实机部署、GitHub Actions 真实执行、真实仪器通信与测量精度、
纹波/瞬态/温度特性、产品良率/MTBF/MTTR、性能提升百分比、企业项目或客户交付。
以上均为 `NOT_VERIFIED` 或未实现，证据见 §1 #19-#23。

---

## 6. 可直接引用的安全表述

- “基于 PyVISA-sim 的电源测试平台应用层二次开发（AI 辅助开发），3 台虚拟仪器、21 条 SCPI 定义（驱动实际发送 18 条）。”
- “12 条结构化用例、4 套测试方案、6 种 DUT 状态、10 个工程指标函数（7 类指标）。”
- “39 个扫描工况（负载 11 / 线性 10 / 二维 18），输出 CSV 与离线 HTML 图表。”
- “9 个故障注入场景、10 个可靠性实验全部符合预期，恢复率 50%（模拟环境，非良率）。”
- “557 项 pytest 全部通过，综合覆盖率 84%（语句 87.1% / 分支 75.3%），ruff 0 错误。”
- “6 页 Streamlit 平台，3 种导出格式 + 离线综合 HTML 报告。”
- “4 张 SQLite 业务表，事件 JSONL 与 SQLite 双写，支持数据库备份。”

## 7. 配套学习材料

源码级索引与十项练习说明见 `portfolio/code_learning_guide.md`。
