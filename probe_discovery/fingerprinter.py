"""
服务指纹识别
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional

import httpx

from .models import ServiceFingerprint, ServiceType

logger = logging.getLogger(__name__)


class ServiceFingerprinter:
    """服务指纹识别器"""
    
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
    
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
    
    async def identify_llm_gateway(self, ip: str, port: int) -> Optional[ServiceFingerprint]:
        """识别 LLM Gateway (如 LiteLLM)"""
        # 测试 /model/info 或 /v1/model/info
        paths = ["/model/info", "/v1/model/info", "/health"]
        
        for path in paths:
            result = await self.probe_endpoint(ip, port, path)
            if not result:
                continue
            
            confidence = 0.0
            endpoints = []
            
            if result["status"] == 200:
                confidence += 0.2
                endpoints.append(path)
            
            # 检查 LiteLLM 特征
            headers = result["headers"]
            if "litellm-version" in headers:
                confidence += 0.4
            
            try:
                body = json.loads(result["body"])
                # LiteLLM 特征字段
                if "model_info" in body or "litellm_params" in body:
                    confidence += 0.4
                # 检查是否有模型列表
                if "data" in body and isinstance(body.get("data"), list):
                    for item in body.get("data", []):
                        if isinstance(item, dict) and "model_name" in item:
                            confidence += 0.2
                            break
            except json.JSONDecodeError:
                pass
            
            if confidence >= 0.5:
                return ServiceFingerprint(
                    service_type=ServiceType.LLM_GATEWAY,
                    confidence=min(confidence, 1.0),
                    endpoints=endpoints,
                    headers=headers,
                    body_patterns=[],
                    version=headers.get("litellm-version")
                )
        
        return None
    
    async def identify_service(self, ip: str, port: int) -> Optional[ServiceFingerprint]:
        """识别服务类型"""
        # 按优先级尝试识别
        
        # 1. 尝试识别 OpenAI API
        fingerprint = await self.identify_openai_api(ip, port)
        if fingerprint:
            logger.debug(f"识别为 OpenAI API: {ip}:{port}, 置信度: {fingerprint.confidence}")
            return fingerprint
        
        # 2. 尝试识别 MCP 服务器
        fingerprint = await self.identify_mcp_server(ip, port)
        if fingerprint:
            logger.debug(f"识别为 MCP Server: {ip}:{port}, 置信度: {fingerprint.confidence}")
            return fingerprint
        
        # 3. 尝试识别 LLM Gateway
        fingerprint = await self.identify_llm_gateway(ip, port)
        if fingerprint:
            logger.debug(f"识别为 LLM Gateway: {ip}:{port}, 置信度: {fingerprint.confidence}")
            return fingerprint
        
        return None
