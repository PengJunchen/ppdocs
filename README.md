# doc-parser

企业级文档解析处理模块 - 统一封装 MinerU VLM、MinerU Pipeline、Docling 为标准化 Pipeline 接口，支持目录提取、章节拆分、图片增强、LLM统一阅读、知识图谱构建。

## 项目状态

| Phase | 名称 | 状态 |
|-------|------|------|
| Phase 1 | 成熟Pipeline集成 | ✅ COMPLETED |
| Phase 1.5 | FastAPI RESTful API | ✅ COMPLETED |
| Phase 2 | 目录提取+章节拆分 | ✅ COMPLETED |
| Phase 3 | 图片增强+LLM统一阅读 | ✅ COMPLETED |
| Phase 4 | 知识图谱+向量化存储 | ✅ COMPLETED |
| Phase 5 | API层+异步任务+端到端测试 | ✅ COMPLETED |
| Phase 5.5 | 全局审计+系统性缺陷修复 | ✅ COMPLETED |

## 快速开始

### 环境要求

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装

```bash
# 创建虚拟环境并安装
uv venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

uv pip install -e ".[dev]"
```

### 一键启动

```bash
# Windows
start.bat

# Linux/Mac
chmod +x start.sh && ./start.sh
```

脚本自动完成: 创建 `.venv` → 安装依赖 → 启动 API 服务 (`http://localhost:8000`)。

### 运行测试

```bash
pytest tests/ -v
```

## 项目结构

```
ppdocs/
├── doc_parser/                  # 主包
│   ├── pipeline/                # Phase 1: Pipeline引擎
│   │   ├── base.py              # BasePipeline + 数据模型 + 异常类
│   │   ├── mineru.py            # MinerUPipeline + MinerUVLMPipeline
│   │   ├── docling_pipeline.py  # DoclingPipeline
│   │   ├── registry.py          # PipelineRegistry + auto_select
│   │   └── __init__.py
│   ├── api/                     # REST API (FastAPI)
│   │   ├── app.py               # App工厂 + 中间件 + 服务注册
│   │   ├── models.py            # API数据模型
│   │   ├── task_manager.py      # 异步任务管理器
│   │   ├── server.py            # CLI入口点
│   │   └── v1/routes.py         # v1路由
│   │   └── v1/discovery_routes.py # 服务发现路由
│   ├── core/                    # Phase 2-4: 目录/章节/图片/阅读/KG
│   │   ├── chapter/             # Phase 2: 目录提取+章节拆分
│   │   │   ├── models.py        # OutlineNode + DocumentOutline
│   │   │   ├── toc.py           # TOCExtractor + 策略A/B/C
│   │   │   ├── splitter.py      # ChapterSplitter
│   │   │   └── __init__.py
│   │   ├── image/               # Phase 3: 图片增强
│   │   │   ├── models.py        # OCRResult + VLMDescriptionResult + EnhancedImage
│   │   │   ├── ocr_enhance.py   # OCREnhancer + MinerUOCREngine
│   │   │   ├── vlm_describe.py  # VLMDescriber + OpenAICompatibleVLM
│   │   │   ├── enhancer.py      # ImageEnhancer 统一入口
│   │   │   └── __init__.py
│   │   ├── reader/              # Phase 3: LLM统一阅读
│   │   │   ├── models.py        # DocumentMetadata + ChapterAnalysis + LLMReadingResult
│   │   │   ├── llm_client.py    # BaseLLMClient + OpenAICompatibleLLM
│   │   │   ├── unified_reader.py # UnifiedReader 三阶段阅读
│   │   │   └── __init__.py
│   │   └── kg/                  # Phase 4: 知识图谱
│   │       ├── models.py        # KGEntity + KGRelation + KGBuildResult
│   │       ├── lightrag_adapter.py # LightRAGAdapter + DummyKGBridge
│   │       ├── builder.py       # KGBuilder 编排器
│   │       └── __init__.py
│   ├── storage/                 # Phase 4: 向量化+图存储
│   │   ├── vector_store.py      # InMemory/Milvus/Qdrant向量存储
│   │   ├── graph_store.py       # InMemory/Neo4j图存储
│   │   ├── embedding.py         # BaseEmbeddingGenerator + OpenAI兼容 + Dummy
│   │   ├── chunker.py           # DocumentChunker 双层分块
│   │   └── __init__.py
│   ├── discovery/               # AI服务自动发现
│   │   ├── scanner.py           # 端口扫描器
│   │   ├── fingerprinter.py     # 服务指纹识别
│   │   ├── tester.py            # 能力测试器
│   │   ├── engine.py            # 发现引擎
│   │   ├── models.py            # 服务发现数据模型
│   │   └── __init__.py
│   ├── task/                    # 异步任务占位
│   └── orchestrator.py          # Phase 5: 全流程编排器
├── tests/                       # 测试套件
│   ├── postman/                 # Postman API测试集合
│   │   ├── doc-parser-api.postman_collection.json
│   │   └── doc-parser-api.postman_environment.json
│   └── ...
├── scripts/                     # 调试/验证脚本
├── output/                      # 测试结果输出
├── docs/                        # 文档
├── PDFTest/                     # 测试PDF和参考结果
├── ref/                         # 参考项目源码 (MinerU/Docling/PaddleOCR/RapidOCR)
├── pyproject.toml
├── start.bat                    # Windows一键启动脚本
├── start.sh                     # Linux/Mac一键启动脚本
├── doc_parser_impl_plan.json    # 实施计划JSON
└── doc_parser_tech_spec_v2.2.md # 技术方案
```

