# Changelog

All notable changes to this project will be documented in this file.

## [0.7.0] - 2026-05-12

### Phase 5.5: 全局审计+系统性缺陷修复 - COMPLETED

#### Added
- **Embedding生成组件** (`doc_parser/storage/embedding.py`):
  - `BaseEmbeddingGenerator` 抽象基类(embed_texts/embed_query/health_check/dim)
  - `OpenAICompatibleEmbedding`: OpenAI兼容接口适配，支持所有OpenAI格式的Embedding服务
  - `DummyEmbeddingGenerator`: 测试用零向量实现，dim可配置
- **服务注册机制** (`doc_parser/api/app.py`):
  - `get_kg_bridge()`: 可配置KG后端，默认DummyKGBridge
  - `get_vector_store()`: 可配置向量存储后端，默认InMemoryVectorStore
  - `get_embedding_generator()`: 可配置Embedding后端，默认DummyEmbeddingGenerator
  - `set_globals()`: 统一设置全局服务实例(kg_bridge/vector_store/embedding_generator)
  - `create_app()` 新增 `kg_bridge`/`vector_store`/`embedding_generator` kwargs
- **Postman API测试集合** (`tests/postman/`):
  - `doc-parser-api.postman_collection.json`: 11个文件夹/35个请求，覆盖全部23个API端点
  - `doc-parser-api.postman_environment.json`: 环境变量定义(base_url/document_id/task_id等)
  - 内含自动化测试脚本，响应变量自动链式传递
- **一键启动脚本**:
  - `start.bat` (Windows): uv检查→创建.venv→安装依赖→启动服务
  - `start.sh` (Linux/Mac): 同上逻辑

#### Fixed
- **API端点硬编码Mock后端**: `routes.py`中KG/Search端点直接使用Mock实现，改为通过`app.py`服务注册获取可配置后端
- **`/process/async`结果丢失**: 异步全流程处理完成后结果未保存，`TaskInfo`新增`orch_result`字段，`_run_full_process()`完成时写入
- **MinerU `resp.json()`位置错误**: 在`async with httpx.AsyncClient()`块外调用`resp.json()`导致响应已关闭，移至块内
- **`ChapterSplitter._assign_unowned()`未实现**: 无明确章节归属的元素被丢弃，实现按最近`page_start`分配逻辑
- **Neo4j伪异步**: `Neo4jGraphStore`的同步driver方法直接在async函数中调用阻塞事件循环，改用`asyncio.to_thread()`包装
- **Milvus schema缺失字段**: `MilvusVectorStore`的collection schema缺少`page_start`/`page_end`字段，无法按页码范围过滤搜索

#### Changed
- `doc_parser/api/v1/routes.py`: Search端点使用`get_embedding_generator()`生成query embedding
- `doc_parser/api/v1/routes.py`: Process端点使用`get_kg_bridge()`/`get_vector_store()`/`get_embedding_generator()`
- `doc_parser/orchestrator.py`: `_stage_vectorize()`集成EmbeddingGenerator生成chunk embedding

## [0.6.0] - 2026-05-12

### Phase 5: API层+异步任务+端到端测试 - COMPLETED

#### Added
- **全流程编排器** (`doc_parser/orchestrator.py`):
  - `DocumentOrchestrator`: 串联7个处理阶段(parse→toc→split→enhance→read→kg→vectorize)
  - `OrchestratorConfig`: 各阶段开关(enable_enhance/enable_read/enable_kg/enable_vectorize) + 子配置
  - `_run_stage()`: 统一阶段执行+错误处理，失败阶段停止后续
  - `OrchestratorResult`: 全流程结果(document_id/stages/outline/reading_result/kg_result/vector_result/errors)
  - `PipelineStage` 枚举: PARSE/TOC/SPLIT/ENHANCE/READ/KG/VECTORIZE
  - `StageResult`: 每阶段执行状态(stage/success/duration/error)
- **API端点** (`doc_parser/api/v1/routes.py`):
  - `POST /v1/process` - 全流程同步处理(parse→toc→split→enhance→read→kg→vectorize)
  - `POST /v1/process/async` - 全流程异步任务(后台执行，返回task_id)
- **API模型** (`doc_parser/api/models.py`): `StageResultResponse`/`ProcessResponse`
- **编排器测试** (`tests/test_orchestrator.py`): 15个测试覆盖配置/阶段/全流程/失败处理
- **API端到端测试** (`tests/test_api.py`): 8个新测试覆盖Process/ProcessAsync/KGQuery/Search端点
- **包导出** (`doc_parser/__init__.py`): 导出编排器核心类

