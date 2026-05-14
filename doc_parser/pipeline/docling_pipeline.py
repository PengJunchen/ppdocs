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

_DOCLING_ELEMENT_TYPE_MAP = {
    "text": ElementType.TEXT,
    "paragraph": ElementType.TEXT,
    "section_header": ElementType.TEXT,
    "table": ElementType.TABLE,
    "picture": ElementType.IMAGE,
    "figure": ElementType.IMAGE,
    "equation": ElementType.EQUATION,
    "formula": ElementType.EQUATION,
    "code": ElementType.CODE,
    "list": ElementType.LIST,
    "list_item": ElementType.LIST,
    "caption": ElementType.TEXT,
    "footnote": ElementType.PAGE_FOOTNOTE,
    "page_header": ElementType.HEADER,
    "page_footer": ElementType.PAGE_FOOTNOTE,
    "picture-group": ElementType.IMAGE,
    "table-group": ElementType.TABLE,
    "key-value-area": ElementType.UNKNOWN,
    "form": ElementType.TABLE,
    "title": ElementType.TEXT,
    "document_index": ElementType.UNKNOWN,
    "checkbox-selected": ElementType.UNKNOWN,
    "checkbox-unselected": ElementType.UNKNOWN,
}


class DoclingPipeline(BasePipeline):
    engine_name: str = "docling"
    supported_formats: list[str] = ["pdf", "docx", "pptx", "html", "md", "xlsx"]

    _DEFAULT_AUTH_HEADER = "X-Api-Key"
    _DEFAULT_AUTH_PREFIX = ""

    def __init__(self, config: PipelineConfig):
        super().__init__(config)
        self.base_url = (config.base_url or "").rstrip("/")
        self.api_key = config.api_key or ""
        self.timeout = config.timeout
        self._auth_header = config.options.get("auth_header", self._DEFAULT_AUTH_HEADER)
        self._auth_prefix = config.options.get("auth_prefix", self._DEFAULT_AUTH_PREFIX)

    def _build_auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        if self._auth_prefix:
            return {self._auth_header: f"{self._auth_prefix} {self.api_key}"}
        return {self._auth_header: self.api_key}

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
        return self._transform_result(raw, filename)

    async def _call_api(
        self, data: bytes, filename: str, **kwargs: Any
    ) -> dict[str, Any]:
        url = f"{self.base_url}/v1/convert/file/async"
        headers = self._build_auth_headers()

        files = {"files": (filename, data)}
        form_data: dict[str, Any] = {}
        if kwargs.get("ocr"):
            form_data["ocr"] = str(kwargs["is_ocr"]).lower()
        if kwargs.get("format"):
            form_data["format"] = kwargs["format"]
        if kwargs.get("output_format"):
            form_data["output_format"] = kwargs["output_format"]

        timeout_cfg = httpx.Timeout(self.timeout, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            try:
                resp = await client.post(
                    url, files=files, data=form_data, headers=headers
                )
                resp.raise_for_status()
            except httpx.TimeoutException as exc:
                raise ParseTimeout(self.timeout) from exc
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body = exc.response.text[:500]
                www_auth = exc.response.headers.get("www-authenticate", "")
                if status == 401:
                    gateway_hint = ""
                    if "kong" in www_auth.lower():
                        gateway_hint = " (Kong API Gateway - check api_key registration and auth_header config)"
                    raise ParseFailed(
                        f"Docling API auth failed{gateway_hint}: {body}"
                    )
                if status == 404:
                    raise ParseFailed(
                        f"Docling API endpoint not found (route may not be registered in API gateway): {body}"
                    )
                raise ParseFailed(
                    f"Docling API returned {status}: {body}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ParseFailed(f"Docling API request failed: {exc}") from exc

            job = resp.json()
            return await self._poll_result(client, job, headers)

    async def _poll_result(
        self, client: httpx.AsyncClient, job: dict, headers: dict[str, str]
    ) -> dict[str, Any]:

        job_id = job.get("task_id", job.get("job_id", job.get("id", "")))
        if not job_id:
            if job.get("content_list") or job.get("md_content") or job.get("markdown"):
                return job
            raise ParseFailed(f"Docling returned unexpected response: {json.dumps(job)[:500]}")

        poll_url = f"{self.base_url}/v1/status/poll/{job_id}"
        result_url = f"{self.base_url}/v1/result/{job_id}"

        max_wait = self.timeout
        interval = 2.0
        elapsed = 0.0

        while elapsed < max_wait:
            await asyncio.sleep(interval)
            elapsed += interval

            try:
                status_resp = await client.get(poll_url, headers=headers)
                status_resp.raise_for_status()
                status_data = status_resp.json()
            except Exception:
                continue

            job_status = status_data.get("task_status", status_data.get("status", ""))
            if job_status in ("success", "completed", "done"):
                try:
                    result_resp = await client.get(result_url, headers=headers)
                    result_resp.raise_for_status()
                    return result_resp.json()
                except Exception as exc:
                    raise ParseFailed(f"Failed to fetch Docling result: {exc}") from exc
            elif job_status in ("failed", "error"):
                raise ParseFailed(f"Docling job failed: {json.dumps(status_data)[:500]}")

            interval = min(interval * 1.5, 10.0)

        raise ParseTimeout(int(max_wait))

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = self._build_auth_headers()
                for path in ["/health", "/readiness", "/"]:
                    try:
                        resp = await client.get(f"{self.base_url}{path}", headers=headers)
                        if resp.status_code == 200:
                            return True
                    except Exception:
                        continue
                return False
        except Exception:
            return False

    def _transform_result(
        self, raw: dict[str, Any], filename: str
    ) -> PipelineResult:
        doc_id = str(uuid.uuid4())
        content_list = self._build_content_list(raw)
        markdown = raw.get("md_content", "") or raw.get("markdown", "")
        if not markdown and raw.get("text"):
            markdown = raw["text"]
        images = self._extract_images(raw)
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
                "filename": filename,
                "backend": "docling",
            },
            raw_result=raw,
        )

    def _build_content_list(self, raw: dict) -> list[ContentItem]:
        items: list[ContentItem] = []

        doc_items = raw.get("content_list", [])
        if not doc_items:
            doc_items = raw.get("items", [])
        if not doc_items and raw.get("body"):
            doc_items = raw["body"].get("items", [])

        if isinstance(doc_items, str):
            try:
                doc_items = json.loads(doc_items)
            except json.JSONDecodeError:
                pass

        if not isinstance(doc_items, list):
            return items

        for idx, raw_item in enumerate(doc_items):
            if not isinstance(raw_item, dict):
                continue

            obj_type = raw_item.get("type", raw_item.get("obj_type", "unknown"))
            elem_type = _DOCLING_ELEMENT_TYPE_MAP.get(obj_type, ElementType.UNKNOWN)

            text = raw_item.get("text", "")
            if not text:
                text = raw_item.get("content", "")
            if not text and raw_item.get("text_html"):
                text = raw_item.get("text_html", "")

            text_level = 0
            level = raw_item.get("level", 0)
            if isinstance(level, int) and level > 0:
                text_level = level
            heading = raw_item.get("heading", {})
            if isinstance(heading, dict) and heading.get("level"):
                text_level = heading["level"]

            if obj_type == "section_header" and text_level == 0:
                text_level = 1

            page_idx = raw_item.get("page_idx", raw_item.get("page", 0))
            if isinstance(page_idx, dict):
                page_idx = page_idx.get("number", 0)
            page_idx = int(page_idx) if page_idx else 0

            bbox: list[float] = []
            prov = raw_item.get("prov", [])
            if isinstance(prov, list) and prov:
                first_prov = prov[0] if isinstance(prov[0], dict) else {}
                bbox = first_prov.get("bbox", [])
                if not page_idx:
                    page_idx = first_prov.get("page_no", 0) or first_prov.get("page", 0)

            table_body = ""
            if elem_type == ElementType.TABLE:
                table_body = raw_item.get("table_body", "")
                if not table_body:
                    table_html = raw_item.get("html", "")
                    if table_html:
                        table_body = table_html
                    elif raw_item.get("data"):
                        table_body = self._grid_to_html(raw_item["data"])

            item = ContentItem(
                type=elem_type,
                text=text,
                text_level=text_level,
                page_idx=page_idx,
                bbox=bbox,
                reading_order=idx,
                table_body=table_body,
                table_caption=raw_item.get("table_caption", []),
                table_footnote=raw_item.get("table_footnote", []),
                image_caption=raw_item.get("image_caption", raw_item.get("caption", [])),
                list_items=raw_item.get("list_items", raw_item.get("item", [])),
                sub_type=raw_item.get("sub_type", ""),
                extra={
                    "obj_type": obj_type,
                    "heading": raw_item.get("heading", {}),
                },
            )
            items.append(item)

        return items

    @staticmethod
    def _grid_to_html(data: Any) -> str:
        if not isinstance(data, list):
            return ""
        rows = []
        for row in data:
            if isinstance(row, list):
                cells = "".join(f"<td>{c}</td>" for c in row)
                rows.append(f"<tr>{cells}</tr>")
        return f"<table>{''.join(rows)}</table>"

    @staticmethod
    def _extract_images(raw: dict) -> list[ImageInfo]:
        images: list[ImageInfo] = []
        raw_images = raw.get("images", {})
        if isinstance(raw_images, dict):
            for name, val in raw_images.items():
                images.append(
                    ImageInfo(filename=name, data=str(val), source_path=name)
                )
        elif isinstance(raw_images, list):
            for img in raw_images:
                if isinstance(img, dict):
                    images.append(
                        ImageInfo(
                            filename=img.get("filename", img.get("name", "")),
                            data=img.get("data", img.get("base64", "")),
                            source_path=img.get("path", ""),
                        )
                    )
        return images

    @staticmethod
    def _extract_tables(content_list: list[ContentItem]) -> list[TableInfo]:
        return [
            TableInfo(
                html=item.table_body,
                caption=item.table_caption,
                footnote=item.table_footnote,
                page_idx=item.page_idx,
                bbox=item.bbox,
            )
            for item in content_list
            if item.type == ElementType.TABLE
        ]

    @staticmethod
    def _extract_equations(content_list: list[ContentItem]) -> list[EquationInfo]:
        return [
            EquationInfo(
                latex=item.text,
                text_format=item.text_format,
                page_idx=item.page_idx,
                bbox=item.bbox,
            )
            for item in content_list
            if item.type == ElementType.EQUATION
        ]
