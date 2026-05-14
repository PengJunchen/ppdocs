from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from doc_parser.core.chapter import ChapterSplitter, DocumentOutline, TOCExtractor
from doc_parser.core.image import ImageEnhancer, ImageEnhancerConfig
from doc_parser.core.kg import KGBuilder, KGBuilderConfig, KGBuildResult
from doc_parser.core.kg.lightrag_adapter import BaseKGBridge, LLMKGBridge
from doc_parser.core.reader import UnifiedReader, UnifiedReaderConfig
from doc_parser.core.reader.models import LLMReadingResult
from doc_parser.pipeline.base import PipelineResult
from doc_parser.storage.chunker import ChunkerConfig, DocumentChunker
from doc_parser.storage.embedding import (
    BaseEmbeddingGenerator,
    DummyEmbeddingGenerator,
)
from doc_parser.storage.vector_store import (
    BaseVectorStore,
    InMemoryVectorStore,
    VectorChunk,
    VectorStoreResult,
)

logger = logging.getLogger(__name__)


class PipelineStage(str, Enum):
    PARSE = "parse"
    TOC = "toc"
    SPLIT = "split"
    ENHANCE = "enhance"
    READ = "read"
    KG = "kg"
    VECTORIZE = "vectorize"


class OrchestratorConfig(BaseModel):
    enable_enhance: bool = True
    enable_read: bool = True
    enable_kg: bool = False
    enable_vectorize: bool = False
    enhance_config: dict[str, Any] = Field(default_factory=lambda: {
        "enable_ocr": True, "enable_vlm": False,
    })
    read_config: dict[str, Any] = Field(default_factory=dict)
    kg_config: dict[str, Any] = Field(default_factory=dict)
    chunker_config: dict[str, Any] = Field(default_factory=lambda: {
        "chunk_size": 1200, "chunk_overlap": 200,
    })


class StageResult(BaseModel):
    stage: str = ""
    success: bool = False
    duration: float = 0.0
    error: str = ""


class OrchestratorResult(BaseModel):
    document_id: str = ""
    total_duration: float = 0.0
    stages: list[StageResult] = Field(default_factory=list)
    outline: Optional[dict[str, Any]] = None
    enhance_result: Optional[dict[str, Any]] = None
    reading_result: Optional[dict[str, Any]] = None
    kg_result: Optional[dict[str, Any]] = None
    vector_result: Optional[dict[str, Any]] = None
    errors: list[str] = Field(default_factory=list)


class DocumentOrchestrator:
    def __init__(
        self,
        kg_bridge: Optional[BaseKGBridge] = None,
        vector_store: Optional[BaseVectorStore] = None,
        embedding_generator: Optional[BaseEmbeddingGenerator] = None,
        llm_client: Optional[Any] = None,
        config: Optional[OrchestratorConfig] = None,
    ):
        self._kg_bridge = kg_bridge or LLMKGBridge(llm_client=llm_client)
        self._vector_store = vector_store or InMemoryVectorStore()
        self._embedding_generator = embedding_generator or DummyEmbeddingGenerator()
        self._llm_client = llm_client
        self._config = config or OrchestratorConfig()

    async def process(
        self,
        pipeline_result: PipelineResult,
    ) -> OrchestratorResult:
        start = time.time()
        result = OrchestratorResult(document_id=pipeline_result.document_id)
        outline: Optional[DocumentOutline] = None
        reading_result: Optional[LLMReadingResult] = None
        enhance_output: Optional[list] = None

        logger.info(
            "[Orchestrator] Start processing document_id=%s, config: enhance=%s read=%s kg=%s vectorize=%s",
            pipeline_result.document_id,
            self._config.enable_enhance,
            self._config.enable_read,
            self._config.enable_kg,
            self._config.enable_vectorize,
        )

        outline = await self._run_stage(
            result, PipelineStage.TOC, self._stage_toc, pipeline_result
        )
        if outline is None:
            logger.error("[Orchestrator] TOC stage failed, aborting pipeline")
            result.total_duration = time.time() - start
            return result

        outline = await self._run_stage(
            result, PipelineStage.SPLIT, self._stage_split, pipeline_result, outline
        )
        if outline is None:
            logger.error("[Orchestrator] SPLIT stage failed, aborting pipeline")
            result.total_duration = time.time() - start
            return result

        logger.info(
            "[Orchestrator] Outline built: %d chapters, %d leaf chapters",
            outline.total_chapters,
            len(outline.get_leaf_chapters()),
        )

        if self._config.enable_enhance:
            enhance_output = await self._run_stage(
                result, PipelineStage.ENHANCE, self._stage_enhance,
                pipeline_result, outline,
            )

        if self._config.enable_read:
            reading_result = await self._run_stage(
                result, PipelineStage.READ, self._stage_read, outline
            )

        if self._config.enable_kg:
            kg_result = await self._run_stage(
                result, PipelineStage.KG, self._stage_kg,
                outline, reading_result,
            )
            if kg_result:
                result.kg_result = kg_result.model_dump()
                logger.info(
                    "[Orchestrator] KG built: %d chunks, %d entities, %d relations",
                    kg_result.total_chunks,
                    sum(ir.total_entities for ir in kg_result.insert_results),
                    sum(ir.total_relations for ir in kg_result.insert_results),
                )

        if self._config.enable_vectorize:
            vec_result = await self._run_stage(
                result, PipelineStage.VECTORIZE, self._stage_vectorize, outline
            )
            if vec_result:
                result.vector_result = vec_result.model_dump()
                logger.info(
                    "[Orchestrator] Vectorized: %d chunks stored",
                    vec_result.total_chunks,
                )

        if outline:
            result.outline = _outline_to_dict(outline)

        if enhance_output is not None:
            result.enhance_result = _enhance_to_dict(enhance_output)

        if reading_result:
            result.reading_result = _reading_to_dict(reading_result)

        result.total_duration = time.time() - start
        logger.info(
            "[Orchestrator] Completed document_id=%s in %.3fs, stages=%d, errors=%d",
            result.document_id,
            result.total_duration,
            len(result.stages),
            len(result.errors),
        )
        return result

    async def _run_stage(
        self,
        result: OrchestratorResult,
        stage: PipelineStage,
        func: Any,
        *args: Any,
    ) -> Any:
        stage_start = time.time()
        logger.info("[Orchestrator] Stage %s started", stage.value)
        try:
            output = await func(*args)
            duration = time.time() - stage_start
            result.stages.append(StageResult(
                stage=stage.value,
                success=True,
                duration=duration,
            ))
            logger.info("[Orchestrator] Stage %s completed in %.3fs", stage.value, duration)
            return output
        except Exception as exc:
            duration = time.time() - stage_start
            logger.exception("[Orchestrator] Stage %s failed after %.3fs: %s", stage.value, duration, exc)
            result.stages.append(StageResult(
                stage=stage.value,
                success=False,
                duration=duration,
                error=str(exc),
            ))
            result.errors.append(f"{stage.value}: {exc}")
            return None

    async def _stage_toc(
        self, pipeline_result: PipelineResult
    ) -> DocumentOutline:
        extractor = TOCExtractor()
        return await extractor.extract(pipeline_result)

    async def _stage_split(
        self, pipeline_result: PipelineResult, outline: DocumentOutline
    ) -> DocumentOutline:
        splitter = ChapterSplitter()
        return await splitter.split(pipeline_result, outline)

    async def _stage_enhance(
        self, pipeline_result: PipelineResult, outline: DocumentOutline
    ) -> list:
        from doc_parser.config import get_section

        enhance_cfg = self._config.enhance_config
        ocr_engine = None
        vlm_client = None

        if enhance_cfg.get("enable_ocr", False):
            from doc_parser.core.image.ocr_enhance import MinerUOCREngine
            ocr_cfg = get_section("ocr", {})
            ocr_url = ocr_cfg.get("api_url", "")
            if ocr_url:
                ocr_engine = MinerUOCREngine(base_url=ocr_url)
                logger.info("[Enhance] Using MinerUOCREngine: %s", ocr_url)

        if enhance_cfg.get("enable_vlm", False):
            from doc_parser.core.image.vlm_describe import VLMDescriber
            vlm_cfg = get_section("vlm", {})
            vlm_url = vlm_cfg.get("base_url", "")
            if vlm_url:
                from doc_parser.core.reader.llm_client import OpenAICompatibleLLM
                vlm_llm = OpenAICompatibleLLM(
                    base_url=vlm_url,
                    api_key=vlm_cfg.get("api_key", ""),
                    model=vlm_cfg.get("model", "qwen-vl-plus"),
                )
                vlm_client = VLMDescriber(llm_client=vlm_llm, max_concurrency=vlm_cfg.get("max_concurrency", 4))
                logger.info("[Enhance] Using VLMDescriber: %s", vlm_url)

        cfg = ImageEnhancerConfig(**enhance_cfg)
        enhancer = ImageEnhancer(config=cfg, ocr_engine=ocr_engine, vlm_client=vlm_client)
        enhanced = await enhancer.enhance(pipeline_result)
        chapters = outline.get_all_chapters()
        for chapter in chapters:
            await enhancer.enhance_chapter_images(chapter, pipeline_result, enhanced)
        return enhanced

    async def _stage_read(
        self, outline: DocumentOutline
    ) -> LLMReadingResult:
        cfg = UnifiedReaderConfig(**self._config.read_config)
        reader = UnifiedReader(llm_client=self._llm_client, config=cfg)
        return await reader.read_document(outline)

    async def _stage_kg(
        self,
        outline: DocumentOutline,
        reading_result: Optional[LLMReadingResult] = None,
    ) -> KGBuildResult:
        cfg = KGBuilderConfig(**self._config.kg_config)
        builder = KGBuilder(kg_bridge=self._kg_bridge, config=cfg)
        cross_relations = None
        if reading_result:
            cross_relations = reading_result.cross_chapter_relations
        return await builder.build(outline, cross_relations=cross_relations)

    async def _stage_vectorize(
        self, outline: DocumentOutline
    ) -> VectorStoreResult:
        cfg = ChunkerConfig(**self._config.chunker_config)
        chunker = DocumentChunker(config=cfg)
        chunks = chunker.chunk_document(outline)

        texts = [c.text for c in chunks]
        embeddings = await self._embedding_generator.embed_texts(texts)
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

        return await self._vector_store.add_chunks(
            chunks, document_id=outline.document_id
        )


