"""
服务发现 API 路由 (独立模块)
"""

import time
from typing import Optional

from fastapi import APIRouter, HTTPException

from probe_discovery import ServiceDiscoveryEngine, DiscoveryConfig
from probe_discovery.models import (
    DiscoveryScanRequest,
    DiscoveryScanResponse,
    DiscoveryStatusResponse,
    DiscoveredServiceResponse,
)

router = APIRouter(prefix="/discovery", tags=["discovery"])

# 全局发现引擎实例
_discovery_engine: Optional[ServiceDiscoveryEngine] = None


def get_discovery_engine() -> ServiceDiscoveryEngine:
    """获取或创建发现引擎"""
    global _discovery_engine
    if _discovery_engine is None:
        _discovery_engine = ServiceDiscoveryEngine()
    return _discovery_engine


@router.post("/scan", response_model=DiscoveryScanResponse)
async def scan_network(request: DiscoveryScanRequest):
    """
    扫描网段发现 AI 服务
    
    示例请求:
    ```json
    {
        "network": "192.168.1.0/24",
        "ports": [11434, 8080, 8000, 3000],
        "full_test": true
    }
    ```
    """
    start_time = time.time()
    
    try:
        engine = get_discovery_engine()
        services = await engine.discover_network(
            network=request.network,
            ports=request.ports,
            full_test=request.full_test
        )
        
        duration = (time.time() - start_time) * 1000
        
        return DiscoveryScanResponse(
            network=request.network,
            total_found=len(services),
            services=[
                DiscoveredServiceResponse.from_service(svc) 
                for svc in services
            ],
            scan_duration_ms=duration
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/single")
async def scan_single(ip: str, port: int, full_test: bool = True):
    """
    扫描单个服务
    
    参数:
    - ip: IP 地址
    - port: 端口号
    - full_test: 是否进行完整能力测试
    """
    try:
        engine = get_discovery_engine()
        service = await engine.discover_single(ip, port, full_test)
        
        if not service:
            raise HTTPException(
                status_code=404, 
                detail=f"未在 {ip}:{port} 识别到 AI 服务"
            )
        
        return DiscoveredServiceResponse.from_service(service)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=DiscoveryStatusResponse)
async def get_discovery_status():
    """获取发现状态"""
    engine = get_discovery_engine()
    services = engine.get_all_services()
    
    # 统计
    by_type = {}
    by_capability = {}
    healthy_count = 0
    
    for svc in services:
        # 按类型统计
        type_name = svc.service_type.value
        by_type[type_name] = by_type.get(type_name, 0) + 1
        
        # 按能力统计
        for cap in svc.capabilities:
            cap_name = cap.value
            by_capability[cap_name] = by_capability.get(cap_name, 0) + 1
        
        # 健康统计
        if svc.health_status == "healthy":
            healthy_count += 1
    
    return DiscoveryStatusResponse(
        total_services=len(services),
        by_type=by_type,
        by_capability=by_capability,
        healthy_count=healthy_count,
        services=[
            DiscoveredServiceResponse.from_service(svc) 
            for svc in services
        ]
    )


@router.get("/services/by-type/{service_type}")
async def get_services_by_type(service_type: str):
    """按类型获取服务"""
    from probe_discovery import ServiceType
    
    engine = get_discovery_engine()
    
    try:
        svc_type = ServiceType(service_type)
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"无效的服务类型: {service_type}"
        )
    
    services = engine.get_services_by_type(svc_type)
    return [
        DiscoveredServiceResponse.from_service(svc) 
        for svc in services
    ]


@router.get("/services/by-capability/{capability}")
async def get_services_by_capability(capability: str):
    """按能力获取服务"""
    from probe_discovery import ServiceCapability
    
    engine = get_discovery_engine()
    
    try:
        cap = ServiceCapability(capability)
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"无效的能力类型: {capability}"
        )
    
    services = engine.get_services_by_capability(cap)
    return [
        DiscoveredServiceResponse.from_service(svc) 
        for svc in services
    ]


@router.get("/services/best/{capability}")
async def get_best_service(capability: str):
    """获取最佳服务（按健康状态和响应时间）"""
    from probe_discovery import ServiceCapability
    
    engine = get_discovery_engine()
    
    try:
        cap = ServiceCapability(capability)
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"无效的能力类型: {capability}"
        )
    
    service = engine.get_best_service(cap)
    
    if not service:
        raise HTTPException(
            status_code=404, 
            detail=f"未找到支持 {capability} 的服务"
        )
    
    return DiscoveredServiceResponse.from_service(service)


@router.delete("/services/{service_id}")
async def remove_service(service_id: str):
    """移除服务"""
    engine = get_discovery_engine()
    
    if engine.remove_service(service_id):
        return {"message": f"服务 {service_id} 已移除"}
    else:
        raise HTTPException(
            status_code=404, 
            detail=f"服务 {service_id} 不存在"
        )


@router.delete("/services")
async def clear_all_services():
    """清空所有服务"""
    engine = get_discovery_engine()
    engine.clear()
    return {"message": "所有服务已清空"}
