# 102 跨项目回归与只读证明

## 1. 为什么需要哈希证明

BatteryLab、PowerLab 都不是 Git 仓库，无法用 commit 证明"没改别人的代码"。
本阶段采用源码哈希树：

- 范围：`.py/.yaml/.yml/.json/.md/.toml/.txt/.cir/.cfg`；
- 排除：`results/`、`.git/`、`__pycache__`、`.pytest_cache`、`.ruff_cache`、`htmlcov`、`node_modules`；
- 比较：运行前与运行后各取一次，输出新增、删除、修改文件清单。

实现：`integration/environment_adapter.py`、`validation/cross_project_regression.py`。

## 2. 调用边界

| 项目 | 允许 | 禁止 |
| --- | --- | --- |
| TestLab | 只读读取源码与配置；子进程只读导入 `engine.result_judge` | 写源码/配置/results；修改测试用例 |
| PowerLab | 只读读取配置与历史结果；子进程调用 `build_closed_loop_buck` 与瞬态求解（不调用保存函数） | 写任何文件；修改配置来"适配" |
| BatteryLab | 本阶段实现与结果写入 | — |

## 3. 如何确认没有写到其他项目

1. 调用 PowerLab 时只使用 `circuit.simulator(...).transient(...)`，不调用
   `save_closed_loop_run` 等保存函数；
2. 调用 TestLab 时只 `import engine.result_judge`，不触发任何写操作；
3. `battery_stage9_demo` 在运行前后各生成一份 `source_snapshot_{before,after}.json`，
   并输出 `cross_project_regression.json`；
4. 若出现 `MODIFIED`，整体状态直接为 FAIL，不允许"解释后放过"。

## 4. 结果位置

| 文件 | 内容 |
| --- | --- |
| `results/stage9/project_interfaces/.../cross_project_manifest.json` | 三项目路径、Git 状态、版本、核心文件、模块数、Python 版本、源码树哈希 |
| `results/stage9/project_interfaces/.../source_snapshot_before.json` | 运行前哈希 |
| `results/stage9/run_stage9_.../source_snapshot_after.json` | 运行后哈希 |
| `results/stage9/run_stage9_.../cross_project_regression.json` | 差异与最终判定 |

## 5. 限制

- 哈希只能证明"文件内容未变"，不能证明"没有被读取"；
- 本阶段确实读取了两个项目的源码与配置，这是设计允许的只读行为；
- 若用户在运行期间手动修改了其他项目，会被误报为 MODIFIED，需要在报告中说明。
