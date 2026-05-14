from __future__ import annotations

import logging
import math
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ChunkMetadata(BaseModel):
    document_id: str = ""
    chapter_id: str = ""
    chapter_title: str = ""
    chunk_index: int = 0
    page_start: int = 0
    page_end: int = 0
    chunk_type: str = "chapter"
    entities: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class VectorChunk(BaseModel):
    id: str = ""
    text: str = ""
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)
    embedding: list[float] = Field(default_factory=list)

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())


class SearchResult(BaseModel):
    chunk_id: str = ""
    text: str = ""
    score: float = 0.0
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)


class VectorStoreResult(BaseModel):
    document_id: str = ""
    total_chunks: int = 0
    chunk_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BaseVectorStore(ABC):
    @abstractmethod
    async def add_chunks(
        self,
        chunks: list[VectorChunk],
        document_id: str = "",
    ) -> VectorStoreResult:
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        document_id: str = "",
        chapter_id: str = "",
        score_threshold: float = 0.0,
    ) -> list[SearchResult]:
        ...

    @abstractmethod
    async def delete_document(self, document_id: str) -> bool:
        ...

    @abstractmethod
    async def get_document_chunks(
        self, document_id: str
    ) -> list[VectorChunk]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class InMemoryVectorStore(BaseVectorStore):
    def __init__(self) -> None:
        self._chunks: dict[str, VectorChunk] = {}

    async def add_chunks(
        self,
        chunks: list[VectorChunk],
        document_id: str = "",
    ) -> VectorStoreResult:
        chunk_ids: list[str] = []
        errors: list[str] = []

        for chunk in chunks:
            if not chunk.id:
                chunk.id = VectorChunk.generate_id()
            self._chunks[chunk.id] = chunk
            chunk_ids.append(chunk.id)

        return VectorStoreResult(
            document_id=document_id,
            total_chunks=len(chunk_ids),
            chunk_ids=chunk_ids,
            errors=errors,
        )

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        document_id: str = "",
        chapter_id: str = "",
        score_threshold: float = 0.0,
    ) -> list[SearchResult]:
        candidates: list[tuple[float, VectorChunk]] = []

        for chunk in self._chunks.values():
            if document_id and chunk.metadata.document_id != document_id:
                continue
            if chapter_id and chunk.metadata.chapter_id != chapter_id:
                continue

            if chunk.embedding and query_embedding:
                score = self._cosine_similarity(query_embedding, chunk.embedding)
            else:
                score = 0.0

            if score >= score_threshold:
                candidates.append((score, chunk))

        candidates.sort(key=lambda x: x[0], reverse=True)

        results: list[SearchResult] = []
        for score, chunk in candidates[:top_k]:
            results.append(SearchResult(
                chunk_id=chunk.id,
                text=chunk.text,
                score=score,
                metadata=chunk.metadata,
            ))
        return results

    async def delete_document(self, document_id: str) -> bool:
        to_delete = [
            cid
            for cid, chunk in self._chunks.items()
            if chunk.metadata.document_id == document_id
        ]
        for cid in to_delete:
            del self._chunks[cid]
        return len(to_delete) > 0

    async def get_document_chunks(
        self, document_id: str
    ) -> list[VectorChunk]:
        return [
            chunk
            for chunk in self._chunks.values()
            if chunk.metadata.document_id == document_id
        ]

    async def health_check(self) -> bool:
        return True

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class MilvusVectorStore(BaseVectorStore):
    def __init__(
        self,
        collection_name: str = "doc_chunks",
        host: str = "localhost",
        port: int = 19530,
        dim: int = 1536,
    ):
        self._collection_name = collection_name
        self._host = host
        self._port = port
        self._dim = dim
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from pymilvus import MilvusClient

            self._client = MilvusClient(
                uri=f"http://{self._host}:{self._port}"
            )
            return self._client
        except ImportError:
            raise ImportError(
                "pymilvus is not installed. Install with: uv pip install pymilvus"
            )

    async def add_chunks(
        self,
        chunks: list[VectorChunk],
        document_id: str = "",
    ) -> VectorStoreResult:
        client = self._get_client()
        chunk_ids: list[str] = []
        errors: list[str] = []

        try:
            self._ensure_collection()

            data = []
            for chunk in chunks:
                if not chunk.id:
                    chunk.id = VectorChunk.generate_id()
                chunk_ids.append(chunk.id)

                data.append({
                    "id": chunk.id,
                    "vector": chunk.embedding,
                    "text": chunk.text,
                    "document_id": chunk.metadata.document_id,
                    "chapter_id": chunk.metadata.chapter_id,
                    "chapter_title": chunk.metadata.chapter_title,
                    "chunk_index": chunk.metadata.chunk_index,
                    "chunk_type": chunk.metadata.chunk_type,
                    "page_start": chunk.metadata.page_start,
                    "page_end": chunk.metadata.page_end,
                })

            if data:
                client.insert(collection_name=self._collection_name, data=data)

        except Exception as exc:
            errors.append(str(exc))
            logger.warning("Milvus insert failed: %s", exc)

        return VectorStoreResult(
            document_id=document_id,
            total_chunks=len(chunk_ids),
            chunk_ids=chunk_ids,
            errors=errors,
        )

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        document_id: str = "",
        chapter_id: str = "",
        score_threshold: float = 0.0,
    ) -> list[SearchResult]:
        client = self._get_client()

        try:
            filter_expr = ""
            conditions = []
            if document_id:
                conditions.append(f'document_id == "{document_id}"')
            if chapter_id:
                conditions.append(f'chapter_id == "{chapter_id}"')
            if conditions:
                filter_expr = " and ".join(conditions)

            results = client.search(
                collection_name=self._collection_name,
                data=[query_embedding],
                limit=top_k,
                filter=filter_expr or None,
                output_fields=["text", "document_id", "chapter_id", "chapter_title", "chunk_index", "chunk_type", "page_start", "page_end"],
            )

            search_results: list[SearchResult] = []
            if results and results[0]:
                for hit in results[0]:
                    score = hit.get("score", hit.get("distance", 0.0))
                    if score < score_threshold:
                        continue
                    entity = hit.get("entity", hit)
                    search_results.append(SearchResult(
                        chunk_id=hit.get("id", ""),
                        text=entity.get("text", ""),
                        score=score,
                        metadata=ChunkMetadata(
                            document_id=entity.get("document_id", ""),
                            chapter_id=entity.get("chapter_id", ""),
                            chapter_title=entity.get("chapter_title", ""),
                            chunk_index=entity.get("chunk_index", 0),
                            chunk_type=entity.get("chunk_type", "chapter"),
                            page_start=entity.get("page_start", 0),
                            page_end=entity.get("page_end", 0),
                        ),
                    ))
            return search_results

        except Exception as exc:
            logger.warning("Milvus search failed: %s", exc)
            return []

    async def delete_document(self, document_id: str) -> bool:
        client = self._get_client()
        try:
            client.delete(
                collection_name=self._collection_name,
                filter=f'document_id == "{document_id}"',
            )
            return True
        except Exception as exc:
            logger.warning("Milvus delete failed: %s", exc)
            return False

    async def get_document_chunks(
        self, document_id: str
    ) -> list[VectorChunk]:
        client = self._get_client()
        try:
            results = client.query(
                collection_name=self._collection_name,
                filter=f'document_id == "{document_id}"',
                output_fields=["text", "chapter_id", "chapter_title", "chunk_index", "chunk_type", "page_start", "page_end"],
            )
            chunks: list[VectorChunk] = []
            for r in results:
                chunks.append(VectorChunk(
                    id=r.get("id", ""),
                    text=r.get("text", ""),
                    metadata=ChunkMetadata(
                        document_id=document_id,
                        chapter_id=r.get("chapter_id", ""),
                        chapter_title=r.get("chapter_title", ""),
                        chunk_index=r.get("chunk_index", 0),
                        chunk_type=r.get("chunk_type", "chapter"),
                        page_start=r.get("page_start", 0),
                        page_end=r.get("page_end", 0),
                    ),
                ))
            return chunks
        except Exception as exc:
            logger.warning("Milvus query failed: %s", exc)
            return []

    async def health_check(self) -> bool:
        try:
            client = self._get_client()
            client.list_collections()
            return True
        except Exception:
            return False

    def _ensure_collection(self) -> None:
        client = self._get_client()
        existing = client.list_collections()
        if self._collection_name not in existing:
            from pymilvus import CollectionSchema, DataType, FieldSchema

            schema = CollectionSchema(fields=[
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self._dim),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=8192),
                FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="chapter_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="chapter_title", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="page_start", dtype=DataType.INT64),
                FieldSchema(name="page_end", dtype=DataType.INT64),
            ])
            client.create_collection(
                collection_name=self._collection_name,
                schema=schema,
            )


