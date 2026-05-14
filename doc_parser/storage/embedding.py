from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BaseEmbeddingGenerator(ABC):
    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @property
    @abstractmethod
    def dim(self) -> int:
        ...


class OpenAICompatibleEmbedding(BaseEmbeddingGenerator):
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        dim: int = 1536,
        batch_size: int = 64,
        timeout: float = 60.0,
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._dim = dim
        self._batch_size = batch_size
        self._timeout = timeout

    @property
    def dim(self) -> int:
        return self._dim

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            batch_embeddings = await self._call_api(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        results = await self._call_api([text])
        return results[0] if results else [0.0] * self._dim

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        url = f"{self._base_url}/embeddings"
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "input": texts,
        }

        timeout_cfg = httpx.Timeout(self._timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Embedding API returned %s: %s",
                    exc.response.status_code,
                    exc.response.text[:300],
                )
                return [[0.0] * self._dim for _ in texts]
            except httpx.HTTPError as exc:
                logger.warning("Embedding API request failed: %s", exc)
                return [[0.0] * self._dim for _ in texts]

        embeddings: list[list[float]] = []
        for item in data.get("data", []):
            embedding = item.get("embedding", [])
            if embedding:
                embeddings.append(embedding)
            else:
                embeddings.append([0.0] * self._dim)

        while len(embeddings) < len(texts):
            embeddings.append([0.0] * self._dim)

        return embeddings

    async def health_check(self) -> bool:
        try:
            result = await self.embed_query("health check")
            return any(v != 0.0 for v in result)
        except Exception:
            return False


class DummyEmbeddingGenerator(BaseEmbeddingGenerator):
    def __init__(self, dim: int = 64):
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._simple_hash(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._simple_hash(text)

    def _simple_hash(self, text: str) -> list[float]:
        values: list[float] = []
        for i in range(self._dim):
            char_code = ord(text[i % len(text)]) if text else 0
            values.append(math.sin(char_code * (i + 1) * 0.1) * 0.5 + 0.5)
        norm = math.sqrt(sum(v * v for v in values))
        if norm > 0:
            values = [v / norm for v in values]
        return values

    async def health_check(self) -> bool:
        return True
