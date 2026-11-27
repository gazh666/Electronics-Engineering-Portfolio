"""第九阶段三项目联合验证包。

本包只做**只读**跨项目访问、适配与数据交换，不修改 TestLab / PowerLab 源码与
历史结果，也不把行为级模型描述为真实硬件实验。
"""

__all__ = [
    "project_registry",
    "environment_adapter",
    "powerlab_adapter",
    "testlab_adapter",
    "battery_port_adapter",
    "protection_adapter",
    "measurement_exchange",
    "interface_validator",
]