class QdrantVectorStore(BaseVectorStore):
    def __init__(
        self,
        collection_name: str = "doc_chunks",
        host: str = "localhost",
        port: int = 6333,
        dim: int = 1536,
        api_key: str = "",
    ):
        self._collection_name = collection_name
        self._host = host
        self._port = port
        self._dim = dim
        self._api_key = api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from qdrant_client import QdrantClient

            kwargs: dict[str, Any] = {
                "host": self._host,
                "port": self._port,
            }
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = QdrantClient(**kwargs)
            return self._client
        except ImportError:
            raise ImportError(
                "qdrant-client is not installed. Install with: uv pip install qdrant-client"
            )

    async def add_chunks(
        self,
        chunks: list[VectorChunk],
        document_id: str = "",
    ) -> VectorStoreResult:
        client = self._get_client()
        chunk_ids: list[str] = []
        errors: list[str] = []

        try:
            self._ensure_collection()

            from qdrant_client.models import PointStruct

            points = []
            for chunk in chunks:
                if not chunk.id:
                    chunk.id = VectorChunk.generate_id()
                chunk_ids.append(chunk.id)

                points.append(PointStruct(
                    id=chunk.id,
                    vector=chunk.embedding,
                    payload={
                        "text": chunk.text,
                        "document_id": chunk.metadata.document_id,
                        "chapter_id": chunk.metadata.chapter_id,
                        "chapter_title": chunk.metadata.chapter_title,
                        "chunk_index": chunk.metadata.chunk_index,
                        "chunk_type": chunk.metadata.chunk_type,
                        "page_start": chunk.metadata.page_start,
                        "page_end": chunk.metadata.page_end,
                    },
                ))

            if points:
                client.upsert(collection_name=self._collection_name, points=points)

        except Exception as exc:
            errors.append(str(exc))
            logger.warning("Qdrant insert failed: %s", exc)

        return VectorStoreResult(
            document_id=document_id,
            total_chunks=len(chunk_ids),
            chunk_ids=chunk_ids,
            errors=errors,
        )

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        document_id: str = "",
        chapter_id: str = "",
        score_threshold: float = 0.0,
    ) -> list[SearchResult]:
        client = self._get_client()

        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            conditions = []
            if document_id:
                conditions.append(FieldCondition(key="document_id", match=MatchValue(value=document_id)))
            if chapter_id:
                conditions.append(FieldCondition(key="chapter_id", match=MatchValue(value=chapter_id)))

            query_filter = Filter(must=conditions) if conditions else None

            results = client.search(
                collection_name=self._collection_name,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=query_filter,
                score_threshold=score_threshold or None,
            )

            search_results: list[SearchResult] = []
            for hit in results:
                payload = hit.payload or {}
                search_results.append(SearchResult(
                    chunk_id=str(hit.id),
                    text=payload.get("text", ""),
                    score=hit.score,
                    metadata=ChunkMetadata(
                        document_id=payload.get("document_id", ""),
                        chapter_id=payload.get("chapter_id", ""),
                        chapter_title=payload.get("chapter_title", ""),
                        chunk_index=payload.get("chunk_index", 0),
                        chunk_type=payload.get("chunk_type", "chapter"),
                        page_start=payload.get("page_start", 0),
                        page_end=payload.get("page_end", 0),
                    ),
                ))
            return search_results

        except Exception as exc:
            logger.warning("Qdrant search failed: %s", exc)
            return []

    async def delete_document(self, document_id: str) -> bool:
        client = self._get_client()
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            client.delete(
                collection_name=self._collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                ),
            )
            return True
        except Exception as exc:
            logger.warning("Qdrant delete failed: %s", exc)
            return False

    async def get_document_chunks(
        self, document_id: str
    ) -> list[VectorChunk]:
        client = self._get_client()
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            points, _ = client.scroll(
                collection_name=self._collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                ),
                limit=1000,
                with_payload=True,
                with_vectors=False,
            )
            chunks: list[VectorChunk] = []
            for point in points:
                payload = point.payload or {}
                chunks.append(VectorChunk(
                    id=str(point.id),
                    text=payload.get("text", ""),
                    metadata=ChunkMetadata(
                        document_id=document_id,
                        chapter_id=payload.get("chapter_id", ""),
                        chapter_title=payload.get("chapter_title", ""),
                        chunk_index=payload.get("chunk_index", 0),
                        chunk_type=payload.get("chunk_type", "chapter"),
                        page_start=payload.get("page_start", 0),
                        page_end=payload.get("page_end", 0),
                    ),
                ))
            return chunks
        except Exception as exc:
            logger.warning("Qdrant scroll failed: %s", exc)
            return []

    async def health_check(self) -> bool:
        try:
            client = self._get_client()
            client.get_collections()
            return True
        except Exception:
            return False

    def _ensure_collection(self) -> None:
        client = self._get_client()
        from qdrant_client.models import Distance, VectorParams

        existing = [c.name for c in client.get_collections().collections]
        if self._collection_name not in existing:
            client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )
