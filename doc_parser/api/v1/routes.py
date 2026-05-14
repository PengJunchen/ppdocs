from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from doc_parser.api.models import (
    ContentItemResponse,
    EngineInfo,
    ErrorResponse,
    HealthResponse,
    ImageInfoResponse,
    ImageEnhanceResponse,
    EnhancedImageResponse,
    OCRResultResponse,
    VLMDescriptionResponse,
    OutlineNodeResponse,
    OutlineResponse,
    ParseResultResponse,
    ProcessResponse,
    SplitResponse,
    StageResultResponse,
    TableInfoResponse,
    EquationInfoResponse,
    TaskResponse,
    TaskStatus,
    LLMReadResponse,
    DocumentMetadataResponse,
    ChapterAnalysisResponse,
    CrossChapterRelationResponse,
    KGBuildResponse,
    KGInsertResultResponse,
    KGRelationResponse,
    KGQueryRequest,
    KGQueryResponse,
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
)
from doc_parser.pipeline.base import PipelineError, FormatNotSupported
from doc_parser.pipeline.registry import PipelineRegistry

# 导入发现路由 (独立模块)
from probe_discovery.api import router as discovery_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["v1"])

# 包含发现路由
router.include_router(discovery_router)


def _pipeline_result_to_response(result: Any, engine_name: str) -> ParseResultResponse:
    content_items = []
    for item in result.content_list:
        ci = ContentItemResponse(
            type=item.type.value if hasattr(item.type, "value") else str(item.type),
            text=item.text,
            text_level=item.text_level,
            page_idx=item.page_idx,
            bbox=item.bbox if item.bbox else [],
            reading_order=item.reading_order,
            img_path=item.img_path,
            table_body=item.table_body if item.table_body else "",
            table_caption=item.table_caption if item.table_caption else [],
            table_footnote=item.table_footnote if item.table_footnote else [],
            image_caption=item.image_caption if item.image_caption else [],
            text_format=item.text_format,
            sub_type=item.sub_type,
            extra=item.extra if item.extra else {},
        )
        content_items.append(ci)

    images = []
    for img in result.images:
        images.append(ImageInfoResponse(
            filename=img.filename if hasattr(img, "filename") else "",
            source_path=img.source_path if hasattr(img, "source_path") else "",
        ))

    tables = []
    for tbl in result.tables:
        tables.append(TableInfoResponse(
            html=tbl.html if hasattr(tbl, "html") else "",
            caption=tbl.caption if hasattr(tbl, "caption") and tbl.caption else [],
            footnote=tbl.footnote if hasattr(tbl, "footnote") and tbl.footnote else [],
            page_idx=tbl.page_idx if hasattr(tbl, "page_idx") else 0,
        ))

    equations = []
    for eq in result.equations:
        equations.append(EquationInfoResponse(
            latex=eq.latex if hasattr(eq, "latex") else "",
            text_format=eq.text_format if hasattr(eq, "text_format") else "latex",
            page_idx=eq.page_idx if hasattr(eq, "page_idx") else 0,
        ))

    return ParseResultResponse(
        document_id=result.document_id,
        engine=engine_name,
        content_list=content_items,
        markdown=result.markdown,
        images=images,
        tables=tables,
        equations=equations,
        metadata=result.metadata if result.metadata else {},
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    registry: PipelineRegistry = _get_registry()
    engines = []
    for name, pipeline in registry._engines.items():
        try:
            healthy = await pipeline.health_check()
        except Exception:
            healthy = False
        engines.append(EngineInfo(
            name=name,
            supported_formats=list(pipeline.supported_formats),
            healthy=healthy,
        ))
    return HealthResponse(status="ok", engines=engines)


@router.get("/engines", response_model=list[EngineInfo])
async def list_engines():
    registry: PipelineRegistry = _get_registry()
    engines = []
    for name, pipeline in registry._engines.items():
        try:
            healthy = await pipeline.health_check()
        except Exception:
            healthy = False
        engines.append(EngineInfo(
            name=name,
            supported_formats=list(pipeline.supported_formats),
            healthy=healthy,
        ))
    return engines


@router.post(
    "/parse",
    response_model=ParseResultResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def parse_document(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
):
    registry: PipelineRegistry = _get_registry()
    data = await file.read()
    filename = file.filename or "unknown"

    try:
        result = await registry.parse_bytes(data, filename, engine=engine)
        resolved = registry._resolve_engine(engine, filename)
        engine_name = resolved.engine_name if resolved else engine
        return _pipeline_result_to_response(result, engine_name)
    except FormatNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected parse error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/parse/async",
    response_model=TaskResponse,
    responses={400: {"model": ErrorResponse}},
)
async def parse_document_async(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
):
    from doc_parser.api.task_manager import _get_task_manager

    registry: PipelineRegistry = _get_registry()
    tm = _get_task_manager()
    data = await file.read()
    filename = file.filename or "unknown"

    try:
        task = await tm.submit_parse(registry, data, filename, engine=engine)
    except FormatNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return TaskResponse(
        task_id=task.task_id,
        status=task.status,
        filename=task.filename,
        engine=task.engine,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/task/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    from doc_parser.api.task_manager import _get_task_manager

    tm = _get_task_manager()
    task = await tm.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    result_resp = None
    if task.result is not None and task.status == TaskStatus.SUCCESS:
        registry: PipelineRegistry = _get_registry()
        resolved = registry._resolve_engine(task.engine, task.filename)
        engine_name = resolved.engine_name if resolved else task.engine
        result_resp = _pipeline_result_to_response(task.result, engine_name)

    process_resp = None
    if task.orch_result is not None and task.status == TaskStatus.SUCCESS:
        orch = task.orch_result
        stages = [
            StageResultResponse(
                stage=s.stage, success=s.success,
                duration=s.duration, error=s.error,
            )
            for s in orch.stages
        ]
        process_resp = ProcessResponse(
            document_id=orch.document_id,
            total_duration=orch.total_duration,
            stages=stages,
            outline=orch.outline,
            enhance_result=orch.enhance_result,
            reading_result=orch.reading_result,
            kg_result=orch.kg_result,
            vector_result=orch.vector_result,
            errors=orch.errors,
        )

    return TaskResponse(
        task_id=task.task_id,
        status=task.status,
        filename=task.filename,
        engine=task.engine,
        created_at=task.created_at,
        updated_at=task.updated_at,
        error=task.error,
        result=result_resp,
        process_result=process_resp,
    )


@router.get("/tasks", response_model=list[dict])
async def list_tasks():
    from doc_parser.api.task_manager import _get_task_manager

    tm = _get_task_manager()
    return await tm.list_tasks()


def _get_registry() -> PipelineRegistry:
    from doc_parser.api.app import get_registry
    return get_registry()


def _outline_node_to_response(node: Any) -> OutlineNodeResponse:
    children = [_outline_node_to_response(c) for c in node.children]
    return OutlineNodeResponse(
        id=node.id,
        title=node.title,
        level=node.level,
        page_start=node.page_start,
        page_end=node.page_end,
        parent_id=node.parent_id,
        children=children,
        element_count=len(node.element_indices),
        markdown=node.markdown,
        image_count=node.image_count,
        table_count=node.table_count,
        equation_count=node.equation_count,
    )


def _outline_to_response(outline: Any) -> OutlineResponse:
    nodes = [_outline_node_to_response(n) for n in outline.nodes]
    return OutlineResponse(
        document_id=outline.document_id,
        title=outline.title,
        nodes=nodes,
        total_chapters=outline.total_chapters,
    )


@router.post(
    "/outline",
    response_model=OutlineResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def extract_outline(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
):
    from doc_parser.core.chapter import TOCExtractor

    registry: PipelineRegistry = _get_registry()
    data = await file.read()
    filename = file.filename or "unknown"

    try:
        result = await registry.parse_bytes(data, filename, engine=engine)
        extractor = TOCExtractor()
        outline = await extractor.extract(result)
        return _outline_to_response(outline)
    except FormatNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Outline extraction error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/split",
    response_model=SplitResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def split_document(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
):
    from doc_parser.core.chapter import TOCExtractor, ChapterSplitter

    registry: PipelineRegistry = _get_registry()
    data = await file.read()
    filename = file.filename or "unknown"

    try:
        result = await registry.parse_bytes(data, filename, engine=engine)
        extractor = TOCExtractor()
        outline = await extractor.extract(result)

        splitter = ChapterSplitter()
        outline = await splitter.split(result, outline)

        total_assigned = sum(
            len(ch.element_indices) for ch in outline.get_all_chapters()
        )
        conservation = {
            "total_elements": len(result.content_list),
            "total_assigned": total_assigned,
            "conservation_rate": (
                total_assigned / len(result.content_list)
                if result.content_list
                else 1.0
            ),
        }

        return SplitResponse(
            outline=_outline_to_response(outline),
            element_conservation=conservation,
        )
    except FormatNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Split document error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _enhanced_image_to_response(ei: Any) -> EnhancedImageResponse:
    ocr_resp = None
    if ei.ocr:
        ocr_resp = OCRResultResponse(
            text=ei.ocr.text,
            confidence=ei.ocr.confidence,
            word_count=ei.ocr.word_count,
        )
    vlm_resp = None
    if ei.vlm_description:
        vlm_resp = VLMDescriptionResponse(
            description=ei.vlm_description.description,
            image_type=ei.vlm_description.image_type,
            key_info=ei.vlm_description.key_info,
            model=ei.vlm_description.model,
        )
    return EnhancedImageResponse(
        path=ei.path,
        page=ei.page,
        bbox=ei.bbox,
        ocr=ocr_resp,
        vlm_description=vlm_resp,
        image_caption=ei.image_caption,
    )


@router.post(
    "/enhance",
    response_model=ImageEnhanceResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def enhance_images(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
    enable_ocr: str = Form("true"),
    enable_vlm: str = Form("false"),
):
    from doc_parser.core.chapter import TOCExtractor, ChapterSplitter
    from doc_parser.core.image import ImageEnhancer, ImageEnhancerConfig
    from doc_parser.core.image.ocr_enhance import DummyOCREngine
    from doc_parser.core.image.vlm_describe import DummyVLMClient

    registry: PipelineRegistry = _get_registry()
    data = await file.read()
    filename = file.filename or "unknown"

    ocr_on = enable_ocr.lower() in ("true", "1", "yes")
    vlm_on = enable_vlm.lower() in ("true", "1", "yes")

    config = ImageEnhancerConfig(enable_ocr=ocr_on, enable_vlm=vlm_on)

    try:
        result = await registry.parse_bytes(data, filename, engine=engine)
        enhancer = ImageEnhancer(config=config)
        enhanced = await enhancer.enhance(result)

        return ImageEnhanceResponse(
            document_id=result.document_id,
            enhanced_images=[_enhanced_image_to_response(ei) for ei in enhanced],
            total_images=len(enhanced),
            ocr_enabled=ocr_on,
            vlm_enabled=vlm_on,
        )
    except FormatNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Image enhance error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/read",
    response_model=LLMReadResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def read_document(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
    enable_llm: str = Form("true"),
):
    from doc_parser.core.chapter import TOCExtractor, ChapterSplitter
    from doc_parser.core.reader import UnifiedReader, UnifiedReaderConfig

    registry: PipelineRegistry = _get_registry()
    data = await file.read()
    filename = file.filename or "unknown"

    llm_on = enable_llm.lower() in ("true", "1", "yes")

    try:
        result = await registry.parse_bytes(data, filename, engine=engine)

        extractor = TOCExtractor()
        outline = await extractor.extract(result)

        splitter = ChapterSplitter()
        outline = await splitter.split(result, outline)

        if llm_on:
            reader = UnifiedReader()
            reading_result = await reader.read_document(outline)
        else:
            reading_result = None

        if reading_result:
            meta = reading_result.metadata
            meta_resp = DocumentMetadataResponse(
                title=meta.title,
                subject=meta.subject,
                summary=meta.summary,
                keywords=meta.keywords,
                document_type=meta.document_type,
                language=meta.language,
                quality_assessment=meta.quality_assessment,
            )
            chapters_resp = [
                ChapterAnalysisResponse(
                    chapter_id=ca.chapter_id,
                    summary=ca.summary,
                    key_points=ca.key_points,
                    entities=ca.entities,
                    relations=ca.relations,
                )
                for ca in reading_result.chapters
            ]
            cross_resp = [
                CrossChapterRelationResponse(
                    source=r.source,
                    target=r.target,
                    relation_type=r.relation_type,
                    description=r.description,
                )
                for r in reading_result.cross_chapter_relations
            ]
            return LLMReadResponse(
                document_id=result.document_id,
                metadata=meta_resp,
                chapters=chapters_resp,
                cross_chapter_relations=cross_resp,
                model=reading_result.model,
            )

        return LLMReadResponse(document_id=result.document_id)
    except FormatNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("LLM read error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/documents/{document_id}/graph",
    response_model=KGBuildResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def build_knowledge_graph(document_id: str):
    from doc_parser.api.app import get_kg_bridge
    from doc_parser.core.chapter import TOCExtractor, ChapterSplitter
    from doc_parser.core.kg import KGBuilder, KGBuilderConfig

    try:
        kg_bridge = get_kg_bridge()
        builder = KGBuilder(kg_bridge=kg_bridge)

        return KGBuildResponse(
            document_id=document_id,
            total_chapters=0,
            total_chunks=0,
        )
    except Exception as exc:
        logger.exception("KG build error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/documents/{document_id}/graph/query",
    response_model=KGQueryResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def query_knowledge_graph(document_id: str, request: KGQueryRequest):
    from doc_parser.api.app import get_kg_bridge
    from doc_parser.core.kg import KGBuilder, KGQueryMode

    try:
        kg_bridge = get_kg_bridge()
        builder = KGBuilder(kg_bridge=kg_bridge)
        mode = KGQueryMode(request.mode)
        result = await builder.query(request.query, mode=mode)

        return KGQueryResponse(
            query=result.query,
            mode=result.mode.value,
            answer=result.answer,
            source_chunks=result.source_chunks,
            source_entities=result.source_entities,
            confidence=result.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid query mode: {request.mode}") from exc
    except Exception as exc:
        logger.exception("KG query error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/documents/{document_id}/search",
    response_model=SearchResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def search_document(document_id: str, request: SearchRequest):
    from doc_parser.api.app import get_vector_store, get_embedding_generator

    try:
        vector_store = get_vector_store()
        embedding_generator = get_embedding_generator()
        query_embedding = await embedding_generator.embed_query(request.query)

        results = await vector_store.search(
            query_embedding=query_embedding,
            top_k=request.top_k,
            document_id=document_id,
            chapter_id=request.chapter_id,
            score_threshold=request.score_threshold,
        )

        search_results = [
            SearchResultResponse(
                chunk_id=r.chunk_id,
                text=r.text,
                score=r.score,
                document_id=r.metadata.document_id,
                chapter_id=r.metadata.chapter_id,
                chapter_title=r.metadata.chapter_title,
                chunk_type=r.metadata.chunk_type,
            )
            for r in results
        ]

        return SearchResponse(
            document_id=document_id,
            query=request.query,
            total_results=len(search_results),
            results=search_results,
        )
    except Exception as exc:
        logger.exception("Search error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/process",
    response_model=ProcessResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def process_document(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
    enable_enhance: Optional[str] = Form(None),
    enable_read: Optional[str] = Form(None),
    enable_kg: Optional[str] = Form(None),
    enable_vectorize: Optional[str] = Form(None),
):
    from doc_parser.api.app import get_kg_bridge, get_vector_store, get_embedding_generator, get_llm_client
    from doc_parser.orchestrator import DocumentOrchestrator, OrchestratorConfig
    from doc_parser.config import get_section

    registry: PipelineRegistry = _get_registry()
    data = await file.read()
    filename = file.filename or "unknown"

    orch_cfg = get_section("orchestrator", {})
    config = OrchestratorConfig(
        enable_enhance=(enable_enhance.lower() in ("true", "1", "yes") if enable_enhance is not None else orch_cfg.get("enable_enhance", True)),
        enable_read=(enable_read.lower() in ("true", "1", "yes") if enable_read is not None else orch_cfg.get("enable_read", True)),
        enable_kg=(enable_kg.lower() in ("true", "1", "yes") if enable_kg is not None else orch_cfg.get("enable_kg", False)),
        enable_vectorize=(enable_vectorize.lower() in ("true", "1", "yes") if enable_vectorize is not None else orch_cfg.get("enable_vectorize", False)),
    )

    try:
        pipeline_result = await registry.parse_bytes(data, filename, engine=engine)
        logger.info("[Process] Parsed file=%s engine=%s doc_id=%s size=%d bytes", filename, engine, pipeline_result.document_id, len(data))
        orchestrator = DocumentOrchestrator(
            kg_bridge=get_kg_bridge(),
            vector_store=get_vector_store(),
            embedding_generator=get_embedding_generator(),
            llm_client=get_llm_client(),
            config=config,
        )
        orch_result = await orchestrator.process(pipeline_result)

        stages = [
            StageResultResponse(
                stage=s.stage, success=s.success,
                duration=s.duration, error=s.error,
            )
            for s in orch_result.stages
        ]

        logger.info(
            "[Process] Completed doc_id=%s duration=%.3fs stages=%d errors=%d",
            orch_result.document_id,
            orch_result.total_duration,
            len(orch_result.stages),
            len(orch_result.errors),
        )

        return ProcessResponse(
            document_id=orch_result.document_id,
            total_duration=orch_result.total_duration,
            stages=stages,
            outline=orch_result.outline,
            enhance_result=orch_result.enhance_result,
            reading_result=orch_result.reading_result,
            kg_result=orch_result.kg_result,
            vector_result=orch_result.vector_result,
            errors=orch_result.errors,
        )
    except FormatNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Process document error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/process/async",
    response_model=TaskResponse,
    responses={400: {"model": ErrorResponse}},
)
async def process_document_async(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
    enable_enhance: Optional[str] = Form(None),
    enable_read: Optional[str] = Form(None),
    enable_kg: Optional[str] = Form(None),
    enable_vectorize: Optional[str] = Form(None),
):
    from doc_parser.api.task_manager import _get_task_manager

    registry: PipelineRegistry = _get_registry()
    tm = _get_task_manager()
    data = await file.read()
    filename = file.filename or "unknown"

    try:
        task = await tm.create_task(filename, engine)
        asyncio.create_task(_run_full_process(
            task.task_id, tm, registry, data, filename, engine,
            enable_enhance, enable_read, enable_kg, enable_vectorize,
        ))
        return TaskResponse(
            task_id=task.task_id,
            status=task.status,
            filename=task.filename,
            engine=task.engine,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _run_full_process(
    task_id: str,
    tm: Any,
    registry: PipelineRegistry,
    data: bytes,
    filename: str,
    engine: str,
    enable_enhance: str,
    enable_read: str,
    enable_kg: str,
    enable_vectorize: str,
) -> None:
    import asyncio as _asyncio

    from doc_parser.api.app import get_kg_bridge, get_vector_store, get_embedding_generator, get_llm_client
    from doc_parser.api.models import TaskStatus as TS
    from doc_parser.orchestrator import DocumentOrchestrator, OrchestratorConfig

    await tm.update_task(task_id, status=TS.PROCESSING)
    try:
        from doc_parser.config import get_section
        orch_cfg = get_section("orchestrator", {})
        config = OrchestratorConfig(
            enable_enhance=(enable_enhance.lower() in ("true", "1", "yes") if enable_enhance is not None else orch_cfg.get("enable_enhance", True)),
            enable_read=(enable_read.lower() in ("true", "1", "yes") if enable_read is not None else orch_cfg.get("enable_read", True)),
            enable_kg=(enable_kg.lower() in ("true", "1", "yes") if enable_kg is not None else orch_cfg.get("enable_kg", False)),
            enable_vectorize=(enable_vectorize.lower() in ("true", "1", "yes") if enable_vectorize is not None else orch_cfg.get("enable_vectorize", False)),
        )
        pipeline_result = await registry.parse_bytes(data, filename, engine=engine)
        orchestrator = DocumentOrchestrator(
            kg_bridge=get_kg_bridge(),
            vector_store=get_vector_store(),
            embedding_generator=get_embedding_generator(),
            llm_client=get_llm_client(),
            config=config,
        )
        orch_result = await orchestrator.process(pipeline_result)
        await tm.update_task(task_id, status=TS.SUCCESS, orch_result=orch_result)
    except Exception as exc:
        await tm.update_task(task_id, status=TS.FAILED, error=str(exc))
        logger.error("Async process task %s failed: %s", task_id, exc)
