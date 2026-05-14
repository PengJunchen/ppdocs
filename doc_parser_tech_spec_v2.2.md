# 企业级文档解析处理模块技术方案 v2.2

## 文档信息
- **版本**: v2.2
- **日期**: 2026年5月
- **核心场景**: 目录驱动章节解析 + 图片OCR/VLM描述 + LLM统一阅读 + 知识图谱构建
- **核心决策**: 成熟方案组合为主，仅目录提取+图片增强做精细化处理

---

# 第一部分：核心问题分析

## Q: 成熟方案组合 vs 源码模型拆分？

### 1.1 源码探索结论

经过对MinerU和Docling源码的深入探索，关键发现如下：

| 能力 | MinerU | Docling | 结论 |
|------|--------|---------|------|
| **目录/TOC提取** | ❌ 无独立TOC提取；PDF中目录页被识别为`INDEX`块；标题层级通过`text_level`/`level`字段体现（需启用`title_aided` LLM辅助） | ❌ 无独立TOC提取；PDF中目录区域被识别为`DOCUMENT_INDEX`（按表格处理）；标题层级通过`SectionHeaderItem.level`体现 | **两者均无独立TOC提取能力** |
| **标题层级** | Pipeline默认2级（DOC_TITLE=1, PARAGRAPH_TITLE=2）；VLM需LLM辅助；DOCX有完整TOC解析 | DOCX/HTML/MD完整支持；PDF管道中`add_heading`不一定传入level | **PDF标题层级均不完美** |
| **全文档解析** | ✅ 成熟Pipeline，SOTA精度 | ✅ 成熟Pipeline，多格式支持 | **直接使用** |
| **图片OCR** | ✅ 内置PytorchPaddleOCR | ✅ 可集成RapidOCR/EasyOCR | **直接使用** |
| **结构化输出** | ✅ content_list.json含完整元素信息 | ✅ DoclingDocument含层级树 | **直接使用** |

### 1.2 核心决策

```
┌─────────────────────────────────────────────────────────────────────┐
│                        v2.2 技术决策                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ✅ 直接使用成熟Pipeline:  全文档解析、OCR、表格、公式              │
│  ✅ 直接使用成熟Pipeline:  版面分析、阅读顺序                       │
│                                                                     │
│  ⚠️ 需要自建模块:          目录提取（两者均无独立能力）              │
│  ⚠️ 需要自建模块:          章节级解析调度                            │
│  ⚠️ 需要自建模块:          图片VLM描述                               │
│  ⚠️ 需要自建模块:          LLM统一阅读                              │
│  ⚠️ 需要自建模块:          章节级实体抽取+KG构建                     │
│                                                                     │
│  结论: 成熟方案组合为主（约70%），自建精细化模块为辅（约30%）       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**为什么不全拆？**
- MinerU/Docling的Pipeline内部已做了大量优化（批量推理、错误恢复、阅读顺序）
- 标题层级识别两者都有局限（PDF场景），拆分出来也不会更好
- 图片OCR两者已内置，无需重复实现
- 唯一需要精细化的是：目录提取→章节拆分→图片VLM描述→LLM统一阅读

---

# 第二部分：v2.2 架构设计

## 2.1 处理流程总览

```
用户上传PDF
      │
      ▼
┌───────────────────────────────────────────────────────────────────┐
│  Stage 1: 全文档快速解析 (成熟Pipeline)                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ MinerU VLM / MinerU Pipeline / Docling                       │   │
│  │                                                              │   │
│  │ 输出:                                                        │   │
│  │ - content_list: 全部元素（含标题层级text_level）             │   │
│  │ - markdown: 完整文档                                         │   │
│  │ - 图片列表: 所有提取的图片                                   │   │
│  │ - 表格HTML: 所有表格结构                                     │   │
│  │ - 公式LaTeX: 所有公式                                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
      │
      ▼
┌───────────────────────────────────────────────────────────────────┐
│  Stage 2: 目录提取与章节构建 (自建模块)                            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ TOCExtractor                                                 │   │
│  │                                                              │   │
│  │ 策略A: 从content_list聚合标题 → 构建目录树                   │   │
│  │ 策略B: 识别INDEX块(目录页) → 解析目录条目                    │   │
│  │ 策略C: LLM辅助优化标题层级                                   │   │
│  │                                                              │   │
│  │ 输出: DocumentOutline (章节树)                               │   │
│  │ - chapters: [{id, title, level, page_start, page_end}]       │   │
│  │ - hierarchy: 嵌套的章节结构                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
      │
      ▼
