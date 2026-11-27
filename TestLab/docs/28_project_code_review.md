# 28 全项目代码及功能审查（第十阶段 Task 1）

## 1. 审查基线（实际执行）

| 项目 | 结果 |
| --- | --- |
| 工作目录 | `TestLab` |
| Python | 3.11.18（conda `kaifa`） |
| `pip check` | `No broken requirements found.` |
| `pytest tests`（审查前） | 518 passed，15.90 s |
| `pytest tests`（修复后） | 557 passed，34.88 s（含覆盖率统计） |
| Git 仓库 | 已初始化，4 个提交，无 remote |
| 工作区状态 | 阶段二至九产物大量未提交（`M`/`??`），阶段十新增文件未提交 |
| 敏感信息扫描 | 未发现 API Key、密码、私钥或令牌 |

审查范围：`instruments/`、`models/`、`bench/`、`analysis/`、`engine/`、
`storage/`、`reliability/`、`ui/`、`configs/`、`scripts/`、`tests/`、`docs/`、
`results/`、`app.py`、`requirements.txt`、`README.md`、`AGENTS.md`，以及本次新增的
`core/`、`reports/`、`scripts/*`。

## 2. 结论摘要

- **Critical：0 项**。未发现核心逻辑错误、数据丢失、清理失败后继续执行、
  历史覆盖或敏感信息泄露。
- **Major：4 项**，其中 3 项已在本阶段修复，1 项以“显式并列口径 + 文档”方式
  处理（不改动已被 518 个测试依赖的旧 API）。
- **Minor：10 项**，已清理可直接修复的问题（ruff 14 处未使用导入/变量），
  其余作为技术债记录，不做大幅重构。

## 3. Major 问题

### M1 运行目录与数据库路径定义分散

- 现象：`ui/service.py`、`storage/sqlite_store.py`、`storage/result_store.py`、
  `scripts/automation_context.py` 及多个 demo 脚本各自拼接
  `PROJECT_ROOT / "results"`，没有统一入口。
- 风险：Docker、CI 或测试环境无法通过一个配置改变全部写入位置；容易出现
  “部分写临时目录、部分写真实历史”。
- 处理：新增 `core/paths.py`（`PROJECT_ROOT`、`CONFIG_DIR`、`RESULTS_DIR`、
  `DATABASE_PATH`、`results_dir()`、`database_path()`、
  `ensure_runtime_directories()`），并接入 service、存储层、app 与脚本。
  默认仍为 `results/testlab.db`，未改变已有数据库位置。
- 验证：`tests/test_project_paths.py`（11 项）与全量回归。

### M2 Docker 环境变量 `TESTLAB_RESULTS_DIR` 不生效

- 现象：原 `app.py` 只读取阶段九 AppTest 使用的
  `TESTLAB_RESULTS_ROOT` / `TESTLAB_DB_PATH`；Dockerfile 设置的
  `TESTLAB_RESULTS_DIR` 会被忽略，容器仍写镜像内默认路径。
- 处理：`core.paths.results_dir()` 按
  `TESTLAB_RESULTS_DIR` → `TESTLAB_RESULTS_ROOT` → 默认 `results/` 解析；
  `database_path()` 支持 `TESTLAB_DB_PATH`。`app.py` 在每次构建服务时调用函数，
  因此 AppTest 在运行前设置的环境变量仍然生效。
- 验证：`test_project_paths.py` 覆盖优先级、兼容变量与数据库覆盖；
  AppTest 46 项通过。

### M3 历史运行缺少软件版本/Commit 与统一综合报告

- 现象：`runs` 表未保存当时的软件版本或 Git commit；Web 只能导出简表 HTML。
- 风险：报告若使用“当前版本”填充历史运行，会造成追溯错误。
- 处理：
  - 新增 `VERSION` 文件与 `read_software_version()`；
  - 综合报告明确区分“当前软件版本（非历史版本）”与
    “历史运行软件版本 / Git commit：未知（历史记录未保存）”；
  - 新增 `reports/generator.py` 综合报告、离线模板与
    `scripts/generate_report.py`，并在历史页接入生成/下载/打印说明。
- 验证：`tests/test_report_generator.py`（13 项）覆盖正常、FAIL、ERROR、
  SKIP、清理失败、中断、快照缺失、中文、转义、NaN/Infinity、
  不存在 run_id、不覆盖、路径越界。

### M4 PASS/FAIL/ERROR/SKIP 统计口径并存

- 现象：
  - `engine.models.summarize_results.pass_rate = PASS/(PASS+FAIL)`（有效判定通过率）；
  - `analysis.metrics.pass_rate_percent = PASS/(PASS+FAIL+ERROR)`；
  - `reports.generator.summarize` 使用后者但字段名相同；
  - Web 仪表盘按 `PASS/(PASS+FAIL)` 计算分类通过率。
- 判断：三种口径本身都有业务含义，问题在于**名称未并列说明**，容易在报告里
  被误读。
- 处理：综合报告显式同时展示三项：
  “有效判定通过率 PASS/(PASS+FAIL)”“整体执行完成率
  (PASS+FAIL+ERROR)/计划”“计划用例通过比例 PASS/计划”。
  不改动旧 API，避免破坏 518 项既有测试与历史脚本。
