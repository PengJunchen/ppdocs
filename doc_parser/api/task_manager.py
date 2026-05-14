from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from doc_parser.api.models import TaskStatus
from doc_parser.pipeline.base import PipelineResult

logger = logging.getLogger(__name__)


def _get_task_manager() -> "TaskManager":
    from doc_parser.api.app import get_task_manager
    return get_task_manager()


class TaskInfo:
    __slots__ = (
        "task_id", "filename", "engine", "status", "created_at",
        "updated_at", "error", "result", "orch_result",
    )

    def __init__(self, task_id: str, filename: str, engine: str):
        self.task_id = task_id
        self.filename = filename
        self.engine = engine
        self.status: TaskStatus = TaskStatus.PENDING
        now = datetime.now(timezone.utc).isoformat()
        self.created_at = now
        self.updated_at = now
        self.error = ""
        self.result: Optional[PipelineResult] = None
        self.orch_result: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "engine": self.engine,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }


class TaskManager:
    def __init__(self, max_tasks: int = 1000, ttl_seconds: int = 3600):
        self._tasks: dict[str, TaskInfo] = {}
        self._max_tasks = max_tasks
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def create_task(self, filename: str, engine: str) -> TaskInfo:
        async with self._lock:
            if len(self._tasks) >= self._max_tasks:
                await self._evict_expired()
            task_id = uuid.uuid4().hex[:16]
            task = TaskInfo(task_id, filename, engine)
            self._tasks[task_id] = task
            logger.info("Task created: %s for %s", task_id, filename)
            return task

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    async def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        error: Optional[str] = None,
        result: Optional[PipelineResult] = None,
        orch_result: Any = None,
    ) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        if status is not None:
            task.status = status
        if error is not None:
            task.error = error
        if result is not None:
            task.result = result
        if orch_result is not None:
            task.orch_result = orch_result
        task.updated_at = datetime.now(timezone.utc).isoformat()

    async def submit_parse(
        self,
        registry: Any,
        data: bytes,
        filename: str,
        engine: str = "auto",
        **kwargs: Any,
    ) -> TaskInfo:
        task = await self.create_task(filename, engine)
        asyncio.create_task(
            self._run_parse(task.task_id, registry, data, filename, engine, **kwargs)
        )
        return task

    async def _run_parse(
        self,
        task_id: str,
        registry: Any,
        data: bytes,
        filename: str,
        engine: str,
        **kwargs: Any,
    ) -> None:
        await self.update_task(task_id, status=TaskStatus.PROCESSING)
        try:
            result = await registry.parse_bytes(data, filename, engine=engine, **kwargs)
            await self.update_task(task_id, status=TaskStatus.SUCCESS, result=result)
            logger.info("Task %s completed successfully", task_id)
        except Exception as exc:
            await self.update_task(
                task_id, status=TaskStatus.FAILED, error=str(exc)
            )
            logger.error("Task %s failed: %s", task_id, exc)

    async def _evict_expired(self) -> None:
        now = time.time()
        expired = []
        for tid, task in self._tasks.items():
            try:
                created = datetime.fromisoformat(task.created_at).timestamp()
                if now - created > self._ttl_seconds:
                    expired.append(tid)
            except Exception:
                expired.append(tid)
        for tid in expired:
            del self._tasks[tid]
        if expired:
            logger.info("Evicted %d expired tasks", len(expired))

    async def list_tasks(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._tasks.values()]

    async def cleanup(self) -> None:
        async with self._lock:
            self._tasks.clear()