┌───────────────────────────────────────────────────────────────────┐
│  Stage 3: 按章节拆分内容 (自建模块)                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ ChapterSplitter                                              │   │
│  │                                                              │   │
│  │ 根据目录树 + content_list的page_idx和reading_order            │   │
│  │ 将全文档元素分配到各章节                                     │   │
│  │                                                              │   │
│  │ 输出: chapters[0].elements, chapters[1].elements, ...        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
      │
      ▼
┌───────────────────────────────────────────────────────────────────┐
│  Stage 4: 图片增强处理 (成熟OCR + VLM描述)                        │
│  ┌──────────────────┐  ┌──────────────────────────┐               │
│  │ 图片OCR (成熟方案) │  │ VLM图片描述 (自建模块)    │              │
│  │ MinerU/PaddleOCR  │  │ QwenVL/GLM-4V/商汤      │              │
│  │ → 提取图片中文字   │  │ → 生成图片语义描述       │              │
│  └──────────────────┘  └──────────────────────────┘               │
│                                                                   │
│  输出: 每张图片的OCR结果 + VLM描述                               │
└───────────────────────────────────────────────────────────────────┘
      │
      ▼
┌───────────────────────────────────────────────────────────────────┐
│  Stage 5: LLM统一阅读 (自建模块)                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ UnifiedReader (LLM)                                          │   │
│  │                                                              │   │
│  │ 输入: 目录结构 + 各章节内容 + 图片描述                        │   │
│  │ 任务:                                                        │   │
│  │ - 理解章节间的逻辑关系                                       │   │
│  │ - 生成文档级metadata（主题、摘要、关键词）                    │   │
│  │ - 提取各章节的核心实体和关系                                  │   │
│  │ - 修正Pipeline可能的解析错误                                  │   │
│  │                                                              │   │
│  │ 输出: DocumentMetadata + ChapterEntities                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
      │
      ▼
┌───────────────────────────────────────────────────────────────────┐
│  Stage 6: 知识图谱构建 (LightRAG)                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ LightRAG                                                     │   │
│  │                                                              │   │
│  │ - 以章节为单位插入内容                                        │   │
│  │ - 附带metadata和实体信息                                     │   │
│  │ - 构建实体关系图                                              │   │
│  │ - 支持naive/local/global/hybrid查询                          │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
      │
      ▼
┌───────────────────────────────────────────────────────────────────┐
│  Stage 7: 向量化存储                                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ - 章节级chunk + 全文档chunk                                  │   │
│  │ - metadata标注（章节、页码、元素类型）                        │   │
│  │ - 向量化存储到Milvus/Qdrant                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

## 2.2 模块职责划分

```
doc_parser/
├── api/                          # REST API层
│   └── v1/
│       ├── documents.py              # 文档上传/解析/结果
│       ├── chapters.py               # 章节级操作
│       ├── graph.py                  # 知识图谱查询
│       └── search.py                 # 向量检索
│
├── pipeline/                     # 成熟Pipeline封装 (直接调用)
│   ├── base.py                       # Pipeline基类
│   ├── mineru_vlm.py                 # MinerU VLM引擎
│   ├── mineru_pipeline.py            # MinerU Pipeline引擎
│   ├── docling_pipeline.py           # Docling引擎
│   └── registry.py                   # Pipeline注册中心
│
├── core/                         # 自建精细化模块 (核心创新)
│   ├── toc/                          # 目录提取
│   │   ├── extractor.py              # TOC提取器（多策略）
│   │   ├── builder.py                # 目录树构建器
│   │   └── optimizer.py              # LLM辅助层级优化
│   ├── chapter/                      # 章节处理
│   │   ├── splitter.py               # 章节拆分器
│   │   ├── parser.py                 # 章节解析器
│   │   └── assembler.py              # 章节结果组装
│   ├── image/                        # 图片增强
│   │   ├── ocr_enhance.py            # 图片OCR增强
│   │   └── vlm_describe.py           # VLM图片描述
│   ├── reader/                       # LLM统一阅读
│   │   ├── unified_reader.py         # 统一阅读器
│   │   ├── metadata_extractor.py      # Metadata提取
│   │   └── entity_extractor.py       # 实体抽取
│   └── kg/                           # 知识图谱
│       ├── builder.py                # KG构建器
│       └── lightrag_adapter.py        # LightRAG适配器
│
├── task/                         # 异步任务
│   └── manager.py
│
├── storage/                      # 存储层
│   ├── document_store.py
│   ├── vector_store.py
│   └── graph_store.py
│
└── models/                       # 数据模型
    ├── document.py                   # 文档/章节/元素模型
    ├── outline.py                    # 目录树模型
    └── config.py
```

