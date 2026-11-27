# 29 测试质量与覆盖率报告（第十阶段 Task 7）

## 1. 执行环境与命令

- 环境：conda `kaifa`，Python 3.11.18
- 静态检查：`python -m ruff check .` → `All checks passed!`
- 测试：
  ```powershell
  python -m pytest tests -q --cov=core --cov=instruments --cov=models ^
    --cov=bench --cov=analysis --cov=engine --cov=storage ^
    --cov=reliability --cov=ui --cov=reports ^
    --cov-report=term-missing --cov-report=html --cov-report=xml
  ```

## 2. 实际测试结果（本阶段最终回归）

| 指标 | 数值 |
| --- | --- |
| 测试总数 | 557 |
| 通过 | 557 |
| 失败 | 0 |
| 跳过 | 0 |
| 仅测试耗时 | 34.88 s（含覆盖率统计；不加覆盖率约 16 s） |
| 退出码 | 0 |

本阶段新增 39 项测试：

| 文件 | 数量 | 覆盖内容 |
| --- | --- | --- |
| `tests/test_report_generator.py` | 14 | 正常/FAIL/ERROR/SKIP、清理失败、中断、快照缺失、中文、HTML 转义、NaN/Infinity、不存在 run_id、不覆盖、路径越界 |
| `tests/test_database_backup.py` | 7 | 正常备份、缺源文件、记录一致、完整性、独立临时库、不覆盖、CLI |
| `tests/test_project_paths.py` | 10 | 默认路径、三类环境变量、优先级、懒创建、存储层一致、UTF-8 中文 |
| `tests/test_release_validation.py` | 5 | 单项检查、配置/版本缺失、主流程、真实数据库隔离 |
| `tests/test_web_report_export.py` | 3 | 服务层生成、重复生成、非法 run_id、历史页生成/下载不重跑 |

## 3. 代码覆盖率（真实执行，未排除重要模块）

总覆盖率：**84%**（语句 5680，未覆盖 733；分支 1786，部分覆盖 335）。

| 模块 | 覆盖率 | 说明 |
| --- | --- | --- |
| `core/paths.py` | 100% | 新增统一路径 |
| `models/virtual_dut.py` | 87% | 非法配置与部分保护分支未覆盖 |
| `bench/virtual_test_bench.py` | 100% | |
| `analysis/metrics.py` | 90% | 参数异常与少数辅助函数 |
| `analysis/data_quality.py` | 84% | 部分异常组合分支 |
| `analysis/performance_analyzer.py` | 85% | 配置校验异常分支 |
| `analysis/statistics.py` | 100% | |
| `engine/models.py` | 98% | |
| `engine/case_loader.py` | 91% | 部分 YAML 类型错误分支 |
| `engine/result_judge.py` | 99% | |
| `engine/suite_runner.py` | 91% | 存储/回调失败分支（部分已覆盖） |
| `engine/test_runner.py` | 89% | 设置值回读失败、部分故障组合 |
| `engine/dut_bridge.py` | 100% | |
| `instruments/base.py` | 87% | 超时/连接异常的少数路径 |
| `instruments/manager.py` | 90% | 重复打开、关闭异常分支 |
| `instruments/multimeter.py` | 100% | |
| `instruments/power_supply.py` | 90% | 参数校验异常 |
| `instruments/electronic_load.py` | 95% | |
| `storage/result_store.py` | 78% | 未初始化 run、读取异常分支 |
| `storage/sqlite_store.py` | 91% | 旧表迁移与查询异常分支 |
| `reliability/fault_models.py` | 80% | 场景配置非法组合 |
| `reliability/fault_injector.py` | 72% | 多故障叠加与部分设备分支 |
| `reliability/retry_policy.py` | 86% | 策略非法值分支 |
| `reliability/reliability_analyzer.py` | 82% | 实验覆盖校验异常 |
| `reliability/fault_logger.py` | 88% | 写入失败分支 |
| `reliability/error_classifier.py` | 97% | |
| `reports/generator.py` | 84% | 报告异常输入与部分格式化分支 |
| `ui/service.py` | 86% | 异常清理与部分扫描分支 |
| `ui/views/history.py` | 84% | 报告下载成功分支 |
| `ui/views/automation.py` | 90% | |
| `ui/views/reliability.py` | 74% | 交互进度分支 |
| `ui/views/performance.py` | 42% | 扫描表单与图表交互分支 |
| `ui/views/instruments.py` | 40% | 表单交互分支 |
| `ui/components.py` | 58% | 展示型组件分支 |

> 覆盖率来自 `coverage.py` 实际运行，HTML 报告在 `htmlcov/`（不提交仓库）。

## 4. 主要未覆盖代码及原因

1. **Streamlit 交互分支**（`ui/views/instruments.py`、`performance.py`）：
   AppTest 覆盖页面渲染与主流程，但未逐一触发所有表单组合与图表展开；
   这些分支依赖真实控件交互，不影响后端正确性。
2. **可靠性多故障叠加**：`fault_injector.py` 的复合故障（同一次调用多设备注入）
   缺少独立用例；现有 F001–F009 覆盖单故障场景。
3. **存储异常回滚**：`sqlite_store.py`、`result_store.py` 的磁盘写入失败、
   只读目录等情况难以在 Windows 临时目录稳定复现，仅覆盖部分分支。
4. **报告异常输入**：损坏的 JSON 快照、非法 YAML 等已做防御，但未全部构造。
5. **配置校验边界**：`case_loader`、`fault_models` 的部分非法类型组合
   （如嵌套列表代替映射）尚未逐一测试。

以上未覆盖项均已在代码中显式处理并记录，不是为提升覆盖率而排除。

## 5. 本阶段修复的问题

- 清理 14 处未使用导入/变量（`ruff --fix` + 手工 2 处），静态检查从
  14 项错误降为 0。
- 修复 `scripts/verify_release.py` 临时数据库连接未关闭导致 Windows
  临时目录清理失败（使用 `contextlib.closing`）。
- 修复综合报告文件名在极短时间连续生成时可能冲突的问题（追加 uuid 后缀）。
- 补齐 `reports/generator` 的转义、NaN、路径限制与不覆盖测试。

## 6. 剩余技术债务

| 债务 | 影响 | 建议 |
| --- | --- | --- |
| Web 交互视图覆盖率低 | 表单组合回归不足 | 后续用 Playwright/AppTest 补齐关键表单 |
| 报告未嵌入 Plotly 曲线 | 扫描运行只能看文件 | 后续可嵌入离线 Plotly JS 或静态 PNG |
| 统计口径并存 | 阅读报告需注意口径 | 下一个大版本统一命名并保留兼容别名 |
| 复合故障场景缺失 | 极端可靠性覆盖不足 | 增加 F010+ 复合场景与实验预期 |
| 无真实硬件测试 | 不能证明硬件特性 | 仅作为后续真实仪器适配目标 |

## 7. 结论

- 557 项测试全部通过，无跳过、无失败；
- 总覆盖率 84%，核心引擎/仪器/存储模块多数在 85%–100%；
- 未达到 100% 的模块均有明确的业务原因，未通过排除模块或写空断言提高数字；
- 静态检查通过，依赖检查干净。
