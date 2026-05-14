"""
AI 服务自动发现模块
通过网段扫描 + 指纹识别自动发现 MCP 服务、OpenAI 兼容 API 等
"""

import asyncio
import ipaddress
import json
import socket
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Callable, Any
from datetime import datetime
import logging

import httpx

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """服务类型枚举"""
    OPENAI_API = "openai_api"          # OpenAI 兼容 API
    MCP_SERVER = "mcp_server"          # MCP 服务器
    LLM_GATEWAY = "llm_gateway"        # LLM 网关 (LiteLLM等)
    UNKNOWN = "unknown"                # 未知类型


class ServiceCapability(Enum):
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


class ServiceFingerprints:
    """服务指纹数据库"""
    
    # OpenAI 兼容 API 指纹
    OPENAI_PATTERNS = {
        "endpoints": ["/v1/models", "/v1/chat/completions", "/v1/completions"],
        "headers": ["openai-version", "x-request-id"],
        "body_keys": ["object", "data", "id", "created", "owned_by"],
        "error_patterns": ["invalid_api_key", "model_not_found"]
    }
    
    # MCP 服务器指纹
    MCP_PATTERNS = {
        "endpoints": ["/health", "/mcp", "/sse", "/messages"],
        "headers": ["content-type: text/event-stream"],
        "body_keys": ["jsonrpc", "method", "tools", "resources"],
        "protocols": ["stdio", "sse", "streamable-http"]
    }
    
    # LLM Gateway 指纹 (LiteLLM等)
    GATEWAY_PATTERNS = {
        "endpoints": ["/health", "/v1/models", "/model/info"],
        "headers": ["litellm-version"],
        "body_keys": ["model_info", "litellm_params"]
    }


class PortScanner:
    """端口扫描器"""
    
    # 常见 AI 服务端口
    COMMON_PORTS = {
        11434: ("Ollama", ServiceType.OPENAI_API),
        8080: ("llama.cpp/通用", ServiceType.OPENAI_API),
        8000: ("vLLM/通用", ServiceType.OPENAI_API),
        3000: ("MCP Server", ServiceType.MCP_SERVER),
        5000: ("Flask/通用", ServiceType.UNKNOWN),
        8001: ("通用", ServiceType.UNKNOWN),
        8081: ("通用", ServiceType.UNKNOWN),
        9000: ("通用", ServiceType.UNKNOWN),
    }
    
    def __init__(self, timeout: float = 2.0, max_concurrent: int = 100):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def scan_host(self, ip: str, port: int) -> Optional[Dict]:
        """扫描单个主机的单个端口"""
        async with self.semaphore:
            try:
                # TCP 连接测试
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port),
                    timeout=self.timeout
                )
                writer.close()
                await writer.wait_closed()
                return {"ip": ip, "port": port, "open": True}
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                return None
    
    async def scan_network(
        self, 
        network: str, 
        ports: Optional[List[int]] = None
    ) -> List[Dict]:
        """
        扫描整个网段
        
        Args:
            network: 网段，如 "192.168.1.0/24"
            ports: 要扫描的端口列表，默认使用 COMMON_PORTS
        
        Returns:
            开放端口列表
        """
        if ports is None:
            ports = list(self.COMMON_PORTS.keys())
        
        net = ipaddress.ip_network(network, strict=False)
        hosts = [str(ip) for ip in net.hosts()]
        
        logger.info(f"开始扫描网段 {network}，共 {len(hosts)} 个主机，{len(ports)} 个端口")
        
        tasks = []
        for host in hosts:
            for port in ports:
                tasks.append(self.scan_host(host, port))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        open_ports = [r for r in results if r is not None and not isinstance(r, Exception)]
        
        logger.info(f"扫描完成，发现 {len(open_ports)} 个开放端口")
        return open_ports


