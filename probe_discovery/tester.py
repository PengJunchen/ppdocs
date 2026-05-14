"""
服务能力测试器
"""

import asyncio
import json
import logging
from typing import List

import httpx

from .models import DiscoveredService, ServiceCapability

logger = logging.getLogger(__name__)


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
        except Exception as e:
            logger.debug(f"Chat 能力测试失败: {e}")
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
        except Exception as e:
            logger.debug(f"Completion 能力测试失败: {e}")
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
        except Exception as e:
            logger.debug(f"Embeddings 能力测试失败: {e}")
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
        except Exception as e:
            logger.debug(f"获取模型列表失败: {e}")
        return []
    
    async def test_mcp_capabilities(self, endpoint: str) -> List[ServiceCapability]:
        """测试 MCP 服务器能力"""
        capabilities = []
        
        # 测试 /health 端点
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{endpoint}/health")
                if response.status_code == 200:
                    capabilities.append(ServiceCapability.CHAT)  # MCP 通常支持 chat
        except Exception:
            pass
        
        # 测试 JSON-RPC 端点
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{endpoint}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": 1
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "result" in data:
                        capabilities.append(ServiceCapability.FUNCTION_CALL)
        except Exception:
            pass
        
        return capabilities
    
    async def test_service(self, service: DiscoveredService) -> DiscoveredService:
        """完整测试服务"""
        from datetime import datetime
        
        endpoint = service.endpoint
        
        if service.service_type.value == "openai_api":
            # 测试 OpenAI API 能力
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
            
        elif service.service_type.value == "mcp_server":
            # 测试 MCP 能力
            capabilities = await self.test_mcp_capabilities(endpoint)
            service.capabilities = capabilities
        
        service.last_checked = datetime.now()
        
        # 健康状态
        if service.capabilities:
            service.health_status = "healthy"
        else:
            service.health_status = "degraded"
        
        return service
