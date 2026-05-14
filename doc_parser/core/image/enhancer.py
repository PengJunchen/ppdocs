from __future__ import annotations

import logging
from typing import Any, Optional

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.core.image.models import EnhancedImage, OCRResult, VLMDescriptionResult
from doc_parser.core.image.ocr_enhance import BaseOCREngine, OCREnhancer
from doc_parser.core.image.vlm_describe import BaseVLMClient, VLMDescriber
from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult

logger = logging.getLogger(__name__)


class ImageEnhancerConfig:
    def __init__(
        self,
        enable_ocr: bool = True,
        enable_vlm: bool = False,
        max_concurrency: int = 4,
        vlm_prompt: str = "",
    ):
        self.enable_ocr = enable_ocr
        self.enable_vlm = enable_vlm
        self.max_concurrency = max_concurrency
        self.vlm_prompt = vlm_prompt


class ImageEnhancer:
    def __init__(
        self,
        ocr_engine: Optional[BaseOCREngine] = None,
        vlm_client: Optional[BaseVLMClient] = None,
        config: Optional[ImageEnhancerConfig] = None,
    ):
        self._config = config or ImageEnhancerConfig()
        
        # 使用传入的引擎或创建真实引擎
        if self._config.enable_ocr:
            if ocr_engine is None:
                from doc_parser.core.image.ocr_enhance import MinerUOCREngine
                ocr_engine = MinerUOCREngine()
            self._ocr_enhancer = OCREnhancer(engine=ocr_engine)
        else:
            self._ocr_enhancer = None
        
        if self._config.enable_vlm:
            if vlm_client is None:
                from doc_parser.core.image.vlm_describe import OpenAICompatibleVLM
                vlm_client = OpenAICompatibleVLM()
            self._vlm_describer = VLMDescriber(
                client=vlm_client,
                max_concurrency=self._config.max_concurrency,
                custom_prompt=self._config.vlm_prompt,
            )
        else:
            self._vlm_describer = None

    async def enhance(self, result: PipelineResult) -> list[EnhancedImage]:
        enhanced: list[EnhancedImage] = []

        if self._ocr_enhancer:
            enhanced = await self._ocr_enhancer.enhance_images(result)

        if self._vlm_describer:
            enhanced = await self._vlm_describer.describe_images(result, existing_enhanced=enhanced if enhanced else None)

        if not enhanced and not self._ocr_enhancer and not self._vlm_describer:
            enhanced = self._build_basic_images(result)

        return enhanced

    def _build_basic_images(self, result: PipelineResult) -> list[EnhancedImage]:
        images: list[EnhancedImage] = []
        for item in result.content_list:
            if item.type == ElementType.IMAGE:
                img_path = item.img_path or item.extra.get("path", "")
                if img_path:
                    images.append(EnhancedImage(
                        path=img_path,
                        page=item.page_idx,
                        bbox=item.bbox,
                        image_caption=item.image_caption if item.image_caption else [],
                    ))
        return images

    async def enhance_chapter_images(
        self,
        chapter: OutlineNode,
        result: PipelineResult,
        all_enhanced: list[EnhancedImage],
    ) -> OutlineNode:
        chapter_pages = set()
        for idx in chapter.element_indices:
            if idx < len(result.content_list):
                chapter_pages.add(result.content_list[idx].page_idx)

        page_start = chapter.page_start
        page_end = chapter.page_end if chapter.page_end is not None else page_start

        chapter_images = [
            ei for ei in all_enhanced
            if page_start <= ei.page <= page_end
        ]

        chapter.metadata["images"] = [img.model_dump(exclude_none=True) for img in chapter_images]
        return chapter