## 使用示例

### 创建Registry并解析文档

```python
from doc_parser.pipeline.registry import create_default_registry

registry = create_default_registry(
    mineru_url="http://10.0.40.153:18089",
    docling_url="http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling",
    docling_api_key="YOUR_API_KEY",
)

# auto模式 - 根据文件格式自动选择引擎
result = await registry.parse("document.pdf")

# 指定引擎
result = await registry.parse("document.pdf", engine="mineru-vlm")
```

### 直接使用Pipeline

```python
from doc_parser.pipeline.mineru import MinerUVLMPipeline
from doc_parser.pipeline.base import PipelineConfig

config = PipelineConfig(base_url="http://10.0.40.153:18089", timeout=300)
pipeline = MinerUVLMPipeline(config)
result = await pipeline.parse("document.pdf")

# 结果包含: content_list, markdown, images, tables, equations, metadata
```

### Docling自定义认证头

```python
from doc_parser.pipeline.docling_pipeline import DoclingPipeline
from doc_parser.pipeline.base import PipelineConfig

config = PipelineConfig(
    base_url="http://your-docling-url",
    api_key="YOUR_KEY",
    options={
        "auth_header": "X-Custom-Auth",   # 默认 "X-Api-Key"
        "auth_prefix": "",                  # 默认 ""（无前缀）
    }
)
pipeline = DoclingPipeline(config)
```

## Pipeline引擎对照

| 引擎 | engine_name | 支持格式 | 优先级 |
|------|------------|---------|--------|
| MinerU VLM | `mineru-vlm` | pdf | PDF首选 |
| MinerU Pipeline | `mineru-pipeline` | pdf | PDF备选 |
| Docling | `docling` | pdf,docx,pptx,html,md,xlsx | DOCX/PPTX首选 |

## REST API

### 启动服务

```bash
# 使用CLI命令
doc-parser-server --host 0.0.0.0 --port 8000

# 或直接运行
python -m doc_parser.api.server

# 或使用一键启动脚本
start.bat          # Windows
./start.sh         # Linux/Mac

# 带环境变量配置
DOCPARSER_MINERU_URL=http://10.0.40.153:18089 \
DOCPARSER_DOCLING_URL=http://your-docling-url \
DOCPARSER_DOCLING_API_KEY=your-key \
doc-parser-server
```

