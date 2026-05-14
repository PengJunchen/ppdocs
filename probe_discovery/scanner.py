"""
端口扫描器
"""

import asyncio
import ipaddress
import logging
from typing import Dict, List, Optional

from .models import ServiceType

logger = logging.getLogger(__name__)


class PortScanner:
    """端口扫描器"""
    
    # 常见 AI 服务端口映射
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
                
                # 获取端口预设信息
                preset = self.COMMON_PORTS.get(port)
                return {
                    "ip": ip,
                    "port": port,
                    "open": True,
                    "preset_name": preset[0] if preset else None,
                    "preset_type": preset[1] if preset else ServiceType.UNKNOWN,
                }
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                return None
            except Exception as e:
                logger.debug(f"扫描 {ip}:{port} 时出错: {e}")
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
        
        try:
            net = ipaddress.ip_network(network, strict=False)
            hosts = [str(ip) for ip in net.hosts()]
        except ValueError as e:
            logger.error(f"无效的网段格式: {network}, 错误: {e}")
            return []
        
        logger.info(f"开始扫描网段 {network}，共 {len(hosts)} 个主机，{len(ports)} 个端口")
        
        tasks = []
        for host in hosts:
            for port in ports:
                tasks.append(self.scan_host(host, port))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        open_ports = [
            r for r in results 
            if r is not None and not isinstance(r, Exception)
        ]
        
        logger.info(f"扫描完成，发现 {len(open_ports)} 个开放端口")
        return open_ports
    
    async def scan_single(self, ip: str, port: int) -> Optional[Dict]:
        """扫描单个端口"""
        return await self.scan_host(ip, port)