- 后续：若要统一，应为旧字段加弃用说明并分版本迁移，不在本阶段进行。

## 4. Minor 问题

| 编号 | 问题 | 判断与处理 |
| --- | --- | --- |
| m1 | `numpy` 未被项目直接 import | 保留固定版本，作为 pandas 的数值依赖约束，已在第三方声明中注明 |
| m2 | `ScenarioTestRunner` 使用本地时区，新引擎使用 UTC | 旧执行器仅用于 `scripts.demo` 回归；在文档说明，未改历史行为 |
| m3 | `reports.generator` 旧 JSON 报告使用本地时间 | 新综合报告统一使用 UTC 并标注；旧函数保留兼容 |
| m4 | `analysis/data_quality.py` 重复实现效率公式 | 用于“报告值 vs 重算值”一致性校验，属有意设计，保留 |
| m5 | service 轻量 HTML 导出与综合报告两套模板 | 前者是内存导出，后者是落盘可打印报告；职责不同，保留 |
| m6 | `finish_run` 对同一 `run_id` 是 UPDATE | run_id 由时间戳+uuid 生成，重复概率极低；不改表结构 |
| m7 | `SQLiteStore` 构造即创建目录与表 | 只在真实使用时实例化，模块导入无副作用 |
| m8 | Web 交互视图分支覆盖率偏低 | 交互分支需要真实点击；AppTest 已覆盖主流程，记录为测试债 |
| m9 | 历史 `docs/.gitkeep` 被删除 | docs/ 已有实际文档，删除合理，无需恢复 |
| m10 | 14 处未使用导入/变量 | 由 `ruff check --fix` 清理，回归通过 |

## 5. 逐项核对清单

| 审查点 | 结论 | 依据 |
| --- | --- | --- |
| 重复数学公式 | 无重复实现（效率重算为数据质量校验） | `analysis/metrics.py`、`data_quality.py` |
| 重复仪器驱动 | 无；统一继承 `BaseInstrument` | `instruments/` |
| 重复资源清理 | 无；`InstrumentManager.close()` 统一关闭 | `instruments/manager.py` |
| 循环导入 | 未发现；12 个核心模块导入成功 | `verify_release.check_imports` |
| 未使用代码/依赖 | 已清理 14 处 ruff 问题；numpy 为间接依赖 | `ruff check .` 全绿 |
| 硬编码绝对路径 | 项目源码未发现 | 全局 grep `C:\`/`D:\`/`/home/` |
| 仅 Windows 路径处理 | 全部使用 `pathlib`；核心路径无盘符 | `core/paths.py`、`tests/test_project_paths.py` |
| 不正确异常捕获 | 执行器只在用例级兜底并记录，不吞 `KeyboardInterrupt` | `engine/test_runner.py`、`suite_runner.py` |
| 无限循环/无限重试 | 无 `while True`；重试上限 10，`max_attempts` 为总次数 | `reliability/retry_policy.py` |
| 数据库连接未释放 | 全部 `contextlib.closing` | `storage/sqlite_store.py` |
| 历史记录覆盖 | 结果表 `ON CONFLICT DO NOTHING`；JSONL 目录唯一 | `sqlite_store.py`、`result_store.py` |
| NaN/Infinity 序列化 | 统一转字符串并 `allow_nan=False` | 存储层、报告层 |
| 效率比例/百分比混淆 | 模型返回 0–1，指标层返回百分数，字段名区分 | `metrics.py`、`report` 字段 `efficiency_percent` |
| 页面逻辑与业务逻辑重复 | 页面只调用 service；service 调用后端 | `ui/`、`ui/service.py` |
| 静态模拟与模型数据混用 | 标签区分 `static_mock` 与 `behavioral_model` | `bench/virtual_test_bench.py` |
| 统计口径不一致 | 见 M4，已在报告中并列展示 | `reports/generator.py` |
| 刷新导致重复执行 | 执行只在按钮/表单分支；进度条仅在持久化后推进 | `ui/views/*`、`test_streamlit_app.py` |
| 清理失败后继续执行 | `cleanup_failed` 强制 ERROR 并停止方案 | `engine/suite_runner.py` |
| 敏感信息 | 未发现；`.gitignore` 排除数据库、日志、密钥 | 全局扫描 |

## 6. 本阶段修复记录

1. 新增 `core/paths.py` 并接入 10 个模块/脚本（M1、M2）。
2. `app.py` 改为运行时读取统一路径函数，兼容三类环境变量。
3. 新增 `VERSION`、综合报告与历史页入口（M3）。
4. 报告并列展示三种统计口径（M4）。
5. `ruff check --fix` 清理 14 处未使用导入/变量；手工修复 2 处未使用变量。
6. 新增 39 项测试（报告 14、备份 7、路径 10、发布验收 5、Web 报告 3）。

## 7. 结论

- 未发现需要停止发布的 Critical 问题；
- Major 问题均已修复或给出明确工程处理；
- 全量测试 557 passed，`ruff check .` 通过，`pip check` 干净；
- 剩余 Minor 问题不影响运行正确性，已登记为技术债。
