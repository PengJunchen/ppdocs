from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_config: Optional[dict[str, Any]] = None

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def load_config(config_path: Optional[str] = None) -> dict[str, Any]:
    global _config

    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH

    if path.exists():
        with open(path, encoding="utf-8") as f:
            _config = json.load(f)
        logger.info("Config loaded from %s", path)
    else:
        logger.warning("Config file not found at %s, using defaults", path)
        _config = {}

    _apply_env_overrides()
    return _config


def get_config() -> dict[str, Any]:
    global _config
    if _config is None:
        return load_config()
    return _config


def get_section(key: str, default: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = get_config()
    return cfg.get(key, default or {})


def _apply_env_overrides() -> None:
    if _config is None:
        return

    env_map: dict[str, str] = {
        "DOCPARSER_MINERU_URL": "pipeline.mineru_url",
        "DOCPARSER_DOCLING_URL": "pipeline.docling_url",
        "DOCPARSER_DOCLING_API_KEY": "pipeline.docling_api_key",
        "DOCPARSER_LLM_URL": "llm.base_url",
        "DOCPARSER_LLM_API_KEY": "llm.api_key",
        "DOCPARSER_LLM_MODEL": "llm.model",
        "DOCPARSER_EMBEDDING_URL": "embedding.base_url",
        "DOCPARSER_EMBEDDING_API_KEY": "embedding.api_key",
        "DOCPARSER_EMBEDDING_MODEL": "embedding.model",
        "DOCPARSER_TASK_TTL": "task_manager.ttl_seconds",
        "DOCPARSER_MAX_TASKS": "task_manager.max_tasks",
    }

    for env_key, config_path in env_map.items():
        env_val = os.environ.get(env_key)
        if env_val is not None:
            _set_nested(_config, config_path, env_val)


def _set_nested(d: dict[str, Any], path: str, value: str) -> None:
    keys = path.split(".")
    for key in keys[:-1]:
        if key not in d or not isinstance(d[key], dict):
            d[key] = {}
        d = d[key]
    last_key = keys[-1]
    existing = d.get(last_key)
    if isinstance(existing, bool):
        d[last_key] = value.lower() in ("true", "1", "yes")
    elif isinstance(existing, int):
        try:
            d[last_key] = int(value)
        except ValueError:
            d[last_key] = value
    elif isinstance(existing, float):
        try:
            d[last_key] = float(value)
        except ValueError:
            d[last_key] = value
    else:
        d[last_key] = value
