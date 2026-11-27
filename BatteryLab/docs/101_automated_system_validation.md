# 101 自动化系统验证框架

## 1. 组成

| 模块 | 职责 |
| --- | --- |
| `validation/system_case_loader.py` | 加载 30 类候选工况并做静态校验（编号唯一、模型类型合法、检查项非空） |
| `validation/system_test_runner.py` | 按模型类型分派执行器；未注册 → `NOT_VERIFIED`；异常 → `ERROR` |
| `validation/system_result_judge.py` | PASS/FAIL/NOT_VERIFIED/ERROR 判定与优先级聚合 |
| `validation/system_fault_injection.py` | 10 个保护故障场景，直接驱动真实控制器 |
| `validation/system_energy_validator.py` | 梯形积分能量守恒与损耗分解 |
| `validation/cross_project_regression.py` | 运行前后三项目源码哈希对比 |

## 2. 状态机

```
executor 缺失        -> NOT_VERIFIED (MODEL_UNAVAILABLE)
执行抛异常           -> ERROR
有检查项且全部满足   -> PASS
任一检查项不满足     -> FAIL
无检查项             -> NOT_VERIFIED
```

聚合优先级：`ERROR > FAIL > NOT_VERIFIED > PASS`。

## 3. 限值冻结

`configs/system_validation.yaml` 在运行前冻结，运行后禁止修改。文件内明确写出
每条限值来源：PowerLab 原有 0.3 V / 0.5 V 动态限值、BatteryLab 第五阶段保护阈值、
本阶段预先登记的 45° 相位裕量目标。

## 4. 结果目录约定

```
results/
  stage9/run_stage9_<ts>_<hex>/          编排运行
    01_interfaces/ ... 10_figures/
    validation_summary.json
    source_snapshot_before.json / after.json
    cross_project_regression.json
    execution.log
    release_manifest.json
  converter_power_map/power_map_<ts>_<hex>/
  system_spice/integrated_<ts>_<hex>/、protection_<ts>_<hex>/
  system_average/load_step_<ts>_<hex>/
  system_lifetime/discharge_<ts>_<hex>/、aging_<ts>_<hex>/
  system_energy/、testlab_integration/、figures/
```

每个目录都有 `run_id.txt`；运行不覆盖历史结果。

## 5. 复现命令

```bash
conda run -n kaifa_battery python -m scripts.verify_project_interfaces
conda run -n kaifa_battery python -m scripts.generate_converter_power_map
conda run -n kaifa_battery python -m scripts.integrated_buck_demo
conda run -n kaifa_battery python -m scripts.system_load_step_demo
conda run -n kaifa_battery python -m scripts.system_protection_demo --spice
conda run -n kaifa_battery python -m scripts.system_discharge_demo
conda run -n kaifa_battery python -m scripts.system_aging_demo
conda run -n kaifa_battery python -m scripts.system_energy_demo
conda run -n kaifa_battery python -m scripts.testlab_integration_demo
conda run -n kaifa_battery python -m scripts.system_engineering_figures
conda run -n kaifa_battery python -m scripts.battery_stage9_demo --profile standard
conda run -n kaifa_battery python -m pytest tests -q
```

## 6. 反作弊规则

1. 缺少模型、缺少映射、缺少波形 → BLOCKED / NOT_VERIFIED；
2. 数值步长回退必须记录实际值；
3. 空检查列表不得判定 PASS；
4. 不得修改其他项目来"适配"；
5. 所有 PASS 必须有 `run_id + 证据文件`。
