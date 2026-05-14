# probe_discovery - AI 服务自动发现模块

独立的 AI 服务自动发现模块，通过网段扫描 + 指纹识别自动发现局域网内的 OpenAI 兼容 API、MCP 服务器等 AI 服务。

## 目录结构

```
probe_discovery/
├── __init__.py          # 模块入口
├── models.py            # 数据模型和配置
├── scanner.py           # 端口扫描器
├── fingerprinter.py     # 服务指纹识别
├── tester.py            # 能力测试器
├── engine.py            # 发现引擎
├── api.py               # FastAPI 路由
├── test_probe_discovery.py  # 测试用例
└── README.md            # 本文档
```

## 核心功能

1. **端口扫描** - 支持 CIDR 网段扫描，并发扫描多个端口
2. **指纹识别** - 自动识别 OpenAI API、MCP Server、LLM Gateway
3. **能力测试** - 测试 Chat、Completion、Embeddings 等能力
4. **服务注册** - 按类型、能力查询服务，自动选择最佳服务
5. **API 集成** - 8 个 REST API 端点

## 使用方式

### 1. 编程方式使用

```python
import asyncio
from probe_discovery import (
    discover_network,
    discover_single,
    ServiceDiscoveryEngine,
    ServiceCapability,
    DiscoveryConfig,
)

# 方式1: 扫描整个网段
async def scan_network():
    services = await discover_network("192.168.1.0/24")
    
    for svc in services:
        print(f"发现服务: {svc.endpoint}")
        print(f"  类型: {svc.service_type.value}")
        print(f"  置信度: {svc.fingerprint.confidence:.2%}")
        print(f"  能力: {[c.value for c in svc.capabilities]}")
        print(f"  模型: {svc.models}")

# 方式2: 发现单个服务
async def scan_single():
    service = await discover_single("192.168.1.100", 11434)
    if service:
        print(f"识别到: {service.service_type.value}")

# 方式3: 使用引擎进行高级操作
async def advanced_usage():
    engine = ServiceDiscoveryEngine()
    
    # 扫描网段
    await engine.discover_network("192.168.1.0/24")
    
    # 获取所有 OpenAI API 服务
    openai_services = engine.get_services_by_type(ServiceType.OPENAI_API)
    
    # 获取支持 Chat 的服务
    chat_services = engine.get_services_by_capability(ServiceCapability.CHAT)
    
    # 获取最佳 Chat 服务（按响应时间）
    best_chat = engine.get_best_service(ServiceCapability.CHAT)
    if best_chat:
        print(f"最佳 Chat 服务: {best_chat.endpoint}")

asyncio.run(scan_network())
```

### 2. API 方式使用

启动 doc-parser 服务后，可通过以下 API 进行服务发现：

#### 扫描网段

```bash
curl -X POST http://localhost:8000/v1/discovery/scan \
  -H "Content-Type: application/json" \
  -d '{
    "network": "192.168.1.0/24",
    "ports": [11434, 8080, 8000, 3000],
    "full_test": true
  }'
```

响应示例：
```json
{
  "network": "192.168.1.0/24",
  "total_found": 2,
  "services": [
    {
      "service_id": "192.168.1.100:11434",
      "service_type": "openai_api",
      "ip": "192.168.1.100",
      "port": 11434,
      "endpoint": "http://192.168.1.100:11434",
      "capabilities": ["chat", "completion"],
      "models": ["llama3:8b", "qwen:14b"],
      "confidence": 0.95,
      "health_status": "healthy"
    }
  ],
  "scan_duration_ms": 5234
}
```

#### 扫描单个服务

```bash
curl "http://localhost:8000/v1/discovery/scan/single?ip=192.168.1.100&port=11434&full_test=true"
```

#### 获取发现状态

```bash
curl http://localhost:8000/v1/discovery/status
```

#### 按类型查询服务

```bash
curl http://localhost:8000/v1/discovery/services/by-type/openai_api
```

#### 按能力查询服务

```bash
curl http://localhost:8000/v1/discovery/services/by-capability/chat
```

#### 获取最佳服务

```bash
curl http://localhost:8000/v1/discovery/services/best/chat
```

## 配置选项

```python
from probe_discovery import DiscoveryConfig

config = DiscoveryConfig(
    # 扫描配置
    scan_timeout=2.0,        # 端口扫描超时(秒)
    probe_timeout=5.0,       # 服务探测超时(秒)
    test_timeout=10.0,       # 能力测试超时(秒)
    max_concurrent=100,      # 最大并发数
    
    # 扫描范围
    ports=[11434, 8080, 8000, 3000, 5000],  # 要扫描的端口
    
    # 行为配置
    full_test=True,          # 是否进行完整能力测试
    min_confidence=0.5,      # 最小置信度阈值
)

engine = ServiceDiscoveryEngine(config)
```

## 服务类型识别

模块支持自动识别以下服务类型：

| 服务类型 | 识别方法 | 置信度计算 |
|---------|---------|-----------|
| **OpenAI API** | `/v1/models` 端点 + `object=list` 字段 | 状态码(30%) + 字段匹配(50%) + 响应头(20%) |
| **MCP Server** | `/health` + SSE 流 + JSON-RPC | 健康端点(20%) + SSE(40%) + JSON-RPC(30%) |
| **LLM Gateway** | `/model/info` + `litellm_params` | 自定义字段匹配 |

## 常见端口映射

| 端口 | 服务 | 类型 |
|-----|------|------|
| 11434 | Ollama | OpenAI API |
| 8080 | llama.cpp/通用 | OpenAI API |
| 8000 | vLLM/通用 | OpenAI API |
| 3000 | MCP Server | MCP |
| 5000 | Flask/通用 | 未知 |

## 测试

```bash
# 运行测试
python -m pytest probe_discovery/test_probe_discovery.py -v
```

## API 端点列表

| 方法 | 端点 | 说明 |
|-----|------|------|
| POST | `/v1/discovery/scan` | 扫描网段 |
| GET | `/v1/discovery/scan/single` | 扫描单个服务 |
| GET | `/v1/discovery/status` | 获取发现状态 |
| GET | `/v1/discovery/services/by-type/{type}` | 按类型查询 |
| GET | `/v1/discovery/services/by-capability/{cap}` | 按能力查询 |
| GET | `/v1/discovery/services/best/{capability}` | 获取最佳服务 |
| DELETE | `/v1/discovery/services/{id}` | 移除服务 |
| DELETE | `/v1/discovery/services` | 清空所有服务 |

## 依赖

- Python 3.8+
- httpx
- pydantic
- fastapi (API 路由)

## 许可证

MIT License
