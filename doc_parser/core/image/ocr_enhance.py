from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from doc_parser.core.image.models import OCRResult, EnhancedImage
from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult

logger = logging.getLogger(__name__)


class BaseOCREngine(ABC):
    @abstractmethod
    async def extract_text(self, image_path: str) -> OCRResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class MinerUOCREngine(BaseOCREngine):
    def __init__(self, base_url: str = "http://10.0.40.153:18089"):
        self._base_url = base_url.rstrip("/")

    async def extract_text(self, image_path: str) -> OCRResult:
        import httpx

        url = f"{self._base_url}/file_parse"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                with open(image_path, "rb") as f:
                    resp = await client.post(
                        url,
                        files={"files": (image_path, f)},
                        params={"parse_method": "ocr"},
                    )
                resp.raise_for_status()
                data = resp.json()
                content_list = data.get("content_list", "")
                if isinstance(content_list, str):
                    import json
                    content_list = json.loads(content_list)

                texts = []
                total_conf = 0.0
                count = 0
                for item in content_list:
                    if isinstance(item, dict):
                        t = item.get("text", "")
                        c = item.get("confidence", 0.0)
                        if t:
                            texts.append(t)
                            total_conf += c
                            count += 1

                return OCRResult(
                    text="\n".join(texts),
                    confidence=total_conf / count if count > 0 else 0.0,
                    word_count=sum(len(t.split()) for t in texts),
                )
        except Exception as exc:
            logger.warning("MinerU OCR failed for %s: %s", image_path, exc)
            return OCRResult()

    async def health_check(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


class DummyOCREngine(BaseOCREngine):
    async def extract_text(self, image_path: str) -> OCRResult:
        return OCRResult()

    async def health_check(self) -> bool:
        return True


class OCREnhancer:
    def __init__(self, engine: Optional[BaseOCREngine] = None):
        self._engine = engine or DummyOCREngine()

    async def enhance_images(
        self,
        result: PipelineResult,
        chapter_images: dict[str, list[EnhancedImage]] | None = None,
    ) -> list[EnhancedImage]:
        image_items = [
            (idx, item)
            for idx, item in enumerate(result.content_list)
            if item.type == ElementType.IMAGE and (item.img_path or item.extra.get("path"))
        ]

        enhanced: list[EnhancedImage] = []

        for idx, item in image_items:
            img_path = item.img_path or item.extra.get("path", "")
            if not img_path:
                continue

            ocr_result = await self._engine.extract_text(img_path)

            existing_texts = self._collect_existing_ocr_texts(result, item)
            ocr_result = self._deduplicate(ocr_result, existing_texts)

            ei = EnhancedImage(
                path=img_path,
                page=item.page_idx,
                bbox=item.bbox,
                ocr=ocr_result,
                image_caption=item.image_caption if item.image_caption else [],
            )
            enhanced.append(ei)

        return enhanced

    def _collect_existing_ocr_texts(
        self, result: PipelineResult, image_item: ContentItem
    ) -> set[str]:
        existing: set[str] = set()
        page = image_item.page_idx
        for item in result.content_list:
            if (
                item.type == ElementType.TEXT
                and item.page_idx == page
                and item.text_level == 0
                and item.text.strip()
            ):
                existing.add(item.text.strip().lower())
        return existing

    def _deduplicate(self, ocr_result: OCRResult, existing: set[str]) -> OCRResult:
        if not existing or not ocr_result.text:
            return ocr_result

        ocr_lines = ocr_result.text.split("\n")
        unique_lines: list[str] = []
        for line in ocr_lines:
            stripped = line.strip().lower()
            if stripped and stripped not in existing:
                unique_lines.append(line)

        if not unique_lines:
            return OCRResult(
                text="",
                confidence=0.0,
                word_count=0,
                language=ocr_result.language,
            )

        new_text = "\n".join(unique_lines)
        ratio = len(unique_lines) / len(ocr_lines) if ocr_lines else 0.0
        return OCRResult(
            text=new_text,
            confidence=ocr_result.confidence * ratio,
            word_count=len(new_text.split()),
            language=ocr_result.language,
        )
