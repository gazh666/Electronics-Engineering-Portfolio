# 19 命令行与 CI 使用

本文件说明阶段七的三个命令行入口、退出码与在持续集成中的使用方式。
全部命令在 `TestLab` 目录下、`kaifa` 环境中执行。

## 1. 执行单个用例

```powershell
conda run -n kaifa python -m scripts.run_single_test --case TC001
conda run -n kaifa python -m scripts.run_single_test --case TC007 --json
```

可选参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--cases` | `configs/test_cases.yaml` | 用例文件 |
| `--results` | `results/automation` | 运行目录根 |
| `--db` | `results/testlab.db` | SQLite 文件 |
| `--json` | 关闭 | 输出完整 JSON |

## 2. 执行测试方案

```powershell
conda run -n kaifa python -m scripts.run_test_suite --list
conda run -n kaifa python -m scripts.run_test_suite --suite SUITE-SMOKE
conda run -n kaifa python -m scripts.run_test_suite --suite SUITE-REGRESSION
conda run -n kaifa python -m scripts.run_test_suite --suite SUITE-PROTECTION
```

引擎自校验（故意包含 FAIL/SKIP/ERROR）：

```powershell
conda run -n kaifa python -m scripts.run_test_suite `
  --suite SUITE-EV `
  --cases configs/engine_validation_cases.yaml `
  --suites configs/engine_validation_suites.yaml
```

`--quiet` 只输出最终汇总。

## 3. 查询历史

```powershell
conda run -n kaifa python -m scripts.query_test_history --list
conda run -n kaifa python -m scripts.query_test_history --run-id <run_id>
conda run -n kaifa python -m scripts.query_test_history --run-id <run_id> --failed-only
```

## 4. 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 至少一个用例执行且全部 PASS |
| 1 | 存在 FAIL |
| 2 | 存在 ERROR（含方案级错误、存储失败、清理失败） |
| 3 | 用户中断（ABORTED），或只有 SKIP/无有效结果 |

CI 中应同时检查退出码与 `summary.json`：`COMPLETED` 不等于全部通过。

## 5. CI 示例

```yaml
# 伪代码：任何 CI 系统均可
steps:
  - run: conda run -n kaifa python -m pytest -q
  - run: conda run -n kaifa python -m scripts.run_test_suite --suite SUITE-REGRESSION
  - run: conda run -n kaifa python -m scripts.query_test_history --list
```

对失败的构建，可用 `query_test_history --run-id ... --failed-only` 直接
定位失败用例与越界检查项；原始记录仍在
`results/automation/run_<run_id>/results.jsonl`。

## 6. 注意事项

- 仪器是虚拟的（PyVISA-sim），CI 不需要真实硬件；
- 同一 `InstrumentManager` 配置在进程中只能打开一次，脚本已按单进程设计；
- 不要删除 `results/automation/` 与 `results/testlab.db` 之外的历史记录，
  当前实现不做自动清理；
- 所有结果均为仿真数据，禁止作为真实产品合格证明。