#### Changed
- `doc_parser/api/v1/routes.py`: 添加asyncio导入，添加全流程处理端点
- `doc_parser/api/models.py`: 添加ProcessResponse/StageResultResponse模型

## [0.5.0] - 2026-05-12

### Phase 4: 知识图谱+向量化存储 - COMPLETED

#### Added
- **KG数据模型** (`doc_parser/core/kg/models.py`): `KGQueryMode`(naive/local/global/hybrid)、`KGEntity`(name/entity_type/description/source_id)、`KGRelation`(source/target/relation_type/weight)、`KGInsertResult`(total_chunks/total_entities/total_relations)、`KGQueryResult`(query/mode/answer/source_chunks/source_entities/confidence)、`KGBuildResult`(total_chapters/total_chunks/insert_results/cross_chapter_relations/build_time)
- **LightRAG适配器** (`doc_parser/core/kg/lightrag_adapter.py`):
  - `BaseKGBridge` 抽象基类 + `LightRAGAdapter`(对接LightRAG库) + `DummyKGBridge`(测试用)
  - `LightRAGAdapter`: 懒加载LightRAG实例，支持自定义LLM/Embedding函数，insert/query/health_check
  - `DummyKGBridge`: 追踪inserted_items用于测试验证
- **KG构建器** (`doc_parser/core/kg/builder.py`):
  - `KGBuilder`: 编排章节内容插入KG + 跨章节关系构建
  - `build()`: DocumentOutline → 逐章节insert → CrossChapterRelation → KG关系内容insert
  - `_build_chapter_content()`: 标题+markdown+图片描述+metadata注释
  - `_build_chapter_metadata()`: 章节ID/标题/层级/页码/实体/图片表格计数
  - `KGBuilderConfig`: chunk_size/chunk_overlap/include_metadata/include_entities/max_content_length
- **向量存储** (`doc_parser/storage/vector_store.py`):
  - `BaseVectorStore` 抽象基类(add_chunks/search/delete_document/get_document_chunks/health_check)
  - `InMemoryVectorStore`: 内存实现，cosine相似度搜索，支持document_id/chapter_id过滤
  - `MilvusVectorStore`: Milvus向量数据库适配器，自动创建collection，支持过滤搜索
  - `QdrantVectorStore`: Qdrant向量数据库适配器，支持过滤搜索和文档级删除
  - 数据模型: `ChunkMetadata`(document_id/chapter_id/chapter_title/chunk_index/page_start/page_end/chunk_type/entities)、`VectorChunk`(text/metadata/embedding/id)、`SearchResult`(chunk_id/text/score/metadata)、`VectorStoreResult`
- **图存储** (`doc_parser/storage/graph_store.py`):
  - `BaseGraphStore` 抽象基类(add_node/add_edge/query/get_node/get_neighbors/delete_document/health_check)
  - `InMemoryGraphStore`: 内存实现，关键词搜索，邻居方向查询(incoming/outgoing/both)，document_id级删除
  - `Neo4jGraphStore`: Neo4j图数据库适配器，Cypher查询
  - 数据模型: `GraphNode`(id/label/properties)、`GraphEdge`(id/source/target/label/properties)、`GraphQueryResult`
- **文档分块器** (`doc_parser/storage/chunker.py`):
  - `DocumentChunker`: 双层分块(chapter级+document级)
  - `chunk_chapter()`: 章节markdown分块+图片描述附加
  - `chunk_document()`: 全文档分块+可选document级分块
  - `ChunkerConfig`: chunk_size/chunk_overlap/include_document_chunk/document_chunk_size
- **API端点** (`doc_parser/api/v1/routes.py`):
  - `POST /v1/documents/{document_id}/graph` - 构建知识图谱
  - `POST /v1/documents/{document_id}/graph/query` - KG查询(hybrid/local/global/naive模式)
  - `POST /v1/documents/{document_id}/search` - 向量搜索(top_k/chapter_id/score_threshold过滤)
- **API模型** (`doc_parser/api/models.py`): `KGRelationResponse`/`KGInsertResultResponse`/`KGBuildResponse`/`KGQueryRequest`/`KGQueryResponse`/`SearchRequest`/`SearchResultResponse`/`SearchResponse`
- **KG模块测试** (`tests/test_kg.py`): 22个测试覆盖KGModels/DummyKGBridge/LightRAGAdapter/KGBuilder
- **向量存储测试** (`tests/test_vector.py`): 30个测试覆盖VectorChunk/ChunkMetadata/InMemoryVectorStore/DocumentChunker/InMemoryGraphStore/SearchResult

