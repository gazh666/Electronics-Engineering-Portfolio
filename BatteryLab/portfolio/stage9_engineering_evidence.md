# 第九阶段工程证据

## 1. TestLab 接口判定

| metric | value | minimum | maximum | unit | status |
|---|---|---|---|---|---|
| output_voltage_mean_v | 4.996826539671714 | 4.9 | 5.1 | V | PASS |
| output_voltage_ripple_vpp | 0.02897828015702686 | nan | 0.05 | V | PASS |
| inductor_peak_current_a | 2.299457030076269 | nan | 3.5 | A | PASS |
| converter_input_voltage_v | 10.592865996053263 | 8.5 | 13.0 | V | PASS |

## 2. 能量与效率

- 变换器效率：93.6828 %
- 能量残差：0.002828 %
- 电池能量：38.5611 mJ
- 负载能量：35.9461 mJ
- 保护通路损耗：0.19004 mJ

## 3. 本次新增系统候选

| 组别 | 稳态电压(V) | 纹波(mV) | 效率(%) | 阶跃偏差(mV) | 恢复(µs) |
|---|---|---|---|---|---|
| baseline_lc_baseline_controller | 4.9724 | 24.54 | 94.158 | 843.0 | 1615.0 |
| optimized_lc_baseline_controller | 4.9687 | 28.2 | 94.807 | 617.96 | 1920.0 |
| optimized_lc_tuned_controller | 4.9777 | 21.0 | 95.206 | 574.97 | 1717.0 |

## 4. 边界

- 全部为软件仿真；未做硬件实测。
- 阶段 9 历史 17/24 收敛计数未在本次重跑。
