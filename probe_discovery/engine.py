"""
服务发现引擎
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from .models import (
    DiscoveredService,
    DiscoveryConfig,
    ServiceCapability,
    ServiceType,
)
from .fingerprinter import ServiceFingerprinter
from .scanner import PortScanner
from .tester import CapabilityTester

logger = logging.getLogger(__name__)


class ServiceDiscoveryEngine:
    """服务发现引擎"""
    
    def __init__(self, config: Optional[DiscoveryConfig] = None):
        self.config = config or DiscoveryConfig()
        self.scanner = PortScanner(
            timeout=self.config.scan_timeout,
            max_concurrent=self.config.max_concurrent
        )
        self.fingerprinter = ServiceFingerprinter(timeout=self.config.probe_timeout)
        self.tester = CapabilityTester(timeout=self.config.test_timeout)
        self.discovered_services: Dict[str, DiscoveredService] = {}
        self.subscribers: List[Callable] = []
        self._lock = asyncio.Lock()
        self._running = False
    
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
        full_test: Optional[bool] = None
    ) -> List[DiscoveredService]:
        """
        发现网段内的 AI 服务
        
        Args:
            network: 网段，如 "192.168.1.0/24"
            ports: 指定端口列表，None 则使用配置
            full_test: 是否进行完整能力测试，None 则使用配置
        
        Returns:
            发现的服务列表
        """
        start_time = time.time()
        
        if ports is None:
            ports = self.config.ports
        if full_test is None:
            full_test = self.config.full_test
        
        logger.info(f"开始发现网段: {network}")
        
        # 1. 端口扫描
        open_ports = await self.scanner.scan_network(network, ports)
        logger.info(f"发现 {len(open_ports)} 个开放端口")
        
        # 2. 服务识别
        identified_services = []
        for port_info in open_ports:
            ip = port_info["ip"]
            port = port_info["port"]
            
            fingerprint = await self.fingerprinter.identify_service(ip, port)
            if fingerprint and fingerprint.confidence >= self.config.min_confidence:
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
                logger.info(
                    f"识别到服务: {service_id} "
                    f"({fingerprint.service_type.value}, "
                    f"置信度: {fingerprint.confidence:.2f})"
                )
        
        logger.info(f"识别到 {len(identified_services)} 个 AI 服务")
        
        # 3. 能力测试
        if full_test:
            logger.info("开始能力测试...")
            tested_services = await asyncio.gather(*[
                self.tester.test_service(svc) for svc in identified_services
            ])
            identified_services = list(tested_services)
        
        # 4. 更新注册表
        async with self._lock:
            for svc in identified_services:
                self.discovered_services[svc.service_id] = svc
        
        # 5. 通知订阅者
        await self._notify_subscribers()
        
        duration = (time.time() - start_time) * 1000
        logger.info(f"发现完成，耗时 {duration:.0f}ms")
        
        return identified_services
    
    async def discover_single(
        self,
        ip: str,
        port: int,
        full_test: Optional[bool] = None
    ) -> Optional[DiscoveredService]:
        """发现单个服务"""
        if full_test is None:
            full_test = self.config.full_test
        
        fingerprint = await self.fingerprinter.identify_service(ip, port)
        if not fingerprint or fingerprint.confidence < self.config.min_confidence:
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
        
        async with self._lock:
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
    
    def get_all_services(self) -> List[DiscoveredService]:
        """获取所有服务"""
        return list(self.discovered_services.values())
    
    def get_service(self, service_id: str) -> Optional[DiscoveredService]:
        """获取指定服务"""
        return self.discovered_services.get(service_id)
    
    def remove_service(self, service_id: str) -> bool:
        """移除服务"""
        if service_id in self.discovered_services:
            del self.discovered_services[service_id]
            return True
        return False
    
    def clear(self):
        """清空所有服务"""
        self.discovered_services.clear()
    
    async def start_continuous_discovery(
        self,
        network: str,
        interval: int = 300
    ):
        """启动持续发现"""
        self._running = True
        logger.info(f"启动持续发现，网段: {network}, 间隔: {interval}s")
        
        while self._running:
            try:
                await self.discover_network(network)
            except Exception as e:
                logger.error(f"持续发现出错: {e}")
            
            await asyncio.sleep(interval)
    
    def stop_continuous_discovery(self):
        """停止持续发现"""
        self._running = False
        logger.info("停止持续发现")


# 便捷使用函数
async def discover_network(
    network: str,
    ports: Optional[List[int]] = None,
    full_test: bool = True,
    config: Optional[DiscoveryConfig] = None
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
    engine = ServiceDiscoveryEngine(config)
    return await engine.discover_network(network, ports, full_test)


async def discover_single(
    ip: str,
    port: int,
    full_test: bool = True,
    config: Optional[DiscoveryConfig] = None
) -> Optional[DiscoveredService]:
    """便捷函数：发现单个服务"""
    engine = ServiceDiscoveryEngine(config)
    return await engine.discover_single(ip, port, full_test)