---

# 第三部分：核心模块设计

## 3.1 目录提取模块 (TOCExtractor)

### 3.1.1 数据模型

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class OutlineNode:
    """目录节点"""
    id: str                           # 唯一标识
    title: str                        # 章节标题
    level: int                        # 层级 (1=章, 2=节, 3=小节)
    page_start: int                   # 起始页码
    page_end: Optional[int] = None    # 结束页码
    children: List['OutlineNode'] = field(default_factory=list)
    parent_id: Optional[str] = None
    
    # 解析后的内容
    elements: List[dict] = field(default_factory=list)  # 该章节下的所有元素
    markdown: str = ""               # 该章节的Markdown内容
    images: List[dict] = field(default_factory=list)    # 该章节的图片
    tables: List[dict] = field(default_factory=list)    # 该章节的表格
    metadata: dict = field(default_factory=dict)         # 该章节的metadata

@dataclass
class DocumentOutline:
    """文档目录"""
    document_id: str
    title: str = ""
    nodes: List[OutlineNode] = field(default_factory=list)
    
    def get_all_chapters(self) -> List[OutlineNode]:
        """获取所有章节（扁平化）"""
        result = []
        def _flatten(nodes):
            for node in nodes:
                result.append(node)
                _flatten(node.children)
        _flatten(self.nodes)
        return result
    
    def get_chapter_by_page(self, page_num: int) -> Optional[OutlineNode]:
        """根据页码找到所属章节"""
        for chapter in self.get_all_chapters():
            if chapter.page_start <= page_num <= (chapter.page_end or page_num):
                return chapter
        return None
```

### 3.1.2 多策略目录提取

```python
from abc import ABC, abstractmethod
from typing import List, Optional

class BaseTOCStrategy(ABC):
    """目录提取策略基类"""
    
    @abstractmethod
    async def extract(self, parse_result: dict) -> DocumentOutline:
        """从解析结果中提取目录"""
        pass

class StrategyA_TitleAggregation(BaseTOCStrategy):
    """
    策略A: 从content_list聚合标题构建目录
    适用: 所有PDF文档
    原理: 遍历所有text_level > 0的元素，按页码和阅读顺序构建目录树
    """
    
    async def extract(self, parse_result: dict) -> DocumentOutline:
        outline = DocumentOutline(document_id=parse_result["document_id"])
        
        content_list = parse_result.get("content_list", [])
        title_items = []
        
        # 收集所有标题
        for item in content_list:
            text_level = item.get("text_level", 0)
            if text_level > 0:
                title_items.append({
                    "title": item.get("text", ""),
                    "level": text_level,
                    "page_idx": item.get("page_idx", 0),
                    "reading_order": item.get("reading_order", 0)
                })
        
        # 构建层级树
        outline.nodes = self._build_tree(title_items)
        return outline
    
    def _build_tree(self, items: List[dict]) -> List[OutlineNode]:
        """根据层级构建树结构"""
        if not items:
            return []
            
        root_nodes = []
        stack = []  # (level, node) 栈
        
        for item in items:
            node = OutlineNode(
                id=f"ch_{len(root_nodes) + len(stack)}",
                title=item["title"],
                level=item["level"],
                page_start=item["page_idx"]
            )
            
            # 找到父节点
            while stack and stack[-1][0] >= item["level"]:
                stack.pop()
            
            if stack:
                parent = stack[-1][1]
                parent.children.append(node)
                node.parent_id = parent.id
            else:
                root_nodes.append(node)
            
            stack.append((item["level"], node))
        
        # 填充page_end
        self._fill_page_end(root_nodes, items)
        return root_nodes
    
    def _fill_page_end(self, nodes, items):
        """填充每章的结束页码"""
        all_chapters = []
        def _collect(nodes):
            for n in nodes:
                all_chapters.append(n)
                _collect(n.children)
        _collect(nodes)
        
        for i, chapter in enumerate(all_chapters):
            if i + 1 < len(all_chapters):
                chapter.page_end = all_chapters[i + 1].page_start - 1
            else:
                chapter.page_end = None  # 最后一章到文档末尾


