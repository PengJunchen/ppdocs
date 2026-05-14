from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from doc_parser.api.models import ErrorResponse
from doc_parser.api.task_manager import TaskManager
from doc_parser.pipeline.base import PipelineConfig
from doc_parser.pipeline.registry import PipelineRegistry, create_default_registry

logger = logging.getLogger(__name__)

_registry: Optional[PipelineRegistry] = None
_task_manager: Optional[TaskManager] = None
_kg_bridge: Any = None
_vector_store: Any = None
_embedding_generator: Any = None


def get_registry() -> PipelineRegistry:
    if _registry is None:
        raise RuntimeError("PipelineRegistry not initialized. Call create_app() first.")
    return _registry


def get_task_manager() -> TaskManager:
    if _task_manager is None:
        raise RuntimeError("TaskManager not initialized. Call create_app() first.")
    return _task_manager


def get_kg_bridge() -> Any:
    if _kg_bridge is None:
        from doc_parser.core.kg import LLMKGBridge
        llm = _get_llm_client()
        return LLMKGBridge(llm_client=llm)
    return _kg_bridge


def get_vector_store() -> Any:
    if _vector_store is None:
        from doc_parser.storage import InMemoryVectorStore
        return InMemoryVectorStore()
    return _vector_store


def get_embedding_generator() -> Any:
    if _embedding_generator is None:
        from doc_parser.storage.embedding import DummyEmbeddingGenerator
        return DummyEmbeddingGenerator()
    return _embedding_generator


_llm_client: Any = None


def _get_llm_client() -> Any:
    if _llm_client is not None:
        return _llm_client
    from doc_parser.core.reader.llm_client import DummyLLMClient
    return DummyLLMClient()


def get_llm_client() -> Any:
    if _llm_client is None:
        from doc_parser.core.reader.llm_client import DummyLLMClient
        return DummyLLMClient()
    return _llm_client


def set_globals(
    registry: PipelineRegistry,
    task_manager: TaskManager,
    kg_bridge: Any = None,
    vector_store: Any = None,
    embedding_generator: Any = None,
    llm_client: Any = None,
) -> None:
    global _registry, _task_manager, _kg_bridge, _vector_store, _embedding_generator, _llm_client
    _registry = registry
    _task_manager = task_manager
    _kg_bridge = kg_bridge
    _vector_store = vector_store
    _embedding_generator = embedding_generator
    _llm_client = llm_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Doc Parser API starting up")
    yield
    tm = get_task_manager()
    await tm.cleanup()
    logger.info("Doc Parser API shutting down")


def create_app(**kwargs: Any) -> FastAPI:
    import os

    from doc_parser.config import get_config, load_config

    config = kwargs.get("config")
    if isinstance(config, dict):
        cfg = config
    else:
        cfg = load_config(kwargs.get("config_path"))

    server_cfg = cfg.get("server", {})
    pipeline_cfg = cfg.get("pipeline", {})
    llm_cfg = cfg.get("llm", {})
    embedding_cfg = cfg.get("embedding", {})
    tm_cfg = cfg.get("task_manager", {})

    mineru_url = kwargs.get("mineru_url") or os.environ.get("DOCPARSER_MINERU_URL", pipeline_cfg.get("mineru_url", "http://10.0.40.153:18089"))
    docling_url = kwargs.get("docling_url") or os.environ.get("DOCPARSER_DOCLING_URL", pipeline_cfg.get("docling_url", ""))
    docling_api_key = kwargs.get("docling_api_key") or os.environ.get("DOCPARSER_DOCLING_API_KEY", pipeline_cfg.get("docling_api_key", ""))
    task_ttl = int(kwargs.get("task_ttl") or os.environ.get("DOCPARSER_TASK_TTL", str(tm_cfg.get("ttl_seconds", 3600))))
    max_tasks = int(kwargs.get("max_tasks") or os.environ.get("DOCPARSER_MAX_TASKS", str(tm_cfg.get("max_tasks", 1000))))
    registry = create_default_registry(
        mineru_url=mineru_url,
        docling_url=docling_url,
        docling_api_key=docling_api_key,
    )
    tm = TaskManager(max_tasks=max_tasks, ttl_seconds=task_ttl)

    llm_client = kwargs.get("llm_client")
    if llm_client is None:
        llm_base_url = kwargs.get("llm_base_url") or os.environ.get("DOCPARSER_LLM_URL", llm_cfg.get("base_url", ""))
        llm_api_key = kwargs.get("llm_api_key") or os.environ.get("DOCPARSER_LLM_API_KEY", llm_cfg.get("api_key", ""))
        llm_model = kwargs.get("llm_model") or os.environ.get("DOCPARSER_LLM_MODEL", llm_cfg.get("model", "qwen-max"))
        if llm_base_url:
            from doc_parser.core.reader.llm_client import OpenAICompatibleLLM
            llm_client = OpenAICompatibleLLM(
                base_url=llm_base_url,
                api_key=llm_api_key,
                model=llm_model,
                max_tokens=llm_cfg.get("max_tokens", 4096),
                temperature=llm_cfg.get("temperature", 0.3),
            )
            logger.info("LLM client configured: %s (model=%s)", llm_base_url, llm_model)

    kg_bridge = kwargs.get("kg_bridge")
    vector_store = kwargs.get("vector_store")
    embedding_generator = kwargs.get("embedding_generator")

    if kg_bridge is None and llm_client is not None:
        from doc_parser.core.kg import LLMKGBridge
        kg_bridge = LLMKGBridge(llm_client=llm_client)
        logger.info("KG bridge: LLMKGBridge with LLM extraction")

    if embedding_generator is None:
        emb_base_url = kwargs.get("embedding_base_url") or os.environ.get("DOCPARSER_EMBEDDING_URL", embedding_cfg.get("base_url", ""))
        emb_api_key = kwargs.get("embedding_api_key") or os.environ.get("DOCPARSER_EMBEDDING_API_KEY", embedding_cfg.get("api_key", ""))
        emb_model = kwargs.get("embedding_model") or os.environ.get("DOCPARSER_EMBEDDING_MODEL", embedding_cfg.get("model", "text-embedding-3-small"))
        if emb_base_url:
            from doc_parser.storage.embedding import OpenAICompatibleEmbedding
            embedding_generator = OpenAICompatibleEmbedding(
                base_url=emb_base_url,
                api_key=emb_api_key,
                model=emb_model,
                dim=embedding_cfg.get("dim", 1536),
            )
            logger.info("Embedding generator configured: %s (model=%s)", emb_base_url, emb_model)

    set_globals(
        registry, tm,
        kg_bridge=kg_bridge,
        vector_store=vector_store,
        embedding_generator=embedding_generator,
        llm_client=llm_client,
    )

    app = FastAPI(
        title="Doc Parser API",
        description="Enterprise document parsing service - unified MinerU VLM/Pipeline + Docling",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_timing(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
        return response

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                code="INTERNAL_ERROR",
                message=str(exc),
            ).model_dump(),
        )

    from doc_parser.api.v1.routes import router as v1_router
    app.include_router(v1_router)

    return app