class ServiceProber:
    """服务探测与指纹识别"""
    
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self.fingerprints = ServiceFingerprints()
    
    async def probe_endpoint(
        self, 
        ip: str, 
        port: int, 
        path: str = "/"
    ) -> Optional[Dict]:
        """探测单个端点"""
        url = f"http://{ip}:{port}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                start = asyncio.get_event_loop().time()
                response = await client.get(url)
                elapsed = (asyncio.get_event_loop().time() - start) * 1000
                
                return {
                    "url": url,
                    "status": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text[:2000],  # 限制大小
                    "response_time_ms": elapsed
                }
        except Exception as e:
            logger.debug(f"探测失败 {url}: {e}")
            return None
    
    async def identify_openai_api(self, ip: str, port: int) -> Optional[ServiceFingerprint]:
        """识别 OpenAI 兼容 API"""
        # 测试 /v1/models 端点
        result = await self.probe_endpoint(ip, port, "/v1/models")
        if not result:
            return None
        
        confidence = 0.0
        endpoints = []
        body_keys = []
        
        # 检查状态码
        if result["status"] == 200:
            confidence += 0.3
            endpoints.append("/v1/models")
        
        # 检查响应体
        try:
            body = json.loads(result["body"])
            body_keys = list(body.keys()) if isinstance(body, dict) else []
            
            # 检查 OpenAI 特征字段
            if body.get("object") == "list":
                confidence += 0.3
            if "data" in body and isinstance(body.get("data"), list):
                confidence += 0.2
                # 检查模型列表
                for item in body.get("data", []):
                    if isinstance(item, dict) and item.get("object") == "model":
                        confidence += 0.1
                        break
        except json.JSONDecodeError:
            pass
        
        # 检查响应头
        headers = result["headers"]
        if "openai-version" in headers or "x-request-id" in headers:
            confidence += 0.1
        
        if confidence >= 0.5:
            return ServiceFingerprint(
                service_type=ServiceType.OPENAI_API,
                confidence=min(confidence, 1.0),
                endpoints=endpoints,
                headers=headers,
                body_patterns=body_keys,
                version=headers.get("openai-version")
            )
        return None
    
    async def identify_mcp_server(self, ip: str, port: int) -> Optional[ServiceFingerprint]:
        """识别 MCP 服务器"""
        # MCP 服务器通常有 /health 或 /sse 端点
        paths = ["/health", "/sse", "/mcp", "/"]
        
        for path in paths:
            result = await self.probe_endpoint(ip, port, path)
            if not result:
                continue
            
            confidence = 0.0
            endpoints = []
            
            # 检查 SSE 流 (MCP 常用)
            content_type = result["headers"].get("content-type", "")
            if "text/event-stream" in content_type:
                confidence += 0.4
                endpoints.append(path)
            
            # 检查 JSON-RPC 特征
            try:
                body = json.loads(result["body"])
                if "jsonrpc" in body or "method" in body:
                    confidence += 0.3
                if "tools" in body or "resources" in body:
                    confidence += 0.3
                    endpoints.append(path)
            except json.JSONDecodeError:
                pass
            
            # 检查健康端点
            if path == "/health" and result["status"] == 200:
                confidence += 0.2
                endpoints.append("/health")
            
            if confidence >= 0.5:
                return ServiceFingerprint(
                    service_type=ServiceType.MCP_SERVER,
                    confidence=min(confidence, 1.0),
                    endpoints=endpoints,
                    headers=result["headers"],
                    body_patterns=[]
                )
        
        return None
    
    async def identify_service(self, ip: str, port: int) -> Optional[ServiceFingerprint]:
        """识别服务类型"""
        # 按优先级尝试识别
        
        # 1. 尝试识别 OpenAI API
        fingerprint = await self.identify_openai_api(ip, port)
        if fingerprint:
            return fingerprint
        
        # 2. 尝试识别 MCP 服务器
        fingerprint = await self.identify_mcp_server(ip, port)
        if fingerprint:
            return fingerprint
        
        return None


