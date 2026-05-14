from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class OpenAICompatibleLLM(BaseLLMClient):
    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "qwen-max",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        import httpx

        if not self._base_url:
            return ""

        payload = {
            "model": kwargs.get("model", self._model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "temperature": kwargs.get("temperature", self._temperature),
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("LLM chat failed: %s", exc)
            return ""

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


class DummyLLMClient(BaseLLMClient):
    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        return ""

    async def health_check(self) -> bool:
        return True