class StrategyB_IndexBlockParsing(BaseTOCStrategy):
    """
    策略B: 解析INDEX块（目录页）构建目录
    适用: PDF中有明确目录页的文档
    原理: 识别INDEX类型的块，解析其中的目录条目和页码
    """
    
    async def extract(self, parse_result: dict) -> DocumentOutline:
        outline = DocumentOutline(document_id=parse_result["document_id"])
        
        # 从middle_json中查找INDEX块
        pdf_info = parse_result.get("middle_json", {}).get("pdf_info", [])
        
        for page_info in pdf_info:
            for block in page_info.get("para_blocks", []):
                if block.get("type") == "index":
                    # 解析目录条目
                    entries = self._parse_index_block(block)
                    outline.nodes = self._build_from_entries(entries)
                    if outline.nodes:
                        return outline
        
        # Fallback: 使用策略A
        return await StrategyA_TitleAggregation().extract(parse_result)
    
    def _parse_index_block(self, block: dict) -> List[dict]:
        """解析INDEX块中的目录条目"""
        entries = []
        for line in block.get("lines", []):
            text = ""
            for span in line.get("spans", []):
                if span.get("type") == "text":
                    text += span.get("content", "")
            
            # 尝试提取页码（通常在行尾）
            page_num = self._extract_page_number(text)
            level = self._detect_level(text)
            
            entries.append({
                "title": text,
                "level": level,
                "page_num": page_num
            })
        
        return entries


class StrategyC_LLMEnhanced(BaseTOCStrategy):
    """
    策略C: LLM辅助目录提取与层级优化
    适用: 标题层级不清晰的文档
    原理: 将所有候选标题发送给LLM，请求返回结构化目录
    """
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def extract(self, parse_result: dict) -> DocumentOutline:
        # 先用策略A获取初始目录
        strategy_a = StrategyA_TitleAggregation()
        initial_outline = await strategy_a.extract(parse_result)
        
        # 收集所有标题文本
        titles = []
        for node in initial_outline.get_all_chapters():
            titles.append({
                "text": node.title,
                "page": node.page_start
            })
        
        # LLM优化
        optimized = await self._llm_optimize_hierarchy(titles)
        
        # 重建目录树
        outline = DocumentOutline(document_id=parse_result["document_id"])
        outline.nodes = self._build_from_llm_result(optimized)
        return outline
    
    async def _llm_optimize_hierarchy(self, titles: List[dict]) -> List[dict]:
        """调用LLM优化标题层级"""
        prompt = f"""请分析以下文档标题列表，为每个标题分配正确的层级编号。
层级规则：
- 1级：章（如"第1章"、"第一章"、最高级标题）
- 2级：节（如"1.1"、"第一节"）
- 3级：小节（如"1.1.1"）
- 层级必须连续，不能跳级

标题列表：
{json.dumps(titles, ensure_ascii=False, indent=2)}

请返回JSON格式：
[{{"title": "...", "level": 1, "page": 1}}, ...]"""
        
        response = await self.llm.chat(prompt)
        return json.loads(response)


class TOCExtractor:
    """目录提取器 - 组合多策略"""
    
    def __init__(self, llm_client=None):
        self.strategies = [
            StrategyB_IndexBlockParsing(),   # 优先: 解析目录页
            StrategyA_TitleAggregation(),     # 兜底: 聚合标题
        ]
        if llm_client:
            self.strategies.append(StrategyC_LLMEnhanced(llm_client))  # 增强: LLM优化
    
    async def extract(self, parse_result: dict) -> DocumentOutline:
        """提取目录（按策略优先级尝试）"""
        for strategy in self.strategies:
            outline = await strategy.extract(parse_result)
            if outline.nodes:
                return outline
        
        # 所有策略都失败，创建默认单章结构
        return DocumentOutline(
            document_id=parse_result["document_id"],
            nodes=[OutlineNode(id="ch_0", title="全文", level=1, page_start=0)]
        )
```

## 3.2 章节拆分模块 (ChapterSplitter)

```python
class ChapterSplitter:
    """章节拆分器 - 将全文档元素分配到各章节"""
    
    def __init__(self):
        pass
    
    async def split(self, parse_result: dict, outline: DocumentOutline) -> DocumentOutline:
        """
        根据目录树将content_list中的元素分配到各章节
        """
        content_list = parse_result.get("content_list", [])
        all_chapters = outline.get_all_chapters()
        
        if not all_chapters:
            # 无目录结构，整个文档作为一章
            outline.nodes[0].elements = content_list
            return outline
        
        # 为每个章节初始化元素列表
        for chapter in all_chapters:
            chapter.elements = []
            chapter.images = []
            chapter.tables = []
        
        # 遍历content_list，按页码分配到章节
        for item in content_list:
            page_idx = item.get("page_idx", 0)
            chapter = outline.get_chapter_by_page(page_idx)
            
            if chapter:
                chapter.elements.append(item)
                
                # 按类型分类
                item_type = item.get("type", "text")
                if item_type == "image":
                    chapter.images.append(item)
                elif item_type == "table":
                    chapter.tables.append(item)
        
        # 生成每章的Markdown
        for chapter in all_chapters:
            chapter.markdown = self._build_chapter_markdown(chapter)
        
        return outline
    
    def _build_chapter_markdown(self, chapter: OutlineNode) -> str:
        """构建章节Markdown"""
        md_parts = [f"{'#' * chapter.level} {chapter.title}\n"]
        
        for elem in chapter.elements:
            elem_type = elem.get("type", "text")
            
            if elem_type == "text":
                md_parts.append(elem.get("text", ""))
            elif elem_type == "title":
                level = elem.get("text_level", 2)
                md_parts.append(f"{'#' * level} {elem.get('text', '')}\n")
            elif elem_type == "table":
                md_parts.append(elem.get("html", ""))
            elif elem_type == "formula":
                md_parts.append(f"$$\n{elem.get('latex', '')}\n$$")
            elif elem_type == "image":
                md_parts.append(f"![图片]({elem.get('path', '')})")
        
        return "\n\n".join(md_parts)
```

## 3.3 图片增强模块 (ImageEnhancer)

```python
class ImageEnhancer:
    """图片增强处理器"""
    
    def __init__(self, ocr_engine=None, vlm_client=None):
        self.ocr = ocr_engine      # MinerU/PaddleOCR OCR
        self.vlm = vlm_client      # VLM图片描述
    
    async def process_chapter_images(self, chapter: OutlineNode) -> OutlineNode:
        """处理章节中的所有图片"""
        enhanced_images = []
        
        for img in chapter.images:
            img_path = img.get("path", "")
            if not img_path:
                continue
            
            # Step 1: OCR提取图片中的文字
            ocr_result = {}
            if self.ocr:
                ocr_result = await self._ocr_image(img_path)
            
            # Step 2: VLM生成图片语义描述
            vlm_description = ""
            if self.vlm:
                vlm_description = await self._describe_image(img_path)
            
            enhanced_images.append({
                "path": img_path,
                "ocr_text": ocr_result.get("text", ""),
                "ocr_confidence": ocr_result.get("confidence", 0),
                "vlm_description": vlm_description,
                "page": img.get("page_idx", 0),
                "bbox": img.get("bbox", [])
            })
        
        chapter.images = enhanced_images
        return chapter
    
    async def _ocr_image(self, image_path: str) -> dict:
        """使用OCR提取图片中的文字"""
        # 调用MinerU或PaddleOCR的OCR能力
        # 这里直接调用成熟方案
        pass
    
    async def _describe_image(self, image_path: str) -> str:
        """使用VLM生成图片描述"""
        prompt = """请详细描述这张图片的内容，包括：
1. 图片类型（图表、截图、照片、示意图等）
2. 主要内容和关键信息
3. 数据趋势或关键数值（如果有）
4. 与文档主题的关联"""
        
        response = await self.vlm.chat(
            messages=[{"role": "user", "content": prompt}],
            image=image_path
        )
        return response
```

## 3.4 LLM统一阅读模块 (UnifiedReader)

```python
class UnifiedReader:
    """LLM统一阅读器 - 理解文档全局结构"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def read_document(self, outline: DocumentOutline) -> dict:
        """
        LLM统一阅读整个文档
        输入: 目录结构 + 各章节摘要 + 图片描述
        输出: 文档级metadata + 各章节实体
        """
        # 1. 构建文档摘要（用于LLM上下文）
        doc_summary = self._build_document_summary(outline)
        
        # 2. LLM统一阅读
        prompt = f"""你是一个文档分析专家。请根据以下文档结构和内容，完成分析任务。

## 文档目录
{self._format_outline(outline)}

## 各章节内容摘要
{doc_summary}

## 任务
请完成以下分析，返回JSON格式：

1. **文档metadata**:
   - title: 文档标题
   - subject: 主题领域
   - summary: 200字以内文档摘要
   - keywords: 5-10个关键词
   - document_type: 文档类型（技术报告/学术论文/产品手册/财务报告/...）
   - language: 语言
   - quality_assessment: 内容质量评估（高/中/低）