## [0.4.0] - 2026-05-11

### Phase 3: 图片增强+LLM统一阅读 - COMPLETED

#### Added
- **图片数据模型** (`doc_parser/core/image/models.py`): `OCRResult`(text/confidence/word_count)、`VLMDescriptionResult`(description/image_type/key_info/model)、`EnhancedImage`(path/page/bbox/ocr/vlm_description/caption, 含has_ocr/has_vlm_description属性)
- **OCR增强模块** (`doc_parser/core/image/ocr_enhance.py`):
  - `BaseOCREngine` 抽象基类 + `MinerUOCREngine`(调用MinerU OCR API) + `DummyOCREngine`
  - `OCREnhancer`: 提取图片元素→OCR识别→与已有文本去重(`_deduplicate`)→返回EnhancedImage列表
  - 去重逻辑: 收集同页已存在的TEXT元素，OCR结果中与之重复的行被移除
- **VLM图片描述模块** (`doc_parser/core/image/vlm_describe.py`):
  - `BaseVLMClient` 抽象基类 + `OpenAICompatibleVLM`(兼容OpenAI API格式的VLM服务) + `DummyVLMClient`
  - `VLMDescriber`: 并发控制(Semaphore)→base64编码图片→VLM推理→JSON解析→合并OCR结果
  - OpenAI兼容: 支持QwenVL/GLM-4V等视觉语言模型的chat/completions接口
- **图片增强统一入口** (`doc_parser/core/image/enhancer.py`):
  - `ImageEnhancer`: 组合OCREnhancer+VLMDescriber，通过`ImageEnhancerConfig`控制启停
  - `enhance()`: PipelineResult → EnhancedImage列表(可选OCR+VLM)
  - `enhance_chapter_images()`: 将EnhancedImage按页码范围分配到章节
- **LLM客户端抽象** (`doc_parser/core/reader/llm_client.py`):
  - `BaseLLMClient` 抽象基类 + `OpenAICompatibleLLM`(兼容OpenAI API格式) + `DummyLLMClient`
- **LLM阅读数据模型** (`doc_parser/core/reader/models.py`): `DocumentMetadata`(title/subject/summary/keywords/document_type/language/quality_assessment)、`ChapterAnalysis`(summary/key_points/entities/relations)、`CrossChapterRelation`(source/target/relation_type/description)、`LLMReadingResult`
- **统一阅读器** (`doc_parser/core/reader/unified_reader.py`):
  - `UnifiedReader`: 三阶段LLM阅读流程
    1. 文档级metadata提取(目录+摘要→LLM→title/subject/keywords/document_type等)
    2. 章节级分析(章节内容+图片描述→LLM→summary/key_points/entities/relations)
    3. 跨章节关系(章节摘要→LLM→cross_chapter_relations)
  - `UnifiedReaderConfig`: 可独立控制三阶段启停，可配置content_preview_length
  - JSON解析容错: `_extract_json()` 支持从Markdown代码块和混杂文本中提取JSON
- **API端点** (`doc_parser/api/v1/routes.py`):
  - `POST /v1/enhance` - 图片增强(可选OCR+VLM，通过enable_ocr/enable_vlm参数控制)
  - `POST /v1/read` - LLM统一阅读(parse→TOC→split→read全流程)
- **API模型** (`doc_parser/api/models.py`): `OCRResultResponse`/`VLMDescriptionResponse`/`EnhancedImageResponse`/`ImageEnhanceResponse`/`DocumentMetadataResponse`/`ChapterAnalysisResponse`/`CrossChapterRelationResponse`/`LLMReadResponse`
- **图片模块测试** (`tests/test_image.py`): 27个测试覆盖OCRResult/VLMDescriptionResult/EnhancedImage/DummyOCREngine/OCREnhancer/DummyVLMClient/VLMDescriber/ImageEnhancer
- **阅读模块测试** (`tests/test_reader.py`): 23个测试覆盖DocumentMetadata/ChapterAnalysis/LLMReadingResult/DummyLLMClient/UnifiedReader/JSON解析
- **API测试** (`tests/test_api.py`): 新增6个测试覆盖/v1/enhance和/v1/read端点
- **端到端验证脚本** (`scripts/validate_phase3.py`): 使用PDFTest真实数据验证完整Phase 3流程

#### Validation Results
- Pipeline模式: 424 items → 63 chapters, 13 images, 100% 元素守恒率
- VLM模式: 452 items → 71 chapters, 14 images, 100% 元素守恒率

## [0.3.0] - 2026-05-11

### Phase 2: 目录提取+章节拆分 - COMPLETED