启动后访问 `http://localhost:8000/docs` 查看Swagger UI。

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DOCPARSER_MINERU_URL` | `http://10.0.40.153:18089` | MinerU服务地址 |
| `DOCPARSER_DOCLING_URL` | (空) | Docling服务地址 |
| `DOCPARSER_DOCLING_API_KEY` | (空) | Docling API密钥 |
| `DOCPARSER_EMBEDDING_URL` | (空) | Embedding模型服务地址(OpenAI兼容) |
| `DOCPARSER_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding模型名称 |
| `DOCPARSER_EMBEDDING_API_KEY` | (空) | Embedding API密钥 |
| `DOCPARSER_TASK_TTL` | `3600` | 异步任务过期时间(秒) |
| `DOCPARSER_MAX_TASKS` | `1000` | 最大并发任务数 |

### 服务注册

`app.py` 提供可配置的后端服务注册，未配置时自动降级为 Dummy/InMemory 实现：

```python
from doc_parser.api.app import create_app

app = create_app(
    kg_bridge=LightRAGAdapter(...),           # 默认: DummyKGBridge
    vector_store=MilvusVectorStore(...),       # 默认: InMemoryVectorStore
    embedding_generator=OpenAICompatibleEmbedding(...),  # 默认: DummyEmbeddingGenerator
)
```

### API端点

#### 文档处理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/health` | 健康检查，返回各引擎状态 |
| GET | `/v1/engines` | 列出可用引擎 |
| POST | `/v1/parse` | 同步解析文档 |
| POST | `/v1/parse/async` | 异步解析（返回task_id） |
| GET | `/v1/task/{task_id}` | 查询异步任务状态和结果 |
| GET | `/v1/tasks` | 列出所有任务 |
| POST | `/v1/outline` | 提取文档目录结构 |
| POST | `/v1/split` | 按章节拆分文档 |
| POST | `/v1/enhance` | 图片增强(OCR+VLM) |
| POST | `/v1/read` | LLM统一阅读(全流程) |
| POST | `/v1/documents/{id}/graph` | 构建知识图谱 |
| POST | `/v1/documents/{id}/graph/query` | KG查询 |
| POST | `/v1/documents/{id}/search` | 向量搜索 |
| POST | `/v1/process` | 全流程同步处理(7阶段) |
| POST | `/v1/process/async` | 全流程异步处理 |

#### 服务发现 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/discovery/scan` | 扫描网段发现AI服务 |
| GET | `/v1/discovery/scan/single` | 扫描单个IP:Port |
| GET | `/v1/discovery/status` | 获取发现状态统计 |
| GET | `/v1/discovery/services/by-type/{type}` | 按类型获取服务列表 |
| GET | `/v1/discovery/services/by-capability/{cap}` | 按能力获取服务列表 |
| GET | `/v1/discovery/services/best/{cap}` | 获取最佳服务 |
| DELETE | `/v1/discovery/services/{id}` | 移除指定服务 |
| DELETE | `/v1/discovery/services` | 清空所有服务 |

### 使用示例

```bash
# 健康检查
curl http://localhost:8000/v1/health

# 同步解析PDF（使用MinerU VLM引擎）
curl -X POST http://localhost:8000/v1/parse \
  -F "file=@document.pdf" \
  -F "engine=mineru-vlm"

# 异步解析
curl -X POST http://localhost:8000/v1/parse/async \
  -F "file=@document.pdf" \
  -F "engine=auto"

# 查询任务状态
curl http://localhost:8000/v1/task/abc123def456

# 列出可用引擎
curl http://localhost:8000/v1/engines

# 提取文档目录
curl -X POST http://localhost:8000/v1/outline \
  -F "file=@document.pdf" \
  -F "engine=mineru-vlm"

# 按章节拆分文档
curl -X POST http://localhost:8000/v1/split \
  -F "file=@document.pdf" \
  -F "engine=mineru-vlm"

# 图片增强（基础模式，不调用外部OCR/VLM）
curl -X POST http://localhost:8000/v1/enhance \
  -F "file=@document.pdf" \
  -F "engine=mineru-vlm" \
  -F "enable_ocr=false" \
  -F "enable_vlm=false"

# LLM统一阅读
curl -X POST http://localhost:8000/v1/read \
  -F "file=@document.pdf" \
  -F "engine=mineru-vlm" \
  -F "enable_llm=true"

# 构建知识图谱
curl -X POST http://localhost:8000/v1/documents/doc123/graph

# KG查询
curl -X POST http://localhost:8000/v1/documents/doc123/graph/query \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是神经网络？", "mode": "hybrid"}'

# 向量搜索
curl -X POST http://localhost:8000/v1/documents/doc123/search \
  -H "Content-Type: application/json" \
  -d '{"query": "neural network", "top_k": 5, "score_threshold": 0.5}'

# 全流程同步处理
curl -X POST http://localhost:8000/v1/process \
  -F "file=@document.pdf" \
  -F "engine=mineru" \
  -F "enable_enhance=true" \
  -F "enable_read=true" \
  -F "enable_kg=true" \
  -F "enable_vectorize=true"

# 全流程异步处理
curl -X POST http://localhost:8000/v1/process/async \
  -F "file=@document.pdf" \
  -F "engine=mineru"

# 查询异步任务状态
curl http://localhost:8000/v1/task/{task_id}
```

