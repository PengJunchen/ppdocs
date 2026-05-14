"""
服务发现数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ServiceType(str, Enum):
    """服务类型枚举"""
    OPENAI_API = "openai_api"          # OpenAI 兼容 API
    MCP_SERVER = "mcp_server"          # MCP 服务器
    LLM_GATEWAY = "llm_gateway"        # LLM 网关 (LiteLLM等)
    UNKNOWN = "unknown"                # 未知类型


class ServiceCapability(str, Enum):
    """服务能力枚举"""
    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDINGS = "embeddings"
    VISION = "vision"
    FUNCTION_CALL = "function_call"
    STREAMING = "streaming"


@dataclass
class ServiceFingerprint:
    """服务指纹特征"""
    service_type: ServiceType
    confidence: float  # 置信度 0-1
    endpoints: List[str]  # 检测到的端点
    headers: Dict[str, str]  # 响应头特征
    body_patterns: List[str]  # 响应体特征
    version: Optional[str] = None


@dataclass
class DiscoveredService:
    """发现的服务信息"""
    service_id: str
    service_type: ServiceType
    ip: str
    port: int
    endpoint: str
    capabilities: List[ServiceCapability] = field(default_factory=list)
    models: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    fingerprint: Optional[ServiceFingerprint] = None
    discovered_at: datetime = field(default_factory=datetime.now)
    last_checked: Optional[datetime] = None
    health_status: str = "unknown"  # healthy, unhealthy, unknown
    response_time_ms: float = 0.0


class DiscoveryConfig(BaseModel):
    """发现配置"""
    # 扫描配置
    scan_timeout: float = Field(default=2.0, description="端口扫描超时(秒)")
    probe_timeout: float = Field(default=5.0, description="服务探测超时(秒)")
    test_timeout: float = Field(default=10.0, description="能力测试超时(秒)")
    max_concurrent: int = Field(default=100, description="最大并发数")
    
    # 扫描范围
    ports: List[int] = Field(
        default_factory=lambda: [11434, 8080, 8000, 3000, 5000, 8001, 8081, 9000],
        description="要扫描的端口列表"
    )
    
    # 行为配置
    full_test: bool = Field(default=True, description="是否进行完整能力测试")
    min_confidence: float = Field(default=0.5, description="最小置信度阈值")
    
    # 健康检查
    health_check_interval: int = Field(default=30, description="健康检查间隔(秒)")
    failure_threshold: int = Field(default=3, description="失败阈值")


class DiscoveredServiceResponse(BaseModel):
    """API 响应模型"""
    service_id: str
    service_type: str
    ip: str
    port: int
    endpoint: str
    capabilities: List[str] = Field(default_factory=list)
    models: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    health_status: str = "unknown"
    response_time_ms: float = 0.0
    discovered_at: str = ""
    
    @classmethod
    def from_service(cls, service: DiscoveredService) -> "DiscoveredServiceResponse":
        return cls(
            service_id=service.service_id,
            service_type=service.service_type.value,
            ip=service.ip,
            port=service.port,
            endpoint=service.endpoint,
            capabilities=[c.value for c in service.capabilities],
            models=service.models,
            confidence=service.fingerprint.confidence if service.fingerprint else 0.0,
            health_status=service.health_status,
            response_time_ms=service.response_time_ms,
            discovered_at=service.discovered_at.isoformat()
        )


class DiscoveryScanRequest(BaseModel):
    """扫描请求"""
    network: str = Field(..., description="网段，如 192.168.1.0/24")
    ports: Optional[List[int]] = Field(None, description="指定端口，默认使用配置")
    full_test: bool = Field(True, description="是否进行完整能力测试")


class DiscoveryScanResponse(BaseModel):
    """扫描响应"""
    network: str
    total_found: int
    services: List[DiscoveredServiceResponse]
    scan_duration_ms: float


class DiscoveryStatusResponse(BaseModel):
    """发现状态响应"""
    total_services: int
    by_type: Dict[str, int]
    by_capability: Dict[str, int]
    healthy_count: int
    services: List[DiscoveredServiceResponse]