def _outline_node_to_dict(node: OutlineNode) -> dict[str, Any]:
    children = [_outline_node_to_dict(c) for c in node.children]
    return {
        "id": node.id,
        "title": node.title,
        "level": node.level,
        "page_start": node.page_start,
        "page_end": node.page_end,
        "parent_id": node.parent_id,
        "children": children,
        "element_count": len(node.element_indices),
        "markdown": node.markdown,
        "image_count": node.image_count,
        "table_count": node.table_count,
        "equation_count": node.equation_count,
        "metadata": node.metadata,
    }


def _outline_to_dict(outline: DocumentOutline) -> dict[str, Any]:
    return {
        "document_id": outline.document_id,
        "title": outline.title,
        "total_chapters": outline.total_chapters,
        "nodes": [_outline_node_to_dict(n) for n in outline.nodes],
    }


def _enhance_to_dict(enhanced: list) -> dict[str, Any]:
    images = []
    for ei in enhanced:
        img: dict[str, Any] = {
            "path": ei.path,
            "page": ei.page,
            "bbox": ei.bbox,
            "image_caption": ei.image_caption,
        }
        if ei.ocr:
            img["ocr"] = {
                "text": ei.ocr.text,
                "confidence": ei.ocr.confidence,
                "word_count": ei.ocr.word_count,
            }
        if ei.vlm_description:
            img["vlm_description"] = {
                "description": ei.vlm_description.description,
                "image_type": ei.vlm_description.image_type,
                "key_info": ei.vlm_description.key_info,
                "model": ei.vlm_description.model,
            }
        images.append(img)
    return {
        "total_images": len(images),
        "images": images,
    }


def _reading_to_dict(reading: LLMReadingResult) -> dict[str, Any]:
    meta = reading.metadata
    return {
        "metadata": {
            "title": meta.title,
            "subject": meta.subject,
            "summary": meta.summary,
            "keywords": meta.keywords,
            "document_type": meta.document_type,
            "language": meta.language,
            "quality_assessment": meta.quality_assessment,
        },
        "chapters": [
            {
                "chapter_id": ca.chapter_id,
                "summary": ca.summary,
                "key_points": ca.key_points,
                "entities": ca.entities,
                "relations": ca.relations,
            }
            for ca in reading.chapters
        ],
        "cross_chapter_relations": [
            {
                "source": r.source,
                "target": r.target,
                "relation_type": r.relation_type,
                "description": r.description,
            }
            for r in reading.cross_chapter_relations
        ],
        "model": reading.model,
    }
