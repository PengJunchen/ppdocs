from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from doc_parser.core.kg.models import (
    KGInsertResult,
    KGQueryMode,
    KGQueryResult,
)

logger = logging.getLogger(__name__)


class BaseKGBridge(ABC):
    @abstractmethod
    async def insert(
        self,
        content: str,
        doc_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> KGInsertResult:
        ...

    @abstractmethod
    async def query(
        self,
        query_text: str,
        mode: KGQueryMode = KGQueryMode.HYBRID,
    ) -> KGQueryResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class LightRAGAdapter(BaseKGBridge):
    def __init__(
        self,
        working_dir: str = "",
        llm_model: str = "",
        embedding_model: str = "",
        llm_base_url: str = "",
        llm_api_key: str = "",
        embedding_base_url: str = "",
        embedding_api_key: str = "",
        max_async: int = 4,
    ):
        self._working_dir = working_dir
        self._llm_model = llm_model
        self._embedding_model = embedding_model
        self._llm_base_url = llm_base_url
        self._llm_api_key = llm_api_key
        self._embedding_base_url = embedding_base_url
        self._embedding_api_key = embedding_api_key
        self._max_async = max_async
        self._rag: Any = None

    def _get_rag(self) -> Any:
        if self._rag is not None:
            return self._rag

        try:
            from lightrag import LightRAG
            from lightrag.llm import openai_complete_if_cache, openai_embed

            llm_func = None
            if self._llm_base_url:
                def llm_func(prompt: str, **kwargs: Any) -> str:
                    return openai_complete_if_cache(
                        self._llm_model,
                        prompt,
                        base_url=self._llm_base_url,
                        api_key=self._llm_api_key,
                        **kwargs,
                    )

            embedding_func = None
            if self._embedding_base_url:
                async def embedding_func(texts: list[str]) -> list[list[float]]:
                    results = []
                    for text in texts:
                        emb = await openai_embed(
                            texts=[text],
                            model=self._embedding_model,
                            base_url=self._embedding_base_url,
                            api_key=self._embedding_api_key,
                        )
                        results.append(emb[0])
                    return results

            kwargs: dict[str, Any] = {"working_dir": self._working_dir}
            if llm_func:
                kwargs["llm_model_func"] = llm_func
            if embedding_func:
                kwargs["embedding_func"] = embedding_func

            self._rag = LightRAG(**kwargs)
            return self._rag

        except ImportError:
            raise ImportError(
                "LightRAG is not installed. Install with: uv pip install lightrag-hku"
            )

    async def insert(
        self,
        content: str,
        doc_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> KGInsertResult:
        import time

        rag = self._get_rag()
        start = time.time()
        errors: list[str] = []

        try:
            meta_str = ""
            if metadata:
                meta_str = f"\n[Metadata: {json.dumps(metadata, ensure_ascii=False)}]"

            full_content = content + meta_str
            await rag.ainsert(full_content)

            return KGInsertResult(
                document_id=doc_id,
                total_chunks=1,
                insert_time=time.time() - start,
            )
        except Exception as exc:
            errors.append(str(exc))
            logger.warning("LightRAG insert failed: %s", exc)
            return KGInsertResult(
                document_id=doc_id,
                errors=errors,
                insert_time=time.time() - start,
            )

    async def query(
        self,
        query_text: str,
        mode: KGQueryMode = KGQueryMode.HYBRID,
    ) -> KGQueryResult:
        rag = self._get_rag()
        try:
            mode_str = mode.value
            result = await rag.aquery(query_text, mode=mode_str)

            answer = result if isinstance(result, str) else str(result)

            return KGQueryResult(
                query=query_text,
                mode=mode,
                answer=answer,
            )
        except Exception as exc:
            logger.warning("LightRAG query failed: %s", exc)
            return KGQueryResult(
                query=query_text,
                mode=mode,
                answer="",
                metadata={"error": str(exc)},
            )

    async def health_check(self) -> bool:
        try:
            self._get_rag()
            return True
        except Exception:
            return False


class DummyKGBridge(BaseKGBridge):
    def __init__(self) -> None:
        self._inserted: list[dict[str, Any]] = []

    async def insert(
        self,
        content: str,
        doc_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> KGInsertResult:
        self._inserted.append({
            "content": content,
            "doc_id": doc_id,
            "metadata": metadata or {},
        })
        return KGInsertResult(
            document_id=doc_id,
            total_chunks=1,
        )

    async def query(
        self,
        query_text: str,
        mode: KGQueryMode = KGQueryMode.HYBRID,
    ) -> KGQueryResult:
        return KGQueryResult(
            query=query_text,
            mode=mode,
            answer="",
        )

    async def health_check(self) -> bool:
        return True

    @property
    def inserted_items(self) -> list[dict[str, Any]]:
        return self._inserted


_ENTITY_EXTRACTION_PROMPT = """你是一个知识图谱构建专家。请从以下文本中提取实体和关系。

## 文本内容
{content}

## 任务
请返回严格的JSON格式（不要包含其他文字）：
{{
  "entities": [
    {{"name": "实体名称", "type": "人物/组织/概念/技术/地点/事件/其他", "description": "简短描述"}}
  ],
  "relations": [
    {{"source": "源实体", "target": "目标实体", "relation_type": "关系类型", "description": "关系描述"}}
  ]
}}

注意：
- 实体类型尽量具体，避免泛化
- 关系类型使用动宾短语（如"开发了"、"属于"、"引用了"）
- 每个关系必须有source和target对应的实体
- 不要编造文本中没有的信息"""


class LLMKGBridge(BaseKGBridge):
    def __init__(
        self,
        llm_client: Optional[Any] = None,
    ) -> None:
        self._llm = llm_client
        self._entities: list[dict[str, Any]] = []
        self._relations: list[dict[str, Any]] = []
        self._inserted: list[dict[str, Any]] = []

    async def insert(
        self,
        content: str,
        doc_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> KGInsertResult:
        import time

        start = time.time()
        entities_count = 0
        relations_count = 0
        errors: list[str] = []

        self._inserted.append({
            "content": content,
            "doc_id": doc_id,
            "metadata": metadata or {},
        })

        if self._llm is not None:
            try:
                prompt = _ENTITY_EXTRACTION_PROMPT.format(content=content[:4000])
                messages = [{"role": "user", "content": prompt}]
                response = await self._llm.chat(messages)

                if response:
                    extracted = self._extract_json(response)
                    if extracted:
                        for ent in extracted.get("entities", []):
                            self._entities.append({
                                **ent,
                                "doc_id": doc_id,
                            })
                            entities_count += 1

                        for rel in extracted.get("relations", []):
                            self._relations.append({
                                **rel,
                                "doc_id": doc_id,
                            })
                            relations_count += 1

                        logger.info(
                            "[LLMKGBridge] Extracted %d entities, %d relations from doc=%s",
                            entities_count,
                            relations_count,
                            doc_id,
                        )
            except Exception as exc:
                errors.append(str(exc))
                logger.warning("[LLMKGBridge] Extraction failed: %s", exc)

        return KGInsertResult(
            document_id=doc_id,
            total_chunks=1,
            total_entities=entities_count,
            total_relations=relations_count,
            insert_time=time.time() - start,
            errors=errors,
        )

    async def query(
        self,
        query_text: str,
        mode: KGQueryMode = KGQueryMode.HYBRID,
    ) -> KGQueryResult:
        if self._llm is None or not self._entities:
            return KGQueryResult(
                query=query_text,
                mode=mode,
                answer="",
            )

        entities_text = "\n".join(
            f"- {e['name']} ({e.get('type', '')}): {e.get('description', '')}"
            for e in self._entities[:50]
        )
        relations_text = "\n".join(
            f"- {r['source']} --[{r.get('relation_type', '')}]--> {r['target']}: {r.get('description', '')}"
            for r in self._relations[:30]
        )

        context = f"## 已知实体\n{entities_text}\n\n## 已知关系\n{relations_text}"
        prompt = f"根据以下知识图谱信息回答问题。\n\n{context}\n\n问题：{query_text}\n\n请给出简洁准确的回答："
        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self._llm.chat(messages)
            return KGQueryResult(
                query=query_text,
                mode=mode,
                answer=response or "",
                source_entities=[e["name"] for e in self._entities[:20]],
            )
        except Exception as exc:
            logger.warning("[LLMKGBridge] Query failed: %s", exc)
            return KGQueryResult(
                query=query_text,
                mode=mode,
                answer="",
                metadata={"error": str(exc)},
            )

    async def health_check(self) -> bool:
        if self._llm is None:
            return True
        return await self._llm.health_check()

    @property
    def inserted_items(self) -> list[dict[str, Any]]:
        return self._inserted

    @property
    def entities(self) -> list[dict[str, Any]]:
        return self._entities

    @property
    def relations(self) -> list[dict[str, Any]]:
        return self._relations

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                return None
        return None
