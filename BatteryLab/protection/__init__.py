"""第五阶段：3S 电池保护与被动均衡。"""

from protection.limits import ProtectionLimits, build_limits, load_limits, load_protection_config
from protection.state_machine import FaultCode, ProtectionState, ProtectionStateMachine

__all__ = [
    "FaultCode",
    "ProtectionLimits",
    "ProtectionState",
    "ProtectionStateMachine",
    "build_limits",
    "load_limits",
    "load_protection_config",
]