class CapabilityTester:
    """服务能力测试器"""
    
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
    
    async def test_chat_capability(self, endpoint: str) -> bool:
        """测试聊天能力"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{endpoint}/v1/chat/completions",
                    json={
                        "model": "test",
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 10
                    }
                )
                # 即使返回 400 (模型不存在)，也说明支持 chat 接口
                return response.status_code in [200, 400, 401]
        except:
            return False
    
    async def test_completion_capability(self, endpoint: str) -> bool:
        """测试补全能力"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{endpoint}/v1/completions",
                    json={
                        "model": "test",
                        "prompt": "hello",
                        "max_tokens": 10
                    }
                )
                return response.status_code in [200, 400, 401]
        except:
            return False
    
    async def test_embeddings_capability(self, endpoint: str) -> bool:
        """测试嵌入能力"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{endpoint}/v1/embeddings",
                    json={
                        "model": "test",
                        "input": "hello"
                    }
                )
                return response.status_code in [200, 400, 401]
        except:
            return False
    
    async def get_models(self, endpoint: str) -> List[str]:
        """获取可用模型列表"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{endpoint}/v1/models")
                if response.status_code == 200:
                    data = response.json()
                    models = []
                    for item in data.get("data", []):
                        if isinstance(item, dict):
                            models.append(item.get("id", ""))
                    return [m for m in models if m]
        except:
            pass
        return []
    
    async def test_service(self, service: DiscoveredService) -> DiscoveredService:
        """完整测试服务"""
        endpoint = service.endpoint
        
        # 测试各项能力
        results = await asyncio.gather(
            self.test_chat_capability(endpoint),
            self.test_completion_capability(endpoint),
            self.test_embeddings_capability(endpoint),
            self.get_models(endpoint)
        )
        
        capabilities = []
        if results[0]:
            capabilities.append(ServiceCapability.CHAT)
        if results[1]:
            capabilities.append(ServiceCapability.COMPLETION)
        if results[2]:
            capabilities.append(ServiceCapability.EMBEDDINGS)
        
        service.capabilities = capabilities
        service.models = results[3]
        service.last_checked = datetime.now()
        
        # 健康状态
        if capabilities:
            service.health_status = "healthy"
        else:
            service.health_status = "degraded"
        
        return service


