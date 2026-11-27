# 第三方组件与许可证声明

TestLab 是建立在 PyVISA / PyVISA-sim 之上的**应用层二次开发**项目。
本文件记录实际使用的上游项目、运行依赖及其许可证，不把上游代码计入自主开发。

## 1. 直接上游项目（未修改源码）

### PyVISA

- 项目：https://github.com/pyvista/pyvista 之外的 VISA 通信库，实际地址
  https://github.com/pyvisa/pyvisa
- 版本：1.16.2（PyPI）
- 许可证：MIT
- 用途：VISA 资源管理与会话抽象，TestLab 通过其 API 访问虚拟仪器。

### PyVISA-sim

- 项目：https://github.com/pyvisa/pyvisa-sim
- 版本：0.7.1（PyPI）
- 许可证：MIT
- 用途：基于 YAML 的虚拟仪器后端，提供 SCPI 响应模拟。
- 说明：本地 `pyvisa-sim-main/` 源码仅作为阅读参考，运行时加载 PyPI 安装版本；
  不修改、移动或删除上游源码。

MIT 许可证原文（两个项目相同模板，版权主体不同）：

```text
The MIT License

Copyright (c) 2014 PyVISA-sim Authors and contributors. See AUTHORS
Copyright (c) 2005-2024 PyVISA Authors and contributors. See AUTHORS

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 2. 运行依赖（第三方库，未修改）

| 组件 | 版本 | 许可证 | 用途 |
| --- | --- | --- | --- |
| PyYAML | 6.0.4 | MIT | 读取仪器、用例、限值与故障场景配置 |
| numpy | 2.4.6 | BSD-3-Clause | pandas 的数值依赖（项目未直接 import） |
| pandas | 3.1.1 | BSD-3-Clause | 扫描数据表格与 Streamlit 数据展示 |
| plotly | 7.1.0 | MIT | 性能扫描与可靠性图表 |
| streamlit | 1.67.0 | Apache-2.0 | Web 平台界面与 AppTest |
| pytest | 9.2.0 | MIT | 单元/集成/界面测试 |
| pytest-cov | 见 requirements-dev.txt | MIT | 覆盖率统计 |
| ruff | 见 requirements-dev.txt | MIT | 静态检查 |

## 3. 使用边界

- TestLab 仅调用上述库的公开 API，未复制其内部实现作为自主代码；
- 上游项目的版权与许可声明必须随分发保留；
- 本项目当前未选定自主许可证，见 `LICENSE`；
- 本仓库不包含真实硬件测量数据、商业芯片 Datasheet 或第三方私有数据集。
