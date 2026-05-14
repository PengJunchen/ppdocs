"""
AI 服务自动发现模块 (probe_discovery)

提供局域网内 OpenAI 兼容 API、MCP 服务器等 AI 服务的自动发现能力
独立于 doc-parser 主项目
"""

from .models import (
    ServiceType,
    ServiceCapability,
    ServiceFingerprint,
    DiscoveredService,
    DiscoveryConfig,
)
from .scanner import PortScanner
from .fingerprinter import ServiceFingerprinter
from .tester import CapabilityTester
from .engine import ServiceDiscoveryEngine, discover_network, discover_single

__all__ = [
    # 枚举和模型
    "ServiceType",
    "ServiceCapability",
    "ServiceFingerprint",
    "DiscoveredService",
    "DiscoveryConfig",
    # 核心组件
    "PortScanner",
    "ServiceFingerprinter",
    "CapabilityTester",
    "ServiceDiscoveryEngine",
    # 便捷函数
    "discover_network",
    "discover_single",
]
