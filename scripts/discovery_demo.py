"""
服务发现演示 - 模拟各种 AI 服务端点
用于在没有真实服务的情况下测试发现逻辑
"""

import asyncio
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time


class MockOpenAIHandler(BaseHTTPRequestHandler):
    """模拟 OpenAI 兼容 API"""
    
    def log_message(self, format, *args):
        pass  # 静默日志
    
    def do_GET(self):
        if self.path == "/v1/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("openai-version", "2023-05-15")
            self.end_headers()
            response = {
                "object": "list",
                "data": [
                    {
                        "id": "gpt-4",
                        "object": "model",
                        "created": 1687882411,
                        "owned_by": "openai"
                    },
                    {
                        "id": "gpt-3.5-turbo",
                        "object": "model",
                        "created": 1677649963,
                        "owned_by": "openai"
                    }
                ]
            }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == "/v1/chat/completions":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "gpt-4",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop"
                }]
            }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == "/v1/completions":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "id": "cmpl-test",
                "object": "text_completion",
                "created": int(time.time()),
                "model": "gpt-4",
                "choices": [{"text": "Hello world", "index": 0}]
            }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == "/v1/embeddings":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "object": "list",
                "data": [{
                    "object": "embedding",
                    "embedding": [0.1, 0.2, 0.3],
                    "index": 0
                }],
                "model": "text-embedding-ada-002"
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()


class MockMCPHandler(BaseHTTPRequestHandler):
    """模拟 MCP 服务器"""
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "status": "healthy",
                "version": "1.0.0",
                "tools": ["weather", "calculator"]
            }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == "/sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            # 发送一个简单的 SSE 事件
            self.wfile.write(b"data: {\"jsonrpc\": \"2.0\", \"method\": \"initialize\"}\n\n")
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body)
            if data.get("jsonrpc") == "2.0":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "tools": [
                            {"name": "weather", "description": "Get weather"},
                            {"name": "calculator", "description": "Calculate"}
                        ]
                    }
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_response(400)
                self.end_headers()
        except:
            self.send_response(400)
            self.end_headers()


def start_mock_server(port, handler_class):
    """启动模拟服务器"""
    server = HTTPServer(("127.0.0.1", port), handler_class)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server


async def run_demo():
    """运行演示"""
    print("=" * 60)
    print("服务发现演示")
    print("=" * 60)
    
    # 启动模拟服务器
    print("\n1. 启动模拟服务器...")
    openai_server = start_mock_server(8081, MockOpenAIHandler)
    mcp_server = start_mock_server(3001, MockMCPHandler)
    print("   ✓ OpenAI API 模拟器运行在 127.0.0.1:8081")
    print("   ✓ MCP Server 模拟器运行在 127.0.0.1:3001")
    
    # 等待服务器启动
    await asyncio.sleep(1)
    
    # 导入并运行发现
    print("\n2. 开始服务发现...")
    from service_discovery import discover_network
    
    services = await discover_network(
        "127.0.0.1/32",
        ports=[8081, 3001],
        full_test=True
    )
    
    # 显示结果
    print("\n3. 发现结果:")
    print("-" * 60)
    
    if not services:
        print("   未发现任何服务")
    else:
        for svc in services:
            print(f"\n   [{svc.service_type.value.upper()}]")
            print(f"   地址: {svc.endpoint}")
            print(f"   置信度: {svc.fingerprint.confidence:.2%}")
            print(f"   检测端点: {svc.fingerprint.endpoints}")
            print(f"   能力: {[c.value for c in svc.capabilities]}")
            print(f"   模型: {svc.models}")
            print(f"   健康: {svc.health_status}")
            print(f"   响应时间: {svc.response_time_ms:.0f}ms")
    
    print("\n" + "=" * 60)
    print("演示完成")
    print("=" * 60)
    
    # 关闭服务器
    openai_server.shutdown()
    mcp_server.shutdown()


if __name__ == "__main__":
    asyncio.run(run_demo())