#### Added
- **数据模型** (`doc_parser/core/chapter/models.py`): `OutlineNode`（递归树结构，含id/title/level/page_start/page_end/children/element_indices/markdown/类型计数）、`DocumentOutline`（文档大纲，含`total_chapters`计算属性、`get_all_chapters()`/`get_chapter_by_page()`/`get_leaf_chapters()`辅助方法）
- **TOC提取器** (`doc_parser/core/chapter/toc.py`):
  - `BaseTOCStrategy` 抽象基类
  - `StrategyA_TitleAggregation`: 从content_list中text_level>0的元素聚合标题，栈式构建层级树
  - `StrategyB_IndexBlockParsing`: 优先识别block_type=="index"的目录块，回退到StrategyA
  - `StrategyC_LLMEnhanced`: LLM辅助层级优化（占位符，Phase 3完善）
  - `TOCExtractor`: 多策略编排器，按 [StrategyB, StrategyA, StrategyC(可选)] 顺序执行
- **章节拆分器** (`doc_parser/core/chapter/splitter.py`):
  - `ChapterSplitter.split()`: 将PipelineResult+DocumentOutline拆分为章节
  - 元素分配: 标题项按title+page匹配后深入到最深叶子节点，非标题项按页码范围或最近page_start分配
  - 类型计数: 自动统计每个章节的image_count/table_count/equation_count
  - Markdown生成: 每个章节独立生成markdown内容
- **API端点** (`doc_parser/api/v1/routes.py`):
  - `POST /v1/outline` - 提取文档目录结构
  - `POST /v1/split` - 按章节拆分文档（含元素守恒率统计）
- **API模型** (`doc_parser/api/models.py`): `OutlineNodeResponse`（递归）、`OutlineResponse`、`SplitResponse`
- **章节测试** (`tests/test_chapter.py`): 28个测试覆盖OutlineNode/DocumentOutline/StrategyA/StrategyB/TOCExtractor/ChapterSplitter
- **API测试** (`tests/test_api.py`): 新增8个测试覆盖/v1/outline和/v1/split端点
- **端到端验证脚本** (`scripts/validate_phase2.py`): 使用PDFTest真实数据验证Pipeline和VLM两种模式

#### Fixed
- **DocumentOutline.total_chapters bug**: 从`model_validator`改为`@computed_field @property`，修复nodes赋值后total_chapters不更新的问题

#### Validation Results
- Pipeline模式: 424 items → 63 chapters, 100% 元素守恒率
- VLM模式: 452 items → 71 chapters, 100% 元素守恒率

## [0.2.0] - 2026-05-11

### FastAPI RESTful API层

#### Added
- **FastAPI应用工厂** (`doc_parser/api/app.py`): `create_app()` 支持环境变量和kwargs配置，CORS中间件，请求计时中间件，全局异常处理
- **API数据模型** (`doc_parser/api/models.py`): `HealthResponse`, `EngineInfo`, `ParseResultResponse`, `TaskResponse`, `TaskStatus`, `ErrorResponse` 等Pydantic v2响应模型
- **异步任务管理器** (`doc_parser/api/task_manager.py`): `TaskManager` 支持异步提交/轮询/过期清理，`TaskInfo` 状态跟踪
- **API路由** (`doc_parser/api/v1/routes.py`):
  - `GET /v1/health` - 健康检查，返回各引擎状态
  - `GET /v1/engines` - 列出所有可用引擎及支持格式
  - `POST /v1/parse` - 同步解析文档（上传文件+指定引擎）
  - `POST /v1/parse/async` - 异步解析文档（返回task_id）
  - `GET /v1/task/{task_id}` - 查询异步任务状态和结果
  - `GET /v1/tasks` - 列出所有任务
- **服务器入口** (`doc_parser/api/server.py`): CLI入口点 `doc-parser-server`
- **API测试** (`tests/test_api.py`): 15个测试覆盖health/engines/parse/async-parse/task全部端点
- **环境变量配置**: `DOCPARSER_MINERU_URL`, `DOCPARSER_DOCLING_URL`, `DOCPARSER_DOCLING_API_KEY`, `DOCPARSER_TASK_TTL`, `DOCPARSER_MAX_TASKS`
- **python-multipart依赖**: FastAPI文件上传所需

#### Fixed
- PipelineRegistry属性名 `_pipelines` → `_engines` (routes.py中引用修正)

## [0.1.1] - 2026-05-11

### Phase 1: 修复与增强

