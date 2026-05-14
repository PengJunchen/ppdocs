"""
服务发现测试脚本
"""

import asyncio
import sys
from service_discovery import (
    ServiceDiscoveryEngine,
    discover_network,
    discover_single,
    ServiceType,
    ServiceCapability
)


async def test_single_discovery():
    """测试单服务发现"""
    print("=" * 60)
    print("测试单服务发现")
    print("=" * 60)
    
    # 测试本地 Ollama (如果存在)
    print("\n1. 探测 localhost:11434 (Ollama)...")
    svc = await discover_single("127.0.0.1", 11434)
    if svc:
        print(f"   ✓ 发现服务: {svc.service_type.value}")
        print(f"   ✓ 置信度: {svc.fingerprint.confidence:.2f}")
        print(f"   ✓ 能力: {[c.value for c in svc.capabilities]}")
        print(f"   ✓ 模型数: {len(svc.models)}")
    else:
        print("   ✗ 未识别到 AI 服务")
    
    # 测试常见端口
    test_ports = [
        ("127.0.0.1", 8080, "llama.cpp/通用"),
        ("127.0.0.1", 8000, "vLLM/通用"),
        ("127.0.0.1", 3000, "MCP Server"),
    ]
    
    for ip, port, name in test_ports:
        print(f"\n2. 探测 {ip}:{port} ({name})...")
        svc = await discover_single(ip, port, full_test=False)
        if svc:
            print(f"   ✓ 发现服务: {svc.service_type.value}")
            print(f"   ✓ 置信度: {svc.fingerprint.confidence:.2f}")
        else:
            print("   ✗ 端口未开放或未识别")


async def test_network_discovery():
    """测试网段发现"""
    print("\n" + "=" * 60)
    print("测试网段发现")
    print("=" * 60)
    
    # 只扫描本地回环，避免扫描整个网段
    print("\n扫描 127.0.0.1/32 (仅本机)...")
    services = await discover_network(
        "127.0.0.1/32",
        ports=[11434, 8080, 8000, 3000, 5000],
        full_test=False  # 快速扫描，不做完整测试
    )
    
    print(f"\n发现 {len(services)} 个服务:")
    for svc in services:
        print(f"\n  [{svc.service_type.value.upper()}]")
        print(f"    地址: {svc.endpoint}")
        print(f"    置信度: {svc.fingerprint.confidence:.2%}")
        print(f"    检测端点: {svc.fingerprint.endpoints}")


async def test_engine_features():
    """测试引擎高级功能"""
    print("\n" + "=" * 60)
    print("测试引擎高级功能")
    print("=" * 60)
    
    engine = ServiceDiscoveryEngine()
    
    # 订阅发现事件
    def on_discover(services):
        print(f"   [事件] 服务注册表更新: {len(services)} 个服务")
    
    engine.subscribe(on_discover)
    
    # 发现服务
    await engine.discover_network("127.0.0.1/32", ports=[11434, 8080], full_test=False)
    
    # 按类型查询
    print("\n按类型查询:")
    openai_services = engine.get_services_by_type(ServiceType.OPENAI_API)
    print(f"  OpenAI API: {len(openai_services)} 个")
    
    mcp_services = engine.get_services_by_type(ServiceType.MCP_SERVER)
    print(f"  MCP Server: {len(mcp_services)} 个")
    
    # 按能力查询
    print("\n按能力查询:")
    chat_services = engine.get_services_by_capability(ServiceCapability.CHAT)
    print(f"  支持 Chat: {len(chat_services)} 个")


async def demo_real_world():
    """真实场景演示"""
    print("\n" + "=" * 60)
    print("真实场景演示: 自动发现并连接模型服务")
    print("=" * 60)
    
    engine = ServiceDiscoveryEngine()
    
    # 发现网段
    print("\n1. 扫描局域网...")
    services = await engine.discover_network(
        "127.0.0.1/32",  # 实际使用时改为真实网段如 "192.168.1.0/24"
        ports=[11434, 8080, 8000, 3000],
        full_test=True
    )
    
    if not services:
        print("   未发现任何 AI 服务")
        return
    
    # 自动选择最佳服务
    print("\n2. 自动选择最佳服务...")
    best_chat = engine.get_best_service(ServiceCapability.CHAT)
    if best_chat:
        print(f"   ✓ 最佳 Chat 服务: {best_chat.endpoint}")
        print(f"     模型: {best_chat.models[:3]}...")
        print(f"     响应时间: {best_chat.response_time_ms:.0f}ms")
    
    best_embed = engine.get_best_service(ServiceCapability.EMBEDDINGS)
    if best_embed:
        print(f"   ✓ 最佳 Embeddings 服务: {best_embed.endpoint}")
    
    # 生成配置
    print("\n3. 生成配置...")
    config = {
        "llm_endpoints": [
            {
                "name": f"{svc.service_type.value}_{svc.ip}",
                "endpoint": svc.endpoint,
                "type": svc.service_type.value,
                "capabilities": [c.value for c in svc.capabilities],
                "models": svc.models[:5]
            }
            for svc in services
        ]
    }
    
    import json
    print(json.dumps(config, indent=2, ensure_ascii=False))


def print_usage():
    print("""
用法: python test_discovery.py [命令]

命令:
    single      测试单服务发现
    network     测试网段发现
    engine      测试引擎功能
    demo        完整演示
    all         运行所有测试

示例:
    python test_discovery.py single
    python test_discovery.py demo
    """)


async def main():
    if len(sys.argv) < 2:
        print_usage()
        return
    
    command = sys.argv[1]
    
    if command == "single":
        await test_single_discovery()
    elif command == "network":
        await test_network_discovery()
    elif command == "engine":
        await test_engine_features()
    elif command == "demo":
        await demo_real_world()
    elif command == "all":
        await test_single_discovery()
        await test_network_discovery()
        await test_engine_features()
        await demo_real_world()
    else:
        print(f"未知命令: {command}")
        print_usage()


if __name__ == "__main__":
    asyncio.run(main())
