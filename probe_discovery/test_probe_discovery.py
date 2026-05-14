"""
服务发现模块测试 (独立模块)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from probe_discovery import (
    ServiceDiscoveryEngine,
    ServiceType,
    ServiceCapability,
    DiscoveryConfig,
    discover_network,
    discover_single,
)
from probe_discovery.models import (
    DiscoveredService,
    ServiceFingerprint,
)


class TestDiscoveryModels:
    """测试数据模型"""
    
    def test_service_type_enum(self):
        """测试服务类型枚举"""
        assert ServiceType.OPENAI_API.value == "openai_api"
        assert ServiceType.MCP_SERVER.value == "mcp_server"
        assert ServiceType.LLM_GATEWAY.value == "llm_gateway"
        assert ServiceType.UNKNOWN.value == "unknown"
    
    def test_service_capability_enum(self):
        """测试服务能力枚举"""
        assert ServiceCapability.CHAT.value == "chat"
        assert ServiceCapability.COMPLETION.value == "completion"
        assert ServiceCapability.EMBEDDINGS.value == "embeddings"
    
    def test_discovery_config_defaults(self):
        """测试配置默认值"""
        config = DiscoveryConfig()
        assert config.scan_timeout == 2.0
        assert config.probe_timeout == 5.0
        assert config.test_timeout == 10.0
        assert config.max_concurrent == 100
        assert config.full_test is True
        assert config.min_confidence == 0.5


class TestPortScanner:
    """测试端口扫描器"""
    
    @pytest.mark.asyncio
    async def test_scan_host_open_port(self):
        """测试扫描开放端口"""
        from probe_discovery.scanner import PortScanner
        
        scanner = PortScanner(timeout=0.1)
        
        # 模拟开放端口 - 使用正确的模块路径
        with patch('probe_discovery.scanner.asyncio.open_connection') as mock_connect:
            mock_reader = MagicMock()
            mock_writer = MagicMock()
            mock_writer.close = MagicMock()
            mock_writer.wait_closed = AsyncMock()
            mock_connect.return_value = (mock_reader, mock_writer)
            
            result = await scanner.scan_host("127.0.0.1", 8080)
            
            assert result is not None
            assert result["ip"] == "127.0.0.1"
            assert result["port"] == 8080
            assert result["open"] is True
    
    @pytest.mark.asyncio
    async def test_scan_host_closed_port(self):
        """测试扫描关闭端口"""
        from probe_discovery.scanner import PortScanner
        
        scanner = PortScanner(timeout=0.1)
        
        # 模拟关闭端口
        with patch('probe_discovery.scanner.asyncio.open_connection') as mock_connect:
            mock_connect.side_effect = ConnectionRefusedError()
            
            result = await scanner.scan_host("127.0.0.1", 9999)
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_scan_network(self):
        """测试扫描网段"""
        from probe_discovery.scanner import PortScanner
        
        scanner = PortScanner(timeout=0.1)
        
        # 模拟扫描结果 - /30 网段只有 2 个可用主机 (.1 和 .2)
        with patch.object(scanner, 'scan_host') as mock_scan:
            mock_scan.side_effect = [
                {"ip": "192.168.1.1", "port": 8080, "open": True},
                None,  # 192.168.1.2 关闭
            ]
            
            results = await scanner.scan_network(
                "192.168.1.0/30",
                ports=[8080]
            )
            
            assert len(results) == 1
            assert results[0]["ip"] == "192.168.1.1"


class TestServiceFingerprinter:
    """测试服务指纹识别"""
    
    @pytest.mark.asyncio
    async def test_identify_openai_api(self):
        """测试识别 OpenAI API"""
        from probe_discovery.fingerprinter import ServiceFingerprinter
        
        fingerprinter = ServiceFingerprinter(timeout=0.1)
        
        # 模拟 OpenAI API 响应
        mock_response = {
            "url": "http://127.0.0.1:8080/v1/models",
            "status": 200,
            "headers": {"openai-version": "2023-05-15"},
            "body": '{"object": "list", "data": [{"id": "gpt-4", "object": "model"}]}',
            "response_time_ms": 50.0
        }
        
        with patch.object(fingerprinter, 'probe_endpoint', return_value=mock_response):
            result = await fingerprinter.identify_openai_api("127.0.0.1", 8080)
            
            assert result is not None
            assert result.service_type == ServiceType.OPENAI_API
            assert result.confidence > 0.5
            assert "/v1/models" in result.endpoints
    
    @pytest.mark.asyncio
    async def test_identify_mcp_server(self):
        """测试识别 MCP 服务器"""
        from probe_discovery.fingerprinter import ServiceFingerprinter
        
        fingerprinter = ServiceFingerprinter(timeout=0.1)
        
        # 模拟 MCP 健康端点响应
        mock_response = {
            "url": "http://127.0.0.1:3000/health",
            "status": 200,
            "headers": {"content-type": "application/json"},
            "body": '{"status": "healthy", "tools": ["weather"]}',
            "response_time_ms": 30.0
        }
        
        with patch.object(fingerprinter, 'probe_endpoint', return_value=mock_response):
            result = await fingerprinter.identify_mcp_server("127.0.0.1", 3000)
            
            assert result is not None
            assert result.service_type == ServiceType.MCP_SERVER
    
    @pytest.mark.asyncio
    async def test_identify_service_unknown(self):
        """测试识别未知服务"""
        from probe_discovery.fingerprinter import ServiceFingerprinter
        
        fingerprinter = ServiceFingerprinter(timeout=0.1)
        
        # 模拟不匹配任何指纹的响应
        mock_response = {
            "url": "http://127.0.0.1:9999/",
            "status": 200,
            "headers": {},
            "body": "<html>Hello</html>",
            "response_time_ms": 10.0
        }
        
        with patch.object(fingerprinter, 'probe_endpoint', return_value=mock_response):
            result = await fingerprinter.identify_service("127.0.0.1", 9999)
            
            assert result is None


class TestCapabilityTester:
    """测试能力测试器"""
    
    @pytest.mark.asyncio
    async def test_test_chat_capability_success(self):
        """测试 Chat 能力检测成功"""
        from probe_discovery.tester import CapabilityTester
        
        tester = CapabilityTester(timeout=0.1)
        
        # 模拟支持 chat 接口 (返回 400 表示接口存在但模型不存在)
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_post.return_value = mock_response
            
            result = await tester.test_chat_capability("http://127.0.0.1:8080")
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_get_models(self):
        """测试获取模型列表"""
        from probe_discovery.tester import CapabilityTester
        
        tester = CapabilityTester(timeout=0.1)
        
        # 模拟模型列表响应
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [
                    {"id": "gpt-4"},
                    {"id": "gpt-3.5-turbo"}
                ]
            }
            mock_get.return_value = mock_response
            
            models = await tester.get_models("http://127.0.0.1:8080")
            
            assert len(models) == 2
            assert "gpt-4" in models
            assert "gpt-3.5-turbo" in models


class TestServiceDiscoveryEngine:
    """测试发现引擎"""
    
    @pytest.mark.asyncio
    async def test_discover_single_service(self):
        """测试发现单个服务"""
        engine = ServiceDiscoveryEngine()
        
        # 模拟指纹
        mock_fingerprint = ServiceFingerprint(
            service_type=ServiceType.OPENAI_API,
            confidence=0.9,
            endpoints=["/v1/models"],
            headers={},
            body_patterns=["object", "data"]
        )
        
        with patch.object(engine.fingerprinter, 'identify_service', return_value=mock_fingerprint):
            with patch.object(engine.tester, 'test_service', return_value=DiscoveredService(
                service_id="127.0.0.1:8080",
                service_type=ServiceType.OPENAI_API,
                ip="127.0.0.1",
                port=8080,
                endpoint="http://127.0.0.1:8080",
                capabilities=[ServiceCapability.CHAT],
                models=["gpt-4"],
                fingerprint=mock_fingerprint,
                health_status="healthy"
            )):
                result = await engine.discover_single("127.0.0.1", 8080)
                
                assert result is not None
                assert result.service_type == ServiceType.OPENAI_API
                assert result.health_status == "healthy"
    
    def test_get_services_by_type(self):
        """测试按类型获取服务"""
        engine = ServiceDiscoveryEngine()
        
        # 添加测试数据
        engine.discovered_services["svc1"] = DiscoveredService(
            service_id="svc1",
            service_type=ServiceType.OPENAI_API,
            ip="127.0.0.1",
            port=8080,
            endpoint="http://127.0.0.1:8080"
        )
        engine.discovered_services["svc2"] = DiscoveredService(
            service_id="svc2",
            service_type=ServiceType.MCP_SERVER,
            ip="127.0.0.1",
            port=3000,
            endpoint="http://127.0.0.1:3000"
        )
        
        openai_services = engine.get_services_by_type(ServiceType.OPENAI_API)
        assert len(openai_services) == 1
        assert openai_services[0].service_id == "svc1"
    
    def test_get_best_service(self):
        """测试获取最佳服务"""
        engine = ServiceDiscoveryEngine()
        
        # 添加测试数据
        engine.discovered_services["svc1"] = DiscoveredService(
            service_id="svc1",
            service_type=ServiceType.OPENAI_API,
            ip="127.0.0.1",
            port=8080,
            endpoint="http://127.0.0.1:8080",
            capabilities=[ServiceCapability.CHAT],
            health_status="healthy",
            response_time_ms=100.0
        )
        engine.discovered_services["svc2"] = DiscoveredService(
            service_id="svc2",
            service_type=ServiceType.OPENAI_API,
            ip="127.0.0.1",
            port=8081,
            endpoint="http://127.0.0.1:8081",
            capabilities=[ServiceCapability.CHAT],
            health_status="healthy",
            response_time_ms=50.0  # 更快
        )
        
        best = engine.get_best_service(ServiceCapability.CHAT)
        assert best is not None
        assert best.service_id == "svc2"  # 选择响应更快的


class TestConvenienceFunctions:
    """测试便捷函数"""
    
    @pytest.mark.asyncio
    async def test_discover_network(self):
        """测试 discover_network 便捷函数"""
        with patch('probe_discovery.engine.ServiceDiscoveryEngine') as MockEngine:
            mock_engine = MagicMock()
            mock_engine.discover_network = AsyncMock(return_value=[])
            MockEngine.return_value = mock_engine
            
            result = await discover_network("192.168.1.0/24")
            
            assert result == []
            mock_engine.discover_network.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_discover_single(self):
        """测试 discover_single 便捷函数"""
        mock_service = DiscoveredService(
            service_id="127.0.0.1:8080",
            service_type=ServiceType.OPENAI_API,
            ip="127.0.0.1",
            port=8080,
            endpoint="http://127.0.0.1:8080"
        )
        
        with patch('probe_discovery.engine.ServiceDiscoveryEngine') as MockEngine:
            mock_engine = MagicMock()
            mock_engine.discover_single = AsyncMock(return_value=mock_service)
            MockEngine.return_value = mock_engine
            
            result = await discover_single("127.0.0.1", 8080)
            
            assert result is not None
            assert result.service_id == "127.0.0.1:8080"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