#### Changed
- **DoclingPipeline默认认证头**: 从 `Authorization: Bearer` 改为 `X-Api-Key`（与Docling官方SDK一致）
- **DoclingPipeline文件上传字段**: 从 `file` 改为 `files`（与Docling官方SDK一致）
- **DoclingPipeline端点路径**: 状态轮询改为 `/v1/status/poll/{task_id}`，结果获取改为 `/v1/result/{task_id}`（与Docling官方SDK一致）
- **DoclingPipeline任务ID字段**: 优先使用 `task_id`（官方SDK格式），兼容 `job_id` 和 `id`
- **DoclingPipeline状态字段**: 优先使用 `task_status`（官方SDK格式），兼容 `status`
- **DoclingPipeline错误处理**: 增加 Kong API Gateway 特定错误提示（401提取www-authenticate头，404提示路由未注册）
- **MinerUVLMPipeline**: VLM模式仅返回md_content无content_list时，自动从markdown生成基础content_list（含标题层级提取）
- **MinerUVLMPipeline**: 增加 409 CUDA OOM 错误处理（与MinerUPipeline一致）

#### Discovered
- **Docling API网关确认使用Kong API Gateway** (`www-authenticate: Key realm="kong"`)
- **Kong网关仅注册了 `/health` 路由**，`/v1/convert/file/async` 等端点返回404 "no Route matched"
- **API Key认证问题**：`Db3S72tVSn2YeSw` 在所有header/query格式下均被Kong key-auth插件拒绝，可能原因：Key未在Kong consumer中注册、或使用了自定义key_names配置

#### Added
- **在线API测试脚本**: `scripts/test_online_apis.py` - 端到端在线验证
- **Kong认证探测脚本**: `scripts/test_kong_auth.py`, `scripts/test_kong_extended.py`
- **项目规则文件**: `.trae/rules/project_rules.md` - uv虚拟环境规范+开发踩坑提点

## [0.1.0] - 2026-05-09

### Phase 1: 成熟Pipeline集成 - COMPLETED

#### Added
- **Pipeline基类** (`doc_parser/pipeline/base.py`): 定义 `BasePipeline` 抽象基类、`PipelineResult`/`ContentItem`/`PipelineConfig` 等Pydantic v2数据模型、`PipelineError`异常类体系(EngineNotFound/ParseFailed/ParseTimeout/FormatNotSupported)
- **MinerU Pipeline引擎** (`doc_parser/pipeline/mineru.py`): 封装MinerU `/file_parse` API为 `MinerUPipeline` 和 `MinerUVLMPipeline`(VLM模式自动添加 `parse_method=vlm` 参数)
- **Docling引擎** (`doc_parser/pipeline/docling_pipeline.py`): 封装Docling `/v1/convert/file/async` 异步转换API，支持job polling获取结果，可配置auth_header/auth_prefix适配不同API网关认证方式
- **Pipeline注册中心** (`doc_parser/pipeline/registry.py`): `PipelineRegistry` 支持注册/查找/auto_select，按文件格式智能选择引擎(PDF→mineru-vlm, DOCX/PPTX→docling)，支持fallback降级链
- **单元测试** (`tests/test_pipeline_base.py`): 42个测试覆盖数据模型序列化、MinerU content_list解析(含string/list-of-strings/list-of-dicts三种格式)、格式验证、错误类体系
- **集成测试** (`tests/test_integration.py`): 11个测试使用真实MinerU JSON结果验证完整transform流程、schema一致性、内容类型覆盖、Registry生产配置
- **注册中心测试** (`tests/test_registry.py`): 7个测试覆盖注册/查找/解析/auto_select/docling转换逻辑

#### Fixed
- MinerU API字段名应为 `files` 而非 `file`
- MinerU `content_list` 实际为JSON字符串，需 `json.loads()` 解析（支持string/list-of-strings/list-of-dicts三种格式）
- MinerU API 409 CUDA OOM 错误提取服务器端错误信息
- Docling API使用 `/v1/convert/file/async` 异步job模式，需polling获取结果
- Docling `_poll_result` 在 `async with` 块外调用已关闭client的bug
- pyproject.toml build-backend 从错误的 `setuptools.backends._legacy:_Backend` 修正为 `setuptools.build_meta`

#### Known Issues
- **Docling API网关认证**: 当前提供的API Key (`Db3S72tVSn2YeSw`) 在所有header/query格式下均返回 `401 No API key found in request`，需与API网关提供方确认认证方式。已实现可配置 `auth_header` 和 `auth_prefix` 作为workaround
- **MinerU服务器CUDA OOM**: 对大PDF文档可能返回409，属于服务器资源问题而非代码问题
