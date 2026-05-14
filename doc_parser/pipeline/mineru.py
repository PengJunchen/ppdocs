from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from doc_parser.pipeline.base import (
    BasePipeline,
    ContentItem,
    ElementType,
    EquationInfo,
    ImageInfo,
    ParseFailed,
    ParseTimeout,
    PipelineConfig,
    PipelineResult,
    TableInfo,
)

logger = logging.getLogger(__name__)

_MINERU_ELEMENT_TYPE_MAP = {
    "text": ElementType.TEXT,
    "table": ElementType.TABLE,
    "image": ElementType.IMAGE,
    "equation": ElementType.EQUATION,
    "chart": ElementType.CHART,
    "code": ElementType.CODE,
    "header": ElementType.HEADER,
    "list": ElementType.LIST,
    "page_footnote": ElementType.PAGE_FOOTNOTE,
    "page_number": ElementType.PAGE_NUMBER,
}


class MinerUPipeline(BasePipeline):
    engine_name: str = "mineru-pipeline"
    supported_formats: list[str] = ["pdf"]

    def __init__(self, config: PipelineConfig):
        super().__init__(config)
        self.base_url = (config.base_url or "").rstrip("/")
        self.timeout = config.timeout

    async def parse(self, file_path: str, **kwargs: Any) -> PipelineResult:
        file_path_obj = Path(file_path)
        self._validate_format(file_path_obj.name)
        data = file_path_obj.read_bytes()
        return await self.parse_bytes(data, file_path_obj.name, **kwargs)

    async def parse_bytes(
        self, data: bytes, filename: str, **kwargs: Any
    ) -> PipelineResult:
        self._validate_format(filename)
        raw = await self._call_api(data, filename, **kwargs)
        return self._transform_result(raw)

    async def _call_api(
        self, data: bytes, filename: str, **kwargs: Any
    ) -> dict[str, Any]:
        url = f"{self.base_url}/file_parse"
        files = {"files": (filename, data, "application/pdf")}
        params = {}
        if kwargs.get("parse_method"):
            params["parse_method"] = kwargs["parse_method"]
        if kwargs.get("is_ocr"):
            params["is_ocr"] = str(kwargs["is_ocr"]).lower()

        timeout_cfg = httpx.Timeout(self.timeout, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            try:
                resp = await client.post(url, files=files, params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException as exc:
                raise ParseTimeout(self.timeout) from exc
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:500]
                code = "PARSE_FAILED"
                if exc.response.status_code == 409:
                    try:
                        err_data = exc.response.json()
                        err_msg = err_data.get("error", body)
                        code = "SERVER_RESOURCE_ERROR"
                    except Exception:
                        err_msg = body
                    raise ParseFailed(f"MinerU API resource error: {err_msg}") from exc
                raise ParseFailed(
                    f"MinerU API returned {exc.response.status_code}: {body}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ParseFailed(f"MinerU API request failed: {exc}") from exc

        return {}

    def _transform_result(self, raw: dict[str, Any]) -> PipelineResult:
        doc_id = str(uuid.uuid4())
        results = raw.get("results", {})
        first_key = next(iter(results), None)
        if not first_key:
            return PipelineResult(
                document_id=doc_id,
                engine=self.engine_name,
                raw_result=raw,
            )

        file_result = results[first_key]
        content_list = self._parse_content_list(file_result)
        markdown = file_result.get("md_content", "")
        images = self._parse_images(file_result)
        tables = self._extract_tables(content_list)
        equations = self._extract_equations(content_list)

        return PipelineResult(
            document_id=doc_id,
            engine=self.engine_name,
            content_list=content_list,
            markdown=markdown,
            images=images,
            tables=tables,
            equations=equations,
            metadata={
                "task_id": raw.get("task_id", ""),
                "backend": raw.get("backend", ""),
                "version": raw.get("version", ""),
                "status": raw.get("status", ""),
                "filename": first_key,
            },
            raw_result=raw,
        )

    @staticmethod
    def _parse_content_list(file_result: dict) -> list[ContentItem]:
        raw_cl = file_result.get("content_list", [])
        if not raw_cl:
            return []

        if isinstance(raw_cl, str):
            try:
                raw_cl = json.loads(raw_cl)
            except json.JSONDecodeError:
                logger.warning("Failed to parse content_list JSON string")
                return []
        elif isinstance(raw_cl, list) and raw_cl and isinstance(raw_cl[0], str):
            joined = "".join(raw_cl)
            try:
                raw_cl = json.loads(joined)
            except json.JSONDecodeError:
                logger.warning("Failed to parse content_list JSON string")
                return []

        if not isinstance(raw_cl, list):
            return []

        items: list[ContentItem] = []
        for idx, raw_item in enumerate(raw_cl):
            if not isinstance(raw_item, dict):
                continue
            elem_type_str = raw_item.get("type", "unknown")
            elem_type = _MINERU_ELEMENT_TYPE_MAP.get(
                elem_type_str, ElementType.UNKNOWN
            )
            text_level = raw_item.get("text_level", 0) or 0

            item = ContentItem(
                type=elem_type,
                text=raw_item.get("text", ""),
                text_level=int(text_level),
                page_idx=raw_item.get("page_idx", 0) or 0,
                bbox=raw_item.get("bbox", []),
                reading_order=idx,
                img_path=raw_item.get("img_path", ""),
                content=raw_item.get("content", ""),
                sub_type=raw_item.get("sub_type", ""),
                text_format=raw_item.get("text_format", "latex"),
                code_body=raw_item.get("code_body", ""),
                code_caption=raw_item.get("code_caption", []),
                code_footnote=raw_item.get("code_footnote", []),
                table_body=raw_item.get("table_body", ""),
                table_caption=raw_item.get("table_caption", []),
                table_footnote=raw_item.get("table_footnote", []),
                image_caption=raw_item.get("image_caption", []),
                image_footnote=raw_item.get("image_footnote", []),
                chart_caption=raw_item.get("chart_caption", []),
                chart_footnote=raw_item.get("chart_footnote", []),
                list_items=raw_item.get("list_items", []),
                extra={
                    k: v
                    for k, v in raw_item.items()
                    if k
                    not in {
                        "type",
                        "text",
                        "text_level",
                        "page_idx",
                        "bbox",
                        "img_path",
                        "content",
                        "sub_type",
                        "text_format",
                        "code_body",
                        "code_caption",
                        "code_footnote",
                        "table_body",
                        "table_caption",
                        "table_footnote",
                        "image_caption",
                        "image_footnote",
                        "chart_caption",
                        "chart_footnote",
                        "list_items",
                    }
                },
            )
            items.append(item)
        return items

    @staticmethod
    def _parse_images(file_result: dict) -> list[ImageInfo]:
        raw_images = file_result.get("images", {})
        if not isinstance(raw_images, dict):
            return []
        images: list[ImageInfo] = []
        for filename, data in raw_images.items():
            images.append(
                ImageInfo(
                    filename=filename,
                    data=str(data),
                    source_path=f"images/{filename}",
                )
            )
        return images

    @staticmethod
    def _extract_tables(content_list: list[ContentItem]) -> list[TableInfo]:
        tables: list[TableInfo] = []
        for item in content_list:
            if item.type == ElementType.TABLE:
                tables.append(
                    TableInfo(
                        html=item.table_body,
                        caption=item.table_caption,
                        footnote=item.table_footnote,
                        page_idx=item.page_idx,
                        bbox=item.bbox,
                        img_path=item.img_path,
                    )
                )
        return tables

    @staticmethod
    def _extract_equations(content_list: list[ContentItem]) -> list[EquationInfo]:
        equations: list[EquationInfo] = []
        for item in content_list:
            if item.type == ElementType.EQUATION:
                equations.append(
                    EquationInfo(
                        latex=item.text,
                        text_format=item.text_format,
                        page_idx=item.page_idx,
                        bbox=item.bbox,
                        img_path=item.img_path,
                    )
                )
        return equations

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/")
                return resp.status_code < 500
        except Exception:
            return False


class MinerUVLMPipeline(MinerUPipeline):
    engine_name: str = "mineru-vlm"

    async def _call_api(
        self, data: bytes, filename: str, **kwargs: Any
    ) -> dict[str, Any]:
        url = f"{self.base_url}/file_parse"
        files = {"files": (filename, data, "application/pdf")}
        params = {"parse_method": "vlm"}
        if kwargs.get("is_ocr"):
            params["is_ocr"] = str(kwargs["is_ocr"]).lower()

        timeout_cfg = httpx.Timeout(self.timeout, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            try:
                resp = await client.post(url, files=files, params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException as exc:
                raise ParseTimeout(self.timeout) from exc
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:500]
                if exc.response.status_code == 409:
                    try:
                        err_data = exc.response.json()
                        err_msg = err_data.get("error", body)
                    except Exception:
                        err_msg = body
                    raise ParseFailed(f"MinerU VLM API resource error: {err_msg}") from exc
                raise ParseFailed(
                    f"MinerU VLM API returned {exc.response.status_code}: {body}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ParseFailed(f"MinerU VLM API request failed: {exc}") from exc

        return {}

    def _transform_result(self, raw: dict[str, Any]) -> PipelineResult:
        result = super()._transform_result(raw)
        if not result.content_list and result.markdown:
            result.content_list = self._markdown_to_content_list(result.markdown)
        return result

    @staticmethod
    def _markdown_to_content_list(markdown: str) -> list[ContentItem]:
        import re

        items: list[ContentItem] = []
        idx = 0
        for line in markdown.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue

            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading_match:
                level = len(heading_match.group(1))
                items.append(
                    ContentItem(
                        type=ElementType.TEXT,
                        text=heading_match.group(2),
                        text_level=level,
                        reading_order=idx,
                    )
                )
                idx += 1
                continue

            items.append(
                ContentItem(
                    type=ElementType.TEXT,
                    text=stripped,
                    text_level=0,
                    reading_order=idx,
                )
            )
            idx += 1

        return items