2. **各章节分析** (对每个章节):
   - chapter_id: 章节ID
   - summary: 100字以内章节摘要
   - key_points: 3-5个关键要点
   - entities: 该章节涉及的核心实体列表
   - relations: 该章节中的实体关系

3. **跨章节关系**:
   - 章节间的逻辑关系（引用、依赖、对比等）
   - 全局核心实体和关系

请返回严格的JSON格式。"""
        
        response = await self.llm.chat(prompt)
        return json.loads(response)
    
    def _build_document_summary(self, outline: DocumentOutline) -> str:
        """构建文档摘要（截取每章前500字）"""
        summary_parts = []
        for chapter in outline.get_all_chapters():
            content_preview = chapter.markdown[:500] if chapter.markdown else "(无内容)"
            images_info = ""
            if chapter.images:
                for img in chapter.images[:3]:  # 最多3张图片描述
                    desc = img.get("vlm_description", "")[:100]
                    images_info += f"  - [图片]: {desc}\n"
            
            summary_parts.append(
                f"### {chapter.title} (第{chapter.page_start}-{chapter.page_end or '?'}页)\n"
                f"{content_preview}\n"
                f"{images_info}"
            )
        
        return "\n".join(summary_parts)
    
    def _format_outline(self, outline: DocumentOutline) -> str:
        """格式化目录"""
        lines = []
        for node in outline.nodes:
            self._format_node(node, 0, lines)
        return "\n".join(lines)
    
    def _format_node(self, node, depth, lines):
        indent = "  " * depth
        lines.append(f"{indent}- {node.title} (页{node.page_start}-{node.page_end or '?'})")
        for child in node.children:
            self._format_node(child, depth + 1, lines)
```

## 3.5 知识图谱构建模块 (KGBuilder)

```python
class KGBuilder:
    """知识图谱构建器 - 基于LightRAG"""
    
    def __init__(self, lightrag_client=None):
        self.lightrag = lightrag_client
    
    async def build(self, outline: DocumentOutline, llm_analysis: dict) -> dict:
        """
        构建知识图谱
        """
        # 1. 以章节为单位插入LightRAG
        for chapter in outline.get_all_chapters():
            # 构建章节内容（包含图片描述）
            chapter_content = chapter.markdown
            
            # 附加图片描述
            if chapter.images:
                chapter_content += "\n\n## 图片说明\n"
                for img in chapter.images:
                    if img.get("vlm_description"):
                        chapter_content += f"- {img['vlm_description']}\n"
            
            # 附加实体信息
            chapter_entities = llm_analysis.get("chapters", {}).get(chapter.id, {}).get("entities", [])
            if chapter_entities:
                chapter_content += f"\n\n## 核心实体\n{', '.join(chapter_entities)}"
            
            # 插入LightRAG
            await self.lightrag.ainsert(chapter_content)
        
        # 2. 插入跨章节关系
        cross_relations = llm_analysis.get("cross_chapter_relations", [])
        if cross_relations:
            relations_text = "\n".join([
                f"{r['source']} → {r['target']}: {r['type']} - {r['description']}"
                for r in cross_relations
            ])
            await self.lightrag.ainsert(relations_text)
        
        return {"status": "success", "chapters_indexed": len(outline.get_all_chapters())}
    
    async def query(self, question: str, mode: str = "hybrid") -> dict:
        """查询知识图谱"""
        answer = await self.lightrag.aquery(question, param=mode)
        return {"answer": answer, "mode": mode}
```

---

# 第四部分：完整处理流程实现

## 4.1 主流程编排

```python
class DocumentProcessingOrchestrator:
    """文档处理编排器 v2.2"""
    
    def __init__(
        self,
        pipeline_registry,      # 成熟Pipeline注册中心
        toc_extractor,          # 目录提取器
        image_enhancer,         # 图片增强器
        unified_reader,         # LLM统一阅读器
        kg_builder,             # 知识图谱构建器
        vector_store,           # 向量存储
        task_manager            # 任务管理器
    ):
        self.pipelines = pipeline_registry
        self.toc = toc_extractor
        self.images = image_enhancer
        self.reader = unified_reader
        self.kg = kg_builder
        self.vector = vector_store
        self.tasks = task_manager
    
    async def process(self, file_path: str, options: dict) -> dict:
        """
        完整处理流程
        """
        doc_id = generate_doc_id(file_path)
        
        # Stage 1: 全文档快速解析 (成熟Pipeline)
        engine = options.get("engine", "auto")
        pipeline = self.pipelines.get(engine)
        parse_result = await pipeline.parse(file_path)
        
        # Stage 2: 目录提取
        outline = await self.toc.extract(parse_result)
        
        # Stage 3: 按章节拆分
        outline = await ChapterSplitter().split(parse_result, outline)
        
        # Stage 4: 图片增强处理
        for chapter in outline.get_all_chapters():
            await self.images.process_chapter_images(chapter)
        
        # Stage 5: LLM统一阅读
        llm_analysis = await self.reader.read_document(outline)
        
        # Stage 6: 知识图谱构建
        kg_result = await self.kg.build(outline, llm_analysis)
        
        # Stage 7: 向量化存储
        chunks = await self.vector.index_document(doc_id, outline, llm_analysis)
        
        return {
            "document_id": doc_id,
            "outline": self._serialize_outline(outline),
            "metadata": llm_analysis.get("metadata", {}),
            "chapters": llm_analysis.get("chapters", {}),
            "kg_status": kg_result["status"],
            "chunks_count": len(chunks)
        }
```

## 4.2 REST API设计

### 4.2.1 文档解析（主入口）

```http
POST /api/v1/documents/parse
Content-Type: multipart/form-data

Parameters:
- file: PDF文件 (必填)
- engine: auto | mineru-vlm | mineru-pipeline | docling (默认: auto)
- options: {
    "enable_toc": true,
    "enable_image_vlm": true,
    "enable_llm_reader": true,
    "enable_kg": true,
    "vlm_model": "qwen-vl",
    "llm_model": "qwen-max"
  }

Response:
{
  "code": 0,
  "data": {
    "document_id": "doc-uuid",
    "task_id": "task-uuid",
    "status": "submitted"
  }
}
```

### 4.2.2 获取解析结果

```http
GET /api/v1/documents/{document_id}

Response:
{
  "code": 0,
  "data": {
    "document_id": "doc-uuid",
    "status": "completed",
    "metadata": {
      "title": "企业级RAG技术方案",
      "subject": "人工智能/文档解析",
      "summary": "本文档提出了...",
      "keywords": ["RAG", "文档解析", "知识图谱"],
      "document_type": "技术报告",
      "quality_assessment": "高"
    },
    "outline": {
      "title": "企业级RAG技术方案",
      "chapters": [
        {
          "id": "ch_0",
          "title": "第一章 绪论",
          "level": 1,
          "page_start": 1,
          "page_end": 5,
          "summary": "本章介绍了...",
          "key_points": ["背景", "目标", "技术路线"],
          "children": [
            {
              "id": "ch_1",
              "title": "1.1 研究背景",
              "level": 2,
              "page_start": 1,
              "page_end": 3
            }
          ]
        }
      ]
    }
  }
}
```

### 4.2.3 章节级操作

```http
# 获取章节详情
GET /api/v1/documents/{document_id}/chapters/{chapter_id}

Response:
{
  "code": 0,
  "data": {
    "id": "ch_0",
    "title": "第一章 绪论",
    "level": 1,
    "page_start": 1,
    "page_end": 5,
    "markdown": "# 第一章 绪论\n\n正文内容...",
    "elements_count": 15,
    "images": [
      {
        "path": "/storage/doc-xxx/img_001.png",
        "ocr_text": "图表中的文字...",
        "vlm_description": "这是一张展示系统架构的示意图...",
        "page": 2
      }
    ],
    "tables": [...],
    "entities": ["RAG", "文档解析", "知识图谱"],
    "relations": [...]
  }
}

# 获取章节Markdown
GET /api/v1/documents/{document_id}/chapters/{chapter_id}/markdown

# 获取章节图片
GET /api/v1/documents/{document_id}/chapters/{chapter_id}/images
```

### 4.2.4 知识图谱查询

```http
POST /api/v1/documents/{document_id}/graph/query

Request:
{
  "query": "文档解析使用了哪些技术方案？",
  "mode": "hybrid"
}

Response:
{
  "code": 0,
  "data": {
    "answer": "根据文档分析，使用了MinerU VLM、PaddleOCR和Docling三种技术方案...",
    "sources": [
      {"text": "MinerU VLM在OmniDocBench上达到95.69分...", "chapter": "第二章", "score": 0.92}
    ]
  }
}
```

### 4.2.5 向量检索

```http
POST /api/v1/documents/{document_id}/search

Request:
{
  "query": "表格识别的准确率",
  "top_k": 5,
  "chapter_filter": "第二章"  // 可选：限定章节范围
}
```

### 4.2.6 API完整路由

```
/api/v1/
├── documents/
│   ├── POST /parse                    # 解析文档（主入口）
│   ├── GET /{document_id}             # 获取文档状态和结果
│   ├── GET /{document_id}/content     # 获取完整内容
│   ├── GET /{document_id}/outline     # 获取目录结构
│   ├── GET /{document_id}/graph       # 获取知识图谱
│   └── POST /{document_id}/graph/query # 图谱查询
│
├── chapters/
│   ├── GET /{document_id}/chapters                   # 获取所有章节
│   ├── GET /{document_id}/chapters/{chapter_id}    # 获取章节详情
│   ├── GET /{document_id}/chapters/{chapter_id}/markdown  # 获取章节MD
│   └── GET /{document_id}/chapters/{chapter_id}/images    # 获取章节图片
│
├── search/
│   └── POST /{document_id}           # 向量检索
│
├── tasks/
│   ├── GET /{task_id}                # 任务状态
│   └── GET /{task_id}/result         # 任务结果
│
└── files/
    └── GET /{file_id}/download       # 文件下载
```

---

# 第五部分：技术对比与决策

## 5.1 成熟方案 vs 源码拆分

| 模块 | 成熟方案 | 源码拆分 | v2.2决策 |
|------|---------|---------|----------|
| 全文档解析 | MinerU VLM/Pipeline | 自建版面+OCR+表格+公式 | **成熟方案** |
| 目录提取 | 无独立能力 | 自建TOC提取 | **自建模块** |
| 章节拆分 | 无 | 自建ChapterSplitter | **自建模块** |
| 图片OCR | MinerU/PaddleOCR内置 | 自建OCR | **成熟方案** |
| 图片VLM描述 | 无 | 自建VLM描述 | **自建模块** |
| LLM统一阅读 | 无 | 自建UnifiedReader | **自建模块** |
| Metadata提取 | 无 | 自建 | **自建模块** |
| 实体/关系抽取 | 无 | LLM+NER | **自建模块** |
| 知识图谱 | 无 | LightRAG | **自建模块** |
| 向量化 | 无 | Embedding+VectorStore | **自建模块** |

## 5.2 工作量估算

| 模块类型 | 占比 | 工作量 | 复杂度 |
|---------|------|--------|--------|
| 成熟方案封装 | 30% | 1周 | 低 |
| 目录提取 | 15% | 1.5周 | 中 |
| 章节拆分 | 10% | 0.5周 | 低 |
| 图片增强 | 10% | 1周 | 中 |
| LLM统一阅读 | 15% | 1.5周 | 中 |
| KG+向量化 | 15% | 1.5周 | 中 |
| API+任务系统 | 5% | 1周 | 低 |
| **总计** | 100% | **8周** | — |

---

# 第六部分：实施计划

## Phase 1: 成熟Pipeline集成 (1周)

| 任务 | 说明 |
|------|------|
| MinerU VLM集成 | 封装为统一Pipeline接口 |
| MinerU Pipeline集成 | 封装为统一Pipeline接口 |
| Docling集成 | 封装为统一Pipeline接口 |
| Pipeline注册中心 | 统一管理+自动选择 |

## Phase 2: 目录+章节模块 (2周)

| 任务 | 说明 |
|------|------|
| TOCExtractor多策略实现 | 策略A/B/C |
| DocumentOutline数据模型 | 目录树结构 |
| ChapterSplitter实现 | 按页码分配元素 |
| 单元测试 | 各种PDF文档测试 |

## Phase 3: 图片增强+LLM阅读 (2.5周)

| 任务 | 说明 |
|------|------|
| ImageEnhancer实现 | OCR+VLM描述 |
| UnifiedReader实现 | LLM统一阅读 |
| MetadataExtractor | 文档级metadata |
| EntityExtractor | 章节级实体抽取 |

## Phase 4: KG+向量化 (1.5周)

| 任务 | 说明 |
|------|------|
| LightRAG集成 | 知识图谱构建 |
| VectorStore集成 | 向量化存储 |
| KG查询API | 图谱检索 |

## Phase 5: API+测试 (1周)

| 任务 | 说明 |
|------|------|
| REST API实现 | FastAPI路由 |
| 异步任务系统 | 任务管理 |
| 集成测试 | 端到端测试 |

---

*文档版本: v2.2 | 最后更新: 2026年5月*