## Postman 测试

项目包含完整的 Postman API 测试集合，覆盖全部 23 个 API 端点：

1. 导入 `tests/postman/doc-parser-api.postman_collection.json` 到 Postman
2. 导入 `tests/postman/doc-parser-api.postman_environment.json` 作为环境
3. 选择 `doc-parser-local` 环境后运行集合

**集合结构 (11个文件夹 / 35个请求)**：
- Health & Info / Parse / Task Management / TOC & Split / Image Enhancement
- LLM Reading / Knowledge Graph / Vector Search / Full Pipeline
- Service Discovery / Error Cases

每个请求内含自动化的 Postman 测试脚本，响应中的 `document_id`/`task_id` 自动存入环境变量供后续请求使用。

## 测试覆盖

当前 **251 个测试** 全部通过，覆盖：
- Pipeline引擎: 42 tests (MinerU/Docling 数据模型、格式兼容)
- 注册中心: 7 tests (引擎选择/降级)
- 集成测试: 11 tests (真实数据transform)
- 章节模块: 28 tests (TOC/Splitter/OutlineNode)
- 图片增强: 27 tests (OCR/VLM/ImageEnhancer)
- 阅读模块: 23 tests (LLMClient/UnifiedReader/JSON解析)
- KG模块: 22 tests (KGBuilder/LightRAGAdapter/DummyKGBridge)
- 向量存储: 30 tests (InMemory/Milvus/Qdrant/Chunker/GraphStore)
- 编排器: 15 tests (配置/阶段/全流程/失败处理)
- API端点: 46+ tests (全部端点覆盖)

## 审计修复记录 (Phase 5.5)

Phase 5 完成后的全局代码审计发现并修复了 7 个系统性缺陷：

| # | 缺陷 | 影响 | 修复 |
|---|------|------|------|
| 1 | 缺失 Embedding 生成组件 | 向量化搜索无法生成query embedding | 新增 `storage/embedding.py` (BaseEmbeddingGenerator + OpenAI兼容 + Dummy) |
| 2 | API端点硬编码 Mock 后端 | 生产环境无法切换真实后端 | `app.py` 添加服务注册 (get_kg_bridge/get_vector_store/get_embedding_generator) |
| 3 | `/process/async` 丢弃结果 | 异步任务完成后无法获取结果 | `TaskInfo` 增加 `orch_result` 字段，任务完成时保存 |
| 4 | MinerU `resp.json()` 位置错误 | 异步HTTP响应未在 async with 内读取 | 移至 `async with` 块内 |
| 5 | `ChapterSplitter._assign_unowned()` 未实现 | 无归属元素丢失 | 实现按最近 page_start 分配逻辑 |
| 6 | Neo4j 伪异步 | 同步驱动在 async 函数中阻塞事件循环 | `asyncio.to_thread()` 包装同步调用 |
| 7 | Milvus schema 缺失字段 | 向量搜索无法过滤 page 范围 | 添加 page_start/page_end 到 collection schema |

## 技术方案

详见 [doc_parser_tech_spec_v2.2.md](doc_parser_tech_spec_v2.2.md) 和 [docs/](docs/) 目录。
