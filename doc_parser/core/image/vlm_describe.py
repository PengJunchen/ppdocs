from __future__ import annotations

import asyncio
import base64
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from doc_parser.core.image.models import VLMDescriptionResult, EnhancedImage
from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult

logger = logging.getLogger(__name__)

_VLM_PROMPT = """请详细描述这张图片的内容，包括：
1. 图片类型（图表、截图、照片、示意图等）
2. 主要内容和关键信息
3. 数据趋势或关键数值（如果有）
4. 与文档主题的关联

请以JSON格式返回：
{"image_type": "图片类型", "description": "详细描述", "key_info": ["关键信息1", "关键信息2"]}"""


class BaseVLMClient(ABC):
    @abstractmethod
    async def describe_image(self, image_path: str, prompt: str = "") -> VLMDescriptionResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class OpenAICompatibleVLM(BaseVLMClient):
    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "qwen-vl-max",
        max_tokens: int = 1024,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens

    async def describe_image(self, image_path: str, prompt: str = "") -> VLMDescriptionResult:
        import httpx
        import json

        if not self._base_url:
            return VLMDescriptionResult(model=self._model)

        use_prompt = prompt or _VLM_PROMPT
        image_url = await self._encode_image(image_path)

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": use_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            "max_tokens": self._max_tokens,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

            parsed = self._parse_response(content)
            parsed.model = self._model
            parsed.confidence = 0.8
            return parsed

        except Exception as exc:
            logger.warning("VLM describe failed for %s: %s", image_path, exc)
            return VLMDescriptionResult(model=self._model)

    async def _encode_image(self, image_path: str) -> str:
        import mimetypes

        mime, _ = mimetypes.guess_type(image_path)
        if mime is None:
            mime = "image/png"

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        return f"data:{mime};base64,{b64}"

    def _parse_response(self, content: str) -> VLMDescriptionResult:
        import json

        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                raw = json.loads(content[start:end])
                return VLMDescriptionResult(
                    description=raw.get("description", content),
                    image_type=raw.get("image_type", ""),
                    key_info=raw.get("key_info", []),
                )
        except (json.JSONDecodeError, KeyError):
            pass

        return VLMDescriptionResult(description=content)

    async def health_check(self) -> bool:
        import httpx

        if not self._base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False


class DummyVLMClient(BaseVLMClient):
    async def describe_image(self, image_path: str, prompt: str = "") -> VLMDescriptionResult:
        return VLMDescriptionResult()

    async def health_check(self) -> bool:
        return True


class VLMDescriber:
    def __init__(
        self,
        client: Optional[BaseVLMClient] = None,
        max_concurrency: int = 4,
        custom_prompt: str = "",
    ):
        self._client = client or DummyVLMClient()
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._prompt = custom_prompt or _VLM_PROMPT

    async def describe_images(
        self,
        result: PipelineResult,
        existing_enhanced: list[EnhancedImage] | None = None,
    ) -> list[EnhancedImage]:
        image_items = [
            (idx, item)
            for idx, item in enumerate(result.content_list)
            if item.type == ElementType.IMAGE and (item.img_path or item.extra.get("path"))
        ]

        path_to_existing: dict[str, EnhancedImage] = {}
        if existing_enhanced:
            for ei in existing_enhanced:
                path_to_existing[ei.path] = ei

        tasks = []
        for idx, item in image_items:
            img_path = item.img_path or item.extra.get("path", "")
            if not img_path:
                continue
            existing = path_to_existing.get(img_path)
            tasks.append((img_path, item, existing))

        results = await asyncio.gather(
            *[self._describe_one(path, item, ex) for path, item, ex in tasks]
        )

        enhanced: list[EnhancedImage] = []
        for ei in results:
            if ei is not None:
                enhanced.append(ei)
        return enhanced

    async def _describe_one(
        self,
        img_path: str,
        item: ContentItem,
        existing: EnhancedImage | None,
    ) -> EnhancedImage | None:
        async with self._semaphore:
            try:
                vlm_result = await self._client.describe_image(img_path, self._prompt)
            except Exception as exc:
                logger.warning("VLM describe error for %s: %s", img_path, exc)
                vlm_result = VLMDescriptionResult()

        if existing:
            existing.vlm_description = vlm_result
            return existing

        return EnhancedImage(
            path=img_path,
            page=item.page_idx,
            bbox=item.bbox,
            vlm_description=vlm_result,
            image_caption=item.image_caption if item.image_caption else [],
        )