class ServiceDiscoveryEngine:
    """服务发现引擎"""
    
    def __init__(
        self,
        scan_timeout: float = 2.0,
        probe_timeout: float = 5.0,
        test_timeout: float = 10.0
    ):
        self.scanner = PortScanner(timeout=scan_timeout)
        self.prober = ServiceProber(timeout=probe_timeout)
        self.tester = CapabilityTester(timeout=test_timeout)
        self.discovered_services: Dict[str, DiscoveredService] = {}
        self.subscribers: List[Callable] = []
    
    def subscribe(self, callback: Callable):
        """订阅发现事件"""
        self.subscribers.append(callback)
    
    async def _notify_subscribers(self):
        """通知订阅者"""
        for callback in self.subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self.discovered_services)
                else:
                    callback(self.discovered_services)
            except Exception as e:
                logger.error(f"通知订阅者失败: {e}")
    
    async def discover_network(
        self,
        network: str,
        ports: Optional[List[int]] = None,
        full_test: bool = True
    ) -> List[DiscoveredService]:
        """
        发现网段内的 AI 服务
        
        Args:
            network: 网段，如 "192.168.1.0/24"
            ports: 指定端口列表，None 则使用默认端口
            full_test: 是否进行完整能力测试
        
        Returns:
            发现的服务列表
        """
        logger.info(f"开始发现网段: {network}")
        
        # 1. 端口扫描
        open_ports = await self.scanner.scan_network(network, ports)
        logger.info(f"发现 {len(open_ports)} 个开放端口")
        
        # 2. 服务识别
        identified_services = []
        for port_info in open_ports:
            ip = port_info["ip"]
            port = port_info["port"]
            
            fingerprint = await self.prober.identify_service(ip, port)
            if fingerprint:
                service_id = f"{ip}:{port}"
                service = DiscoveredService(
                    service_id=service_id,
                    service_type=fingerprint.service_type,
                    ip=ip,
                    port=port,
                    endpoint=f"http://{ip}:{port}",
                    fingerprint=fingerprint
                )
                identified_services.append(service)
                logger.info(f"识别到服务: {service_id} ({fingerprint.service_type.value}, 置信度: {fingerprint.confidence:.2f})")
        
        logger.info(f"识别到 {len(identified_services)} 个 AI 服务")
        
        # 3. 能力测试
        if full_test:
            logger.info("开始能力测试...")
            tested_services = await asyncio.gather(*[
                self.tester.test_service(svc) for svc in identified_services
            ])
            identified_services = list(tested_services)
        
        # 4. 更新注册表
        for svc in identified_services:
            self.discovered_services[svc.service_id] = svc
        
        # 5. 通知订阅者
        await self._notify_subscribers()
        
        return identified_services
    
    async def discover_single(
        self,
        ip: str,
        port: int,
        full_test: bool = True
    ) -> Optional[DiscoveredService]:
        """发现单个服务"""
        fingerprint = await self.prober.identify_service(ip, port)
        if not fingerprint:
            return None
        
        service_id = f"{ip}:{port}"
        service = DiscoveredService(
            service_id=service_id,
            service_type=fingerprint.service_type,
            ip=ip,
            port=port,
            endpoint=f"http://{ip}:{port}",
            fingerprint=fingerprint
        )
        
        if full_test:
            service = await self.tester.test_service(service)
        
        self.discovered_services[service_id] = service
        await self._notify_subscribers()
        
        return service
    
    def get_services_by_type(self, service_type: ServiceType) -> List[DiscoveredService]:
        """按类型获取服务"""
        return [
            svc for svc in self.discovered_services.values()
            if svc.service_type == service_type
        ]
    
    def get_services_by_capability(self, capability: ServiceCapability) -> List[DiscoveredService]:
        """按能力获取服务"""
        return [
            svc for svc in self.discovered_services.values()
            if capability in svc.capabilities
        ]
    
    def get_best_service(self, capability: ServiceCapability) -> Optional[DiscoveredService]:
        """获取最佳服务（按健康状态和响应时间）"""
        candidates = self.get_services_by_capability(capability)
        if not candidates:
            return None
        
        # 优先健康的服务，然后按响应时间排序
        healthy = [s for s in candidates if s.health_status == "healthy"]
        if healthy:
            return min(healthy, key=lambda s: s.response_time_ms)
        return candidates[0]


# 便捷使用函数
async def discover_network(
    network: str,
    ports: Optional[List[int]] = None,
    full_test: bool = True
) -> List[DiscoveredService]:
    """
    便捷函数：发现网段内的 AI 服务
    
    示例:
        services = await discover_network("192.168.1.0/24")
        for svc in services:
            print(f"{svc.service_type.value}: {svc.endpoint}")
            print(f"  能力: {[c.value for c in svc.capabilities]}")
            print(f"  模型: {svc.models}")
    """
    engine = ServiceDiscoveryEngine()
    return await engine.discover_network(network, ports, full_test)


async def discover_single(ip: str, port: int, full_test: bool = True) -> Optional[DiscoveredService]:
    """便捷函数：发现单个服务"""
    engine = ServiceDiscoveryEngine()
    return await engine.discover_single(ip, port, full_test)


# 示例用法
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def demo():
        # 发现本地网段
        services = await discover_network("127.0.0.1/32", ports=[11434, 8080, 3000])
        
        print("\n=== 发现结果 ===")
        for svc in services:
            print(f"\n服务: {svc.service_id}")
            print(f"  类型: {svc.service_type.value}")
            print(f"  置信度: {svc.fingerprint.confidence:.2f}")
            print(f"  能力: {[c.value for c in svc.capabilities]}")
            print(f"  模型: {svc.models[:5]}...")  # 最多显示5个
            print(f"  健康: {svc.health_status}")
    
    asyncio.run(demo())
