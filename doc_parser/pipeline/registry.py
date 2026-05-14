from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from doc_parser.pipeline.base import (
    BasePipeline,
    EngineNotFound,
    FormatNotSupported,
    PipelineConfig,
    PipelineResult,
)
from doc_parser.pipeline.docling_pipeline import DoclingPipeline
from doc_parser.pipeline.mineru import MinerUPipeline, MinerUVLMPipeline

logger = logging.getLogger(__name__)

_ENGINE_PRIORITY_PDF = ["mineru-vlm", "mineru-pipeline", "docling"]
_ENGINE_PRIORITY_DOCX = ["docling", "mineru-pipeline"]
_ENGINE_PRIORITY_PPTX = ["docling", "mineru-pipeline"]
_ENGINE_PRIORITY_HTML = ["docling"]
_ENGINE_PRIORITY_MD = ["docling"]
_ENGINE_PRIORITY_XLSX = ["docling"]

_FORMAT_PRIORITY: dict[str, list[str]] = {
    "pdf": _ENGINE_PRIORITY_PDF,
    "docx": _ENGINE_PRIORITY_DOCX,
    "pptx": _ENGINE_PRIORITY_PPTX,
    "html": _ENGINE_PRIORITY_HTML,
    "md": _ENGINE_PRIORITY_MD,
    "xlsx": _ENGINE_PRIORITY_XLSX,
}

_FALLBACK_CHAIN = ["mineru-vlm", "mineru-pipeline", "docling"]


class PipelineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, BasePipeline] = {}

    def register(self, engine: BasePipeline) -> None:
        self._engines[engine.engine_name] = engine
        logger.info("Registered pipeline engine: %s", engine.engine_name)

    def get(self, engine_name: str) -> BasePipeline:
        engine = self._engines.get(engine_name)
        if engine is None:
            raise EngineNotFound(engine_name)
        return engine

    def list_engines(self) -> list[str]:
        return list(self._engines.keys())

    async def auto_select(
        self, filename: str, fallback: bool = True
    ) -> BasePipeline:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        priority = _FORMAT_PRIORITY.get(ext, _FALLBACK_CHAIN)

        for engine_name in priority:
            engine = self._engines.get(engine_name)
            if engine is None:
                continue
            if not engine.supports_format(filename):
                continue

            if fallback:
                try:
                    healthy = await engine.health_check()
                except Exception:
                    healthy = False
                if healthy:
                    logger.info(
                        "Auto-selected engine '%s' for '%s'",
                        engine_name,
                        filename,
                    )
                    return engine
                logger.warning(
                    "Engine '%s' unhealthy, trying next", engine_name
                )
            else:
                return engine

        if fallback and ext != "":
            for engine_name in _FALLBACK_CHAIN:
                engine = self._engines.get(engine_name)
                if engine is None:
                    continue
                try:
                    healthy = await engine.health_check()
                except Exception:
                    healthy = False
                if healthy:
                    return engine

        raise FormatNotSupported(
            f"No available engine for format '{ext}'"
        )

    async def parse(
        self,
        file_path: str,
        engine: str = "auto",
        **kwargs: Any,
    ) -> PipelineResult:
        pipeline = self._resolve_engine(engine, file_path)
        return await pipeline.parse(file_path, **kwargs)

    async def parse_bytes(
        self,
        data: bytes,
        filename: str,
        engine: str = "auto",
        **kwargs: Any,
    ) -> PipelineResult:
        pipeline = self._resolve_engine(engine, filename)
        return await pipeline.parse_bytes(data, filename, **kwargs)

    def _resolve_engine(
        self, engine: str, filename: str
    ) -> BasePipeline:
        if engine == "auto":
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            priority = _FORMAT_PRIORITY.get(ext, _FALLBACK_CHAIN)
            for engine_name in priority:
                eng = self._engines.get(engine_name)
                if eng and eng.supports_format(filename):
                    return eng
            raise FormatNotSupported(
                f"No registered engine supports format '{ext}'"
            )
        return self.get(engine)


def create_default_registry(
    mineru_url: str = "",
    docling_url: str = "",
    docling_api_key: str = "",
    timeout: int = 300,
) -> PipelineRegistry:
    registry = PipelineRegistry()

    if mineru_url:
        mineru_config = PipelineConfig(
            engine="mineru-pipeline",
            base_url=mineru_url,
            timeout=timeout,
        )
        registry.register(MinerUPipeline(mineru_config))

        vlm_config = PipelineConfig(
            engine="mineru-vlm",
            base_url=mineru_url,
            timeout=timeout,
        )
        registry.register(MinerUVLMPipeline(vlm_config))

    if docling_url:
        docling_config = PipelineConfig(
            engine="docling",
            base_url=docling_url,
            api_key=docling_api_key,
            timeout=timeout,
        )
        registry.register(DoclingPipeline(docling_config))

    return registry
